"""Indicateurs techniques (sans dépendance externe autre que pandas)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def bollinger(close: pd.Series, period: int, num_std: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bandes de Bollinger : (milieu, haut, bas) = moyenne ± num_std écarts-types."""
    mid = sma(close, period)
    width = num_std * close.rolling(period, min_periods=period).std(ddof=0)
    return mid, mid + width, mid - width


def macd(close: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series]:
    """(ligne MACD, ligne de signal)."""
    line = ema(close, fast) - ema(close, slow)
    return line, line.ewm(span=signal, adjust=False, min_periods=signal).mean()


def supertrend(df: pd.DataFrame, period: int, mult: float) -> pd.Series:
    """True quand la tendance Supertrend est haussière ; False pendant le démarrage.

    Bandes à milieu ± mult × ATR, qui ne reculent pas tant que le prix ne les franchit pas.
    """
    high, low, close = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    band = mult * atr(df, period).to_numpy(float)
    upper_basic, lower_basic = (high + low) / 2 + band, (high + low) / 2 - band
    up = np.zeros(len(close), dtype=bool)
    final_upper = final_lower = math.nan
    for i in range(len(close)):
        if math.isnan(band[i]):
            continue
        if math.isnan(final_upper):
            final_upper, final_lower = upper_basic[i], lower_basic[i]
            continue
        if upper_basic[i] < final_upper or close[i - 1] > final_upper:
            final_upper = upper_basic[i]
        if lower_basic[i] > final_lower or close[i - 1] < final_lower:
            final_lower = lower_basic[i]
        up[i] = close[i] >= final_lower if up[i - 1] else close[i] > final_upper
    return pd.Series(up, index=df.index)


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
