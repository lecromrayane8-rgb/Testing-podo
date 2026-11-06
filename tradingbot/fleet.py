"""Les 15 bots : trois équipes de cinq (long terme, court terme, scalping), en argent fictif, chacun sur sa crypto.

Un bot, c'est une crypto, une technique, une unité de temps, un sens et un objectif :
- le sens : acheteur (il gagne si le prix monte) ou vendeur à découvert (il gagne si le prix baisse). Chaque technique
  existe dans les deux sens : la version vendeuse applique la même règle au graphique retourné (un sommet y devient un
  creux, une résistance un support) ;
- l'objectif (take-profit) : sans objectif, le bot sort par sa règle ; avec, il encaisse aussi dès que le prix a
  parcouru 2 fois la distance de son stop ;
- tout son capital à chaque trade, avec le levier de son équipe (×1, ×3 et ×5 par défaut). Pour un trade dont le stop
  est loin, le levier est réduit : le stop passe toujours avant le prix de liquidation.

Le choix (`select`) : chaque combinaison (technique × sens × objectif × crypto × unité de temps) est backtestée sur
l'historique réel, frais des contrats à terme et financement compris. Comme au labo, l'historique est coupé en trois :
étude (la première moitié), validation (jusqu'à 80 %), test final (les 20 % les plus récents). Le classement ne regarde
que l'étude et la validation ; le test final dit ensuite, honnêtement, si le choix tient. Les mieux classées sont
gardées, même si leur avantage est très petit, avec des cryptos et des techniques variées. Le meilleur de milliers
d'essais est souvent chanceux : c'est le direct qui tranche.

Le direct (`Fleet`) : exactement le même moteur (`Book`), bougie clôturée par bougie clôturée, avec le stop et
l'objectif surveillés au prix du moment entre deux bougies. Un bot liquidé, qui a perdu la moitié de son capital, ou
que le gardien juge nettement perdant après 20 trades est remplacé par le suivant du classement. Jamais de réglage
changé après une perte : seulement des bots testés d'avance qui prennent la place des autres.

Argent fictif seulement : rien ne part jamais sur une plateforme. Le bot en argent réel reste au comptant et sans levier.
"""
from __future__ import annotations

import json
import logging
import math
import os
import pickle
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

from .broker import atomic_write
from .data import ohlcv_to_frame, timeframe_to_ms
from .execution import FUTURES, ExecutionParams
from .explain import decimal, diagnose, pct, price as fmt_price, read_chart
from .indicators import atr, bollinger, sma, supertrend_line
from .lab import ALL_VARIANTS, JUMP, STUDY_SHARE, TEST_SHARE, default_workers
from .notify import ALERT
from .risk import TradeStats, elimination_reason
from .scanner import MEMECOINS, ScanResult, liquid_markets
from .strategy import StrategyParams, compute_signals, exit_reason

log = logging.getLogger(__name__)

FLEET_DIR = "bots"  # data/bots
SELECTION_FILE = "selection.json"
STATE_FILE = "etat.json"
LOCK_FILE = "en-cours.json"
CAPITAL = 1000.0
BOTS_PER_SECTION = 5
BENCH = 12  # remplaçants gardés par équipe
MAINTENANCE = 0.005  # marge de maintenance : 0,5 % de la position
LIQ_SAFETY = 0.9  # le stop reste à moins de 90 % de la distance de liquidation
MIN_NOTIONAL = 10.0  # en dessous, plus de trade possible (une plateforme refuserait un si petit ordre)
TARGET_R = 2.0  # l'objectif : 2 fois la distance du stop
TARGETS = (0.0, TARGET_R)
MIN_BARS = 300  # bougies au-delà de la chauffe pour juger une combinaison
MIN_PART_TRADES = 3  # trades minimum dans l'étude et dans la validation
MIN_TEST_TRADES = 5
REPLACE_DRAWDOWN = 0.5  # remplacé après avoir perdu la moitié de son capital
ELIMINATE_AFTER = 20  # le gardien juge un bot après 20 trades
KEEP_TRADES = 120  # trades gardés par bot dans l'état du direct
KEEP_EVENTS = 300
HEARTBEAT_S = 45  # au-delà, un autre lancement considère que les bots ne tournent plus
BEAT_S = 10  # le signal de vie, écrit à part : même un tour lent (réseau) ne le retarde pas
RETRY_S = 60  # une crypto dont les bougies ne viennent pas est réessayée une minute plus tard
SIDES = ("long", "short")
TF_LABELS = {"1m": "1 min", "5m": "5 min", "15m": "15 min", "30m": "30 min", "1h": "1 h", "4h": "4 h", "1d": "1 jour"}


def tf_label(tf: str) -> str:
    return TF_LABELS.get(tf, tf)


def _iso(ms: int | float | None = None) -> str:
    when = datetime.now(timezone.utc) if ms is None else datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return when.isoformat(timespec="seconds")


