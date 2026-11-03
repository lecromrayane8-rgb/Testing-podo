"""Stratégies : trois familles de règles, avec les mêmes signaux en backtest et en direct.

- retour_moyenne : achète un repli marqué (RSI court survendu) dans une tendance haussière,
  revend au rebond (clôture au-dessus d'une moyenne courte). Beaucoup de petits gains.
- cassure : suivi de tendance. Achète quand la clôture dépasse le plus haut des N bougies
  précédentes, revend quand elle passe sous le plus bas des M précédentes. Peu de gagnants,
  mais de gros gains quand une tendance s'installe.
- croisement : suivi de tendance. Achète quand la moyenne rapide croise la lente par le haut,
  revend au croisement inverse.

Pour toutes : stop-loss à k × ATR sous le prix d'achat, stop temporel optionnel (0 = aucun),
filtre de tendance optionnel (clôture au-dessus de la moyenne longue, 0 = aucun filtre).
Les signaux d'une bougie n'utilisent que cette bougie et les précédentes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import atr, rsi, sma

STRATEGY_TYPES = ("retour_moyenne", "cassure", "croisement")
EXIT_LABELS = {"retour_moyenne": "rebond", "cassure": "fin de tendance", "croisement": "fin de tendance"}


@dataclass(frozen=True)
class StrategyParams:
    strategy_type: str = "retour_moyenne"
    trend_period: int = 200  # filtre de tendance ; 0 = sans filtre
    rsi_period: int = 2
    rsi_entry: float = 10.0
    exit_period: int = 5
    breakout_period: int = 20
    breakout_exit_period: int = 10
    fast_period: int = 20
    slow_period: int = 100
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
        if self.stop_atr_mult <= 0 or self.trend_period < 0 or self.max_bars_in_trade < 0:
            raise ValueError("STOP_ATR_MULT doit être positif, TREND_PERIOD et MAX_BARS_IN_TRADE >= 0")

    @property
    def warmup_bars(self) -> int:
        periods = [self.atr_period, self.trend_period]
        if self.strategy_type == "retour_moyenne":
            periods += [self.rsi_period, self.exit_period]
        elif self.strategy_type == "cassure":
            periods += [self.breakout_period + 1, self.breakout_exit_period + 1]
        else:
            periods += [self.slow_period + 1]
        return max(periods) + 1

    @property
    def exit_label(self) -> str:
        return EXIT_LABELS[self.strategy_type]


def compute_signals(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    """Ajoute `atr`, `entry` (signal d'achat) et `exit` (signal de sortie) à chaque bougie."""
    out = df.copy()
    close = out["close"]
    out["atr"] = atr(out, p.atr_period)
    trend_ok = close > sma(close, p.trend_period) if p.trend_period else pd.Series(True, index=out.index)
    if p.strategy_type == "retour_moyenne":
        out["rsi"] = rsi(close, p.rsi_period)
        entry = trend_ok & (out["rsi"] < p.rsi_entry)
        exit_ = close > sma(close, p.exit_period)
    elif p.strategy_type == "cassure":
        # Plus haut / plus bas des bougies PRÉCÉDENTES (shift) : pas de regard vers le futur.
        upper = out["high"].rolling(p.breakout_period, min_periods=p.breakout_period).max().shift(1)
        lower = out["low"].rolling(p.breakout_exit_period, min_periods=p.breakout_exit_period).min().shift(1)
        entry = trend_ok & (close > upper)
        exit_ = close < lower
    else:
        fast, slow = sma(close, p.fast_period), sma(close, p.slow_period)
        above = fast > slow
        entry = trend_ok & above & ~above.shift(1, fill_value=False)
        exit_ = fast < slow
    valid = out["atr"].notna() & (out["atr"] > 0)
    out["entry"] = (entry & valid).fillna(False).astype(bool)
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
