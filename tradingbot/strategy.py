"""Stratégies : huit familles de règles, avec les mêmes signaux en backtest et en direct.

Acheter un repli (retour à la moyenne) :
- retour_moyenne : RSI court survendu dans une tendance haussière ; revend au rebond
  (clôture au-dessus d'une moyenne courte).
- bollinger : clôture sous la bande basse de Bollinger ; revend au retour sur la bande du milieu.

Suivre une tendance :
- cassure : clôture au-dessus du plus haut des N bougies précédentes ; revend sous le plus bas des M.
- bollinger_cassure : clôture au-dessus de la bande haute ; revend sous la bande du milieu.
- croisement : la moyenne rapide croise la lente par le haut ; revend au croisement inverse.
- macd : la ligne MACD croise sa ligne de signal par le haut ; revend au croisement inverse.
- momentum : le prix repasse au-dessus de son niveau d'il y a N bougies ; revend quand il retombe dessous.
- supertrend : la tendance Supertrend devient haussière ; revend quand elle redevient baissière.

Pour toutes : stop-loss à k × ATR sous le prix d'achat, stop temporel optionnel (0 = aucun),
filtre de tendance optionnel (clôture au-dessus de la moyenne longue, 0 = aucun filtre).
Les signaux d'une bougie n'utilisent que cette bougie et les précédentes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import atr, bollinger, macd, rsi, sma, supertrend

STRATEGY_TYPES = (
    "retour_moyenne", "bollinger", "cassure", "bollinger_cassure", "croisement", "macd", "momentum", "supertrend",
)
MEAN_REVERSION = ("retour_moyenne", "bollinger")


@dataclass(frozen=True)
class StrategyParams:
    strategy_type: str = "retour_moyenne"
    trend_period: int = 200  # filtre de tendance ; 0 = sans filtre
    rsi_period: int = 2
    rsi_entry: float = 10.0
    exit_period: int = 5
    bb_period: int = 20
    bb_std: float = 2.0
    breakout_period: int = 20
    breakout_exit_period: int = 10
    fast_period: int = 20
    slow_period: int = 100
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    momentum_period: int = 100
    st_period: int = 10
    st_mult: float = 3.0
    atr_period: int = 14
    stop_atr_mult: float = 2.5
    max_bars_in_trade: int = 24  # 0 = pas de stop temporel

    def __post_init__(self):
        if self.strategy_type not in STRATEGY_TYPES:
            raise ValueError(
                f"STRATEGY_TYPE doit valoir {', '.join(STRATEGY_TYPES)} (reçu : {self.strategy_type!r})"
            )
        if self.strategy_type == "croisement" and self.fast_period >= self.slow_period:
            raise ValueError("FAST_PERIOD doit être plus petit que SLOW_PERIOD")
        if self.strategy_type == "macd" and self.macd_fast >= self.macd_slow:
            raise ValueError("MACD_FAST doit être plus petit que MACD_SLOW")
        if self.stop_atr_mult <= 0 or self.bb_std <= 0 or self.st_mult <= 0:
            raise ValueError("STOP_ATR_MULT, BB_STD et ST_MULT doivent être positifs")
        if self.trend_period < 0 or self.max_bars_in_trade < 0:
            raise ValueError("TREND_PERIOD et MAX_BARS_IN_TRADE doivent être >= 0")

    @property
    def warmup_bars(self) -> int:
        periods = {
            "retour_moyenne": [self.rsi_period, self.exit_period],
            "bollinger": [self.bb_period],
            "bollinger_cassure": [self.bb_period],
            "cassure": [self.breakout_period + 1, self.breakout_exit_period + 1],
            "croisement": [self.slow_period + 1],
            "macd": [self.macd_slow + self.macd_signal + 1],
            "momentum": [self.momentum_period + 2],
            "supertrend": [self.st_period + 2],
        }[self.strategy_type]
        return max([self.atr_period, self.trend_period, *periods]) + 1

    @property
    def exit_label(self) -> str:
        return "rebond" if self.strategy_type in MEAN_REVERSION else "fin de tendance"


def _crossing_up(condition: pd.Series) -> pd.Series:
    """Vrai seulement à la bougie où la condition devient vraie."""
    return condition & ~condition.shift(1, fill_value=False)


def compute_signals(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    """Ajoute `atr`, `entry` (signal d'achat) et `exit` (signal de sortie) à chaque bougie."""
    out = df.copy()
    close = out["close"]
    out["atr"] = atr(out, p.atr_period)
    trend_ok = close > sma(close, p.trend_period) if p.trend_period else pd.Series(True, index=out.index)
    t = p.strategy_type
    if t == "retour_moyenne":
        out["rsi"] = rsi(close, p.rsi_period)
        entry = out["rsi"] < p.rsi_entry
        exit_ = close > sma(close, p.exit_period)
    elif t in ("bollinger", "bollinger_cassure"):
        mid, upper, lower = bollinger(close, p.bb_period, p.bb_std)
        entry = close < lower if t == "bollinger" else close > upper
        exit_ = close > mid if t == "bollinger" else close < mid
    elif t == "cassure":
        # Plus haut / plus bas des bougies PRÉCÉDENTES (shift) : pas de regard vers le futur.
        upper = out["high"].rolling(p.breakout_period, min_periods=p.breakout_period).max().shift(1)
        lower = out["low"].rolling(p.breakout_exit_period, min_periods=p.breakout_exit_period).min().shift(1)
        entry = close > upper
        exit_ = close < lower
    elif t == "croisement":
        fast, slow = sma(close, p.fast_period), sma(close, p.slow_period)
        entry = _crossing_up(fast > slow)
        exit_ = fast < slow
    elif t == "macd":
        line, signal = macd(close, p.macd_fast, p.macd_slow, p.macd_signal)
        entry = _crossing_up(line > signal)
        exit_ = line < signal
    elif t == "momentum":
        change = close / close.shift(p.momentum_period) - 1
        entry = _crossing_up(change > 0)
        exit_ = change < 0
    else:
        up = supertrend(out, p.st_period, p.st_mult)
        entry = _crossing_up(up)
        exit_ = ~up
    valid = out["atr"].notna() & (out["atr"] > 0)
    out["entry"] = (entry & trend_ok & valid).fillna(False).astype(bool)
    out["exit"] = exit_.fillna(False).astype(bool)
    return out


def exit_reason(exit_signal: bool, bars_held: int, p: StrategyParams) -> str | None:
    if exit_signal:
        return p.exit_label
    if p.max_bars_in_trade and bars_held >= p.max_bars_in_trade:
        return "temps"
    return None


def initial_stop(entry_price: float, atr_value: float, p: StrategyParams) -> float:
    return entry_price - p.stop_atr_mult * atr_value
