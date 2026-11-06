import numpy as np
import pytest

from tests.conftest import frame_from_closes
from tradingbot.indicators import macd
from tradingbot.strategy import StrategyParams, compute_signals, exit_reason

BREAKOUT = StrategyParams(strategy_type="cassure", breakout_period=5, breakout_exit_period=3, trend_period=0,
                          atr_period=3, max_bars_in_trade=0)
CROSS = StrategyParams(strategy_type="croisement", fast_period=3, slow_period=6, trend_period=0, atr_period=3,
                       max_bars_in_trade=0)


def test_breakout_buys_a_new_high_and_sells_a_new_low():
    closes = [100.0] * 10 + [101.0, 106.0, 107.0, 104.0, 99.0]
    data = compute_signals(frame_from_closes(closes, spread=0.0), BREAKOUT)
    assert list(np.flatnonzero(data["entry"])) == [10, 11, 12]  # clôture au-dessus du plus haut des 5 précédentes
    assert data["exit"].iloc[14] and not data["exit"].iloc[13]  # sous le plus bas des 3 précédentes


def test_breakout_never_looks_ahead():
    closes = list(np.linspace(100, 120, 40))
    full = compute_signals(frame_from_closes(closes), BREAKOUT)
    cut = compute_signals(frame_from_closes(closes[:30]), BREAKOUT)
    assert (full["entry"].iloc[:30].to_numpy() == cut["entry"].to_numpy()).all()


def test_crossover_buys_only_on_the_cross():
    closes = [100.0] * 8 + [95.0, 94.0, 93.0, 97.0, 103.0, 108.0, 110.0, 112.0]
    data = compute_signals(frame_from_closes(closes), CROSS)
    crosses = list(np.flatnonzero(data["entry"]))
    assert len(crosses) == 1  # puis on reste au-dessus : pas de nouvel achat
    i = crosses[0]
    fast = data["close"].rolling(3).mean()
    slow = data["close"].rolling(6).mean()
    assert fast.iloc[i] > slow.iloc[i] and fast.iloc[i - 1] <= slow.iloc[i - 1]


def test_trend_filter_blocks_entries_below_the_long_average():
    closes = list(np.linspace(150, 100, 60)) + [101.0, 106.0, 107.0]
    filtered = compute_signals(frame_from_closes(closes), StrategyParams(
        strategy_type="cassure", breakout_period=5, breakout_exit_period=3, trend_period=50, atr_period=3))
    assert not filtered["entry"].any()


def test_exit_labels_and_optional_time_stop():
    assert exit_reason(True, 1, StrategyParams()) == "rebond"
    assert exit_reason(True, 1, BREAKOUT) == "fin de tendance"
    assert exit_reason(False, 24, StrategyParams()) == "temps"
    assert exit_reason(False, 10_000, BREAKOUT) is None  # 0 = pas de stop temporel


def test_warmup_covers_the_longest_period():
    assert StrategyParams().warmup_bars == 201
    assert StrategyParams(strategy_type="cassure", breakout_period=55, trend_period=0).warmup_bars == 57
    assert StrategyParams(strategy_type="croisement", fast_period=50, slow_period=200, trend_period=0).warmup_bars == 202


@pytest.mark.parametrize("kwargs, message", [
    ({"strategy_type": "magique"}, "STRATEGY_TYPE"),
    ({"strategy_type": "croisement", "fast_period": 100, "slow_period": 50}, "FAST_PERIOD"),
    ({"stop_atr_mult": 0}, "STOP_ATR_MULT"),
])
def test_invalid_parameters_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        StrategyParams(**kwargs)


def test_bollinger_rebound_buys_below_the_lower_band_and_sells_at_the_middle():
    closes = [100.0, 101.0] * 15 + [95.0, 97.0, 101.0]
    p = StrategyParams(strategy_type="bollinger", bb_period=20, bb_std=2.0, trend_period=0, atr_period=3)
    data = compute_signals(frame_from_closes(closes), p)
    assert data["entry"].iloc[30] and not data["entry"].iloc[29]  # 95 : sous la bande basse
    assert data["exit"].iloc[32] and not data["exit"].iloc[30]  # 101 : au-dessus du milieu


