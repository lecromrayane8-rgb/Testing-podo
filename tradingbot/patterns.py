"""La lecture du graphique, écrite comme des règles : ce que les traders tracent à la main, défini une fois pour toutes.

Chaque fonction rend, pour chaque bougie, un signal d'achat (la version « vente à découvert » applique la même règle
au graphique retourné, comme pour toutes les techniques). Trois garanties communes :

- aucun regard vers le futur : le signal d'une bougie n'utilise que cette bougie et les précédentes ; un sommet ou un
  creux n'est connu que `window` bougies plus tard, quand le prix s'en est éloigné ;
- une mémoire courte : ce qui compte tient dans les `lookback` dernières bougies, pour que le bot en direct, qui ne lit
  que les dernières bougies, voie exactement ce que voit le backtest ;
- des définitions de manuel, fixées d'avance : jamais ajustées sur nos données.

Les définitions (pour un acheteur) :
- zone à combler (fair value gap) : trois bougies laissent un trou entre le plus haut de la première et le plus bas de
  la troisième ; le prix revient dans le trou puis clôture au-dessus ;
- order block : la dernière bougie baissière avant une envolée (au moins `impulse_atr` fois la taille moyenne d'une
  bougie en `impulse_bars` bougies) ; le prix revient sur cette bougie puis clôture au-dessus ;
- prise de liquidité : la mèche passe sous le dernier creux marquant (là où dorment les stops), puis la bougie
  clôture au-dessus ;
- cassure de structure : la clôture dépasse le dernier sommet marquant ;
- avalement : une bougie verte dont le corps recouvre celui de la bougie rouge d'avant, au plus bas des dernières
  bougies ;
- marteau : une longue mèche basse (au moins deux fois le corps), presque pas de mèche haute, au plus bas des
  dernières bougies ;
- bougie intérieure : une bougie contenue dans la précédente, puis une clôture au-dessus du plus haut de celle-ci ;
- divergence : le prix fait un creux plus bas que le précédent, mais pas le RSI ;
- retracement de Fibonacci : après une jambe de hausse (d'un creux marquant à un sommet marquant), le prix en reperd
  entre 50 % et 61,8 % et la bougie clôture en hausse ;
- double creux : deux creux marquants au même prix, puis une clôture au-dessus du sommet qui les sépare.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .levels import pivot_points


def last_swings(high: np.ndarray, low: np.ndarray, window: int, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque bougie, le dernier sommet et le dernier creux marquants déjà connus (confirmés `window` bougies
    après), s'ils datent de moins de `lookback` bougies ; NaN sinon."""
    n = len(high)
    tops, bottoms = pivot_points(high, low, window)

    def carry(indices: np.ndarray, values: np.ndarray) -> np.ndarray:
        price = np.full(n, np.nan)
        born = np.full(n, np.nan)
        known = indices + window
        keep = known < n
        price[known[keep]] = values[indices[keep]]
        born[known[keep]] = indices[keep]
        price, born = pd.Series(price).ffill().to_numpy(), pd.Series(born).ffill().to_numpy()
        with np.errstate(invalid="ignore"):
            return np.where(np.arange(n) - born <= lookback, price, np.nan)

    return carry(tops, high), carry(bottoms, low)


