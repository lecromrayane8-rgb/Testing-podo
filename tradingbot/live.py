"""Boucle de trading en direct : mêmes règles que le backtest, appliquées aux bougies clôturées."""
from __future__ import annotations

import csv
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from .broker import Fill, OrderStatus, atomic_write, combine_fills
from .config import Settings
from .data import timeframe_to_ms
from .obsidian import JOURNAL, ObsidianJournal
from .risk import RiskGuard, TradeStats, elimination_reason, position_size
from .strategy import compute_signals, exit_reason, initial_stop

log = logging.getLogger(__name__)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def _local(ms: int) -> str:
    """Heure d'ouverture d'une bougie, à l'heure de l'ordinateur (plus lisible que l'heure UTC)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().strftime("%d/%m %H:%M")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def px(price: float) -> str:
    """Prix lisible pour toutes les cryptos : 68450.00 pour le BTC, 0.000012340 pour PEPE (5 chiffres utiles)."""
    if not price or not math.isfinite(price) or price <= 0:
        return f"{price:.2f}"
    return f"{price:.{max(2, 4 - math.floor(math.log10(price)))}f}"


def slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-")


def bot_tag(settings: Settings) -> str:
    """Identifiant de fichier d'un bot : mode, plateforme, paire, unité (et stratégie dans le tournoi)."""
    tag = f"{settings.mode}_{settings.exchange}_{settings.symbol.replace('/', '-')}_{settings.timeframe}"
    return f"{tag}_{slug(settings.bot_label)}" if settings.bot_label else tag


def bot_paths(settings: Settings) -> tuple[Path, Path]:
    """État et journal des trades d'un bot."""
    tag = bot_tag(settings)
    return settings.data_dir / f"state_{tag}.json", settings.data_dir / f"trades_{tag}.csv"


def bot_name(settings: Settings) -> str:
    name = f"{settings.symbol} {settings.timeframe}"
    return f"{name} · {settings.bot_label}" if settings.bot_label else name


