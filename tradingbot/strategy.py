"""Stratégie : achat des replis courts dans une tendance haussière (retour à la moyenne).

Entrée : clôture au-dessus de la moyenne longue (tendance haussière) ET RSI court survendu.
Sortie : clôture au-dessus de la moyenne courte (le rebond a eu lieu), ou stop-loss ATR,
ou stop temporel si le rebond ne vient pas.

Ce type de stratégie a typiquement un taux de réussite élevé (beaucoup de petits gains)
mais des pertes moyennes plus grosses que les gains moyens : seul le backtest dit si
l'espérance est positive sur le marché choisi.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .indicators import atr, rsi, sma


@dataclass(frozen=True)
class StrategyParams:
    trend_period: int = 200
    rsi_period: int = 2
    rsi_entry: float = 10.0
    exit_period: int = 5
    atr_period: int = 14
    stop_atr_mult: float = 2.5
    max_bars_in_trade: int = 24

    @property
    def warmup_bars(self) -> int:
        return max(self.trend_period, self.exit_period, self.atr_period, self.rsi_period) + 1


def compute_indicators(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    out = df.copy()
    out["trend_ma"] = sma(out["close"], p.trend_period)
    out["exit_ma"] = sma(out["close"], p.exit_period)
    out["rsi"] = rsi(out["close"], p.rsi_period)
    out["atr"] = atr(out, p.atr_period)
    return out


def _valid(*values: float) -> bool:
    return all(v is not None and not math.isnan(v) for v in values)


def entry_signal(close: float, trend_ma: float, rsi_value: float, atr_value: float, p: StrategyParams) -> bool:
    if not _valid(close, trend_ma, rsi_value, atr_value) or atr_value <= 0:
        return False
    return close > trend_ma and rsi_value < p.rsi_entry


def exit_reason(close: float, exit_ma: float, bars_held: int, p: StrategyParams) -> str | None:
    if _valid(exit_ma) and close > exit_ma:
        return "rebond"
    if bars_held >= p.max_bars_in_trade:
        return "temps"
    return None


def initial_stop(entry_price: float, atr_value: float, p: StrategyParams) -> float:
    return entry_price - p.stop_atr_mult * atr_value
