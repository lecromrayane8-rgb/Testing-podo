"""Le trader fictif : un seul compte, beaucoup de cryptos, les stratégies retenues par le labo, une explication par trade.

Comme un trader humain, il regarde le graphique de chaque crypto, entre quand une de ses règles donne un signal, met un
stop, et note pourquoi il est entré ; à la sortie, il écrit ce qui s'est passé et la leçon (tradingbot/explain.py).
Mais ses décisions restent des règles testées : il n'utilise que les stratégies que le labo a retenues
(« prometteur » ou « à surveiller »), et seulement si ses frais ne dépassent pas ceux avec lesquels le labo les a
testées. Si le labo n'a rien retenu, il attend : c'est ce que ferait un bon trader.

Argent fictif seulement : rien ne part jamais sur une plateforme.
- Taille des positions : chaque trade risque `risk_per_trade` du compte si son stop est touché (1 % par défaut).
- Levier (profil « futures ») : le total des positions peut dépasser le compte, jusqu'à `max_leverage` fois. Le levier
  ne crée aucun gain : il permet de prendre la taille voulue quand le stop est proche. Frais des contrats à terme et
  financement toutes les 8 heures ; si la valeur du compte tombe sous la marge de maintenance, tout est liquidé.
- Le gardien : après `eliminate_after` trades d'une stratégie sur une crypto, si même le haut de sa fourchette est
  négatif, le trader ne la joue plus sur cette crypto (mêmes règles que le tournoi). Il ne change jamais les réglages.
- Le rejeu : les mêmes règles rejouées sur l'historique récent (backtest), pour voir tout de suite des trades et leurs
  explications. Forcément flatteur (les stratégies ont été choisies sur ce passé) : ce n'est pas une preuve.
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .broker import atomic_write
from .data import ohlcv_to_frame, timeframe_to_ms
from .execution import FUTURES, ExecutionParams
from .explain import diagnose, lessons, read_chart, rule_sentence
from .indicators import atr
from .lab import ALL_VARIANTS, FUTURES_LAB_FILE, LAB_FILES, load_lab
from .risk import RiskParams, TradeStats, elimination_reason
from .robustness import research_risk
from .strategy import StrategyParams, compute_signals, exit_reason, initial_stop

log = logging.getLogger(__name__)

TRADER_DIR = "trader"
ACCOUNT_FILE = "compte.json"
REPLAY_FILE = "rejeu.json"
RETAINED = ("prometteur", "à surveiller")
PROFILES = ("futures", "spot")
MIN_NOTIONAL = 10.0  # en dessous, pas de trade (une plateforme refuserait un si petit ordre)
MAINTENANCE = 0.005  # marge de maintenance : 0,5 % du total des positions
KEEP_TRADES = 500
KEEP_HISTORY = 2000
REPLAY_DAYS = {"1m": 7, "5m": 30, "15m": 60, "30m": 90, "1h": 180, "4h": 365, "1d": 730}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def finite(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


@dataclass(frozen=True)
class TraderSettings:
    capital: float = 1000.0  # argent fictif de départ
    risk_per_trade: float = 0.01  # perte si le stop est touché, en part du compte
    max_leverage: float = 3.0  # profil futures : total des positions jusqu'à 3 fois le compte
    max_positions: int = 5
    profile: str = "futures"  # « futures » (frais des contrats à terme, levier) ou « spot » (au comptant, sans levier)
    coins: int = 20  # les cryptos les plus échangées
    plays: int = 4  # stratégies jouées au plus
    eliminate_after: int = 20

    def __post_init__(self):
        if self.profile not in PROFILES:
            raise ValueError(f"TRADER_PROFILE doit valoir {' ou '.join(PROFILES)} (reçu : {self.profile!r})")
        if not self.capital > 0 or not 0 < self.risk_per_trade <= 0.05:
            raise ValueError("TRADER_CAPITAL doit être positif et TRADER_RISK entre 0 et 0,05 (5 % par trade)")
        if not 1 <= self.max_leverage <= 20 or not 1 <= self.max_positions <= 20:
            raise ValueError("TRADER_LEVERAGE doit être entre 1 et 20, TRADER_POSITIONS entre 1 et 20")
        if not 1 <= self.coins <= 100 or not 1 <= self.plays <= 10:
            raise ValueError("TRADER_COINS doit être entre 1 et 100, TRADER_PLAYS entre 1 et 10")

    @property
    def leverage(self) -> float:
        return self.max_leverage if self.profile == "futures" else 1.0

    def execution(self, spot: ExecutionParams) -> ExecutionParams:
        """Toujours des ordres au marché : frais des futures, ou ceux du comptant réglés dans .env."""
        if self.profile == "futures":
            return FUTURES
        return replace(spot, order_type="market", funding_rate_8h=0.0)


def side_cost(ex: ExecutionParams) -> float:
    """Coût d'un ordre (frais + glissement) tel que le labo l'a simulé : frais maker sans glissement en limite."""
    return ex.maker_fee_rate if ex.order_type == "limit" else ex.fee_rate + ex.slippage


@dataclass(frozen=True)
class Play:
    """Une stratégie du labo, dans son unité de temps, que le trader joue sur toutes ses cryptos."""
    name: str
    timeframe: str
    status: str  # verdict du labo : « prometteur » ou « à surveiller »
    lab: str  # titre du labo qui l'a retenue
    expectancy: float | None  # % par trade après frais, dans le labo
    trades: int
    custom: StrategyParams | None = None  # réglages explicites (tests) ; sinon ceux de la variante du labo

    @property
    def params(self) -> StrategyParams:
        return self.custom or ALL_VARIANTS[self.name]

    @property
    def key(self) -> str:
        return f"{self.name} ({self.timeframe})"


def choose_playbook(data_dir: Path, settings: TraderSettings, spot: ExecutionParams) -> list[Play]:
    """Les meilleures stratégies retenues par les labos, jouables avec les frais du trader (au plus ceux du test)."""
    cost = side_cost(settings.execution(spot))
    best: dict[tuple[str, str], Play] = {}
    for name, title in LAB_FILES:
        lab = load_lab(data_dir / name) or {}
        if settings.profile == "spot" and name == FUTURES_LAB_FILE:
            continue
        try:
            lab_cost = side_cost(ExecutionParams(**lab["execution"])) if lab.get("execution") else side_cost(spot)
        except (TypeError, ValueError):
            continue
        if cost > lab_cost * 1.05 + 1e-12:
            continue  # testée avec des frais plus bas que ceux du trader : le verdict ne vaut pas pour lui
        for r in lab.get("rows") or []:
            variant, tf = r.get("variant"), r.get("timeframe")
            if variant not in ALL_VARIANTS or not tf or r.get("verdict") not in RETAINED:
                continue
            play = Play(variant, tf, r["verdict"], title, finite(r.get("expectancy_pct")), int(r.get("trades") or 0))
            old = best.get((variant, tf))
            if old is None or (play.status, play.expectancy or -1e9) > (old.status, old.expectancy or -1e9):
                best[(variant, tf)] = play
    ranked = sorted(best.values(), key=lambda p: (p.status != "prometteur", -(p.expectancy or 0)))
    return ranked[:settings.plays]


def play_view(p: Play) -> dict:
    return {"name": p.name, "timeframe": p.timeframe, "status": p.status, "lab": p.lab, "expectancy": p.expectancy,
            "trades": p.trades, "key": p.key, "family": p.params.strategy_type, "why": rule_sentence(p.params)}


def lookback_for(play: Play) -> int:
    """Autant d'historique que le bot en direct : mêmes signaux qu'en backtest."""
    warmup = play.params.warmup_bars
    return min(max(3 * warmup, warmup + 300), 1000)


class Account:
    """Le compte fictif du trader. Comptabilité des futures : le gain d'une position est quantité × (vente - achat) ;
    les frais et le financement sortent de l'argent du compte ; valeur = argent + gains latents."""

    def __init__(self, path: Path | None, settings: TraderSettings, execution: ExecutionParams, start: datetime):
        self.path, self.settings, self.ex = path, settings, execution
        state = None
        if path is not None:
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                state = None
        if not isinstance(state, dict) or state.get("version") != 1:
            state = {"version": 1, "created": _iso(start), "start": settings.capital, "cash": settings.capital,
                     "positions": [], "trades": [], "stats": {}, "eliminated": {}, "history": [], "playbook": [],
                     "last_bar": {}, "next_id": 1}
        state["settings"] = asdict(settings)
        state["execution"] = asdict(execution)
        self.state = state

    # --- comptes -------------------------------------------------------------------------------------------------
    def value(self, prices: dict[str, float]) -> float:
        return self.state["cash"] + sum(p["qty"] * ((prices.get(p["symbol"]) or p["entry_price"]) - p["entry_price"])
                                        for p in self.state["positions"])

    def exposure(self) -> float:
        return sum(p["notional"] for p in self.state["positions"])

    def holds(self, symbol: str) -> bool:
        return any(p["symbol"] == symbol for p in self.state["positions"])

    def position(self, play: Play, symbol: str) -> dict | None:
        return next((p for p in self.state["positions"] if p["play"] == play.key and p["symbol"] == symbol), None)

    def eliminated(self, play: Play, symbol: str) -> str | None:
        return self.state["eliminated"].get(f"{play.key}|{symbol}")

    # --- entrées et sorties ---------------------------------------------------------------------------------------
    def open(self, play: Play, symbol: str, mark: float, atr_value: float, bar_ts: int, now: datetime,
             prices: dict[str, float], reading: dict | None = None) -> tuple[dict | None, str]:
        """Achat au marché. Renvoie (position, '') ou (None, la raison du refus)."""
        s = self.settings
        if len(self.state["positions"]) >= s.max_positions:
            return None, f"déjà {s.max_positions} positions ouvertes"
        if self.holds(symbol):
            return None, "déjà une position sur cette crypto"
        if reason := self.eliminated(play, symbol):
            return None, f"stratégie éliminée sur cette crypto ({reason})"
        price = mark * (1 + self.ex.slippage)
        stop = initial_stop(price, atr_value, play.params)
        risk = 1 - stop / price
        if not (risk > 0 and math.isfinite(risk)):
            return None, "stop impossible à placer"
        value = self.value(prices)
        notional = min(value * s.risk_per_trade / risk, value * s.leverage - self.exposure())
        if notional < MIN_NOTIONAL:
            return None, "pas assez de marge disponible"
        fee = notional * self.ex.fee_rate
        self.state["cash"] -= fee
        pos = {"id": self.state["next_id"], "symbol": symbol, "play": play.key, "name": play.name,
               "timeframe": play.timeframe, "family": play.params.strategy_type, "status": play.status,
               "entry_time": _iso(now), "entry_bar_ts": bar_ts, "entry_price": price, "entry_mark": mark,
               "qty": notional / price, "notional": notional, "entry_fee": fee, "stop": stop, "risk": risk,
               "leverage": notional / value if value > 0 else math.nan, "max_high": mark, "min_low": mark,
               "why": rule_sentence(play.params),
               "reading": (reading or {}).get("sentences", [])[:6], "trend": (reading or {}).get("trend"),
               "plan": (reading or {}).get("plan")}
        self.state["next_id"] += 1
        self.state["positions"].append(pos)
        return pos, ""

    def close(self, pos: dict, mark: float, reason: str, now: datetime, bars: int | None = None,
              mfe: float | None = None, mae: float | None = None, slip: bool = True) -> dict:
        price = mark * (1 - self.ex.slippage) if slip else mark
        hours = max((now - datetime.fromisoformat(pos["entry_time"])).total_seconds() / 3600, 0.0)
        funding = pos["notional"] * self.ex.funding_rate_8h * hours / 8
        exit_fee = pos["qty"] * price * self.ex.fee_rate
        move = pos["qty"] * (price - pos["entry_price"])
        self.state["cash"] += move - exit_fee - funding
        pnl = move - exit_fee - funding - pos["entry_fee"]
        self.state["positions"].remove(pos)
        net = pnl / pos["notional"]
        gross = mark / pos["entry_mark"] - 1
        fees = (pos["entry_fee"] + exit_fee + funding) / pos["notional"]
        mfe = mfe if mfe is not None else pos["max_high"] / pos["entry_mark"] - 1
        mae = mae if mae is not None else pos["min_low"] / pos["entry_mark"] - 1
        trade = {k: pos[k] for k in ("id", "symbol", "play", "name", "timeframe", "family", "status", "entry_time",
                                     "entry_price", "notional", "stop", "risk", "leverage", "why", "reading",
                                     "trend", "plan")}
        trade.update(exit_time=_iso(now), exit_price=price, reason=reason, pnl=pnl, net=net, gross=gross, fees=fees,
                     funding=funding, mfe=mfe, mae=mae, bars=bars)
        trade["diagnosis"] = diagnose({"reason": reason, "net": net, "gross": gross, "family": pos["family"],
                                       "mfe": mfe, "mae": mae, "risk": pos["risk"], "fees": fees, "bars": bars})
        self.state["trades"].append(trade)
        del self.state["trades"][:-KEEP_TRADES]
        self._learn(pos, net)
        return trade

    def _learn(self, pos: dict, net: float) -> None:
        """Le gardien : une stratégie qui perd nettement sur une crypto n'y est plus jouée."""
        for key in (f"{pos['play']}|{pos['symbol']}", pos["play"]):
            stats = TradeStats.from_dict(self.state["stats"].get(key))
            stats.add(net)
            self.state["stats"][key] = stats.to_dict()
        key = f"{pos['play']}|{pos['symbol']}"
        if key not in self.state["eliminated"]:
            reason = elimination_reason(TradeStats.from_dict(self.state["stats"][key]), self.settings.eliminate_after)
            if reason:
                self.state["eliminated"][key] = reason

    def liquidate_if_needed(self, prices: dict[str, float], now: datetime) -> list[dict]:
        """Si la valeur tombe sous la marge de maintenance, toutes les positions sont vendues (« liquidation »)."""
        positions = self.state["positions"]
        if not positions or self.value(prices) > MAINTENANCE * self.exposure():
            return []
        return [self.close(p, prices.get(p["symbol"]) or p["entry_mark"], "liquidation", now)
                for p in list(positions)]

    def mark(self, prices: dict[str, float], now: datetime, force: bool = False) -> None:
        """Note la valeur du compte, au plus une fois par heure (le dernier prix connu sert si une crypto manque)."""
        for p in self.state["positions"]:
            price = prices.get(p["symbol"])
            if price:
                p["last_price"] = price
                p["max_high"] = max(p["max_high"], price)
                p["min_low"] = min(p["min_low"], price)
        known = {p["symbol"]: p.get("last_price") for p in self.state["positions"]}
        value = self.value({**{k: v for k, v in known.items() if v}, **prices})
        history = self.state["history"]
        if force or not history or now - datetime.fromisoformat(history[-1]["t"]) >= timedelta(hours=1):
            history.append({"t": _iso(now), "value": value})
            del history[:-KEEP_HISTORY]
        self.state["value"], self.state["updated"] = value, _iso(now)

    def save(self) -> None:
        if self.path is not None:
            atomic_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=1, default=str))