class BotLog(logging.LoggerAdapter):
    """Préfixe chaque message du nom du bot, sans toucher aux `extra` (JOURNAL) passés à l'appel."""

    def process(self, msg, kwargs):
        return f"[{self.extra['bot']}] {msg}", kwargs


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

    Avec ORDER_TYPE=limit, entrées et sorties passent par un ordre limite post-only au meilleur
    prix du carnet, suivi d'une itération à l'autre (`state["order"]`). Les stops restent
    toujours au marché.
    """

    def __init__(
        self,
        broker,
        settings: Settings,
        store: StateStore,
        journal_path: Path | None = None,
        notes: ObsidianJournal | None = None,
    ):
        self.broker = broker
        self.s = settings
        self.ex = settings.execution
        self.store = store
        self.journal_path = journal_path
        self.notes = notes
        self.name = bot_name(settings)
        self.log = BotLog(log, {"bot": self.name})
        self.tf_ms = timeframe_to_ms(settings.timeframe)
        # Assez d'historique pour que les moyennes exponentielles (RSI, ATR, MACD) et le Supertrend
        # aient oublié leur point de départ : mêmes valeurs qu'en backtest sur tout l'historique.
        warmup = settings.strategy.warmup_bars
        self.lookback = min(max(3 * warmup, warmup + 300), 1000)
        self.state = store.load()
        self.state.setdefault("position", None)
        self.state.setdefault("order", None)
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
        self.state.setdefault("initial_capital", capital)
        self.log.info("Capital confié au bot : %.2f", capital, extra=JOURNAL)

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

        if self.state["order"]:
            self._poll_order(price, now_ms)
        pos = self.state["position"]
        if pos and not self.state["order"] and price <= pos["stop"]:
            self._sell_market("stop", price, now_ms)

        self.guard.update(self.equity(price), _day(now_ms))
        self._on_candles(now_ms)
        if self.state["order"] and now_ms >= self.state["order"]["expires_ts"]:
            self._expire_order(now_ms)
        # Pour le tableau de bord : dernière valeur connue, position latente comprise.
        self.state.update(last_price=price, equity=self.equity(price), updated_at=_iso(now_ms))
        self._save()

    def _on_candles(self, now_ms: int) -> None:
        candles = self.broker.fetch_candles(self.s.timeframe, self.lookback)
        closed = candles[candles["ts"] + self.tf_ms <= now_ms]
        if len(closed) < self.s.strategy.warmup_bars:
            self.log.warning("Pas assez d'historique (%d bougies) pour calculer les indicateurs", len(closed))
            return
        last_ts = int(closed["ts"].iloc[-1])
        if self.state["last_candle_ts"] is not None and last_ts <= self.state["last_candle_ts"]:
            return
        self.state["last_candle_ts"] = last_ts

        row = compute_signals(closed, self.s.strategy).iloc[-1]
        pos = self.state["position"]
        if self.state["order"]:
            verdict = "ordre limite en attente"
        elif pos:
            verdict = "signal de vente" if row.exit else "position gardée"
        else:
            verdict = "signal d'achat" if row.entry else "pas de signal d'achat, en attente"
        # Dans le tournoi (des dizaines de bots), ce détail resterait illisible : la console garde les trades.
        self.log.log(
            logging.DEBUG if self.s.bot_label else logging.INFO,
            "Bougie de %s terminée : clôture %s, %s (valeur %.2f)",
            _local(last_ts), px(row.close), verdict, self.equity(row.close),
        )
        if self.state["order"]:
            return  # un ordre limite est déjà en cours
        if pos:
            bars_held = (last_ts - pos["entry_bar_ts"]) // self.tf_ms + 1
            reason = exit_reason(bool(row.exit), bars_held, self.s.strategy)
            if reason:
                self._exit(reason, last_ts, now_ms)
        elif row.entry:
            blocked = self.guard.blocked_reason()
            if self.state.get("eliminated"):
                self.log.info("Signal d'achat ignoré : stratégie éliminée (%s)", self.state["eliminated"])
            elif blocked:
                self.log.warning("Signal d'achat ignoré : %s", blocked)
            else:
                self._enter(row.atr, last_ts, now_ms)

    # --- entrées --------------------------------------------------------------------
    def _affordable_qty(self, price: float, cost_rate: float, already_spent: float = 0.0) -> float:
        budget = min(self.state["capital"] - already_spent, self.broker.balances().quote)
        return max(budget, 0.0) / (price * (1 + cost_rate))

    def _entry_qty(self, price: float, atr_value: float, cost_rate: float) -> float:
        stop = initial_stop(price, atr_value, self.s.strategy)
        qty = min(position_size(self.equity(price), price, stop, self.s.risk), self._affordable_qty(price, cost_rate))
        return self.broker.normalize_qty(qty, price)

    def _enter(self, atr_value: float, last_ts: int, now_ms: int) -> None:
        bar_ts = last_ts + self.tf_ms
        if self.ex.order_type == "market":
            self._buy_market(atr_value, bar_ts, now_ms)
            return
        bid, _ = self.broker.best_bid_ask()
        qty = self._entry_qty(bid, atr_value, self.ex.maker_fee_rate)
        if qty <= 0:
            self.log.warning("Signal d'achat ignoré : taille sous le minimum de la plateforme (capital trop faible ?)")
            return
        placed = self._place_limit("buy", qty, bid)
        if placed is None:
            if self.ex.limit_entry_fallback == "market":
                self._buy_market(atr_value, bar_ts, now_ms)
            return
        order_id, price = placed
        self._track_order(order_id, "buy", qty, price, "entree", bar_ts, atr=atr_value)
        self.log.info("Ordre limite d'ACHAT %.8f à %s (id %s)", qty, px(price), order_id, extra=JOURNAL)

    def _buy_market(self, atr_value: float, bar_ts: int, now_ms: int) -> None:
        price = self.broker.last_price()
        qty = self._entry_qty(price, atr_value, self.ex.fee_rate + self.ex.slippage)
        if qty <= 0:
            self.log.warning("Signal d'achat ignoré : taille sous le minimum de la plateforme (capital trop faible ?)")
            return
        self._open_position(self.broker.market_buy(qty), atr_value, bar_ts, now_ms)

    def _open_position(self, fill: Fill, atr_value: float, bar_ts: int, now_ms: int) -> None:
        self.state["position"] = {
            "qty": fill.qty,
            "entry_price": fill.price,
            "cost": fill.quote,
            "stop": initial_stop(fill.price, atr_value, self.s.strategy),
            "entry_bar_ts": bar_ts,
            "entry_time": _iso(now_ms),
        }
        self._save()
        self.log.info(
            "ACHAT %.8f %s à %s (coût %.2f), stop %s",
            fill.qty, self.s.symbol, px(fill.price), fill.quote, px(self.state["position"]["stop"]),
            extra=JOURNAL,
        )

    # --- sorties --------------------------------------------------------------------
    def _exit(self, reason: str, last_ts: int, now_ms: int) -> None:
        if self.ex.order_type == "market":
            self._sell_market(reason, self.broker.last_price(), now_ms)
            return
        _, ask = self.broker.best_bid_ask()
        qty = self.broker.normalize_qty(min(self.state["position"]["qty"], self.broker.balances().base), ask)
        placed = self._place_limit("sell", qty, ask) if qty > 0 else None
        if placed is None:
            self._sell_market(reason, self.broker.last_price(), now_ms)
            return
        order_id, price = placed
        self._track_order(order_id, "sell", qty, price, reason, last_ts + self.tf_ms)
        self.log.info("Ordre limite de VENTE (%s) %.8f à %s (id %s)", reason, qty, px(price), order_id, extra=JOURNAL)

    def _sell_market(self, reason: str, price: float, now_ms: int, previous: Fill | None = None) -> None:
        """Vend au marché ce qui reste de la position (après un éventuel ordre limite partiel)."""
        pos = self.state["position"]
        sold = previous.qty if previous else 0.0
        qty = self.broker.normalize_qty(min(pos["qty"] - sold, self.broker.balances().base), price)
        fill = combine_fills(previous, self.broker.market_sell(qty) if qty > 0 else None)
        if fill is None:
            self._forget_position()
            return
        self._close_position(fill, reason, now_ms)

    def _close_position(self, fill: Fill, reason: str, now_ms: int) -> None:
        pos = self.state["position"]
        pnl = fill.quote - pos["cost"]
        self.state["capital"] += pnl
        self.state["position"] = None
        stats = TradeStats.from_dict(self.state.get("perf"))
        stats.add(pnl / pos["cost"])
        self.state["perf"] = stats.to_dict()
        if not self.state.get("eliminated"):
            elimination = elimination_reason(stats, self.s.risk.eliminate_after_trades)
            if elimination:
                self.state["eliminated"] = elimination
                self.log.warning("Stratégie éliminée, plus aucun achat : %s", elimination)
        self._save()
        self.log.info(
            "VENTE (%s) %.8f à %s : PnL %+.2f (%+.2f %%), capital %.2f",
            reason, fill.qty, px(fill.price), pnl, 100 * pnl / pos["cost"], self.state["capital"],
            extra=JOURNAL,
        )
        self._record_trade(pos, fill, pnl, reason, now_ms)

    def _forget_position(self) -> None:
        self.log.error(
            "Position introuvable sur le compte (vendue manuellement ?). "
            "Position oubliée, capital recalculé depuis le solde."
        )
        self.state["position"] = None
        self.state["capital"] = None
        self._init_capital()
        self._save()

    # --- ordres limites -------------------------------------------------------------
    def _place_limit(self, side: str, qty: float, price: float) -> tuple[str, float] | None:
        """Ordre post-only ; s'il croiserait le carnet (le prix a bougé), on reprend le meilleur prix."""
        for _ in range(3):
            try:
                return self.broker.place_limit(side, qty, price)
            except ccxt.OrderImmediatelyFillable:
                bid, ask = self.broker.best_bid_ask()
                price = bid if side == "buy" else ask
        self.log.warning("Ordre limite %s refusé 3 fois (le marché bouge trop vite)", side)
        return None

    def _track_order(self, order_id: str, side: str, qty: float, price: float, reason: str, bar_ts: int, atr: float | None = None) -> None:
        self.state["order"] = {
            "id": order_id,
            "side": side,
            "qty": qty,
            "price": price,
            "reason": reason,
            "atr": atr,
            "bar_ts": bar_ts,
            "expires_ts": bar_ts + self.ex.limit_timeout_bars * self.tf_ms,
        }
        self._save()

    def _poll_order(self, price: float, now_ms: int) -> None:
        order = self.state["order"]
        status = self.broker.order_status(order["id"])
        if status.open:
            if order["side"] == "sell" and price <= self.state["position"]["stop"]:
                self.log.warning("Stop touché pendant l'ordre limite de vente : annulation et vente au marché")
                self._finish_order(self.broker.cancel(order["id"]), "stop", now_ms)
            return
        self._finish_order(status, order["reason"], now_ms)

    def _expire_order(self, now_ms: int) -> None:
        order = self.state["order"]
        self.log.info("Ordre limite %s expiré : annulation", order["id"], extra=JOURNAL)
        self._finish_order(self.broker.cancel(order["id"]), order["reason"], now_ms)

    def _finish_order(self, status: OrderStatus, reason: str, now_ms: int) -> None:
        order = self.state["order"]
        if status.open:
            self.log.warning("Annulation de l'ordre %s pas encore confirmée, nouvel essai au prochain tour", order["id"])
            return
        self.state["order"] = None
        if order["side"] == "sell":
            self._sell_market(reason, self.broker.last_price(), now_ms, previous=status.fill)
        else:
            self._finish_buy(order, status, now_ms)
        self._save()

    def _finish_buy(self, order: dict, status: OrderStatus, now_ms: int) -> None:
        fill = status.fill
        if fill is None or status.filled < order["qty"]:
            if self.ex.limit_entry_fallback == "market":
                price = self.broker.last_price()
                cost_rate = self.ex.fee_rate + self.ex.slippage
                if fill is None:
                    qty = self._entry_qty(price, order["atr"], cost_rate)
                else:
                    remaining = min(order["qty"] - status.filled, self._affordable_qty(price, cost_rate, fill.quote))
                    qty = self.broker.normalize_qty(remaining, price)
                if qty > 0:
                    fill = combine_fills(fill, self.broker.market_buy(qty))
            elif fill is None:
                self.log.info("Achat limite non exécuté : trade abandonné (LIMIT_ENTRY_FALLBACK=skip)", extra=JOURNAL)
        if fill is None:
            return
        if self.broker.normalize_qty(fill.qty, fill.price) <= 0:
            self.log.warning("Achat partiel de %.8f trop petit pour être revendu : ignoré", fill.qty)
            self.state["capital"] -= fill.quote
            return
        self._open_position(fill, order["atr"], order["bar_ts"], now_ms)

    # --- journal et boucle infinie -------------------------------------------------
    def _record_trade(self, pos: dict, fill: Fill, pnl: float, reason: str, now_ms: int) -> None:
        record = {
            "entree": pos["entry_time"],
            "sortie": _iso(now_ms),
            "prix_entree": pos["entry_price"],
            "prix_sortie": fill.price,
            "quantite": fill.qty,
            "cout": round(pos["cost"], 4),
            "pnl": round(pnl, 4),
            "raison": reason,
        }
        if self.notes:
            try:
                self.notes.trade(self.s.mode, self.s.symbol, self.s.timeframe, record, pos["cost"])
            except OSError as exc:  # le journal ne doit jamais arrêter le bot (et ses stops)
                self.log.warning("Note Obsidian non écrite : %s", exc)
        if not self.journal_path:
            return
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        header = list(record)
        if self.journal_path.exists():
            # Journal d'une version précédente : on garde ses colonnes pour ne pas décaler les lignes.
            with self.journal_path.open(newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), header)
        new = not self.journal_path.exists()
        with self.journal_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow(record)