def finite(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# --- Les trois équipes et leurs techniques --------------------------------------------------------------------------

# Une impulsion à l'échelle du long terme (comme une crypto qui prend 8 % en une journée de bougies de 4 h) : seuil rond
# fixé d'avance, pas ajusté sur les données.
EXTRA: dict[str, StrategyParams] = {
    "Impulsion +8 % en 6 bougies + volume x2": StrategyParams(impulse_bars=6, impulse_pct=0.08, volume_mult=2.0,
                                                              **JUMP),
}


def technique(name: str) -> StrategyParams:
    """Les réglages d'une technique, par son nom (ceux du labo, ou l'impulsion du long terme)."""
    return EXTRA[name] if name in EXTRA else ALL_VARIANTS[name]


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    timeframes: tuple[str, ...]
    leverage: float  # levier maximum par défaut
    days: tuple[tuple[str, int], ...]  # jours d'historique pour le choix, par unité de temps
    min_trades: int  # trades de l'étude et de la validation en dessous desquels on ne juge pas
    techniques: tuple[str, ...]
    blurb: str

    def history_days(self, timeframe: str) -> int:
        return dict(self.days)[timeframe]


SECTIONS = (
    Section("long", "Long terme", ("4h", "1d"), 1.0, (("4h", 730), ("1d", 1500)), 15, (
        "Repli RSI(2) < 10 + MM200", "Bollinger rebond 20/2 + MM200", "Bollinger cassure 20/2", "Cassure 20/10",
        "Cassure 55/20", "Croisement MM 20/100", "Croisement MM 50/200", "MACD 12/26/9", "Momentum 28",
        "Momentum 100", "Supertrend 10/3", "Prix au-dessus de la MM 50", "Rebond sur support",
        "Cassure de résistance", "Impulsion +8 % en 6 bougies + volume x2"),
        "Bougies de 4 heures et d'un jour : peu de trades, qui durent des jours ou des semaines, pour suivre les "
        "grandes tendances."),
    Section("court", "Court terme", ("15m", "1h"), 3.0, (("15m", 90), ("1h", 365)), 30, (
        "Repli RSI(2) < 10 + MM200", "Bollinger rebond 20/2,5 + MM200", "Bollinger cassure 20/2 + volume x2",
        "Cassure 20/10 + volume x2", "Cassure 55/20", "Croisement MM 20/100", "MACD 12/26/9 + MM200", "Momentum 50",
        "Supertrend 10/3", "Supertrend 10/3 + heures actives", "Rebond sur support",
        "Cassure de résistance + volume x2", "Impulsion +3 % en 15 bougies + volume x3", "Cassure 20/10 + compression",
        "Prix au-dessus de la MM 20"),
        "Bougies de 15 minutes et d'une heure : des trades de quelques heures à quelques jours."),
    Section("scalping", "Scalping", ("1m", "5m"), 5.0, (("1m", 10), ("5m", 45)), 40, (
        "Repli RSI(2) < 5 + MM200 + volatilité", "Bollinger rebond 20/2,5 + volatilité",
        "Bollinger cassure 20/2 + volatilité", "Cassure 20/10 + volatilité", "Cassure 20/10 + heures actives",
        "Supertrend 10/3 + volatilité", "Croisement MM 20/100 + volatilité", "MACD 12/26/9 + MM200 + volume x2",
        "Momentum 50 + volume x2", "Impulsion +1 % en 5 bougies + volume x3",
        "Impulsion +0,5 % en 1 bougie + volume x3", "Rebond sur support", "Cassure de résistance + volume x2",
        "Cassure 20/10 + compression", "Bollinger cassure 20/2 + compression"),
        "Bougies de 1 et 5 minutes : beaucoup de petits trades rapides, où les frais pèsent lourd."),
)
SECTION_KEYS = {s.key: s for s in SECTIONS}


@dataclass(frozen=True)
class FleetSettings:
    capital: float = CAPITAL  # argent fictif de chaque bot
    leverage_long: float = 1.0
    leverage_court: float = 3.0
    leverage_scalping: float = 5.0
    coins: int = 15  # les cryptos les plus échangées
    hot: int = 10  # plus les plus agitées du moment

    def __post_init__(self):
        if not 10 <= self.capital <= 1e9:
            raise ValueError("FLOTTE_CAPITAL doit être entre 10 et 1 000 000 000 USDT")
        for value in (self.leverage_long, self.leverage_court, self.leverage_scalping):
            if not 1 <= value <= 20:
                raise ValueError("Les leviers des bots (FLOTTE_LEVIER_...) doivent être entre 1 et 20")
        if not 1 <= self.coins <= 50 or not 0 <= self.hot <= 30:
            raise ValueError("FLOTTE_CRYPTOS doit être entre 1 et 50, FLOTTE_AGITEES entre 0 et 30")

    def leverage(self, section: str) -> float:
        return {"long": self.leverage_long, "court": self.leverage_court, "scalping": self.leverage_scalping}[section]


def settings_from_env(environ: dict[str, str]) -> FleetSettings:
    """FLOTTE_CAPITAL, FLOTTE_LEVIER_LONG, FLOTTE_LEVIER_COURT, FLOTTE_LEVIER_SCALPING, FLOTTE_CRYPTOS et
    FLOTTE_AGITEES dans .env ; absents : les valeurs par défaut."""
    d = FleetSettings()

    def num(name, default, kind=float):
        raw = (environ.get(name) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            return kind(float(raw))
        except ValueError:
            raise ValueError(f"{name} doit être un nombre (reçu : {raw!r})") from None

    return FleetSettings(capital=num("FLOTTE_CAPITAL", d.capital), leverage_long=num("FLOTTE_LEVIER_LONG", d.leverage_long),
                         leverage_court=num("FLOTTE_LEVIER_COURT", d.leverage_court),
                         leverage_scalping=num("FLOTTE_LEVIER_SCALPING", d.leverage_scalping),
                         coins=num("FLOTTE_CRYPTOS", d.coins, int), hot=num("FLOTTE_AGITEES", d.hot, int))


@dataclass(frozen=True)
class Spec:
    """Ce qu'est un bot."""
    section: str
    symbol: str
    timeframe: str
    technique: str
    side: str = "long"
    target_r: float = 0.0  # objectif à target_r fois la distance du stop ; 0 = sortie par la règle seulement
    leverage: float = 1.0  # levier maximum

    def __post_init__(self):
        if self.side not in SIDES:
            raise ValueError(f"Sens inconnu : {self.side!r}")

    @property
    def params(self) -> StrategyParams:
        return technique(self.technique)

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.timeframe}|{self.technique}|{self.side}|{self.target_r:g}"

    @property
    def family(self) -> str:
        return self.params.strategy_type

    @property
    def coin(self) -> str:
        return self.symbol.split("/")[0]


def spec_from(d: dict) -> Spec:
    return Spec(**{k: d[k] for k in ("section", "symbol", "timeframe", "technique", "side", "target_r", "leverage")})


# --- Les règles en mots ----------------------------------------------------------------------------------------------

SIDE_LABELS = {"long": "acheteur", "short": "vendeur à découvert"}
SIDE_HINTS = {"long": "il gagne si le prix monte", "short": "il gagne si le prix baisse"}
SHORT_REASONS = {"rebond": "rechute", "résistance ou support cassé": "support ou résistance cassée",
                 "retour sous le niveau": "retour au-dessus du niveau"}


def condition(p: StrategyParams, side: str) -> str:
    """Le signal d'entrée d'une technique, au présent : « le prix clôture au-dessus de… »."""
    up = side == "long"
    t = p.strategy_type
    if t == "retour_moyenne":
        text = (f"le RSI sur {p.rsi_period} bougies passe sous {p.rsi_entry:g} (une chute brutale : un rebond est "
                "attendu)" if up else f"le RSI sur {p.rsi_period} bougies passe au-dessus de {100 - p.rsi_entry:g} "
                "(une envolée brutale : une rechute est attendue)")
    elif t == "bollinger":
        text = ("le prix clôture sous la bande basse de Bollinger (loin sous sa moyenne : un retour vers le milieu est "
                "attendu)" if up else "le prix clôture au-dessus de la bande haute de Bollinger (loin au-dessus de sa "
                "moyenne : un retour vers le milieu est attendu)")
    elif t == "bollinger_cassure":
        text = ("le prix clôture au-dessus de la bande haute de Bollinger (un mouvement inhabituellement fort, qu'il "
                "suit)" if up else "le prix clôture sous la bande basse de Bollinger (une chute inhabituellement forte, "
                "qu'il suit)")
    elif t == "cassure":
        text = (f"le prix clôture au-dessus du plus haut des {p.breakout_period} bougies précédentes (un nouveau sommet)"
                if up else f"le prix clôture sous le plus bas des {p.breakout_period} bougies précédentes (un nouveau "
                "creux)")
    elif t == "croisement":
        word = "au-dessus de" if up else "sous"
        text = (f"le prix passe {word} sa moyenne des {p.slow_period} dernières clôtures" if p.fast_period == 1 else
                f"la moyenne des {p.fast_period} dernières clôtures passe {word} celle des {p.slow_period} (la "
                f"tendance tourne à la {'hausse' if up else 'baisse'})")
    elif t == "macd":
        text = ("la ligne MACD croise sa ligne de signal par le haut (la hausse accélère)" if up else
                "la ligne MACD croise sa ligne de signal par le bas (la baisse accélère)")
    elif t == "momentum":
        text = f"le prix repasse {'au-dessus de' if up else 'sous'} son niveau d'il y a {p.momentum_period} bougies"
    elif t == "supertrend":
        text = f"le Supertrend passe à la {'hausse' if up else 'baisse'}"
    elif t == "impulsion":
        text = (f"le prix prend plus de {pct(p.impulse_pct, 1, False)} en {p.impulse_bars} bougie"
                f"{'s' if p.impulse_bars > 1 else ''} (un mouvement soudain, sur lequel il saute)" if up else
                f"le prix perd environ {pct(p.impulse_pct / (1 + p.impulse_pct), 1, False)} en {p.impulse_bars} bougie"
                f"{'s' if p.impulse_bars > 1 else ''} (une chute soudaine, sur laquelle il saute)")
    elif t == "support":
        text = ("le prix descend sur un support solide puis clôture au-dessus, en hausse (un rebond)" if up else
                "le prix monte jusqu'à une résistance solide puis clôture en dessous, en baisse (un rejet)")
    else:
        text = ("le prix clôture nettement au-dessus d'une résistance solide (une cassure)" if up else
                "le prix clôture nettement sous un support solide (une cassure vers le bas)")
    if p.trend_period:
        text += (f", dans une tendance de fond haussière (au-dessus de la moyenne des {p.trend_period} bougies)" if up
                 else f", dans une tendance de fond baissière (sous la moyenne des {p.trend_period} bougies)")
    filters = []
    if p.volume_mult:
        filters.append(f"si le volume vaut au moins {p.volume_mult:g} fois sa moyenne")
    if p.min_atr_pct:
        filters.append(f"si les bougies bougent d'au moins {pct(p.min_atr_pct, 1, False)}")
    if p.active_hours:
        filters.append(f"pendant les heures actives ({p.active_hours} h UTC)")
    if p.squeeze_quantile:
        filters.append("après un marché calme (bandes de Bollinger resserrées)")
    return text + (" ; seulement " + ", ".join(filters) if filters else "")


def exit_condition(p: StrategyParams, side: str) -> str:
    up = side == "long"
    t = p.strategy_type
    above, below = ("au-dessus", "sous") if up else ("sous", "au-dessus")
    if t == "retour_moyenne":
        return f"le prix clôture {above} de sa moyenne des {p.exit_period} dernières bougies" if up else \
            f"le prix clôture sous sa moyenne des {p.exit_period} dernières bougies"
    if t == "bollinger":
        return "le prix revient au milieu des bandes de Bollinger"
    if t == "bollinger_cassure":
        return f"le prix clôture {'sous' if up else 'au-dessus de'} le milieu des bandes de Bollinger".replace(
            "de le", "du")
    if t in ("cassure", "impulsion"):
        word = f"sous le plus bas des {p.breakout_exit_period}" if up else \
            f"au-dessus du plus haut des {p.breakout_exit_period}"
        return f"le prix clôture {word} bougies précédentes" + (" (le mouvement s'essouffle)" if t == "impulsion" else "")
    if t == "croisement":
        return (f"le prix repasse {below} sa moyenne des {p.slow_period} clôtures" if p.fast_period == 1 else
                f"la moyenne des {p.fast_period} repasse {below} celle des {p.slow_period}").replace(
            "au-dessus sa", "au-dessus de sa").replace("au-dessus celle", "au-dessus de celle")
    if t == "macd":
        return f"la ligne MACD repasse {below} sa ligne de signal".replace("au-dessus sa", "au-dessus de sa")
    if t == "momentum":
        return f"le prix repasse {below} son niveau d'il y a {p.momentum_period} bougies".replace(
            "au-dessus son", "au-dessus de son")
    if t == "supertrend":
        return f"le Supertrend repasse à la {'baisse' if up else 'hausse'}"
    if t == "support":
        return ("le prix touche la résistance suivante, ou si le support cède" if up else
                "le prix touche le support suivant, ou si la résistance cède")
    return ("le prix retombe sous l'ancienne résistance" if up else "le prix remonte au-dessus de l'ancien support")


def entry_rule(spec: Spec) -> str:
    return f"Il {'achète' if spec.side == 'long' else 'vend à découvert'} quand {condition(spec.params, spec.side)}."


def exit_rule(spec: Spec) -> str:
    p = spec.params
    target = (f", à son objectif ({decimal(spec.target_r, 0)} fois la distance du stop, dans l'autre sens)"
              if spec.target_r else "")
    timer = f", et au plus tard après {p.max_bars_in_trade} bougies" if p.max_bars_in_trade else ""
    return (f"Il sort à son stop (à {decimal(p.stop_atr_mult)} fois la taille moyenne d'une bougie de son prix "
            f"d'entrée){target}, ou quand {exit_condition(p, spec.side)}{timer}.")


def reason_label(reason: str, side: str) -> str:
    return SHORT_REASONS.get(reason, reason) if side == "short" else reason


# --- Le moteur : un bot, bougie par bougie ---------------------------------------------------------------------------

def mirror(df: pd.DataFrame) -> pd.DataFrame:
    """Le graphique retourné : un vendeur à découvert sur `df` voit ce que voit un acheteur sur ce graphique."""
    out = df.copy()
    out["open"], out["close"] = 1 / df["open"], 1 / df["close"]
    out["high"], out["low"] = 1 / df["low"], 1 / df["high"]
    return out


@dataclass
class Signals:
    entry: np.ndarray
    exit: np.ndarray
    atr: np.ndarray  # sur le vrai prix : la distance du stop


def signals_for(df: pd.DataFrame, params: StrategyParams, side: str) -> Signals:
    data = compute_signals(df if side == "long" else mirror(df), params)
    return Signals(data["entry"].to_numpy(bool), data["exit"].to_numpy(bool),
                   atr(df, params.atr_period).to_numpy(float))


def lookback_for(params: StrategyParams) -> int:
    """Bougies lues en direct : assez pour que les signaux soient ceux du backtest."""
    warmup = params.warmup_bars
    return min(max(3 * warmup, warmup + 300), 1000)


class Book:
    """Le compte d'un bot et sa position. Le backtest et le direct appellent les mêmes méthodes dans le même ordre :
    `open_bar` (à l'ouverture d'une bougie : ce que la clôture précédente a décidé), `range_bar` (pendant la bougie :
    stop d'abord, par prudence, puis objectif ; en direct aussi au prix du moment) et `close_bar` (à la clôture : les
    signaux). Comptabilité des contrats à terme : gain = quantité × écart de prix, frais et financement à part."""

    def __init__(self, spec: Spec, capital: float = CAPITAL, ex: ExecutionParams = FUTURES, state: dict | None = None,
                 keep: int | None = None, explain: bool = False):
        self.spec, self.ex, self.keep, self.explain = spec, ex, keep, explain
        self.params = spec.params
        self.tf_ms = timeframe_to_ms(spec.timeframe)
        self.s = state if state is not None else {
            "start": capital, "cash": capital, "position": None, "pending": None, "trades": [], "stats": {},
            "count": 0, "wins": 0, "pnl": 0.0, "dead": None, "peak": capital, "drawdown": 0.0, "last_ts": None}

    @property
    def position(self) -> dict | None:
        return self.s["position"]

    @property
    def idle(self) -> bool:
        return self.s["position"] is None and self.s["pending"] is None

    @staticmethod
    def move(pos: dict, price: float) -> float:
        """Le gain (ou la perte) de la position si elle était fermée à ce prix, avant frais."""
        return (1 if pos["side"] == "long" else -1) * pos["qty"] * (price - pos["price"])

    def equity(self, mark: float | None = None) -> float:
        pos = self.s["position"]
        if pos is None or not mark:
            return self.s["cash"]
        return self.s["cash"] + self.move(pos, mark)

    def leverage_for(self, risk: float) -> float:
        """Le levier de l'équipe, réduit pour un stop lointain : le stop passe toujours avant la liquidation."""
        return float(max(1, math.floor(min(self.spec.leverage, LIQ_SAFETY / (risk + MAINTENANCE)))))

    def _fill(self, mark: float, opening: bool) -> float:
        """Prix obtenu au marché : l'acheteur paie un peu plus que le graphique, le vendeur reçoit un peu moins."""
        buying = (self.spec.side == "long") == opening
        return mark * (1 + self.ex.slippage) if buying else mark * (1 - self.ex.slippage)

    # 1. À l'ouverture de la bougie : ce que la clôture précédente a décidé.
    def open_bar(self, ts: int, mark: float, at: str | None = None) -> list[dict]:
        pending, self.s["pending"] = self.s["pending"], None
        if not pending:
            return []
        if pending["kind"] == "exit" and self.s["position"]:
            return [self._close(ts, self._fill(mark, False), mark, pending["reason"], self.ex.fee_rate, False, at)]
        if pending["kind"] == "entry" and self.s["position"] is None and not self.s["dead"]:
            opened = self._open(ts, mark, pending["atr"], at)
            return [opened] if opened else []
        return []

    def _open(self, ts: int, mark: float, atr_value: float, at: str | None) -> dict | None:
        s, p = self.s, self.params
        if not (mark > 0 and atr_value > 0 and math.isfinite(atr_value)):
            return None
        long = self.spec.side == "long"
        price = self._fill(mark, True)
        distance = p.stop_atr_mult * atr_value
        risk = distance / price
        if not 0 < risk < 0.9:
            return None  # stop impossible à placer : la bougie moyenne vaut presque le prix
        leverage = self.leverage_for(risk)
        margin = s["cash"]
        notional = margin * leverage
        if notional < MIN_NOTIONAL:
            s["dead"] = s["dead"] or "plus assez d'argent pour trader"
            return None
        fee = notional * self.ex.fee_rate
        s["cash"] -= fee
        target = None
        if self.spec.target_r:
            target = price + self.spec.target_r * distance if long else price - self.spec.target_r * distance
            target = target if target > 0 else None
        liquidation = price * (1 - 1 / leverage + MAINTENANCE) if long else price * (1 + 1 / leverage - MAINTENANCE)
        pos = {"side": self.spec.side, "entry_ts": int(ts), "entry_mark": mark, "price": price, "qty": notional / price,
               "notional": notional, "margin": margin, "leverage": leverage, "fee": fee, "stop": price - distance
               if long else price + distance, "target": target, "liquidation": liquidation, "risk": risk,
               "high": mark, "low": mark, "bars": 0}
        if at:
            pos["entry_at"] = at
        s["position"] = pos
        return {"kind": "entry", **pos}

    # 2. Pendant la bougie : stop d'abord (le pire), puis objectif. `o` None : un prix suivi en direct, sans saut.
    def range_bar(self, ts: int, o: float | None, h: float, low: float, at: str | None = None) -> list[dict]:
        pos = self.s["position"]
        if pos is None:
            return []
        pos["high"], pos["low"] = max(pos["high"], h), min(pos["low"], low)
        long = pos["side"] == "long"
        stop, liq, target = pos["stop"], pos["liquidation"], pos["target"]
        if (low <= stop) if long else (h >= stop):
            mark = stop if o is None else (min(o, stop) if long else max(o, stop))
            if (mark <= liq) if long else (mark >= liq):
                return [self._liquidate(ts, at)]
            return [self._close(ts, self._fill(mark, False), mark, "stop", self.ex.fee_rate, True, at)]
        if (low <= liq) if long else (h >= liq):
            return [self._liquidate(ts, at)]
        if target is not None and ((h > target) if long else (low < target)):
            mark = target if o is None else (max(o, target) if long else min(o, target))
            return [self._close(ts, mark, mark, "objectif", self.ex.maker_fee_rate, True, at)]  # ordre limite posé
        return []

    # 3. À la clôture : les signaux.
    def close_bar(self, ts: int, close: float, entry: bool, exit_: bool, atr_value: float) -> None:
        s, pos = self.s, self.s["position"]
        s["last_ts"] = int(ts)
        if pos is not None:
            pos["bars"] = int((ts - pos["entry_ts"]) // self.tf_ms + 1)
            self._mark(self.equity(close))
            reason = exit_reason(bool(exit_), pos["bars"], self.params)
            if reason:
                s["pending"] = {"kind": "exit", "reason": reason_label(reason, self.spec.side)}
        elif not s["dead"] and entry and math.isfinite(atr_value) and atr_value > 0:
            s["pending"] = {"kind": "entry", "atr": float(atr_value), "signal_ts": int(ts)}

    def _mark(self, equity: float) -> None:
        s = self.s
        s["peak"] = max(s["peak"], equity)
        if s["peak"] > 0:
            s["drawdown"] = min(s["drawdown"], equity / s["peak"] - 1)

    def _close(self, ts: int, fill: float, mark: float, reason: str, fee_rate: float, during: bool,
               at: str | None) -> dict:
        s, pos = self.s, self.s["position"]
        hours = max(ts - pos["entry_ts"], 0) / 3_600_000
        funding = pos["notional"] * self.ex.funding_rate_8h * hours / 8  # compté comme un coût dans les deux sens
        exit_fee = pos["qty"] * fill * fee_rate
        move = self.move(pos, fill)
        s["cash"] += move - exit_fee - funding
        pnl = move - exit_fee - funding - pos["fee"]
        return self._record(ts, pos, fill, mark, reason, pnl, pos["fee"] + exit_fee + funding, funding, during, at)

    def _liquidate(self, ts: int, at: str | None) -> dict:
        """Le prix a atteint le seuil de liquidation : toute la mise du trade (le capital du bot) est perdue."""
        s, pos = self.s, self.s["position"]
        s["cash"] = 0.0
        trade = self._record(ts, pos, pos["liquidation"], pos["liquidation"], "liquidation", -pos["margin"],
                             pos["margin"], 0.0, True, at)
        s["dead"] = "liquidé"
        return trade

    def _record(self, ts, pos, fill, mark, reason, pnl, fees, funding, during, at) -> dict:
        s = self.s
        long = pos["side"] == "long"
        net = pnl / pos["notional"]
        trade = {k: pos[k] for k in ("side", "entry_ts", "entry_mark", "price", "qty", "notional", "margin", "leverage",
                                     "stop", "target", "liquidation", "risk")}
        trade.update(
            exit_ts=int(ts), exit_mark=mark, exit_price=fill, reason=reason, pnl=pnl, net=net, roi=pnl / pos["margin"],
            gross=(mark / pos["entry_mark"] - 1) * (1 if long else -1), fees=fees / pos["notional"], funding=funding,
            mfe=pos["high"] / pos["entry_mark"] - 1 if long else 1 - pos["low"] / pos["entry_mark"],
            mae=pos["low"] / pos["entry_mark"] - 1 if long else 1 - pos["high"] / pos["entry_mark"],
            bars=int(pos["bars"] + (1 if during else 0)), equity=s["cash"])
        if pos.get("entry_at"):
            trade["entry_at"] = pos["entry_at"]
        if at:
            trade["exit_at"] = at
        if self.explain:
            trade["diagnosis"] = diagnose({"reason": reason, "net": net, "gross": trade["gross"], "mfe": trade["mfe"],
                                           "mae": trade["mae"], "risk": pos["risk"], "fees": trade["fees"],
                                           "bars": trade["bars"], "family": self.spec.family if long else ""})
        s["trades"].append(trade)
        if self.keep:
            del s["trades"][:-self.keep]
        stats = TradeStats.from_dict(s["stats"])
        stats.add(net)
        s["stats"] = stats.to_dict()
        s["count"] += 1
        s["wins"] += pnl > 0
        s["pnl"] += pnl
        s["position"] = None
        if s["cash"] < MIN_NOTIONAL:
            s["dead"] = s["dead"] or "plus assez d'argent pour trader"
        self._mark(s["cash"])
        return {"kind": "exit", **trade}

    def finish(self, ts: int, close: float) -> dict | None:
        """Fin de l'historique : la position encore ouverte est vendue à la dernière clôture."""
        if self.s["position"] is None:
            return None
        self.s["pending"] = None
        return self._close(ts, self._fill(close, False), close, "fin du test", self.ex.fee_rate, False, None)


def simulate(df: pd.DataFrame, spec: Spec, capital: float = CAPITAL, ex: ExecutionParams = FUTURES,
             signals: Signals | None = None, explain: bool = False) -> Book:
    """Le backtest d'un bot : chaque bougie passe par le même moteur que le direct (les bougies sans position, sans
    ordre en attente et sans signal sont sautées : il ne s'y passe rien)."""
    sig = signals or signals_for(df, spec.params, spec.side)
    book = Book(spec, capital, ex, explain=explain)
    ts = df["ts"].to_numpy(np.int64)
    o, h, low, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    warm = spec.params.warmup_bars
    entry = sig.entry.copy()
    entry[:max(warm - 1, 0)] = False  # comme en direct : pas de signal avant d'avoir l'historique de chauffe
    for i in range(len(df)):
        if book.idle and not entry[i]:
            continue
        t = int(ts[i])
        book.open_bar(t, float(o[i]))
        book.range_bar(t, float(o[i]), float(h[i]), float(low[i]))
        if i + 1 >= warm:
            book.close_bar(t, float(c[i]), bool(entry[i]), bool(sig.exit[i]), float(sig.atr[i]))
        if book.s["dead"] and book.idle:
            break
    if len(df):
        book.finish(int(ts[-1]), float(c[-1]))
    return book


# --- Le choix des bots -----------------------------------------------------------------------------------------------

def _mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else math.nan


def judge(book: Book, start_ts: int, end_ts: int) -> dict:
    """Une combinaison jugée comme au labo : étude, validation (classement) et test final (jamais regardé pour
    choisir). Rendements par trade sans levier (`net`, frais compris) ; résultat total avec le levier."""
    spec, s = book.spec, book.s
    cut = start_ts + (end_ts - start_ts) * STUDY_SHARE
    test_start = start_ts + (end_ts - start_ts) * (1 - TEST_SHARE)
    parts: dict[str, list[float]] = {"study": [], "valid": [], "test": []}
    gross = []
    for t in s["trades"]:
        part = "study" if t["entry_ts"] < cut else "valid" if t["entry_ts"] < test_start else "test"
        parts[part].append(t["net"])
        gross.append(t["gross"])
    sv = parts["study"] + parts["valid"]
    n = len(sv)
    std = float(np.std(sv, ddof=1)) if n > 1 else math.nan
    mean = _mean(sv)
    score = mean / (std / math.sqrt(n)) if n > 1 and std > 0 else (math.inf if n > 1 and mean > 0 else -math.inf)
    nets = [t["net"] for t in s["trades"]]
    return {
        **asdict(spec), "key": spec.key, "family": spec.family,
        "trades": len(nets), "win_rate": sum(x > 0 for x in nets) / len(nets) if nets else math.nan,
        "mean": _mean(nets), "gross_mean": _mean(gross),
        "study_n": len(parts["study"]), "study_mean": _mean(parts["study"]),
        "valid_n": len(parts["valid"]), "valid_mean": _mean(parts["valid"]),
        "test_n": len(parts["test"]), "test_mean": _mean(parts["test"]),
        "sv_n": n, "sv_mean": mean, "score": score,
        "total_return": s["cash"] / s["start"] - 1, "drawdown": s["drawdown"], "liquidated": s["dead"] == "liquidé",
        "start_ts": int(start_ts), "end_ts": int(end_ts),
    }


def eligible(r: dict, section: Section) -> bool:
    """Gagnante, frais compris, sur l'étude ET sur la validation, avec assez de trades, sans liquidation."""
    return (not r["liquidated"] and r["sv_n"] >= section.min_trades and r["study_n"] >= MIN_PART_TRADES
            and r["valid_n"] >= MIN_PART_TRADES and r["study_mean"] > 0 and r["valid_mean"] > 0)


def label(r: dict, section: Section) -> tuple[str, str]:
    if eligible(r, section) and r["test_n"] >= MIN_TEST_TRADES and r["test_mean"] > 0:
        return "3", "Gagnant sur les 3 périodes du backtest"
    if eligible(r, section):
        return "2", "Gagnant sur l'étude et la validation, pas sur le test final"
    return "essai", "À l'essai : rien de mieux sur cette équipe"


def _rank_key(r: dict) -> float:
    score = r.get("score")
    return -score if isinstance(score, (int, float)) and not math.isnan(score) else math.inf


def tiers(rows: list[dict], section: Section) -> tuple[list[dict], list[dict], list[dict]]:
    """Le classement en trois paliers : gagnantes sur l'étude et la validation ; puis celles qui ont au moins assez de
    trades pour être jugées ; puis le reste (jamais une combinaison liquidée dans le backtest). Dans chaque palier, de
    la plus régulière à la moins régulière (gain moyen rapporté à sa dispersion)."""
    good = sorted((r for r in rows if eligible(r, section)), key=_rank_key)
    keys = {r["key"] for r in good}
    enough = max(5, section.min_trades // 2)
    fair = sorted((r for r in rows if r["key"] not in keys and not r["liquidated"] and r["sv_n"] >= enough),
                  key=_rank_key)
    keys |= {r["key"] for r in fair}
    rest = sorted((r for r in rows if r["key"] not in keys and not r["liquidated"] and r["trades"] > 0), key=_rank_key)
    return good, fair, rest


def choose(rows: list[dict], section: Section, count: int = BOTS_PER_SECTION,
           bench: int = BENCH) -> tuple[list[dict], list[dict]]:
    """Les `count` mieux classées, des cryptos toutes différentes et des techniques variées, puis les remplaçants.
    D'abord celles qui gagnent sur l'étude et la validation ; s'il en manque, les suivantes du classement."""
    good, fair, rest = tiers(rows, section)
    ranked = good + fair + rest
    order = {r["key"]: i for i, r in enumerate(ranked)}
    chosen: list[dict] = []
    taken: set[str] = set()

    def pick(tier: list[dict], ok) -> None:
        for r in tier:
            if len(chosen) >= count:
                return
            if r["key"] not in taken and ok(r):
                chosen.append(r)
                taken.add(r["key"])

    def new_coin(r) -> bool:
        return r["symbol"] not in {c["symbol"] for c in chosen}

    for tier in (good, fair, rest):  # une gagnante passe toujours avant une perdante, même de la même famille
        pick(tier, lambda r: new_coin(r) and (r["family"], r["side"]) not in {(c["family"], c["side"]) for c in chosen})
        pick(tier, new_coin)
    pick(ranked, lambda r: True)
    chosen.sort(key=lambda r: order[r["key"]])
    seen = {(c["symbol"], c["timeframe"], c["technique"], c["side"]) for c in chosen}
    reserve = []
    for r in ranked:
        if len(reserve) >= bench:
            break
        what = (r["symbol"], r["timeframe"], r["technique"], r["side"])
        if r["key"] in taken or what in seen:
            continue  # la même combinaison avec ou sans objectif : un seul des deux
        seen.add(what)
        reserve.append(r)
    return chosen, reserve


def _dataset_job(job: tuple) -> list[dict]:
    """Toutes les techniques, dans les deux sens et avec ou sans objectif, sur une crypto et une unité de temps."""
    section_key, symbol, timeframe, df, techniques, leverage, capital, ex = job
    out = []
    if len(df) < 2:
        return out
    start, end = int(df["ts"].iloc[0]), int(df["ts"].iloc[-1])
    for name in techniques:
        params = technique(name)
        if len(df) < params.warmup_bars + MIN_BARS:
            continue
        for side in SIDES:
            try:
                sig = signals_for(df, params, side)
                for target in TARGETS:
                    spec = Spec(section_key, symbol, timeframe, name, side, target, leverage)
                    out.append(judge(simulate(df, spec, capital, ex, sig), start, end))
            except Exception as exc:  # des bougies étranges sur une crypto n'arrêtent jamais tout le choix
                log.warning("%s %s %s : combinaison ignorée (%s)", symbol, timeframe, name, exc)
    return out


def run_jobs(jobs: list[tuple], workers: int | None = None) -> list[dict]:
    """Chaque (crypto, unité) sur un cœur du processeur si possible ; en série si le parallèle échoue."""
    workers = default_workers() if workers is None else max(1, workers)
    results: list[dict] = []
    if workers > 1 and len(jobs) > 1:
        try:
            with ProcessPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
                futures = [pool.submit(_dataset_job, job) for job in jobs]
                for done, future in enumerate(as_completed(futures), start=1):
                    results += future.result()
                    if done % 10 == 0 or done == len(jobs):
                        log.info("Choix des bots : %d/%d séries calculées (%d cœurs)", done, len(jobs),
                                 min(workers, len(jobs)))
            return results
        except (OSError, RuntimeError, BrokenProcessPool, pickle.PicklingError) as exc:
            log.warning("Calcul en parallèle impossible (%s) : le choix continue sur un seul cœur.", exc)
            results = []
    for done, job in enumerate(jobs, start=1):
        results += _dataset_job(job)
        if done % 10 == 0 or done == len(jobs):
            log.info("Choix des bots : %d/%d séries calculées", done, len(jobs))
    return results


def fleet_universe(exchange, coins: int = 15, hot: int = 10, min_volume: float = 5_000_000) -> list[ScanResult]:
    """Les cryptos du choix : les plus échangées, les plus agitées du moment (celles qui prennent 20 ou 50 % dans la
    journée) et les memecoins assez échangés. Sans monnaies stables ni tokens à levier."""
    liquid = liquid_markets(exchange, "USDT", min_volume)  # de la plus agitée à la plus calme
    chosen = sorted(liquid, key=lambda r: r.volume, reverse=True)[:coins]
    names = {r.symbol for r in chosen}
    for r in liquid:
        if len(chosen) >= coins + hot:
            break
        if r.symbol not in names:
            chosen.append(r)
            names.add(r.symbol)
    chosen += [r for r in liquid if r.symbol in MEMECOINS and r.symbol not in names]
    return chosen


def backtest_view(df: pd.DataFrame, spec: Spec, capital: float, ex: ExecutionParams, points: int = 160) -> dict:
    """Le backtest d'un bot choisi, pour sa page : la courbe de son capital et ses derniers trades."""
    book = simulate(df, spec, capital, ex)
    trades = book.s["trades"]
    curve = [[int(df["ts"].iloc[0]), capital]] + [[t["exit_ts"], t["equity"]] for t in trades]
    if len(curve) > points:
        step = len(curve) / points
        curve = [curve[int(i * step)] for i in range(points)] + [curve[-1]]
    recent = [{k: t[k] for k in ("side", "entry_ts", "exit_ts", "price", "exit_price", "net", "roi", "reason",
                                 "leverage")} for t in trades[-8:]]
    return {"curve": curve, "recent": recent, "first": int(df["ts"].iloc[0]), "last": int(df["ts"].iloc[-1])}


def select(datasets: dict[tuple[str, str, str], pd.DataFrame], settings: FleetSettings = FleetSettings(),
           universe: list[ScanResult] | None = None, ex: ExecutionParams = FUTURES, workers: int | None = None,
           exchange_id: str = "binance") -> dict:
    """`datasets` : (équipe, crypto, unité) -> bougies. Renvoie le choix complet, prêt à être enregistré."""
    jobs = []
    for (section_key, symbol, timeframe), df in datasets.items():
        section = SECTION_KEYS[section_key]
        jobs.append((section_key, symbol, timeframe, df, section.techniques, settings.leverage(section_key),
                     settings.capital, ex))
    rows = run_jobs(jobs, workers)
    sections = []
    for section in SECTIONS:
        mine = [r for r in rows if r["section"] == section.key]
        chosen, bench = choose(mine, section)
        bots = []
        for r in chosen:
            spec = spec_from(r)
            code, text = label(r, section)
            df = datasets[(section.key, spec.symbol, spec.timeframe)]
            bots.append({**r, "label": code, "label_text": text,
                         "backtest": backtest_view(df, spec, settings.capital, ex)})
        top = [r for tier in tiers(mine, section) for r in tier][:25]
        sections.append({
            "key": section.key, "title": section.title, "timeframes": list(section.timeframes),
            "leverage": settings.leverage(section.key), "tested": len(mine),
            "eligible": sum(eligible(r, section) for r in mine),
            "bots": bots, "bench": [{**r, "label": label(r, section)[0], "label_text": label(r, section)[1]}
                                    for r in bench],
            "top": [{k: r[k] for k in ("symbol", "timeframe", "technique", "side", "target_r", "sv_n", "sv_mean",
                                       "test_n", "test_mean", "total_return", "drawdown", "score")}
                    | {"eligible": eligible(r, section)} for r in top],
        })
    date = _iso()
    return {"version": 1, "id": date, "date": date, "exchange": exchange_id, "settings": asdict(settings),
            "execution": asdict(ex), "tested": len(rows),
            "universe": [{"symbol": r.symbol, "volume": r.volume, "amplitude": r.amplitude, "change": r.change}
                         for r in (universe or [])],
            "sections": sections}


def format_selection(selection: dict) -> str:
    lines = [f"{selection['tested']} combinaisons backtestées (technique × sens × objectif × crypto × unité de temps), "
             "frais des contrats à terme compris."]
    n = 0
    for sec in selection["sections"]:
        lines += ["", f"=== {sec['title']} (levier jusqu'à ×{sec['leverage']:g}) : {sec['eligible']} gagnantes sur "
                      f"l'étude et la validation, sur {sec['tested']} essais ==="]
        for b in sec["bots"]:
            n += 1
            test = "—" if not b["test_n"] else f"{100 * b['test_mean']:+.3f} %"
            lines.append(f"Bot {n:>2} · {b['symbol']:<12} {tf_label(b['timeframe']):<7} {b['technique']} · "
                         f"{SIDE_LABELS[b['side']]}{' · objectif 2R' if b['target_r'] else ''}")
            lines.append(f"         {b['sv_n']} trades, {100 * b['sv_mean']:+.3f} % par trade (étude + validation), "
                         f"test final {test} sur {b['test_n']} · {b['label_text']}")
    lines += ["", "Le meilleur de milliers d'essais est souvent chanceux : c'est le direct, en argent fictif, qui tranche."]
    return "\n".join(lines)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=1, default=float, allow_nan=True))


def load_json(path: Path, tries: int = 1) -> dict | None:
    """Un fichier JSON du bot, ou None. Sous Windows, un fichier en train d'être remplacé peut être refusé un instant :
    `tries` lectures, à 50 ms d'intervalle."""
    for attempt in range(max(1, tries)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if attempt + 1 < tries:
                time.sleep(0.05)
    return None


# --- Le direct -------------------------------------------------------------------------------------------------------

def new_bot(r: dict, capital: float, slot: int, now_ms: int) -> dict:
    spec = spec_from(r)
    return {"spec": asdict(spec), "key": spec.key, "label": r.get("label", "essai"),
            "label_text": r.get("label_text", ""), "started": _iso(now_ms),
            "backtest": {k: r.get(k) for k in ("trades", "win_rate", "mean", "gross_mean", "sv_n", "sv_mean",
                                               "study_n", "study_mean", "valid_n", "valid_mean", "test_n",
                                               "test_mean", "total_return", "drawdown", "start_ts", "end_ts")}
            | {"curve": (r.get("backtest") or {}).get("curve") or [], "recent": (r.get("backtest") or {}).get("recent")
               or []},
            "book": Book(spec, capital).s, "reading": None, "closes": [], "signal": None, "last_price": None,
            "slot": slot}


class Fleet:
    """Les bots en direct, en argent fictif : un tour toutes les quelques secondes."""

    def __init__(self, exchange, folder: Path | None, selection: dict, ex: ExecutionParams = FUTURES,
                 clock=time.time, read: bool = True):
        self.exchange, self.folder, self.ex, self.clock, self.read = exchange, folder, ex, clock, read
        self.next_fetch: dict[tuple[str, str], int] = {}
        self.beat_lock = threading.Lock()
        self.selection = selection
        state = load_json(folder / STATE_FILE) if folder else None
        if state and state.get("selection") != selection.get("id"):
            self._archive(state)
            state = None
        self.state = state if state and state.get("version") == 1 else self._fresh()
        self.save()

    def _fresh(self) -> dict:
        now = int(self.clock() * 1000)
        capital = float((self.selection.get("settings") or {}).get("capital") or CAPITAL)
        slots, events, used = [], [], []
        n = 0
        for sec in self.selection.get("sections") or []:
            for r in sec.get("bots") or []:
                n += 1
                try:
                    bot = new_bot(r, capital, n, now)
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning("Bot %d ignoré (%s)", n, exc)
                    bot = None
                slots.append({"slot": n, "section": sec["key"], "bot": bot, "retired": []})
                if bot:
                    used.append(bot["key"])
        events.append({"t": _iso(now), "kind": "depart", "slot": None,
                       "text": f"Départ de {sum(1 for s in slots if s['bot'])} bots, {capital:g} USDT fictifs chacun."})
        return {"version": 1, "selection": self.selection.get("id"), "created": _iso(now), "updated": _iso(now),
                "capital": capital, "slots": slots, "events": events, "used": used}

    def _archive(self, state: dict) -> None:
        """Une nouvelle sélection : l'ancienne équipe est gardée à part, positions closes au dernier prix connu."""
        for slot in state.get("slots") or []:
            bot = slot.get("bot")
            if not bot:
                continue
            try:
                book = Book(spec_from(bot["spec"]), state=bot["book"], ex=self.ex, keep=KEEP_TRADES)
                last = finite(bot.get("last_price"))
                if book.position and last:
                    now = int(self.clock() * 1000)
                    book.s["pending"] = None
                    book._close(max(now, book.position["entry_ts"]), book._fill(last, False), last,
                                "nouvelle sélection", self.ex.fee_rate, False, _iso(now))
            except (KeyError, TypeError, ValueError):
                continue
        if self.folder:
            stamp = str(state.get("selection") or "ancienne").replace(":", "-")[:19]
            save_json(self.folder / f"etat-{stamp}.json", state)

    def bots(self) -> list[tuple[dict, dict, Book]]:
        out = []
        for slot in self.state["slots"]:
            bot = slot.get("bot")
            if bot:
                out.append((slot, bot, Book(spec_from(bot["spec"]), state=bot["book"], ex=self.ex, keep=KEEP_TRADES,
                                            explain=True)))
        return out

    def event(self, kind: str, slot: dict, text: str, **extra) -> dict:
        e = {"t": _iso(self.clock() * 1000), "kind": kind, "slot": slot["slot"], "section": slot["section"],
             "text": text, **extra}
        self.state["events"].append(e)
        del self.state["events"][:-KEEP_EVENTS]
        return e

    def _prices(self, symbols: list[str]) -> dict[str, float]:
        try:
            tickers = self.exchange.fetch_tickers(symbols)
        except ccxt.NetworkError:
            raise  # réseau coupé : le tour est retenté plus tard (inutile d'essayer chaque crypto)
        except Exception as exc:  # une liste refusée (une crypto retirée...) : chaque crypto à part
            log.debug("Prix groupés indisponibles (%s)", exc)
            tickers = {}
            for s in symbols:
                try:
                    tickers[s] = self.exchange.fetch_ticker(s)
                except Exception as exc2:
                    log.debug("%s : prix indisponible (%s)", s, exc2)
        return {s: float(t["last"]) for s, t in tickers.items() if s in symbols and (t or {}).get("last")}

    def cycle(self, now_ms: int | None = None) -> list[dict]:
        """Un tour : les bougies qui viennent de se clôturer (dans l'ordre du temps : stop et objectif sur ce qu'elles
        ont parcouru, puis les signaux), puis le prix du moment pour le stop et l'objectif entre deux bougies."""
        now_ms = int(self.clock() * 1000) if now_ms is None else now_ms
        at = _iso(now_ms)
        bots = self.bots()
        events: list[dict] = []
        prices = self._prices(sorted({b[1]["spec"]["symbol"] for b in bots})) if bots else {}
        groups: dict[tuple[str, str], list] = {}
        for item in bots:
            spec = item[1]["spec"]
            groups.setdefault((spec["symbol"], spec["timeframe"]), []).append(item)
        for (symbol, timeframe), items in groups.items():
            if now_ms < self.next_fetch.get((symbol, timeframe), 0):
                continue
            tf_ms = timeframe_to_ms(timeframe)
            limit = max(lookback_for(b[2].params) for b in items)
            try:
                candles = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit))
            except Exception as exc:  # une crypto qui ne répond pas ne bloque pas les autres
                log.warning("%s %s : bougies indisponibles (%s), nouvel essai dans une minute", symbol, timeframe, exc)
                self.next_fetch[(symbol, timeframe)] = now_ms + RETRY_S * 1000
                continue
            closed = candles[candles["ts"] + tf_ms <= now_ms]
            if closed.empty:
                continue
            self.next_fetch[(symbol, timeframe)] = int(closed["ts"].iloc[-1]) + 2 * tf_ms + 2000
            for slot, bot, book in items:
                try:
                    events += self._on_candles(slot, bot, book, closed, prices.get(symbol), at)
                except Exception as exc:  # un bot qui bute sur ses bougies ne bloque jamais les autres
                    log.warning("Bot %s (%s %s) : bougie non traitée (%s)", slot["slot"], symbol, timeframe, exc)
        for slot, bot, book in bots:  # puis le prix du moment : stop et objectif entre deux bougies
            price = prices.get(bot["spec"]["symbol"])
            if price:
                bot["last_price"] = price
                if book.position:
                    forming = now_ms - now_ms % book.tf_ms
                    events += self._report(slot, bot, book.range_bar(forming, None, price, price, at))
        events += self._replace(now_ms)
        self.state["updated"] = at
        self.save()
        return events

    def _on_candles(self, slot: dict, bot: dict, book: Book, closed: pd.DataFrame, price: float | None,
                    at: str) -> list[dict]:
        last = book.s["last_ts"]
        new = closed[closed["ts"] > last] if last is not None else closed.iloc[-1:]
        if new.empty:
            return []
        events = []
        pos = book.position
        if pos is not None:  # le stop et l'objectif sur les bougies terminées depuis l'achat (prix manqués entre deux tours)
            for row in new[new["ts"] >= pos["entry_ts"]].itertuples():
                events += self._report(slot, bot, book.range_bar(int(row.ts), float(row.open), float(row.high),
                                                                 float(row.low), at))
                if book.position is None:
                    break
        last_row = closed.iloc[-1]
        ts = int(last_row["ts"])
        if len(closed) >= book.params.warmup_bars:
            sig = signals_for(closed, book.params, book.spec.side)
            book.close_bar(ts, float(last_row["close"]), bool(sig.entry[-1]), bool(sig.exit[-1]), float(sig.atr[-1]))
            bot["signal"] = {"ts": ts, "entry": bool(sig.entry[-1]), "exit": bool(sig.exit[-1])}
        else:
            book.s["last_ts"] = ts
        if book.s["pending"]:
            events += self._report(slot, bot, book.open_bar(ts + book.tf_ms, price or float(last_row["close"]), at))
        tail = closed.iloc[-60:]
        bot["closes"] = [[int(t), float(c)] for t, c in zip(tail["ts"], tail["close"])]
        if not self.read:
            return events
        try:
            reading = read_chart(closed, fees=2 * (self.ex.fee_rate + self.ex.slippage))
            bot["reading"] = {k: reading.get(k) for k in ("price", "trend", "ma200", "support", "resistance", "rsi",
                                                         "candle_pct", "change", "volume_ratio", "round_below",
                                                         "round_above")} | {"sentences": reading["sentences"][:9]}
        except Exception as exc:  # une lecture ratée n'empêche pas de trader
            log.debug("Lecture du graphique impossible : %s", exc)
        return events

    def _report(self, slot: dict, bot: dict, results: list[dict]) -> list[dict]:
        out = []
        spec = spec_from(bot["spec"])
        name = f"Bot {slot['slot']}"
        for r in results:
            if r["kind"] == "entry":
                verb = "achète" if r["side"] == "long" else "vend à découvert"
                target = f", objectif {fmt_price(r['target'])}" if r["target"] else ", sortie par sa règle"
                text = (f"{name} {verb} {spec.coin} à {fmt_price(r['price'])}, levier ×{r['leverage']:g} : stop "
                        f"{fmt_price(r['stop'])}{target}. Signal : {condition(spec.params, spec.side)}.")
                out.append(self.event("achat" if r["side"] == "long" else "vente", slot, text, symbol=spec.symbol))
            else:
                text = (f"{name} sort de {spec.coin} à {fmt_price(r['exit_price'])} ({r['reason']}) : "
                        f"{pct(r['roi'])} sur son capital ({pct(r['net'], 2)} sur la position, frais compris).")
                out.append(self.event("sortie", slot, text, symbol=spec.symbol, roi=r["roi"], pnl=r["pnl"]))
        return out

    def retire_reason(self, book: Book) -> str | None:
        s = book.s
        if s["dead"]:
            return s["dead"]
        if s["position"] is not None or s["pending"] is not None:
            return None
        if s["cash"] < s["start"] * (1 - REPLACE_DRAWDOWN):
            return "a perdu plus de la moitié de son capital"
        return elimination_reason(TradeStats.from_dict(s["stats"]), ELIMINATE_AFTER)

    def _replace(self, now_ms: int) -> list[dict]:
        events = []
        capital = float(self.state.get("capital") or CAPITAL)
        for slot in self.state["slots"]:
            bot = slot.get("bot")
            if bot:
                reason = self.retire_reason(Book(spec_from(bot["spec"]), state=bot["book"], ex=self.ex))
                if not reason:
                    continue
                slot["retired"].append({"key": bot["key"], "spec": bot["spec"], "reason": reason, "until": _iso(now_ms),
                                        "started": bot["started"], "start": bot["book"]["start"],
                                        "end": bot["book"]["cash"], "count": bot["book"]["count"],
                                        "wins": bot["book"]["wins"]})
            nxt = self._next(slot)
            if nxt is None:
                if bot:
                    slot["bot"] = None
                    events.append(self.event("remplacement", slot, f"Bot {slot['slot']} ({spec_from(bot['spec']).coin}) "
                                             f"s'arrête : {reason}. Plus de remplaçant : refais le choix des bots."))
                continue
            slot["bot"] = new_bot(nxt, capital, slot["slot"], now_ms)
            self.state["used"].append(slot["bot"]["key"])
            spec = spec_from(nxt)
            old = f"{spec_from(bot['spec']).coin} s'arrête ({reason})" if bot else "était vide"
            events.append(self.event("remplacement", slot, f"Bot {slot['slot']} : {old}. Remplaçant : {spec.coin} en "
                                     f"{tf_label(spec.timeframe)}, {spec.technique}, {SIDE_LABELS[spec.side]}."))
        return events

    def _next(self, slot: dict) -> dict | None:
        """Le remplaçant : le suivant du classement de l'équipe, sur une crypto que l'équipe n'a pas déjà."""
        sec = next((s for s in self.selection.get("sections") or [] if s["key"] == slot["section"]), None)
        if not sec:
            return None
        used = set(self.state["used"])
        symbols = {o["bot"]["spec"]["symbol"] for o in self.state["slots"]
                   if o is not slot and o.get("bot") and o["section"] == slot["section"]}
        for r in sec.get("bench") or []:
            try:
                key = spec_from(r).key
            except (KeyError, TypeError, ValueError):
                continue
            if key not in used and r["symbol"] not in symbols:
                return r
        return None

    def save(self) -> None:
        """L'état sur le disque. Sous Windows, le site peut lire le fichier au même instant : un refus est retenté,
        et sinon le tour suivant l'écrira (l'état reste en mémoire)."""
        if self.folder:
            for attempt in range(3):
                try:
                    save_json(self.folder / STATE_FILE, self.state)
                    break
                except OSError as exc:
                    if attempt == 2:
                        log.debug("État des bots non écrit ce tour-ci : %s", exc)
                    else:
                        time.sleep(0.1)
            self.beat()

    def beat(self) -> None:
        """Le signal de vie : « les bots tournent », pour que personne ne les lance une deuxième fois."""
        if self.folder:
            with self.beat_lock:  # le tour et le fil du signal de vie n'écrivent jamais le fichier en même temps
                try:
                    atomic_write(self.folder / LOCK_FILE, json.dumps({"pid": os.getpid(), "t": self.clock()}))
                except OSError as exc:
                    log.debug("Signal de vie non écrit : %s", exc)

    def release(self) -> None:
        if self.folder:
            try:
                (self.folder / LOCK_FILE).unlink()
            except OSError:
                pass


