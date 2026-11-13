"""Stratégies : trente familles de règles, avec les mêmes signaux en backtest et en direct.

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
  soudain) ; revend sous le plus bas des M bougies précédentes (le mouvement s'essouffle).

Supports et résistances (tradingbot/levels.py : les niveaux où le prix s'est déjà retourné plusieurs fois) :
- support : la bougie descend jusqu'à un support solide puis clôture au-dessus, en hausse (un rebond) ; revend quand
  le prix touche la résistance suivante, ou si le support cède ;
- resistance : la clôture franchit nettement une résistance solide (une cassure) ; revend si le prix retombe sous
  l'ancien niveau, devenu support.
Les niveaux utilisés sont ceux connus à la clôture précédente : la bougie du signal ne compte pas dans son propre
niveau.

D'autres outils de traders (ajoutés pour l'essaim de bots, réglages classiques fixés d'avance) :
- ema_croisement : la moyenne exponentielle rapide (9) croise la lente (21) par le haut ; revend au croisement inverse ;
- vwap : la clôture repasse au-dessus du prix moyen pondéré par le volume, avec la moyenne exponentielle rapide
  au-dessus de la lente (la stratégie de scalping la plus citée) ; revend sous le VWAP ;
- stochastique : le %K croise le %D par le haut en zone de survente (sous 20) ; revend au-dessus de 80 ;
- keltner : la clôture sort au-dessus du canal de Keltner (moyenne exponentielle + k × ATR) ; revend sous la moyenne ;
- adx : le DI+ passe au-dessus du DI− avec une tendance forte (ADX > 25) ; revend quand le DI− repasse devant ;
- psar : le Parabolic SAR passe sous le prix ; revend quand il repasse au-dessus ;
- ichimoku : la clôture passe au-dessus du nuage avec la Tenkan au-dessus de la Kijun ; revend sous la Kijun ;
- zscore : la clôture tombe à plus de k écarts-types sous sa moyenne ; revend au retour sur la moyenne ;
- heikin : les bougies Heikin-Ashi (lissées) deviennent vertes N fois de suite ; revend à la première rouge.

La lecture du graphique (tradingbot/patterns.py : ce que les traders tracent à la main, défini une fois pour toutes) :
- fvg : le prix revient dans une zone à combler (un trou laissé par trois bougies) puis clôture au-dessus ;
- order_block : le prix revient sur la dernière bougie baissière d'avant une envolée, puis clôture au-dessus ;
- balayage : la mèche passe sous le dernier creux marquant (prise de liquidité), puis la bougie clôture au-dessus ;
- structure : la clôture dépasse le dernier sommet marquant (cassure de structure) ; revend sous le dernier creux ;
- avalement, marteau : la bougie de retournement, au plus bas des dernières bougies ;
- interieure : une bougie contenue dans la précédente, puis une clôture au-dessus de celle-ci ;
- divergence : le prix fait un creux plus bas, pas le RSI ;
- fibonacci : après une jambe de hausse, le prix en reperd entre 50 % et 61,8 % et repart ;
- double_creux : deux creux au même prix, puis une clôture au-dessus du sommet qui les sépare.
Sauf la cassure de structure, elles revendent quand le rebond s'essouffle (clôture sous le plus bas des M bougies
précédentes).

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

import numpy as np
import pandas as pd

from .indicators import (
    adx, atr, bollinger, ema, heikin_ashi, ichimoku, macd, parabolic_sar, rolling_vwap, rsi, sma, stochastic, supertrend,
)
from . import patterns
from .levels import level_series

STRATEGY_TYPES = (
    "retour_moyenne", "bollinger", "cassure", "bollinger_cassure", "croisement", "macd", "momentum", "supertrend",
    "impulsion", "support", "resistance",
    "ema_croisement", "vwap", "stochastique", "keltner", "adx", "psar", "ichimoku", "zscore", "heikin",
    "fvg", "order_block", "balayage", "structure", "avalement", "marteau", "interieure", "divergence", "fibonacci",
    "double_creux",
)
MEAN_REVERSION = ("retour_moyenne", "bollinger", "stochastique", "zscore")
LEVEL_FAMILIES = ("support", "resistance")
# La lecture du graphique (tradingbot/patterns.py) : zones, structure, bougies de retournement, figures.
PATTERN_FAMILIES = ("fvg", "order_block", "balayage", "structure", "avalement", "marteau", "interieure", "divergence",
                    "fibonacci", "double_creux")


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
    level_window: int = 5  # supports et résistances : un sommet ou un creux net sur 5 bougies de chaque côté
    level_lookback: int = 150  # seuls comptent les sommets et creux des 150 dernières bougies
    level_touches: int = 2  # un niveau solide a été touché au moins 2 fois
    level_tol: float = 0.5  # largeur d'une zone : 0,5 fois la taille moyenne d'une bougie
    atr_period: int = 14
    stop_atr_mult: float = 2.5
    max_bars_in_trade: int = 24  # 0 = pas de stop temporel
    min_atr_pct: float = 0.0  # filtre de volatilité : ATR / prix minimum (0,003 = 0,3 %) ; 0 = sans filtre
    volume_mult: float = 0.0  # filtre de volume : volume >= k × sa moyenne ; 0 = sans filtre
    volume_period: int = 20
    active_hours: str = ""  # heures UTC d'achat, « 13-21 » ; vide = toute la journée
    squeeze_quantile: float = 0.0  # compression des bandes de Bollinger avant l'achat ; 0 = sans filtre
    squeeze_period: int = 120
    ema_fast: int = 9  # moyennes exponentielles (ema_croisement, et filtre de la famille vwap)
    ema_slow: int = 21
    vwap_period: int = 48  # VWAP glissant sur 48 bougies
    stoch_k: int = 14
    stoch_d: int = 3
    stoch_low: float = 20.0
    stoch_high: float = 80.0
    keltner_period: int = 20
    keltner_mult: float = 2.0
    adx_period: int = 14
    adx_min: float = 25.0
    psar_step: float = 0.02
    psar_max: float = 0.2
    ichi_tenkan: int = 9
    ichi_kijun: int = 26
    ichi_senkou: int = 52
    zscore_period: int = 20
    zscore_entry: float = 2.0
    heikin_bars: int = 2
    # La lecture du graphique : des définitions de manuel, fixées d'avance (jamais ajustées sur les données).
    swing_lookback: int = 60  # un sommet ou un creux marquant compte pendant 60 bougies
    zone_valid: int = 30  # une zone (à combler, order block, retracement, double creux) attend le prix 30 bougies
    gap_min_atr: float = 0.25  # zone à combler : au moins un quart de la taille moyenne d'une bougie
    surge_bars: int = 3  # order block : une envolée d'au moins surge_atr fois la bougie moyenne en 3 bougies
    surge_atr: float = 2.0
    pattern_span: int = 10  # avalement, marteau : au plus bas des 10 dernières bougies
    wick_ratio: float = 2.0  # marteau : la mèche basse vaut au moins 2 fois le corps
    divergence_period: int = 14  # divergence : le RSI classique, sur 14 bougies
    divergence_weak: float = 40.0  # et il était sous 40 au premier creux
    fib_low: float = 0.5  # retracement : entre 50 % et 61,8 % de la jambe
    fib_high: float = 0.618
    leg_min_atr: float = 3.0  # une jambe d'au moins 3 fois la taille moyenne d'une bougie
    double_tol: float = 0.5  # double creux : deux creux à moins d'une demi-bougie moyenne l'un de l'autre

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
        if self.level_window < 1 or self.level_lookback <= 2 * self.level_window or self.level_touches < 1 \
                or not self.level_tol > 0:
            raise ValueError("LEVEL_WINDOW >= 1, LEVEL_LOOKBACK > 2 x LEVEL_WINDOW, LEVEL_TOUCHES >= 1 et "
                             "LEVEL_TOL > 0")
        if not 0 <= self.squeeze_quantile < 1 or self.squeeze_period < 2:
            raise ValueError("SQUEEZE_QUANTILE doit être entre 0 et 1 (0,2 = 20 %), SQUEEZE_PERIOD >= 2")
        if self.active_hours:
            self.hours_window  # « 13-21 » mal écrit : erreur claire dès le chargement des réglages
        if not 1 <= self.ema_fast < self.ema_slow:
            raise ValueError("EMA_FAST doit être plus petit que EMA_SLOW")
        if min(self.vwap_period, self.stoch_k, self.stoch_d, self.keltner_period, self.adx_period,
               self.zscore_period) < 2 or self.heikin_bars < 1:
            raise ValueError("Les périodes des indicateurs doivent être >= 2 (HEIKIN_BARS >= 1)")
        if not 0 < self.stoch_low < self.stoch_high < 100:
            raise ValueError("STOCH_LOW et STOCH_HIGH doivent être entre 0 et 100, le premier plus petit")
        if not self.keltner_mult > 0 or not self.zscore_entry > 0 or not 0 <= self.adx_min < 100:
            raise ValueError("KELTNER_MULT et ZSCORE_ENTRY doivent être positifs, ADX_MIN entre 0 et 100")
        if not 0 < self.psar_step <= self.psar_max < 1:
            raise ValueError("PSAR_STEP doit être positif et au plus PSAR_MAX (< 1)")
        if not 1 <= self.ichi_tenkan < self.ichi_kijun < self.ichi_senkou:
            raise ValueError("ICHI_TENKAN < ICHI_KIJUN < ICHI_SENKOU")
        if min(self.swing_lookback, self.zone_valid, self.surge_bars, self.pattern_span, self.divergence_period) < 2 \
                or min(self.gap_min_atr, self.surge_atr, self.wick_ratio, self.leg_min_atr, self.double_tol) <= 0 \
                or not 0 < self.fib_low < self.fib_high < 1 or not 0 < self.divergence_weak < 100:
            raise ValueError("Réglages de la lecture du graphique impossibles (périodes >= 2, seuils positifs, "
                             "FIB_LOW < FIB_HIGH entre 0 et 1)")

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
            "support": [self.level_lookback + self.level_window + self.atr_period + 2],
            "resistance": [self.level_lookback + self.level_window + self.atr_period + 2],
            "ema_croisement": [self.ema_slow + 2],
            "vwap": [self.vwap_period + 2, self.ema_slow + 2],
            "stochastique": [self.stoch_k + self.stoch_d + 2],
            "keltner": [self.keltner_period + 2],
            "adx": [2 * self.adx_period + 2],
            "psar": [10],
            "ichimoku": [self.ichi_senkou + self.ichi_kijun + 2],
            "zscore": [self.zscore_period + 2],
            "heikin": [self.heikin_bars + 10],
        }.get(self.strategy_type) or [  # la lecture du graphique : sommets, creux et zones des dernières bougies
            self.swing_lookback + self.zone_valid + 2 * self.level_window + self.atr_period + 2,
            self.breakout_exit_period + 1, 5 * self.divergence_period]
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
        if self.strategy_type == "support":
            return "résistance ou support cassé"
        if self.strategy_type == "resistance":
            return "retour sous le niveau"
        if self.strategy_type == "stochastique":
            return "suracheté"
        if self.strategy_type == "zscore":
            return "retour à la moyenne"
        if self.strategy_type == "structure":
            return "retour sous le dernier creux"
        if self.strategy_type in PATTERN_FAMILIES:
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
    elif t in LEVEL_FAMILIES:
        lv = level_series(out, p.level_window, p.level_lookback, p.level_tol, p.level_touches, p.atr_period)
        out["support"], out["resistance"] = lv["support"], lv["resistance"]
        support, resistance, below, target, tol = (
            lv[k].shift(1) for k in ("support", "resistance", "next_support", "next_resistance", "level_tol"))
        if t == "support":  # rebond : venu d'au-dessus, le prix touche le support, puis clôture au-dessus et en hausse
            entry = (out["low"] <= below + tol) & (close > below) & (close > out["open"])
            exit_ = (out["high"] >= target - tol) | (close < support - tol)  # résistance suivante, ou support cassé
        else:  # cassure : clôture nettement au-dessus de la résistance ; sortie si le prix retombe sous le niveau
            entry = _crossing_up(close > resistance + tol)
            exit_ = close < support - tol
    elif t == "ema_croisement":
        fast, slow = ema(close, p.ema_fast), ema(close, p.ema_slow)
        entry = _crossing_up(fast > slow)
        exit_ = fast < slow
    elif t == "vwap":
        vw = rolling_vwap(out, p.vwap_period)
        entry = _crossing_up(close > vw) & (ema(close, p.ema_fast) > ema(close, p.ema_slow))
        exit_ = close < vw
    elif t == "stochastique":
        k, d = stochastic(out, p.stoch_k, p.stoch_d)
        entry = _crossing_up(k > d) & (k.shift(1) < p.stoch_low)
        exit_ = k >= p.stoch_high
    elif t == "keltner":
        mid = ema(close, p.keltner_period)
        upper = mid + p.keltner_mult * atr(out, p.keltner_period)
        entry = _crossing_up(close > upper)
        exit_ = close < mid
    elif t == "adx":
        strength, plus, minus = adx(out, p.adx_period)
        entry = _crossing_up(plus > minus) & (strength > p.adx_min)
        exit_ = plus < minus
    elif t == "psar":
        _, rising = parabolic_sar(out, p.psar_step, p.psar_max)
        entry = _crossing_up(rising)
        exit_ = ~rising
    elif t == "ichimoku":
        tenkan, kijun, span_a, span_b = ichimoku(out, p.ichi_tenkan, p.ichi_kijun, p.ichi_senkou)
        cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1, skipna=False)
        entry = _crossing_up((close > cloud_top) & (tenkan > kijun))
        exit_ = close < kijun
    elif t == "zscore":
        mean = sma(close, p.zscore_period)
        spread = close.rolling(p.zscore_period, min_periods=p.zscore_period).std(ddof=0)
        z = (close - mean) / spread.where(spread > 0)
        entry = (z < -p.zscore_entry) & ~(z.shift(1) < -p.zscore_entry)
        exit_ = z > 0
    elif t == "heikin":
        ha_open, ha_close = heikin_ashi(out)
        green = ha_close > ha_open
        streak = green.rolling(p.heikin_bars, min_periods=p.heikin_bars).sum() == p.heikin_bars
        entry = streak & ~green.shift(p.heikin_bars, fill_value=True)
        exit_ = ~green
    elif t in PATTERN_FAMILIES:
        entry, exit_ = _pattern_signals(out, p)
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


def pattern_marks(df: pd.DataFrame, p: StrategyParams) -> dict[str, np.ndarray]:
    """Ce qu'une technique de lecture du graphique regarde, bougie par bougie, pour le dessiner : `top` et `bottom`
    (dernier sommet et dernier creux marquants), `zone_top` et `zone_bottom` (la zone attendue). Calculé par le code
    qui donne les signaux : le graphique montre ce que le bot a vu."""
    out = df.copy()
    out["atr"] = atr(out, p.atr_period)
    marks: dict[str, np.ndarray] = {}
    _pattern_signals(out, p, marks)
    return marks


def _pattern_signals(out: pd.DataFrame, p: StrategyParams, marks: dict | None = None) -> tuple[pd.Series, pd.Series]:
    """La lecture du graphique (tradingbot/patterns.py). Sortie commune, sauf pour la cassure de structure : le rebond
    s'essouffle (clôture sous le plus bas des `breakout_exit_period` bougies précédentes)."""
    t = p.strategy_type
    high, low, open_, close = (out[k].to_numpy(float) for k in ("high", "low", "open", "close"))
    size = out["atr"].to_numpy(float)
    track = None
    if marks is not None:
        if t in ("structure", "balayage"):
            marks["top"], marks["bottom"] = patterns.known_swings(high, low, p.level_window, p.swing_lookback)
        elif t in ("fvg", "order_block", "fibonacci"):
            track = marks["zone_top"], marks["zone_bottom"] = np.full(len(out), np.nan), np.full(len(out), np.nan)
    if t == "structure":
        entry, exit_ = patterns.structure_break(high, low, close, p.level_window, p.swing_lookback)
        return pd.Series(entry, index=out.index), pd.Series(exit_, index=out.index)
    if t == "balayage":
        entry = patterns.liquidity_sweep(high, low, open_, close, p.level_window, p.swing_lookback)
    elif t == "avalement":
        entry = patterns.engulfing(high, low, open_, close, p.pattern_span)
    elif t == "marteau":
        entry = patterns.hammer(high, low, open_, close, size, p.pattern_span, p.wick_ratio)
    elif t == "interieure":
        entry = patterns.inside_break(high, low, close)
    elif t == "divergence":
        strength = rsi(out["close"], p.divergence_period).to_numpy(float)
        entry = patterns.rsi_divergence(low, strength, p.level_window, p.swing_lookback, p.divergence_weak)
    elif t == "double_creux":
        entry = patterns.double_bottom(high, low, close, size, p.level_window, p.swing_lookback, p.double_tol,
                                       p.zone_valid)
    else:
        if t == "fvg":
            top, bottom = patterns.fair_value_gaps(high, low, size, p.gap_min_atr)
        elif t == "order_block":
            top, bottom = patterns.order_blocks(high, low, open_, close, size, p.surge_bars, p.surge_atr)
        else:
            top, bottom = patterns.fib_zones(high, low, size, p.level_window, p.swing_lookback, p.fib_low,
                                             p.fib_high, p.leg_min_atr)
        entry = patterns.zone_retest(low, open_, close, top, bottom, p.zone_valid,
                                     "bottom" if t == "fibonacci" else "top", track)
    lower = out["low"].rolling(p.breakout_exit_period, min_periods=p.breakout_exit_period).min().shift(1)
    return pd.Series(entry, index=out.index), out["close"] < lower


def exit_reason(exit_signal: bool, bars_held: int, p: StrategyParams) -> str | None:
    if exit_signal:
        return p.exit_label
    if p.max_bars_in_trade and bars_held >= p.max_bars_in_trade:
        return "temps"
    return None


def initial_stop(entry_price: float, atr_value: float, p: StrategyParams) -> float:
    return entry_price - p.stop_atr_mult * atr_value