def known_swings(high, low, window: int, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    """Le dernier sommet et le dernier creux marquants tels qu'on les connaissait à la bougie précédente : les niveaux
    qu'une bougie peut casser ou balayer."""
    top, bottom = last_swings(high, low, window, lookback)
    return _before(top), _before(bottom)


def structure_break(high, low, close, window: int, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    """Cassure de structure : la clôture dépasse le dernier sommet marquant (entrée, à la première bougie seulement) ;
    elle passe sous le dernier creux marquant (sortie)."""
    top, bottom = known_swings(high, low, window, lookback)
    with np.errstate(invalid="ignore"):
        above = close > top
        return above & ~_before(above, False), close < bottom


def liquidity_sweep(high, low, open_, close, window: int, lookback: int) -> np.ndarray:
    """Prise de liquidité : la mèche passe sous le dernier creux marquant, puis la bougie clôture au-dessus, en hausse."""
    _, bottom = known_swings(high, low, window, lookback)
    with np.errstate(invalid="ignore"):
        return (low < bottom) & (close > bottom) & (close > open_)


def engulfing(high, low, open_, close, span: int) -> np.ndarray:
    """Avalement haussier : bougie rouge, puis bougie verte dont le corps recouvre le sien, au plus bas des `span`
    dernières bougies."""
    o1, c1 = _before(open_), _before(close)
    body = (c1 < o1) & (close > open_) & (open_ <= c1) & (close >= o1)
    floor = pd.Series(low).rolling(span, min_periods=span).min().to_numpy()
    return body & (np.minimum(low, _before(low)) <= floor)


def hammer(high, low, open_, close, atr: np.ndarray, span: int, wick: float) -> np.ndarray:
    """Marteau : une mèche basse d'au moins `wick` fois le corps et de plus de la moitié de la bougie, une mèche haute
    de moins du quart, une bougie d'au moins la taille moyenne, au plus bas des `span` dernières bougies."""
    body = np.abs(close - open_)
    size = high - low
    lower = np.minimum(open_, close) - low
    upper = high - np.maximum(open_, close)
    floor = pd.Series(low).rolling(span, min_periods=span).min().to_numpy()
    with np.errstate(invalid="ignore"):
        return (size >= atr) & (lower >= wick * body) & (lower >= 0.5 * size) & (upper <= 0.25 * size) & (low <= floor)


def inside_break(high, low, close) -> np.ndarray:
    """Bougie intérieure : la bougie d'avant tient dans celle qui la précède ; la clôture dépasse le plus haut de
    cette bougie mère."""
    mother_high, mother_low = _before(high, np.nan, 2), _before(low, np.nan, 2)
    inside = (_before(high) < mother_high) & (_before(low) > mother_low)
    return inside & (close > mother_high)


def rsi_divergence(low, rsi: np.ndarray, window: int, lookback: int, weak: float) -> np.ndarray:
    """Divergence haussière : deux creux marquants à moins de `lookback` bougies l'un de l'autre, le second plus bas
    que le premier alors que le RSI, lui, est plus haut ; le RSI du premier était sous `weak`. Signal à la bougie où
    le second creux est confirmé."""
    n = len(low)
    entry = np.zeros(n, dtype=bool)
    _, bottoms = pivot_points(np.asarray(low, dtype=float), np.asarray(low, dtype=float), window)
    for first, second in zip(bottoms[:-1], bottoms[1:]):
        known = second + window
        if (known < n and second - first <= lookback and low[second] < low[first] and rsi[second] > rsi[first]
                and rsi[first] < weak):
            entry[known] = True
    return entry


def double_bottom(high, low, close, atr: np.ndarray, window: int, lookback: int, tol: float, valid: int) -> np.ndarray:
    """Double creux : deux creux marquants au même prix (à `tol` fois la taille moyenne d'une bougie près), à moins de
    `lookback` bougies l'un de l'autre ; signal à la première clôture au-dessus du sommet qui les sépare, dans les
    `valid` bougies qui suivent la confirmation du second creux."""
    n = len(low)
    entry = np.zeros(n, dtype=bool)
    _, bottoms = pivot_points(np.asarray(low, dtype=float), np.asarray(low, dtype=float), window)
    for first, second in zip(bottoms[:-1], bottoms[1:]):
        known = second + window
        if known >= n or second - first > lookback or not abs(low[second] - low[first]) <= tol * atr[second]:
            continue
        neck = high[first:second + 1].max()
        for i in range(known, min(n, known + valid + 1)):
            if close[i] > neck:  # la première clôture au-dessus : la figure est complète
                entry[i] = True
                break
    return entry


def zone_retest(low, open_, close, top: np.ndarray, bottom: np.ndarray, valid: int, hold: str = "top",
                track: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    """Le retour du prix dans une zone. `top` et `bottom` : les bords de la zone née à cette bougie (NaN : aucune). La
    zone la plus récente remplace l'ancienne ; elle meurt après `valid` bougies, ou si une clôture passe sous son
    bord bas. Signal : la bougie descend dans la zone (plus bas sous le bord haut) et clôture au-dessus du bord haut
    (`hold` = "top") ou au-dessus du bord bas, en hausse (`hold` = "bottom"). Une zone ne sert qu'une fois.
    `track` (pour le graphique) : deux tableaux qui reçoivent les bords de la zone attendue à chaque bougie."""
    n = len(low)
    entry = np.zeros(n, dtype=bool)
    low, open_, close, top, bottom = (np.asarray(a, dtype=float).tolist() for a in (low, open_, close, top, bottom))
    zone_top = zone_bottom = None
    age = 0
    for i in range(n):
        if zone_top is not None:  # une zone est en attente
            if track is not None:
                track[0][i], track[1][i] = zone_top, zone_bottom
            age += 1
            if age > valid or close[i] < zone_bottom:
                zone_top = None
            elif low[i] <= zone_top and (close[i] > zone_top if hold == "top" else
                                         (close[i] > zone_bottom and close[i] > open_[i])):
                entry[i] = True
                zone_top = None
        if top[i] == top[i]:  # une zone naît à cette bougie : elle comptera dès la suivante
            zone_top, zone_bottom, age = top[i], bottom[i], 0
    return entry


def fair_value_gaps(high, low, atr: np.ndarray, min_size: float) -> tuple[np.ndarray, np.ndarray]:
    """Les zones à combler haussières : le plus bas de la bougie dépasse le plus haut de celle d'il y a deux bougies,
    d'au moins `min_size` fois la taille moyenne d'une bougie. Rend les bords (haut, bas) de la zone née à chaque
    bougie."""
    before = _before(high, np.nan, 2)
    with np.errstate(invalid="ignore"):
        gap = (low - before) >= min_size * atr
    return np.where(gap, low, np.nan), np.where(gap, before, np.nan)


def order_blocks(high, low, open_, close, atr: np.ndarray, bars: int, strength: float,
                 search: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Les order blocks haussiers : à la bougie où le prix vient de monter d'au moins `strength` fois la taille
    moyenne d'une bougie en `bars` bougies, la dernière bougie baissière d'avant l'envolée (parmi les `search`
    précédentes). Rend les bords (haut, bas) de cette bougie, à la bougie où l'envolée apparaît."""
    n = len(close)
    top, bottom = np.full(n, np.nan), np.full(n, np.nan)
    with np.errstate(invalid="ignore"):
        surge = (close - _before(close, np.nan, bars)) >= strength * atr
    starts = np.flatnonzero(surge & ~_before(surge, False))
    for i in starts:
        for j in range(i - bars, max(i - bars - search, -1), -1):
            if close[j] < open_[j]:
                top[i], bottom[i] = high[j], low[j]
                break
    return top, bottom


def fib_zones(high, low, atr: np.ndarray, window: int, lookback: int, low_ratio: float, high_ratio: float,
              min_leg: float) -> tuple[np.ndarray, np.ndarray]:
    """Les zones de retracement : quand un sommet marquant est confirmé après un creux marquant (à moins de `lookback`
    bougies), et que la jambe entre les deux vaut au moins `min_leg` fois la taille moyenne d'une bougie, la zone va
    de `low_ratio` à `high_ratio` de la jambe sous le sommet. Rend ses bords à la bougie où le sommet est confirmé."""
    n = len(high)
    top, bottom = np.full(n, np.nan), np.full(n, np.nan)
    tops, bottoms = pivot_points(np.asarray(high, dtype=float), np.asarray(low, dtype=float), window)
    for peak in tops:
        known = peak + window
        before = bottoms[bottoms < peak]
        if known >= n or not len(before):
            continue
        trough = before[-1]
        leg = high[peak] - low[trough]
        if peak - trough <= lookback and leg >= min_leg * atr[peak]:
            top[known], bottom[known] = high[peak] - low_ratio * leg, high[peak] - high_ratio * leg
    return top, bottom


def _before(values, fill=np.nan, k: int = 1) -> np.ndarray:
    """Les valeurs d'il y a `k` bougies."""
    values = np.asarray(values)
    out = np.empty(len(values), dtype=bool if values.dtype == bool else float)
    out[:k] = fill
    out[k:] = values[:-k] if k else values
    return out