def fleet_running(folder: Path, clock=time.time) -> bool:
    """Les bots tournent-ils (lancés par le site ou par un lanceur) ? Oui si leur dernier tour est récent."""
    lock = load_json(folder / LOCK_FILE, tries=3)
    return bool(lock) and clock() - float(lock.get("t") or 0) < HEARTBEAT_S


def run(fleet: Fleet, seconds: float = 5.0, once: bool = False, sleep=time.sleep, reload=None,
        reload_every: float = 60.0) -> None:
    """La boucle du direct. `reload()` -> le choix enregistré : s'il a changé, la nouvelle équipe prend la place.
    Réseau coupé : le tour est retenté de plus en plus tard (jusqu'à une minute), sans remplir le journal."""
    checked = fleet.clock()
    failures = 0
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(BEAT_S):
            fleet.beat()

    if not once:
        threading.Thread(target=heartbeat, name="signal-de-vie", daemon=True).start()
    try:
        while True:
            if reload and fleet.clock() - checked >= reload_every:
                checked = fleet.clock()
                try:
                    selection = reload()
                    if selection and selection.get("id") != fleet.selection.get("id"):
                        log.info("Nouveau choix de bots : la nouvelle équipe prend la place de l'ancienne.")
                        fleet._archive(fleet.state)
                        fleet.selection = selection
                        fleet.state = fleet._fresh()
                        fleet.next_fetch.clear()
                except Exception as exc:
                    log.warning("Choix des bots illisible (%s)", exc)
            try:
                for e in fleet.cycle():
                    log.info("%s", e["text"], extra=ALERT if e["kind"] == "remplacement" else None)
                if failures:
                    log.info("Bots : la connexion est revenue, ils reprennent.")
                failures = 0
            except Exception as exc:  # le réseau coupe : on retente plus tard
                failures += 1
                if failures in (1, 5) or failures % 60 == 0:
                    log.warning("Bots : %s (tour %d raté, ils réessaient tout seuls)", exc, failures)
            if once:
                return
            sleep(seconds if not failures else min(60.0, seconds * 2 ** min(failures, 4)))
    finally:
        stop.set()
        fleet.release()