def test_bollinger_breakout_buys_above_the_upper_band():
    closes = [100.0, 101.0] * 15 + [106.0, 99.0]
    p = StrategyParams(strategy_type="bollinger_cassure", bb_period=20, trend_period=0, atr_period=3,
                       max_bars_in_trade=0)
    data = compute_signals(frame_from_closes(closes), p)
    assert list(np.flatnonzero(data["entry"])) == [30]
    assert data["exit"].iloc[31]


def test_macd_buys_on_the_cross_above_its_signal():
    closes = list(np.linspace(120, 100, 60)) + list(np.linspace(100, 130, 30))
    p = StrategyParams(strategy_type="macd", trend_period=0, atr_period=3, max_bars_in_trade=0)
    data = compute_signals(frame_from_closes(closes), p)
    assert len(np.flatnonzero(data["entry"])) == 1
    i = int(np.flatnonzero(data["entry"])[0])
    assert i >= 60  # au creux ou après, jamais pendant la baisse
    line, signal = macd(data["close"], 12, 26, 9)
    assert line.iloc[i] > signal.iloc[i] and line.iloc[i - 1] <= signal.iloc[i - 1]


def test_momentum_buys_when_price_climbs_back_above_its_past_level():
    closes = list(np.linspace(100, 90, 30)) + list(np.linspace(90, 110, 30))
    p = StrategyParams(strategy_type="momentum", momentum_period=10, trend_period=0, atr_period=3,
                       max_bars_in_trade=0)
    data = compute_signals(frame_from_closes(closes), p)
    entries = list(np.flatnonzero(data["entry"]))
    assert len(entries) == 1
    i = entries[0]
    assert data["close"].iloc[i] > data["close"].iloc[i - 10] and data["close"].iloc[i - 1] <= data["close"].iloc[i - 11]


def test_supertrend_flips_up_in_a_rally_and_down_in_a_crash():
    closes = list(np.linspace(100, 80, 40)) + list(np.linspace(80, 120, 40)) + list(np.linspace(120, 90, 20))
    p = StrategyParams(strategy_type="supertrend", st_period=5, st_mult=2.0, trend_period=0, atr_period=5,
                       max_bars_in_trade=0)
    data = compute_signals(frame_from_closes(closes), p)
    entries = np.flatnonzero(data["entry"])
    assert len(entries) >= 1 and 40 <= entries[0] < 80  # pendant la remontée
    assert data["exit"].iloc[-1]  # la chute finale retourne la tendance


def test_new_families_never_look_ahead():
    closes = list(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.02, 300))))
    for kind in ("bollinger", "bollinger_cassure", "macd", "momentum", "supertrend"):
        p = StrategyParams(strategy_type=kind, trend_period=0, momentum_period=20, atr_period=5)
        full = compute_signals(frame_from_closes(closes), p)
        cut = compute_signals(frame_from_closes(closes[:200]), p)
        assert (full["entry"].iloc[:200].to_numpy() == cut["entry"].to_numpy()).all(), kind


def test_new_parameters_are_validated():
    with pytest.raises(ValueError, match="MACD_FAST"):
        StrategyParams(strategy_type="macd", macd_fast=30, macd_slow=26)
    with pytest.raises(ValueError, match="BB_STD"):
        StrategyParams(strategy_type="bollinger", bb_std=0)


def breakout_frame(volume_spike_at=None):
    closes = list(np.full(60, 100.0)) + [101.0, 102.0, 103.0]  # sort de son range de 60 bougies
    df = frame_from_closes(closes, spread=0.001)
    if volume_spike_at is not None:
        df.loc[df.index[volume_spike_at], "volume"] = 5.0
    return df