class Trader:
    """La boucle du trader en argent fictif : prix, stops, nouvelles bougies, signaux, explications."""

    def __init__(self, exchange, account: Account, plays: list[Play], universe: list[str]):
        self.exchange, self.account = exchange, account
        self.next_fetch: dict[tuple[str, str], int] = {}
        self.universe = universe
        self.set_plays(plays)
        account.state["universe"] = universe

    def set_plays(self, plays: list[Play]) -> None:
        """Nouvelles stratégies (le labo a reparlé) ; celles qui ont encore une position restent jusqu'à la vente."""
        keys = {p.key for p in plays}
        kept = []
        for pos in self.account.state["positions"]:
            if pos["play"] not in keys and pos.get("name") in ALL_VARIANTS:
                kept.append(Play(pos["name"], pos["timeframe"], pos.get("status", "à surveiller"), "", None, 0))
                keys.add(pos["play"])
        self.plays = plays + kept
        self.account.state["playbook"] = [play_view(p) for p in plays]
        self.account.state["notice"] = None if plays else (
            "Le labo n'a retenu aucune stratégie jouable avec ces frais : le trader attend, comme le ferait un bon "
            "trader. Il relit les labos chaque heure : dès qu'une recherche retient une stratégie, il la joue.")

    def cycle(self, now: datetime | None = None) -> list[dict]:
        """Un tour : renvoie ce qui s'est passé (achats et ventes), pour le journal."""
        now = now or datetime.now(timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        acc, events = self.account, []
        tickers = self.exchange.fetch_tickers()
        symbols = sorted(set(self.universe) | {p["symbol"] for p in acc.state["positions"]})  # stops toujours suivis
        prices = {s: float(tickers[s]["last"]) for s in symbols if (tickers.get(s) or {}).get("last")}
        for pos in list(acc.state["positions"]):  # les stops, au prix du moment
            price = prices.get(pos["symbol"])
            if price and price <= pos["stop"]:
                events.append(("vente", acc.close(pos, price, "stop", now)))
        events += [("vente", t) for t in acc.liquidate_if_needed(prices, now)]
        for tf in sorted({p.timeframe for p in self.plays}, key=timeframe_to_ms):
            tf_ms = timeframe_to_ms(tf)
            plays = [p for p in self.plays if p.timeframe == tf]
            limit = max(lookback_for(p) for p in plays)
            for symbol in symbols:
                if now_ms < self.next_fetch.get((symbol, tf), 0) or symbol not in prices:
                    continue
                try:
                    candles = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, tf, limit=limit))
                except Exception as exc:  # une crypto qui ne répond pas ne bloque pas les autres
                    log.warning("%s %s : bougies indisponibles (%s)", symbol, tf, exc)
                    continue
                closed = candles[candles["ts"] + tf_ms <= now_ms]
                if closed.empty:
                    continue
                last_ts = int(closed["ts"].iloc[-1])
                self.next_fetch[(symbol, tf)] = last_ts + 2 * tf_ms  # la prochaine bougie se clôt là
                for play in plays:
                    events += self._on_candle(play, symbol, closed, last_ts, tf_ms, prices, now)
        acc.mark(prices, now)
        acc.save()
        return events

    def _on_candle(self, play: Play, symbol: str, closed: pd.DataFrame, last_ts: int, tf_ms: int,
                   prices: dict[str, float], now: datetime) -> list[tuple[str, dict]]:
        acc = self.account
        key = f"{play.key}|{symbol}"
        if acc.state["last_bar"].get(key) == last_ts or len(closed) < play.params.warmup_bars:
            return []
        acc.state["last_bar"][key] = last_ts
        row = compute_signals(closed, play.params).iloc[-1]
        pos = acc.position(play, symbol)
        price = prices[symbol]
        if pos:
            pos["max_high"] = max(pos["max_high"], float(row.high))
            pos["min_low"] = min(pos["min_low"], float(row.low))
            bars = (last_ts - pos["entry_bar_ts"]) // tf_ms + 1
            reason = exit_reason(bool(row.exit), bars, play.params)
            if reason:
                return [("vente", acc.close(pos, price, reason, now, bars=bars))]
            return []
        if not row.entry:
            return []
        opened, why_not = acc.open(play, symbol, price, float(row.atr), last_ts + tf_ms, now, prices,
                                   read_chart(closed, fees=2 * (acc.ex.fee_rate + acc.ex.slippage)))
        if opened:
            return [("achat", opened)]
        acc.state.setdefault("skipped", []).append({"t": _iso(now), "symbol": symbol, "play": play.key,
                                                    "why": why_not})
        del acc.state["skipped"][:-50]
        return []