# --- Ce que le site affiche ------------------------------------------------------------------------------------------

def _position_view(book: Book, last: float | None) -> dict | None:
    pos = book.position
    if pos is None:
        return None
    mark = last or pos["entry_mark"]
    equity = book.equity(mark)
    return {**{k: pos[k] for k in ("side", "entry_ts", "entry_mark", "price", "notional", "margin", "leverage", "stop",
                                    "target", "liquidation", "risk", "bars")},
            "entry_at": pos.get("entry_at") or _iso(pos["entry_ts"]), "last": mark,
            "pnl": equity - pos["margin"], "roi": equity / pos["margin"] - 1 if pos["margin"] else None,
            "move": (mark / pos["entry_mark"] - 1) * (1 if pos["side"] == "long" else -1)}


def bot_view(slot: dict, full: bool = False) -> dict:
    bot = slot.get("bot")
    base = {"slot": slot["slot"], "name": f"Bot {slot['slot']}", "section": slot["section"],
            "retired": list(reversed(slot.get("retired") or []))[:5]}
    if not bot:
        return {**base, "empty": True}
    spec = spec_from(bot["spec"])
    book = Book(spec, state=bot["book"])
    s = book.s
    last = finite(bot.get("last_price"))
    value = book.equity(last)
    trades = list(reversed(s["trades"]))
    view = {
        **base, "empty": False, "symbol": spec.symbol, "coin": spec.coin, "timeframe": spec.timeframe,
        "tf_label": tf_label(spec.timeframe), "technique": spec.technique, "family": spec.family, "side": spec.side,
        "side_label": SIDE_LABELS[spec.side], "side_hint": SIDE_HINTS[spec.side], "target_r": spec.target_r,
        "leverage": spec.leverage, "label": bot.get("label"), "label_text": bot.get("label_text"),
        "rule": entry_rule(spec), "exit_rule": exit_rule(spec), "started": bot.get("started"),
        "start": s["start"], "value": value, "pnl": value - s["start"], "pnl_pct": value / s["start"] - 1,
        "count": s["count"], "wins": s["wins"], "win_rate": s["wins"] / s["count"] if s["count"] else None,
        "drawdown": s["drawdown"], "dead": s["dead"], "last_price": last, "position": _position_view(book, last),
        "pending": s["pending"], "signal": bot.get("signal"), "closes": bot.get("closes") or [],
        "trades": trades if full else trades[:3], "backtest": bot.get("backtest") or {},
    }
    if full:
        view["reading"] = bot.get("reading")
    return view