def test_volatility_filter_waits_for_candles_that_move_enough():
    base = StrategyParams(strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=0)
    df = breakout_frame()
    assert compute_signals(df, base)["entry"].iloc[60]  # sans filtre : la cassure est prise
    calm = compute_signals(df, StrategyParams(**{**base.__dict__, "min_atr_pct": 0.05}))
    assert not calm["entry"].any()  # bougies d'environ 0,3 % : sous les 5 % exigés


def test_volume_filter_needs_a_crowd_behind_the_move():
    p = StrategyParams(strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=0,
                       volume_mult=2.0)
    assert not compute_signals(breakout_frame(), p)["entry"].any()  # volume constant : jamais deux fois la moyenne
    spiked = compute_signals(breakout_frame(volume_spike_at=60), p)
    assert spiked["entry"].iloc[60] and spiked["entry"].sum() == 1
    assert p.warmup_bars >= p.volume_period + 1


@pytest.mark.parametrize("kwargs", [{"min_atr_pct": -0.1}, {"volume_mult": -1.0}, {"volume_period": 0}])
def test_filter_settings_are_validated(kwargs):
    with pytest.raises(ValueError, match="MIN_ATR_PCT"):
        StrategyParams(**kwargs)


def test_active_hours_keep_only_entries_during_the_chosen_hours():
    base = dict(strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=0)
    df = breakout_frame()
    assert df.index[60].hour == 10  # la cassure arrive sur la bougie de 10 h UTC
    assert not compute_signals(df, StrategyParams(**base, active_hours="13-21"))["entry"].any()
    assert compute_signals(df, StrategyParams(**base, active_hours="8-12"))["entry"].iloc[60]
    assert compute_signals(df, StrategyParams(**base, active_hours="22-11"))["entry"].iloc[60]  # passe minuit


def test_squeeze_buys_a_breakout_only_after_a_calm_market():
    rng = np.random.default_rng(3)
    agitated = list(100 * (1 + 0.02 * np.sin(np.arange(150) / 2)))
    calm = list(100 + 0.01 * rng.standard_normal(40))
    busier = list(100 * (1 + 0.04 * np.sin(np.arange(150, 190) / 2)))  # de plus en plus agité
    p = StrategyParams(strategy_type="cassure", breakout_period=20, breakout_exit_period=10, trend_period=0,
                       squeeze_quantile=0.2, squeeze_period=100)
    assert compute_signals(frame_from_closes(agitated + calm + [108.0]), p)["entry"].iloc[-1]
    assert not compute_signals(frame_from_closes(agitated + busier + [108.0]), p)["entry"].iloc[-1]
    assert p.warmup_bars >= p.bb_period + p.squeeze_period


@pytest.mark.parametrize("kwargs, message", [
    ({"active_hours": "13h-21h"}, "ACTIVE_HOURS"), ({"active_hours": "5-5"}, "ACTIVE_HOURS"),
    ({"active_hours": "13-30"}, "ACTIVE_HOURS"), ({"squeeze_quantile": 1.5}, "SQUEEZE_QUANTILE"),
])
def test_new_filter_settings_are_validated(kwargs, message):
    with pytest.raises(ValueError, match=message):
        StrategyParams(**kwargs)


IMPULSE = StrategyParams(strategy_type="impulsion", impulse_bars=3, impulse_pct=0.02, breakout_exit_period=3,
                         trend_period=0, atr_period=3, max_bars_in_trade=0)


def test_impulse_buys_the_candle_where_a_sudden_move_appears_and_sells_when_it_fades():
    closes = [100.0] * 10 + [100.5, 101.5, 103.0, 105.0, 106.0, 104.0, 101.0]
    data = compute_signals(frame_from_closes(closes, spread=0.0), IMPULSE)
    # +3 % en 3 bougies à la bougie 12 ; les suivantes prolongent la même envolée : pas de nouvel achat.
    assert list(np.flatnonzero(data["entry"])) == [12]
    assert data["exit"].iloc[16] and not data["exit"].iloc[15]  # sous le plus bas des 3 bougies précédentes
    assert IMPULSE.exit_label == "essoufflement"


