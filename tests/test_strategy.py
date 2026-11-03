import numpy as np
import pytest

from tests.conftest import frame_from_closes
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