def safe_view(slot: dict, full: bool = False) -> dict:
    """La vue d'un bot ; un bot illisible (technique disparue d'une ancienne version...) devient une place vide."""
    try:
        return bot_view(slot, full)
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Bot %s illisible : %s", slot.get("slot"), exc)
        return {"slot": slot.get("slot"), "name": f"Bot {slot.get('slot')}", "section": slot.get("section"),
                "retired": [], "empty": True}


def fleet_view(selection: dict | None, state: dict | None, running: bool, full_slot: int | None = None) -> dict:
    """Tout ce que montre l'écran « Direct » : les équipes, chaque bot, les totaux, le fil des événements."""
    if not selection:
        return {"ready": False, "running": running}
    out = {"ready": True, "running": running, "selection": {k: selection.get(k) for k in ("id", "date", "tested",
                                                                                          "exchange")},
           "universe": [u.get("symbol") for u in selection.get("universe") or []]}
    slots = (state or {}).get("slots") or []
    current = state and state.get("selection") == selection.get("id")
    sections = []
    for sec in selection.get("sections") or []:
        meta = SECTION_KEYS.get(sec["key"])
        bots = [safe_view(s, full=s["slot"] == full_slot) for s in slots if s["section"] == sec["key"]] if current else []
        sections.append({"key": sec["key"], "title": sec["title"], "timeframes": sec["timeframes"],
                         "tf_labels": [tf_label(t) for t in sec["timeframes"]], "leverage": sec["leverage"],
                         "tested": sec["tested"], "eligible": sec["eligible"], "blurb": meta.blurb if meta else "",
                         "bots": bots, "top": sec.get("top") or []})
    out["sections"] = sections
    views = [b for sec in sections for b in sec["bots"] if not b["empty"]]
    retired = [r for s in slots for r in s.get("retired") or []] if current else []
    start = sum(b["start"] for b in views) + sum(finite(r.get("start")) or 0 for r in retired)
    value = sum(b["value"] for b in views) + sum(finite(r.get("end")) or 0 for r in retired)
    count = sum(b["count"] for b in views) + sum(int(r.get("count") or 0) for r in retired)
    wins = sum(b["wins"] for b in views) + sum(int(r.get("wins") or 0) for r in retired)
    out["totals"] = {"start": start, "value": value, "pnl": value - start, "pnl_pct": value / start - 1 if start else None,
                     "positions": sum(1 for b in views if b["position"]), "bots": len(views), "count": count,
                     "wins": wins, "win_rate": wins / count if count else None, "retired": len(retired),
                     "since": (state or {}).get("created") if current else None,
                     "updated": (state or {}).get("updated") if current else None}
    out["events"] = list(reversed((state or {}).get("events") or []))[:40] if current else []
    if full_slot is not None:
        out["bot"] = next((b for b in views if b["slot"] == full_slot), None)
    return out


