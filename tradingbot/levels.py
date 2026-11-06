"""Supports et résistances : les prix où le marché s'est déjà retourné, comme un trader les trace à la main.

Un support est un niveau sous le prix où les acheteurs sont revenus (le prix y a rebondi) ; une résistance, un niveau
au-dessus où les vendeurs sont revenus. Le bot les trouve en trois temps :
1. les sommets et les creux nets (« pivots ») : le plus haut (ou le plus bas) de `window` bougies de chaque côté.
   Un pivot n'est connu que `window` bougies plus tard (il faut avoir vu le prix repartir) : pas de regard vers le
   futur ;
2. les pivots proches les uns des autres (écart inférieur à `tol_mult` fois la taille moyenne d'une bougie) forment
   une même zone ; plus une zone a été touchée, plus elle est solide. Sommets et creux vont dans le même panier : une
   résistance franchie devient souvent un support, et inversement ;
3. au prix du moment : le support est la zone solide la plus proche en dessous, la résistance la plus proche au-dessus.

Tout ne dépend que des `lookback` dernières bougies : le bot en direct, qui ne voit qu'une fenêtre d'historique, trouve
exactement les mêmes niveaux que le backtest. La recherche (Osler, 2000 et 2003) trouve que les supports et
résistances annoncent bien des arrêts de tendance, en partie parce que les ordres s'accumulent aux chiffres ronds.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Level:
    price: float  # milieu de la zone
    low: float  # bas de la zone
    high: float  # haut de la zone
    touches: int  # nombre de sommets et de creux dans la zone
    first: int  # indice de la première touche
    last: int  # indice de la dernière touche


def candle_size(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Taille moyenne d'une bougie (moyenne simple du « true range ») : elle ne dépend que des `period` dernières."""
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.rolling(period, min_periods=period).mean()


