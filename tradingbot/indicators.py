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


def supertrend_line(df: pd.DataFrame, period: int, mult: float) -> pd.Series:
    """La ligne du Supertrend, pour les graphiques : la bande basse quand la tendance monte, la haute sinon (mêmes
    calculs que `supertrend`)."""
    high, low, close = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    band = mult * atr(df, period).to_numpy(float)
    upper_basic, lower_basic = (high + low) / 2 + band, (high + low) / 2 - band
    up = np.zeros(len(close), dtype=bool)
    line = np.full(len(close), math.nan)
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
        line[i] = final_lower if up[i] else final_upper
    return pd.Series(line, index=df.index)


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


def rolling_vwap(df: pd.DataFrame, period: int) -> pd.Series:
    """Prix moyen pondéré par le volume (VWAP) sur les `period` dernières bougies (prix typique = (haut+bas+clôture)/3).
    Glissant plutôt que remis à zéro chaque jour : il ne dépend que des dernières bougies, en direct comme en backtest."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["volume"].clip(lower=0)
    value = (typical * volume).rolling(period, min_periods=period).sum()
    total = volume.rolling(period, min_periods=period).sum()
    return (value / total.where(total > 0)).fillna(typical.rolling(period, min_periods=period).mean())


def stochastic(df: pd.DataFrame, k_period: int, d_period: int) -> tuple[pd.Series, pd.Series]:
    """Stochastique : (%K, %D). %K = où se trouve la clôture entre le plus bas et le plus haut des `k_period` bougies."""
    low = df["low"].rolling(k_period, min_periods=k_period).min()
    high = df["high"].rolling(k_period, min_periods=k_period).max()
    span = (high - low).where(high > low)
    k = (100 * (df["close"] - low) / span).fillna(50.0).where(low.notna())
    return k, k.rolling(d_period, min_periods=d_period).mean()


def adx(df: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(ADX, DI+, DI−) de Wilder : la force de la tendance et le côté qui domine."""
    high, low, close = df["high"], df["low"], df["close"]
    up, down = high.diff(), -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    smooth = dict(alpha=1 / period, adjust=False, min_periods=period)
    atr_w = tr.ewm(**smooth).mean()
    plus_di = 100 * plus_dm.ewm(**smooth).mean() / atr_w.where(atr_w > 0)
    minus_di = 100 * minus_dm.ewm(**smooth).mean() / atr_w.where(atr_w > 0)
    total = (plus_di + minus_di).where((plus_di + minus_di) > 0)
    dx = 100 * (plus_di - minus_di).abs() / total
    return dx.ewm(**smooth).mean(), plus_di, minus_di


def parabolic_sar(df: pd.DataFrame, step: float, max_step: float) -> tuple[pd.Series, pd.Series]:
    """(SAR, tendance haussière ?) : le point d'arrêt de Wilder, qui suit le prix et se retourne quand il est touché."""
    high, low = df["high"].to_numpy(float), df["low"].to_numpy(float)
    n = len(high)
    sar = np.full(n, math.nan)
    up = np.zeros(n, dtype=bool)
    if n < 2:
        return pd.Series(sar, index=df.index), pd.Series(up, index=df.index)
    rising = high[1] >= high[0]
    point = low[0] if rising else high[0]
    extreme = high[1] if rising else low[1]
    accel = step
    for i in range(1, n):
        point = point + accel * (extreme - point)
        if rising:
            point = min(point, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if low[i] < point:
                rising, point, extreme, accel = False, extreme, low[i], step
            elif high[i] > extreme:
                extreme, accel = high[i], min(accel + step, max_step)
        else:
            point = max(point, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if high[i] > point:
                rising, point, extreme, accel = True, extreme, high[i], step
            elif low[i] < extreme:
                extreme, accel = low[i], min(accel + step, max_step)
        sar[i], up[i] = point, rising
    return pd.Series(sar, index=df.index), pd.Series(up, index=df.index)


def ichimoku(df: pd.DataFrame, tenkan: int, kijun: int, senkou: int) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """(Tenkan, Kijun, nuage A, nuage B). Le nuage d'une bougie a été calculé `kijun` bougies plus tôt (il est « projeté
    vers l'avant ») : seulement du passé."""
    def middle(n):
        return (df["high"].rolling(n, min_periods=n).max() + df["low"].rolling(n, min_periods=n).min()) / 2
    t, k = middle(tenkan), middle(kijun)
    return t, k, ((t + k) / 2).shift(kijun), middle(senkou).shift(kijun)


def heikin_ashi(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(ouverture, clôture) des bougies Heikin-Ashi : des bougies lissées qui montrent mieux la tendance."""
    ha_close = ((df["open"] + df["high"] + df["low"] + df["close"]) / 4).to_numpy(float)
    o = df["open"].to_numpy(float)
    ha_open = np.empty(len(o))
    if len(o):
        ha_open[0] = (o[0] + df["close"].iloc[0]) / 2
    for i in range(1, len(o)):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2
    return pd.Series(ha_open, index=df.index), pd.Series(ha_close, index=df.index)