def overlays(df: pd.DataFrame, p: StrategyParams, side: str) -> list[dict]:
    """Les lignes que regarde la technique, sur le vrai prix (la version vendeuse lit les mêmes, à l'envers)."""
    close, high, low = df["close"], df["high"], df["low"]
    up = side == "long"
    lines = []

    def add(key, label_, values, color, dash=False):
        lines.append({"key": key, "label": label_, "color": color, "dash": dash,
                      "values": [None if not math.isfinite(v) else float(v) for v in values.tolist()]})

    t = p.strategy_type
    if t in ("bollinger", "bollinger_cassure") or p.squeeze_quantile:
        mid, upper, lower = bollinger(close, p.bb_period, p.bb_std)
        add("bb-mid", f"milieu des bandes de Bollinger ({p.bb_period} bougies)", mid, "var(--series-1)")
        add("bb-up", "bande haute", upper, "var(--series-1)", True)
        add("bb-low", "bande basse", lower, "var(--series-1)", True)
    if t == "retour_moyenne":
        add("exit-ma", f"moyenne {p.exit_period} (sortie)", sma(close, p.exit_period), "var(--series-4)")
    if t == "cassure":
        hi_n = high.rolling(p.breakout_period).max().shift(1)
        lo_n = low.rolling(p.breakout_period).min().shift(1)
        hi_m = high.rolling(p.breakout_exit_period).max().shift(1)
        lo_m = low.rolling(p.breakout_exit_period).min().shift(1)
        if up:
            add("in", f"plus haut des {p.breakout_period} bougies (entrée)", hi_n, "var(--series-1)")
            add("out", f"plus bas des {p.breakout_exit_period} bougies (sortie)", lo_m, "var(--series-4)", True)
        else:
            add("in", f"plus bas des {p.breakout_period} bougies (entrée)", lo_n, "var(--series-1)")
            add("out", f"plus haut des {p.breakout_exit_period} bougies (sortie)", hi_m, "var(--series-4)", True)
    if t == "impulsion":
        exit_line = (low.rolling(p.breakout_exit_period).min().shift(1) if up else
                     high.rolling(p.breakout_exit_period).max().shift(1))
        add("out", f"{'plus bas' if up else 'plus haut'} des {p.breakout_exit_period} bougies (sortie)", exit_line,
            "var(--series-4)", True)
    if t == "croisement":
        if p.fast_period > 1:
            add("fast", f"moyenne {p.fast_period}", sma(close, p.fast_period), "var(--series-1)")
        add("slow", f"moyenne {p.slow_period}", sma(close, p.slow_period), "var(--series-4)")
    if t == "momentum":
        add("ref", f"prix d'il y a {p.momentum_period} bougies", close.shift(p.momentum_period), "var(--series-4)")
    if t == "supertrend":
        add("st", "ligne du Supertrend", supertrend_line(df, p.st_period, p.st_mult), "var(--series-4)")
    if t == "macd":
        add("ma50", "moyenne 50 (repère)", sma(close, 50), "var(--series-1)")
    if p.trend_period:
        add("trend", f"moyenne {p.trend_period} (filtre de tendance)", sma(close, p.trend_period), "var(--series-7)")
    return lines


