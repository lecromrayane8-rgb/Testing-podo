"""Boucle de trading en direct : mêmes règles que le backtest, appliquées aux bougies clôturées."""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from .broker import atomic_write
from .config import Settings
from .data import timeframe_to_ms
from .risk import RiskGuard, position_size
from .strategy import compute_indicators, entry_signal, exit_reason, initial_stop

log = logging.getLogger(__name__)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict) -> None:
        atomic_write(self.path, json.dumps(state, indent=2))


class Bot:
    """Gère une seule position longue spot sur une paire.

    Le bot ne compte que le capital qu'il gère lui-même (`capital`, initialisé à MAX_CAPITAL
    ou au solde disponible) : il ne touche pas aux autres avoirs du compte.
    """

    def __init__(self, broker, settings: Settings, store: StateStore, journal_path: Path | None = None):
        self.broker = broker
        self.s = settings
        self.store = store
        self.journal_path = journal_path
        self.tf_ms = timeframe_to_ms(settings.timeframe)
        self.lookback = min(settings.strategy.warmup_bars + 150, 1000)
        self.state = store.load()
        self.state.setdefault("position", None)
        self.state.setdefault("last_candle_ts", None)
        self.state.setdefault("capital", None)
        self.guard = RiskGuard.from_dict(settings.risk, self.state.get("guard"))

    # --- comptabilité -------------------------------------------------------------
    def _init_capital(self) -> None:
        if self.state["capital"] is not None:
            return
        quote = self.broker.balances().quote
        capital = min(quote, self.s.max_capital) if self.s.max_capital > 0 else quote
        if capital <= 0:
            raise RuntimeError("Aucun solde disponible en devise de cotation pour trader.")
        self.state["capital"] = capital
        log.info("Capital confié au bot : %.2f", capital)

    def equity(self, price: float) -> float:
        pos = self.state["position"]
        capital = self.state["capital"]
        return capital - pos["cost"] + pos["qty"] * price if pos else capital

    def _save(self) -> None:
        self.state["guard"] = self.guard.to_dict()
        self.store.save(self.state)

    # --- boucle -------------------------------------------------------------------
    def step(self, now_ms: int | None = None) -> None:
        now_ms = now_ms or int(time.time() * 1000)
        self._init_capital()
        price = self.broker.last_price()

        pos = self.state["position"]
        if pos and price <= pos["stop"]:
            self._sell("stop", price, now_ms)

        self.guard.update(self.equity(price), _day(now_ms))

        candles = self.broker.fetch_candles(self.s.timeframe, self.lookback)
        closed = candles[candles["ts"] + self.tf_ms <= now_ms]
        if len(closed) < self.s.strategy.warmup_bars:
            log.warning("Pas assez d'historique (%d bougies) pour calculer les indicateurs", len(closed))
            self._save()
            return
        last_ts = int(closed["ts"].iloc[-1])
        if self.state["last_candle_ts"] is not None and last_ts <= self.state["last_candle_ts"]:
            self._save()
            return
        self.state["last_candle_ts"] = last_ts

        row = compute_indicators(closed, self.s.strategy).iloc[-1]
        log.info(
            "Bougie %s clôture=%.2f RSI=%.1f MM_tendance=%.2f MM_sortie=%.2f equity=%.2f",
            _iso(last_ts), row.close, row.rsi, row.trend_ma, row.exit_ma, self.equity(price),
        )
        pos = self.state["position"]
        if pos:
            bars_held = (last_ts - pos["entry_bar_ts"]) // self.tf_ms + 1
            reason = exit_reason(row.close, row.exit_ma, bars_held, self.s.strategy)
            if reason:
                self._sell(reason, self.broker.last_price(), now_ms)
        elif entry_signal(row.close, row.trend_ma, row.rsi, row.atr, self.s.strategy):
            blocked = self.guard.blocked_reason()
            if blocked:
                log.warning("Signal d'achat ignoré : %s", blocked)
            else:
                self._buy(row.atr, last_ts, now_ms)
        self._save()

    def _buy(self, atr_value: float, last_ts: int, now_ms: int) -> None:
        price = self.broker.last_price()
        stop = initial_stop(price, atr_value, self.s.strategy)
        qty = position_size(self.equity(price), price, stop, self.s.risk)
        budget = min(self.state["capital"], self.broker.balances().quote)
        qty = min(qty, budget / (price * (1 + self.s.fee_rate + self.s.slippage)))
        qty = self.broker.normalize_qty(qty, price)
        if qty <= 0:
            log.warning("Signal d'achat ignoré : taille sous le minimum de la plateforme (capital trop faible ?)")
            return
        fill = self.broker.market_buy(qty)
        self.state["position"] = {
            "qty": fill.qty,
            "entry_price": fill.price,
            "cost": fill.quote,
            "stop": initial_stop(fill.price, atr_value, self.s.strategy),
            "entry_bar_ts": last_ts + self.tf_ms,
            "entry_time": _iso(now_ms),
        }
        self._save()
        log.info(
            "ACHAT %.8f %s à %.2f (coût %.2f), stop %.2f",
            fill.qty, self.s.symbol, fill.price, fill.quote, self.state["position"]["stop"],
        )

    def _sell(self, reason: str, price: float, now_ms: int) -> None:
        pos = self.state["position"]
        qty = self.broker.normalize_qty(min(pos["qty"], self.broker.balances().base), price)
        if qty <= 0:
            log.error(
                "Position introuvable sur le compte (vendue manuellement ?). "
                "Position oubliée, capital recalculé depuis le solde."
            )
            self.state["position"] = None
            self.state["capital"] = None
            self._init_capital()
            self._save()
            return
        fill = self.broker.market_sell(qty)
        pnl = fill.quote - pos["cost"]
        self.state["capital"] += pnl
        self.state["position"] = None
        self._save()
        log.info(
            "VENTE (%s) %.8f à %.2f : PnL %+.2f (%+.2f %%), capital %.2f",
            reason, fill.qty, fill.price, pnl, 100 * pnl / pos["cost"], self.state["capital"],
        )
        self._journal(pos, fill, pnl, reason, now_ms)

    def _journal(self, pos: dict, fill, pnl: float, reason: str, now_ms: int) -> None:
        if not self.journal_path:
            return
        new = not self.journal_path.exists()
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if new:
                writer.writerow(["entree", "sortie", "prix_entree", "prix_sortie", "quantite", "pnl", "raison"])
            writer.writerow(
                [pos["entry_time"], _iso(now_ms), pos["entry_price"], fill.price, fill.qty, round(pnl, 4), reason]
            )

    def run_forever(self) -> None:
        log.info(
            "Démarrage du bot : mode=%s plateforme=%s paire=%s unité=%s",
            self.s.mode, self.s.exchange, self.s.symbol, self.s.timeframe,
        )
        while True:
            try:
                self.step()
            except ccxt.AuthenticationError:
                log.critical("Clés API refusées par la plateforme : vérifie API_KEY / API_SECRET et le MODE.")
                raise
            except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
                log.warning("Erreur plateforme, nouvel essai dans %ss : %s", self.s.poll_seconds, exc)
            time.sleep(self.s.poll_seconds)