def replay(frames: dict[tuple[str, str], pd.DataFrame], plays: list[Play], settings: TraderSettings,
           execution: ExecutionParams, path: Path | None = None) -> Account:
    """Les règles du trader rejouées sur l'historique : un backtest par stratégie et par crypto, puis un seul compte
    qui prend les trades dans l'ordre du temps, avec ses limites (positions, une par crypto, levier, gardien)."""
    candidates = []
    for play in plays:
        for (symbol, tf), df in frames.items():
            if tf != play.timeframe or len(df) <= play.params.warmup_bars:
                continue
            result = run_backtest(df, play.params, research_risk(RiskParams()), 10_000.0, execution, explain=True)
            tf_ms = timeframe_to_ms(tf)
            atrs = atr(df, play.params.atr_period).to_numpy(float)  # celle du stop du backtest
            for t in result.trades:
                if t.reason == "fin du test":
                    continue
                atr_value = float(atrs[max(t.entry_index - 1, 0)])  # la bougie du signal
                candidates.append((t, play, symbol, atr_value, int(df["ts"].iloc[t.entry_index]), tf_ms))
    start = min((c[0].entry_time for c in candidates), default=pd.Timestamp.now(tz="UTC")).to_pydatetime()
    acc = Account(None, settings, execution, start)
    acc.state["replay"] = True
    acc.state["playbook"] = [play_view(p) for p in plays]
    events = sorted([(c[0].entry_time, 1, i) for i, c in enumerate(candidates)] +
                    [(c[0].exit_time, 0, i) for i, c in enumerate(candidates)])  # à la même bougie : sortie d'abord
    open_by_candidate: dict[int, dict] = {}
    for when, kind, i in events:
        t, play, symbol, atr_value, bar_ts, tf_ms = candidates[i]
        now = when.to_pydatetime()
        if kind == 1:
            pos, _ = acc.open(play, symbol, t.entry_mark, atr_value, bar_ts, now, {}, t.context)
            if pos:
                open_by_candidate[i] = pos
        elif i in open_by_candidate:
            pos = open_by_candidate.pop(i)
            bars = (int(when.timestamp() * 1000) - bar_ts) // tf_ms + 1
            mark = t.exit_mark if math.isfinite(t.exit_mark) else t.exit_price
            acc.close(pos, mark, t.reason, now, bars=bars, mfe=t.mfe, mae=t.mae)
            acc.mark({}, now)
    end = max((c[0].exit_time for c in candidates), default=pd.Timestamp(start)).to_pydatetime()
    acc.mark({}, end, force=True)
    acc.path = path
    acc.save()
    return acc