def chart_view(df: pd.DataFrame, slot: dict, ex: ExecutionParams = FUTURES, shown: int = 150) -> dict:
    """Le graphique d'un bot : bougies, lignes de sa technique, supports et résistances, ses vrais trades, ce que sa
    règle aurait fait sur ces mêmes bougies, et sa position avec stop, objectif et liquidation."""
    bot = slot.get("bot")
    if not bot:
        raise ValueError("Ce bot n'est plus en service.")
    spec = spec_from(bot["spec"])
    p = spec.params
    if len(df) < 30:
        raise ValueError("Pas assez d'historique pour ce graphique.")
    window = df.iloc[-shown:]
    first = int(window["ts"].iloc[0])
    reading = read_chart(df, fees=2 * (ex.fee_rate + ex.slippage))
    last = float(df["close"].iloc[-1])
    levels = [{**z, "kind": "support" if z["price"] < last else "resistance"}
              for z in reading.pop("levels") if z["touches"] >= 2]
    rule = []
    if len(df) > p.warmup_bars + 2:
        sim = simulate(df, spec, CAPITAL, ex)
        rule = [{"side": t["side"], "entry": t["entry_ts"], "exit": t["exit_ts"], "net": t["net"],
                 "reason": t["reason"], "entry_price": t["price"], "exit_price": t["exit_price"]}
                for t in sim.s["trades"] if t["exit_ts"] >= first and t["reason"] != "fin du test"]
        open_now = sim.position
    else:
        open_now = None
    signal = None
    if len(df) >= p.warmup_bars:
        sig = signals_for(df, p, spec.side)
        signal = {"entry": bool(sig.entry[-1]), "exit": bool(sig.exit[-1])}
    trades = [{"side": t["side"], "entry": t["entry_ts"], "exit": t["exit_ts"], "net": t["net"], "roi": t["roi"],
               "reason": t["reason"], "entry_price": t["price"], "exit_price": t["exit_price"]}
              for t in bot["book"]["trades"] if t["exit_ts"] >= first]
    book = Book(spec, state=bot["book"])
    return {"slot": slot["slot"], "symbol": spec.symbol, "timeframe": spec.timeframe, "last": last,
            "candles": window[["ts", "open", "high", "low", "close", "volume"]].values.tolist(),
            "lines": [{**ln, "values": ln["values"][-len(window):]} for ln in overlays(df, p, spec.side)],
            "levels": levels, "reading": reading, "rule_trades": rule, "rule_open": bool(open_now),
            "trades": trades, "position": _position_view(book, finite(bot.get("last_price")) or last),
            "signal": signal, "side": spec.side}