def test_impulse_never_looks_ahead_and_ignores_small_moves():
    closes = list(100 * np.exp(np.cumsum(np.random.default_rng(11).normal(0, 0.015, 300))))
    full = compute_signals(frame_from_closes(closes), IMPULSE)
    cut = compute_signals(frame_from_closes(closes[:200]), IMPULSE)
    assert (full["entry"].iloc[:200].to_numpy() == cut["entry"].to_numpy()).all()
    calm = compute_signals(frame_from_closes(list(np.linspace(100, 101, 60))), IMPULSE)
    assert not calm["entry"].any()  # +1 % en 60 bougies n'est pas un mouvement soudain


@pytest.mark.parametrize("kwargs", [{"impulse_bars": 0}, {"impulse_pct": 0.0}, {"impulse_pct": 1.5}])
def test_impulse_settings_are_validated(kwargs):
    with pytest.raises(ValueError, match="IMPULSE_BARS"):
        StrategyParams(strategy_type="impulsion", **kwargs)


def test_support_bounce_buys_near_the_floor_and_sells_near_the_ceiling():
    from tests.test_levels import range_market
    df = frame_from_closes(range_market(900, seed=3), spread=0.001)
    data = compute_signals(df, StrategyParams(strategy_type="support", trend_period=0))
    entries, exits = data.index[data["entry"]], data.index[data["exit"]]
    assert len(entries) >= 5 and len(exits) >= 5
    assert (data.loc[entries, "close"] < 103).all()  # on achète en bas du range...
    assert (data.loc[data["exit"] & (data["close"] > 105), "close"] > 106).all()  # ...et on revend en haut


def test_resistance_breakout_buys_the_break_then_sells_when_price_falls_back():
    from tests.test_levels import range_market
    closes = np.concatenate([range_market(400, seed=2), np.linspace(110, 118, 12), np.linspace(118, 104, 15)])
    data = compute_signals(frame_from_closes(closes, spread=0.001),
                           StrategyParams(strategy_type="resistance", trend_period=0))
    entries = np.flatnonzero(data["entry"])
    assert len(entries) >= 1 and 400 <= entries[-1] < 412  # la cassure du plafond du range
    after = np.flatnonzero(data["exit"].to_numpy() & (np.arange(len(data)) > entries[-1]))
    assert len(after) and closes[after[0]] < 110.5  # retombé sous l'ancienne résistance


def test_level_families_never_look_ahead():
    closes = list(100 * np.exp(np.cumsum(np.random.default_rng(5).normal(0, 0.02, 700))))
    for kind in ("support", "resistance"):
        p = StrategyParams(strategy_type=kind, trend_period=0)
        full = compute_signals(frame_from_closes(closes), p)
        cut = compute_signals(frame_from_closes(closes[:450]), p)
        assert (full["entry"].iloc[:450].to_numpy() == cut["entry"].to_numpy()).all(), kind
        assert (full["exit"].iloc[:450].to_numpy() == cut["exit"].to_numpy()).all(), kind


@pytest.mark.parametrize("kwargs", [{"level_window": 0}, {"level_lookback": 8, "level_window": 5},
                                    {"level_touches": 0}, {"level_tol": 0}])
def test_level_settings_are_validated(kwargs):
    with pytest.raises(ValueError, match="LEVEL_"):
        StrategyParams(strategy_type="support", **kwargs)


def test_level_families_wait_for_enough_history_and_name_their_exit():
    p = StrategyParams(strategy_type="support", trend_period=0, level_lookback=150, level_window=5, atr_period=14)
    assert p.warmup_bars >= 150 + 5 + 14
    assert p.exit_label == "résistance ou support cassé"
    assert StrategyParams(strategy_type="resistance").exit_label == "retour sous le niveau"
