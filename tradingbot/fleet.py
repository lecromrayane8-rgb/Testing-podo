"""Le moteur des bots en argent fictif, commun au backtest et au direct (l'essaim de tradingbot/swarm.py s'en sert).

Un bot, c'est une crypto, une technique, une unité de temps, un sens et un objectif :
- le sens : acheteur (il gagne si le prix monte) ou vendeur à découvert (il gagne si le prix baisse). Chaque technique
  existe dans les deux sens : la version vendeuse applique la même règle au graphique retourné (un sommet y devient un
  creux, une résistance un support) ;
- l'objectif (take-profit) : sans objectif, le bot sort par sa règle ; avec, il encaisse aussi dès que le prix a
  parcouru 2 fois la distance de son stop ;
- tout son capital à chaque trade, avec le levier de son horizon. Pour un trade dont le stop est loin, le levier est
  réduit : le stop passe toujours avant le prix de liquidation.

`Book` : le compte d'un bot, bougie par bougie, avec les frais des contrats à terme et le financement ; le backtest
(`simulate`) et le direct appellent les mêmes méthodes dans le même ordre (tests de parité). `judge` coupe l'historique
comme le labo : étude (première moitié), validation (jusqu'à 80 %), test final (le plus récent). Les textes
(`condition`, `entry_rule`, `exit_rule`) disent chaque règle en mots simples, dans les deux sens ; `overlays` et
`chart_view` dessinent ce que regarde une technique.

Argent fictif seulement : rien ne part jamais sur une plateforme. Le bot en argent réel reste au comptant et sans levier.
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .broker import atomic_write
from .data import timeframe_to_ms
from .execution import FUTURES, ExecutionParams
from .explain import decimal, diagnose, pct, read_chart
from .indicators import atr, bollinger, ema, ichimoku, parabolic_sar, rolling_vwap, sma, supertrend_line
from .lab import ALL_VARIANTS, JUMP, STUDY_SHARE, TEST_SHARE
from .risk import TradeStats
from .strategy import StrategyParams, compute_signals, exit_reason

log = logging.getLogger(__name__)

FLEET_DIR = "bots"  # data/bots
LOCK_FILE = "en-cours.json"
CAPITAL = 1000.0
MAINTENANCE = 0.005  # marge de maintenance : 0,5 % de la position
LIQ_SAFETY = 0.9  # le stop reste à moins de 90 % de la distance de liquidation
MIN_NOTIONAL = 10.0  # en dessous, plus de trade possible (une plateforme refuserait un si petit ordre)
TARGET_R = 2.0  # l'objectif : 2 fois la distance du stop
TARGETS = (0.0, TARGET_R)
# La gestion du stop pendant le trade : fixe ; suiveur (il monte avec le meilleur prix atteint, à la distance du
# départ) ; sécurisé (dès que le trade a gagné une fois sa distance de stop, le stop passe au prix d'entrée, frais
# compris). Décidée à la clôture de chaque bougie, elle compte dès la suivante : identique en backtest et en direct.
STOP_MODES = ("fixe", "suiveur", "securise")
STOP_LABELS = {"fixe": "stop fixe", "suiveur": "stop suiveur", "securise": "stop sécurisé"}
# Les façons de sortir testées pour chaque technique et chaque sens : (objectif, gestion du stop).
EXITS = ((0.0, "fixe"), (TARGET_R, "fixe"), (0.0, "suiveur"), (TARGET_R, "securise"))
MIN_BARS = 300  # bougies au-delà de la chauffe pour juger une combinaison
MIN_PART_TRADES = 3  # trades minimum dans l'étude et dans la validation
MIN_TEST_TRADES = 5
HEARTBEAT_S = 45  # au-delà, un autre lancement considère que les bots ne tournent plus
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


# --- Les techniques ------------------------------------------------------------------------------------------------

# Une impulsion à l'échelle du long terme (comme une crypto qui prend 8 % en une journée de bougies de 4 h) : seuil rond
# fixé d'avance, pas ajusté sur les données.
_TREND = {"stop_atr_mult": 3.0, "max_bars_in_trade": 0}  # suivre une tendance : stop large, pas de stop temporel
_SWING = {"stop_atr_mult": 2.5, "max_bars_in_trade": 24}  # acheter un repli : stop plus serré, 24 bougies au plus
EXTRA: dict[str, StrategyParams] = {
    "Impulsion +8 % en 6 bougies + volume x2": StrategyParams(impulse_bars=6, impulse_pct=0.08, volume_mult=2.0,
                                                              **JUMP),
    # Les outils de traders ajoutés pour l'essaim (réglages classiques, fixés d'avance) : les plus cités sur les sites
    # de trading et les réseaux sociaux (EMA 9/21, VWAP, stochastique, Heikin-Ashi...), jugés par le test en direct.
    "EMA 9/21": StrategyParams(strategy_type="ema_croisement", trend_period=0, **_TREND),
    "EMA 9/21 + MM200": StrategyParams(strategy_type="ema_croisement", **_TREND),
    "EMA 20/50": StrategyParams(strategy_type="ema_croisement", ema_fast=20, ema_slow=50, trend_period=0, **_TREND),
    "VWAP + EMA 9/21": StrategyParams(strategy_type="vwap", trend_period=0, stop_atr_mult=2.0, max_bars_in_trade=0),
    "Stochastique 14/3": StrategyParams(strategy_type="stochastique", trend_period=0, **_SWING),
    "Stochastique 14/3 + MM200": StrategyParams(strategy_type="stochastique", **_SWING),
    "Keltner 20/2": StrategyParams(strategy_type="keltner", trend_period=0, **_TREND),
    "ADX 14 > 25": StrategyParams(strategy_type="adx", trend_period=0, **_TREND),
    "Parabolic SAR": StrategyParams(strategy_type="psar", trend_period=0, **_TREND),
    "Ichimoku 9/26/52": StrategyParams(strategy_type="ichimoku", trend_period=0, **_TREND),
    "Écart à la moyenne 20/2": StrategyParams(strategy_type="zscore", trend_period=0, **_SWING),
    "Écart à la moyenne 20/2 + MM200": StrategyParams(strategy_type="zscore", **_SWING),
    "Heikin-Ashi 2 bougies": StrategyParams(strategy_type="heikin", trend_period=0, **_TREND),
    "Heikin-Ashi 3 bougies + MM200": StrategyParams(strategy_type="heikin", heikin_bars=3, **_TREND),
}


def technique(name: str) -> StrategyParams:
    """Les réglages d'une technique, par son nom (ceux du labo, ou les outils ajoutés pour l'essaim)."""
    return EXTRA[name] if name in EXTRA else ALL_VARIANTS[name]


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
    stop_mode: str = "fixe"  # fixe, suiveur ou securise (STOP_MODES)

    def __post_init__(self):
        if self.side not in SIDES:
            raise ValueError(f"Sens inconnu : {self.side!r}")
        if self.stop_mode not in STOP_MODES:
            raise ValueError(f"Gestion du stop inconnue : {self.stop_mode!r}")

    @property
    def params(self) -> StrategyParams:
        return technique(self.technique)

    @property
    def key(self) -> str:
        base = f"{self.symbol}|{self.timeframe}|{self.technique}|{self.side}|{self.target_r:g}"
        return base if self.stop_mode == "fixe" else f"{base}|{self.stop_mode}"  # les bots d'avant gardent leur nom

    @property
    def family(self) -> str:
        return self.params.strategy_type

    @property
    def coin(self) -> str:
        return self.symbol.split("/")[0]


def spec_from(d: dict) -> Spec:
    return Spec(**{k: d[k] for k in ("section", "symbol", "timeframe", "technique", "side", "target_r", "leverage")},
                stop_mode=d.get("stop_mode") or "fixe")


# --- Les règles en mots ----------------------------------------------------------------------------------------------

SIDE_LABELS = {"long": "acheteur", "short": "vendeur à découvert"}
SIDE_HINTS = {"long": "il gagne si le prix monte", "short": "il gagne si le prix baisse"}
SHORT_REASONS = {"rebond": "rechute", "résistance ou support cassé": "support ou résistance cassée",
                 "retour sous le niveau": "retour au-dessus du niveau", "suracheté": "survendu"}


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
    elif t == "ema_croisement":
        text = (f"la moyenne exponentielle {p.ema_fast} passe {'au-dessus de' if up else 'sous'} la {p.ema_slow} (la "
                f"tendance tourne à la {'hausse' if up else 'baisse'})")
    elif t == "vwap":
        text = (f"le prix repasse {'au-dessus de' if up else 'sous'} son VWAP ({p.vwap_period} bougies), avec la moyenne "
                f"exponentielle {p.ema_fast} {'au-dessus de' if up else 'sous'} la {p.ema_slow}")
    elif t == "stochastique":
        text = (f"le stochastique sort de la survente (sous {p.stoch_low:g}) en croisant sa moyenne par le haut" if up else
                f"le stochastique sort du surachat (au-dessus de {100 - p.stoch_low:g}) en croisant sa moyenne par le bas")
    elif t == "keltner":
        text = (f"le prix clôture {'au-dessus' if up else 'en dessous'} du canal de Keltner (à "
                f"{decimal(p.keltner_mult)} fois la taille moyenne d'une bougie de sa moyenne)")
    elif t == "adx":
        text = (f"le {'DI+ passe devant le DI−' if up else 'DI− passe devant le DI+'}, avec une tendance forte (ADX au-dessus "
                f"de {p.adx_min:g})")
    elif t == "psar":
        text = f"le Parabolic SAR passe {'sous' if up else 'au-dessus du'} prix"
    elif t == "ichimoku":
        text = (f"le prix passe {'au-dessus' if up else 'en dessous'} du nuage d'Ichimoku, avec la Tenkan "
                f"{'au-dessus de' if up else 'sous'} la Kijun")
    elif t == "zscore":
        text = (f"le prix tombe à plus de {decimal(p.zscore_entry)} écarts-types {'sous' if up else 'au-dessus de'} sa "
                f"moyenne des {p.zscore_period} bougies (un retour vers la moyenne est attendu)")
    elif t == "heikin":
        text = (f"les bougies Heikin-Ashi (lissées) deviennent {'vertes' if up else 'rouges'} {p.heikin_bars} fois de "
                "suite")
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
    if t == "ema_croisement":
        return f"la moyenne exponentielle {p.ema_fast} repasse {'sous' if up else 'au-dessus de'} la {p.ema_slow}"
    if t == "vwap":
        return f"le prix repasse {'sous' if up else 'au-dessus de'} son VWAP"
    if t == "stochastique":
        return (f"le stochastique dépasse {p.stoch_high:g} (suracheté)" if up else
                f"le stochastique tombe sous {100 - p.stoch_high:g} (survendu)")
    if t == "keltner":
        return f"le prix repasse {'sous' if up else 'au-dessus de'} la moyenne du canal de Keltner"
    if t == "adx":
        return f"le {'DI− repasse devant le DI+' if up else 'DI+ repasse devant le DI−'}"
    if t == "psar":
        return f"le Parabolic SAR repasse {'au-dessus du' if up else 'sous le'} prix"
    if t == "ichimoku":
        return f"le prix repasse {'sous' if up else 'au-dessus de'} la Kijun"
    if t == "zscore":
        return "le prix revient sur sa moyenne"
    if t == "heikin":
        return f"une bougie Heikin-Ashi {'rouge' if up else 'verte'} apparaît"
    return ("le prix retombe sous l'ancienne résistance" if up else "le prix remonte au-dessus de l'ancien support")


def entry_rule(spec: Spec) -> str:
    return f"Il {'achète' if spec.side == 'long' else 'vend à découvert'} quand {condition(spec.params, spec.side)}."


def exit_rule(spec: Spec) -> str:
    p = spec.params
    target = (f", à son objectif ({decimal(spec.target_r, 0)} fois la distance du stop, dans l'autre sens)"
              if spec.target_r else "")
    timer = f", et au plus tard après {p.max_bars_in_trade} bougies" if p.max_bars_in_trade else ""
    up = spec.side == "long"
    moves = {"fixe": "",
             "suiveur": f" Son stop est suiveur : à chaque clôture, il {'monte' if up else 'descend'} pour rester à la "
                        f"même distance du {'plus haut' if up else 'plus bas'} atteint depuis l'entrée (il ne recule "
                        "jamais).",
             "securise": " Son stop est sécurisé : dès que le trade a gagné une fois la distance de son stop, le stop "
                         "passe au prix d'entrée, frais compris, et le trade ne peut presque plus perdre."}[spec.stop_mode]
    return (f"Il sort à son stop (à {decimal(p.stop_atr_mult)} fois la taille moyenne d'une bougie de son prix "
            f"d'entrée){target}, ou quand {exit_condition(p, spec.side)}{timer}.{moves}")


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
        stop = price - distance if long else price + distance
        pos = {"side": self.spec.side, "entry_ts": int(ts), "entry_mark": mark, "price": price, "qty": notional / price,
               "notional": notional, "margin": margin, "leverage": leverage, "fee": fee, "stop": stop, "stop0": stop,
               "distance": distance, "target": target, "liquidation": liquidation, "risk": risk,
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
            reason = "stop" if not pos.get("moved") else \
                "stop suiveur" if self.spec.stop_mode == "suiveur" else "stop sécurisé"
            return [self._close(ts, self._fill(mark, False), mark, reason, self.ex.fee_rate, True, at)]
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
            self._move_stop(pos)
            self._mark(self.equity(close))
            reason = exit_reason(bool(exit_), pos["bars"], self.params)
            if reason:
                s["pending"] = {"kind": "exit", "reason": reason_label(reason, self.spec.side)}
        elif not s["dead"] and entry and math.isfinite(atr_value) and atr_value > 0:
            s["pending"] = {"kind": "entry", "atr": float(atr_value), "signal_ts": int(ts)}

    def _move_stop(self, pos: dict) -> None:
        """Le stop suiveur ou sécurisé, décidé à la clôture avec le meilleur prix atteint (plus haut ou plus bas des
        bougies terminées) : il compte dès la bougie suivante, et ne recule jamais."""
        mode = self.spec.stop_mode
        if mode == "fixe":
            return
        long = pos["side"] == "long"
        distance = pos.get("distance") or abs(pos["price"] - pos.get("stop0", pos["stop"]))
        best = pos["high"] if long else pos["low"]
        if mode == "suiveur":
            new = best - distance if long else best + distance
        else:
            if (best - pos["entry_mark"] if long else pos["entry_mark"] - best) < distance:
                return
            cost = 2 * self.ex.fee_rate + self.ex.slippage  # au prix d'entrée, frais d'un aller-retour compris
            new = pos["price"] * (1 + cost) if long else pos["price"] * (1 - cost)
        if (new > pos["stop"]) if long else (new < pos["stop"]):
            pos["stop"] = new
            pos["moved"] = int(pos.get("moved") or 0) + 1

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
        trade["stop0"] = pos.get("stop0", pos["stop"])  # le stop du départ (le stop suiveur ou sécurisé a pu bouger)
        trade.update(
            exit_ts=int(ts), exit_mark=mark, exit_price=fill, reason=reason, pnl=pnl, net=net, roi=pnl / pos["margin"],
            gross=(mark / pos["entry_mark"] - 1) * (1 if long else -1), fees=fees / pos["notional"], funding=funding,
            mfe=pos["high"] / pos["entry_mark"] - 1 if long else 1 - pos["low"] / pos["entry_mark"],
            mae=pos["low"] / pos["entry_mark"] - 1 if long else 1 - pos["high"] / pos["entry_mark"],
            bars=int(pos["bars"] + (1 if during else 0)), equity=s["cash"])
        if pos.get("entry_at"):
            trade["entry_at"] = pos["entry_at"]
        if pos.get("context"):
            trade["context"] = pos["context"]  # ce que montrait le graphique au signal (l'analyse du trade s'en sert)
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

def fleet_running(folder: Path, clock=time.time) -> bool:
    """Les bots tournent-ils (lancés par le site ou par un lanceur) ? Oui si leur dernier tour est récent."""
    lock = load_json(folder / LOCK_FILE, tries=3)
    return bool(lock) and clock() - float(lock.get("t") or 0) < HEARTBEAT_S


# --- Ce que le site affiche ------------------------------------------------------------------------------------------

def _position_view(book: Book, last: float | None) -> dict | None:
    pos = book.position
    if pos is None:
        return None
    mark = last or pos["entry_mark"]
    equity = book.equity(mark)
    return {**{k: pos[k] for k in ("side", "entry_ts", "entry_mark", "price", "notional", "margin", "leverage", "stop",
                                    "target", "liquidation", "risk", "bars")},
            "stop0": pos.get("stop0", pos["stop"]), "moved": int(pos.get("moved") or 0),
            "stop_mode": book.spec.stop_mode,
            "entry_at": pos.get("entry_at") or _iso(pos["entry_ts"]), "last": mark,
            "pnl": equity - pos["margin"], "roi": equity / pos["margin"] - 1 if pos["margin"] else None,
            "move": (mark / pos["entry_mark"] - 1) * (1 if pos["side"] == "long" else -1)}


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
    if t in ("ema_croisement", "vwap"):
        add("ema-fast", f"moyenne exponentielle {p.ema_fast}", ema(close, p.ema_fast), "var(--series-1)")
        add("ema-slow", f"moyenne exponentielle {p.ema_slow}", ema(close, p.ema_slow), "var(--series-4)")
    if t == "vwap":
        add("vwap", f"VWAP ({p.vwap_period} bougies)", rolling_vwap(df, p.vwap_period), "var(--series-5)")
    if t == "keltner":
        mid = ema(close, p.keltner_period)
        band = p.keltner_mult * atr(df, p.keltner_period)
        add("kc-mid", "milieu du canal de Keltner", mid, "var(--series-1)")
        add("kc-up", "haut du canal", mid + band, "var(--series-1)", True)
        add("kc-low", "bas du canal", mid - band, "var(--series-1)", True)
    if t == "psar":
        add("psar", "Parabolic SAR", parabolic_sar(df, p.psar_step, p.psar_max)[0], "var(--series-4)", True)
    if t == "ichimoku":
        tenkan, kijun, span_a, span_b = ichimoku(df, p.ichi_tenkan, p.ichi_kijun, p.ichi_senkou)
        add("tenkan", "Tenkan", tenkan, "var(--series-1)")
        add("kijun", "Kijun", kijun, "var(--series-4)")
        add("span-a", "nuage (bord A)", span_a, "var(--series-3)", True)
        add("span-b", "nuage (bord B)", span_b, "var(--series-2)", True)
    if t == "zscore":
        mean = sma(close, p.zscore_period)
        spread = close.rolling(p.zscore_period, min_periods=p.zscore_period).std(ddof=0)
        add("z-mid", f"moyenne {p.zscore_period}", mean, "var(--series-1)")
        add("z-low", f"moyenne − {decimal(p.zscore_entry)} écarts-types", mean - p.zscore_entry * spread, "var(--series-1)",
            True)
        add("z-up", f"moyenne + {decimal(p.zscore_entry)} écarts-types", mean + p.zscore_entry * spread, "var(--series-1)",
            True)
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