def summary(state: dict | None) -> dict:
    """Ce que le site affiche : valeur, résultat, positions, derniers trades expliqués, leçons, stratégies jouées."""
    if not state:
        return {"exists": False}
    trades = state.get("trades") or []
    start = finite(state.get("start")) or 0.0
    value = finite(state.get("value")) or finite(state.get("cash")) or start
    closed = [t for t in trades if t.get("reason") != "fin du test"]
    wins = sum((t.get("net") or 0) > 0 for t in closed)
    learned = lessons([{"strategy": t["play"], "symbol": t["symbol"], "net": t["net"], "trend": t.get("trend"),
                        "kind": (t.get("diagnosis") or {}).get("kind")} for t in closed])
    positions = []
    for p in state.get("positions") or []:
        last = finite(p.get("last_price")) or finite(p.get("entry_mark"))
        positions.append({**p, "last_price": last,
                          "pnl_pct": 100 * (last / p["entry_mark"] - 1) if last and p.get("entry_mark") else None})
    return {
        "exists": True, "replay": bool(state.get("replay")), "created": state.get("created"),
        "updated": state.get("updated"), "start": start, "value": value,
        "pnl_pct": 100 * (value / start - 1) if start else None,
        "settings": state.get("settings"), "positions": positions,
        "trades": list(reversed(closed[-30:])), "count": len(closed),
        "win_rate": wins / len(closed) if closed else None, "lessons": learned[:8],
        "playbook": state.get("playbook") or [], "eliminated": state.get("eliminated") or {},
        "history": state.get("history") or [], "skipped": (state.get("skipped") or [])[-5:],
        "universe": state.get("universe") or [],
    }