MAX_CONSECUTIVE_FAILURES = 5


def run_bots(bots: list[Bot], poll_seconds: int, after_cycle=None, sleep=time.sleep, cycles: int | None = None) -> None:
    """Fait tourner plusieurs bots dans la même boucle : la panne de l'un n'arrête pas les autres."""
    for bot in bots:
        bot.log.info(
            "Démarrage : mode=%s plateforme=%s ordres=%s", bot.s.mode, bot.s.exchange, bot.ex.order_type, extra=JOURNAL
        )
    failures = {bot.name: 0 for bot in bots}
    active = list(bots)
    done = 0
    while active and (cycles is None or done < cycles):
        for bot in list(active):
            try:
                bot.step()
                failures[bot.name] = 0
            except ccxt.AuthenticationError:
                bot.log.critical("Clés API refusées par la plateforme : vérifie API_KEY / API_SECRET et le MODE.")
                raise
            except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
                bot.log.warning("Erreur plateforme, nouvel essai dans %ss : %s", poll_seconds, exc)
            except Exception:
                failures[bot.name] += 1
                bot.log.exception("Erreur inattendue (%d/%d)", failures[bot.name], MAX_CONSECUTIVE_FAILURES)
                if failures[bot.name] >= MAX_CONSECUTIVE_FAILURES:
                    bot.log.critical("Bot arrêté après %d erreurs de suite : ses stops ne sont plus surveillés", MAX_CONSECUTIVE_FAILURES)
                    active.remove(bot)
        if after_cycle:
            try:
                after_cycle()
            except Exception as exc:  # le tableau de bord ne doit jamais arrêter le trading
                log.warning("Tableau de bord non mis à jour : %s", exc)
        done += 1
        if active and (cycles is None or done < cycles):
            sleep(poll_seconds)
    if not active:
        raise RuntimeError("Tous les bots se sont arrêtés sur des erreurs : voir data/bot.log")
