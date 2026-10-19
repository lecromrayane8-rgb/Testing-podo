"""Indicateurs techniques (sans dépendance externe autre que pandas)."""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI de Wilder. Vaut 100 si aucune baisse, 50 si le prix est parfaitement plat."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    out = 100 - 100 / (1 + avg_gain / avg_loss)
    return out.mask((avg_gain == 0) & (avg_loss == 0), 50.0)


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range (lissage de Wilder)."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
