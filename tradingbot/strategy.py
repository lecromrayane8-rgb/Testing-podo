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

Sauter sur un mouvement :
- impulsion : le prix vient de prendre au moins `impulse_pct` en `impulse_bars` bougies (un mouvement
  soudain, comme ceux du radar) ; revend sous le plus bas des M bougies précédentes (le mouvement s'essouffle).

Pour toutes : stop-loss à k × ATR sous le prix d'achat, stop temporel optionnel (0 = aucun),
filtre de tendance optionnel (clôture au-dessus de la moyenne longue, 0 = aucun filtre).
Filtres optionnels d'achat, surtout utiles en très court terme où les frais pèsent lourd :
- volatilité : n'acheter que si l'ATR vaut au moins `min_atr_pct` du prix (les bougies bougent assez
  pour qu'un trade puisse rapporter plus que ses frais) ;
- volume : n'acheter que si le volume de la bougie atteint `volume_mult` fois sa moyenne (le mouvement
  est suivi par beaucoup d'acheteurs) ;
- heures actives : n'acheter que pendant `active_hours` (heures UTC, « 13-21 » = de 13 h à 21 h), quand
  le marché échange le plus ;
- compression : n'acheter que si les bandes de Bollinger de la bougie précédente étaient parmi les plus
  serrées des `squeeze_period` dernières (`squeeze_quantile` = 0,2 : les 20 % les plus serrées) ; un
  marché calme qui se réveille donne souvent un mouvement plus grand qu'un marché déjà agité.
Les signaux d'une bougie n'utilisent que cette bougie et les précédentes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import atr, bollinger, macd, rsi, sma, supertrend

STRATEGY_TYPES = (
    "retour_moyenne", "bollinger", "cassure", "bollinger_cassure", "croisement", "macd", "momentum", "supertrend",
    "impulsion",
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
    impulse_bars: int = 5  # impulsion : hausse d'au moins impulse_pct (0,01 = 1 %) en impulse_bars bougies
    impulse_pct: float = 0.01
    atr_period: int = 14
    stop_atr_mult: float = 2.5
    max_bars_in_trade: int = 24  # 0 = pas de stop temporel
    min_atr_pct: float = 0.0  # filtre de volatilité : ATR / prix minimum (0,003 = 0,3 %) ; 0 = sans filtre
    volume_mult: float = 0.0  # filtre de volume : volume >= k × sa moyenne ; 0 = sans filtre
    volume_period: int = 20
    active_hours: str = ""  # heures UTC d'achat, « 13-21 » ; vide = toute la journée
    squeeze_quantile: float = 0.0  # compression des bandes de Bollinger avant l'achat ; 0 = sans filtre
    squeeze_period: int = 120

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
        if self.min_atr_pct < 0 or self.volume_mult < 0 or self.volume_period < 1:
            raise ValueError("MIN_ATR_PCT et VOLUME_MULT doivent être >= 0, VOLUME_PERIOD >= 1")
        if self.impulse_bars < 1 or not 0 < self.impulse_pct < 1:
            raise ValueError("IMPULSE_BARS doit être >= 1 et IMPULSE_PCT entre 0 et 1 (0,01 = 1 %)")
        if not 0 <= self.squeeze_quantile < 1 or self.squeeze_period < 2:
            raise ValueError("SQUEEZE_QUANTILE doit être entre 0 et 1 (0,2 = 20 %), SQUEEZE_PERIOD >= 2")
        if self.active_hours:
            self.hours_window  # « 13-21 » mal écrit : erreur claire dès le chargement des réglages

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
            "impulsion": [self.impulse_bars + 2, self.breakout_exit_period + 1],
        }[self.strategy_type]
        volume = [self.volume_period] if self.volume_mult else []
        squeeze = [self.bb_period + self.squeeze_period + 1] if self.squeeze_quantile else []
        return max([self.atr_period, self.trend_period, *volume, *squeeze, *periods]) + 1

    @property
    def hours_window(self) -> tuple[int, int]:
        """« 13-21 » -> (13, 21) : de 13 h (incluse) à 21 h (exclue), en UTC ; « 22-6 » passe minuit."""
        try:
            start, end = (int(x) for x in self.active_hours.split("-"))
        except ValueError:
            raise ValueError(f"ACTIVE_HOURS doit ressembler à 13-21 (reçu : {self.active_hours!r})") from None
        if not (0 <= start <= 23 and 0 <= end <= 24) or start == end:
            raise ValueError(f"ACTIVE_HOURS doit ressembler à 13-21 (reçu : {self.active_hours!r})")
        return start, end

    @property
    def exit_label(self) -> str:
        if self.strategy_type == "impulsion":
            return "essoufflement"
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
    elif t == "impulsion":
        # Seulement la bougie où le mouvement apparaît : pas de rachat à chaque bougie d'une même envolée.
        rise = close / close.shift(p.impulse_bars) - 1
        entry = _crossing_up(rise >= p.impulse_pct)
        lower = out["low"].rolling(p.breakout_exit_period, min_periods=p.breakout_exit_period).min().shift(1)
        exit_ = close < lower
    else:
        up = supertrend(out, p.st_period, p.st_mult)
        entry = _crossing_up(up)
        exit_ = ~up
    valid = out["atr"].notna() & (out["atr"] > 0)
    if p.min_atr_pct:
        valid &= out["atr"] / close >= p.min_atr_pct
    if p.volume_mult:
        valid &= out["volume"] >= p.volume_mult * sma(out["volume"], p.volume_period)
    if p.active_hours:
        start, end = p.hours_window
        hours = out.index.hour
        inside = (hours >= start) & (hours < end) if start < end else (hours >= start) | (hours < end)
        valid &= pd.Series(inside, index=out.index)
    if p.squeeze_quantile:
        mid, upper, lower = bollinger(close, p.bb_period, p.bb_std)
        width = ((upper - lower) / mid).shift(1)  # la bougie d'avant : celle de l'achat peut déjà s'écarter
        calm = width.rolling(p.squeeze_period, min_periods=p.squeeze_period).quantile(p.squeeze_quantile)
        valid &= width <= calm
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