def settings_from_env(environ: dict[str, str]) -> TraderSettings:
    """Les réglages du trader dans .env (TRADER_CAPITAL, TRADER_RISK, TRADER_LEVERAGE, TRADER_POSITIONS,
    TRADER_PROFILE, TRADER_COINS, TRADER_PLAYS) ; absents : les valeurs par défaut."""
    d = TraderSettings()
    def num(name, default, kind=float):
        raw = (environ.get(name) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            return kind(float(raw)) if kind is int else kind(raw)
        except ValueError:
            raise ValueError(f"{name} doit être un nombre (reçu : {raw!r})") from None
    return TraderSettings(capital=num("TRADER_CAPITAL", d.capital), risk_per_trade=num("TRADER_RISK", d.risk_per_trade),
                          max_leverage=num("TRADER_LEVERAGE", d.max_leverage),
                          max_positions=num("TRADER_POSITIONS", d.max_positions, int),
                          profile=(environ.get("TRADER_PROFILE") or d.profile).strip().lower(),
                          coins=num("TRADER_COINS", d.coins, int), plays=num("TRADER_PLAYS", d.plays, int))


REFRESH_S = 3600  # le trader relit les labos (et la liste des cryptos) chaque heure


def run(exchange, account: Account, refresh, seconds: float = 20.0, once: bool = False, sleep=time.sleep,
        clock=time.time, initial: tuple[list[Play], list[str]] | None = None) -> None:
    """`refresh()` -> (stratégies, cryptos) : appelé au départ (sauf `initial`) puis chaque heure, pour suivre ce que
    dit le labo."""
    plays, universe = initial or refresh()
    trader = Trader(exchange, account, plays, universe)
    refreshed = clock()
    while True:
        if clock() - refreshed >= REFRESH_S:
            try:
                plays, universe = refresh()
                trader.universe = universe
                account.state["universe"] = universe
                trader.set_plays(plays)
            except Exception as exc:
                log.warning("Trader : labos ou liste des cryptos illisibles (%s)", exc)
            refreshed = clock()
        try:
            for kind, item in trader.cycle():
                if kind == "achat":
                    log.info("ACHAT %s · %s à %.6g (stop %.6g, levier %.1f) : %s", item["symbol"], item["play"],
                             item["entry_price"], item["stop"], item["leverage"], item["why"])
                else:
                    log.info("VENTE %s · %s (%s) : %+.2f %% · %s", item["symbol"], item["play"], item["reason"],
                             100 * item["net"], item["diagnosis"]["text"])
        except Exception as exc:  # le réseau coupe : on retente au tour suivant
            log.warning("Trader : %s (nouvel essai dans %.0f s)", exc, seconds)
        if once:
            return
        sleep(seconds)