def pivot_points(high: np.ndarray, low: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Indices des sommets (plus haut de `window` bougies de chaque côté) et des creux, au sens strict à gauche."""
    n = len(high)
    if n < 2 * window + 1:
        return np.array([], dtype=int), np.array([], dtype=int)
    hs = pd.Series(high)
    ls = pd.Series(low)
    left_high = hs.rolling(window, min_periods=window).max().shift(1).to_numpy()  # les `window` bougies d'avant
    right_high = hs[::-1].rolling(window, min_periods=window).max()[::-1].shift(-1).to_numpy()  # celles d'après
    left_low = ls.rolling(window, min_periods=window).min().shift(1).to_numpy()
    right_low = ls[::-1].rolling(window, min_periods=window).min()[::-1].shift(-1).to_numpy()
    with np.errstate(invalid="ignore"):
        tops = (high > left_high) & (high >= right_high)
        bottoms = (low < left_low) & (low <= right_low)
    return np.flatnonzero(tops), np.flatnonzero(bottoms)


def _zones(prices: list[float], idxs: list[int], tol: float) -> list[Level]:
    """Regroupe des prix voisins (écart <= tol entre deux prix consécutifs, une fois triés) en zones."""
    if not prices:
        return []
    order = sorted(range(len(prices)), key=prices.__getitem__)
    zones, group = [], [order[0]]
    for k in order[1:]:
        if prices[k] - prices[group[-1]] <= tol:
            group.append(k)
        else:
            zones.append(group)
            group = [k]
    zones.append(group)
    out = []
    for g in zones:
        ps = [prices[k] for k in g]
        ix = [idxs[k] for k in g]
        out.append(Level(sum(ps) / len(ps), min(ps), max(ps), len(g), min(ix), max(ix)))
    return out


def _window_pivots(df: pd.DataFrame, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Tous les pivots (sommets et creux) triés par indice : (indices, prix)."""
    high, low = df["high"].to_numpy(float), df["low"].to_numpy(float)
    tops, bottoms = pivot_points(high, low, window)
    idx = np.concatenate([tops, bottoms])
    price = np.concatenate([high[tops], low[bottoms]])
    order = np.argsort(idx, kind="stable")
    return idx[order], price[order]


def level_series(df: pd.DataFrame, window: int = 5, lookback: int = 150, tol_mult: float = 0.5,
                 min_touches: int = 2, size_period: int = 14) -> pd.DataFrame:
    """Pour chaque bougie, à sa clôture : les supports et résistances solides autour du prix, et la largeur d'une zone.

    Une bougie t ne voit que les pivots déjà confirmés (indice <= t - window) et encore récents (>= t - lookback).
    Un prix qui est DANS une zone (à moins de `level_tol` de son milieu) ne l'a pas encore franchie : elle compte à la
    fois comme support et comme résistance. Colonnes (NaN quand rien n'est trouvé) :
    - support : la zone la plus haute dont le milieu est sous le prix + level_tol (le plancher sur lequel on est) ;
    - resistance : la zone la plus basse dont le milieu est au-dessus du prix - level_tol (le plafond à franchir) ;
    - next_support / next_resistance : la zone suivante, au-delà de celle où le prix se trouve ;
    - support_touches, resistance_touches, level_tol.
    """
    n = len(df)
    close = df["close"].to_numpy(float)
    tol = (tol_mult * candle_size(df, size_period)).to_numpy(float)
    piv_idx, piv_price = _window_pivots(df, window)
    support = np.full(n, math.nan)
    resistance = np.full(n, math.nan)
    next_support = np.full(n, math.nan)
    next_resistance = np.full(n, math.nan)
    s_touch = np.zeros(n, dtype=int)
    r_touch = np.zeros(n, dtype=int)
    idx_list = piv_idx.tolist()
    price_list = piv_price.tolist()
    lo = hi = 0  # fenêtre [lo, hi) des pivots visibles
    for t in range(n):
        while hi < len(idx_list) and idx_list[hi] <= t - window:
            hi += 1
        while lo < hi and idx_list[lo] < t - lookback:
            lo += 1
        if hi - lo < min_touches or math.isnan(tol[t]):
            continue
        zones = [z for z in _zones(price_list[lo:hi], idx_list[lo:hi], tol[t]) if z.touches >= min_touches]
        if not zones:
            continue
        mids = [z.price for z in zones]  # déjà triés par prix
        c, width = close[t], tol[t]
        k = bisect_left(mids, c + width)  # zones sous prix + largeur : [0, k)
        if k > 0:
            support[t], s_touch[t] = zones[k - 1].price, zones[k - 1].touches
        j = bisect_right(mids, c - width)  # zones au-dessus de prix - largeur : [j, ...)
        if j < len(zones):
            resistance[t], r_touch[t] = zones[j].price, zones[j].touches
        k2 = bisect_left(mids, c - width)
        if k2 > 0:
            next_support[t] = zones[k2 - 1].price
        j2 = bisect_right(mids, c + width)
        if j2 < len(zones):
            next_resistance[t] = zones[j2].price
    return pd.DataFrame({"support": support, "support_touches": s_touch, "resistance": resistance,
                         "resistance_touches": r_touch, "next_support": next_support,
                         "next_resistance": next_resistance, "level_tol": tol}, index=df.index)


def levels_now(df: pd.DataFrame, window: int = 5, lookback: int = 150, tol_mult: float = 0.5,
               size_period: int = 14) -> list[Level]:
    """Toutes les zones visibles à la dernière bougie (même celles touchées une seule fois), de la plus basse à la
    plus haute : pour dessiner un graphique ou expliquer un trade."""
    n = len(df)
    if n == 0:
        return []
    tol = float((tol_mult * candle_size(df, size_period)).iloc[-1])
    if math.isnan(tol):
        return []
    piv_idx, piv_price = _window_pivots(df, window)
    t = n - 1
    keep = (piv_idx <= t - window) & (piv_idx >= t - lookback)
    return _zones(piv_price[keep].tolist(), piv_idx[keep].tolist(), tol)


def nearest(levels: list[Level], price: float, min_touches: int = 2) -> tuple[Level | None, Level | None]:
    """(support, résistance) : les zones solides les plus proches sous et au-dessus de `price`."""
    solid = [z for z in levels if z.touches >= min_touches]
    below = [z for z in solid if z.price < price]
    above = [z for z in solid if z.price > price]
    return (max(below, key=lambda z: z.price) if below else None,
            min(above, key=lambda z: z.price) if above else None)


def round_step(price: float) -> float:
    """Le pas des chiffres ronds qui comptent pour ce prix : 68 400 -> 1 000 ; 0,1532 -> 0,01."""
    if not price > 0:
        return math.nan
    return 10 ** (math.floor(math.log10(price)) - 1)


def round_levels(price: float) -> tuple[float, float]:
    """Les chiffres ronds juste en dessous et juste au-dessus du prix (68 400 -> 68 000 et 69 000)."""
    step = round_step(price)
    if math.isnan(step):
        return math.nan, math.nan
    below = math.floor(price / step) * step
    above = below + step
    return round(below, 12), round(above, 12)
