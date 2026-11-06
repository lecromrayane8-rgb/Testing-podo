import time

import numpy as np
import pytest

from tests.conftest import frame_from_closes
from tradingbot.levels import level_series, levels_now, nearest, pivot_points, round_levels, round_step


def range_market(n=400, low=100.0, high=110.0, period=40, seed=1):
    """Un marché qui fait des allers-retours entre deux niveaux (avec un peu de bruit)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    mid, half = (low + high) / 2, (high - low) / 2
    return mid + half * np.sin(2 * np.pi * t / period) + rng.normal(0, 0.15, n)


def test_pivots_are_the_clear_tops_and_bottoms():
    high = np.array([1, 2, 3, 2, 1, 2, 5, 2, 1, 1, 1], dtype=float)
    low = high - 0.5
    tops, bottoms = pivot_points(high, low, 2)
    assert list(tops) == [2, 6] and list(bottoms) == [4, 8]  # 8 : début d'un creux plat


def test_a_range_shows_its_floor_as_support_and_its_ceiling_as_resistance():
    df = frame_from_closes(range_market(), spread=0.001)
    levels = level_series(df, window=5, lookback=200)
    last = levels.iloc[-1]
    price = df["close"].iloc[-1]
    assert 98.5 < last["support"] < 101.5 and last["support_touches"] >= 3
    assert 108.5 < last["resistance"] < 111.5 and last["resistance_touches"] >= 3
    assert last["support"] < price < last["resistance"]
    zones = levels_now(df, window=5, lookback=200)
    support, resistance = nearest(zones, price)
    assert support.price == pytest.approx(last["support"]) and resistance.price == pytest.approx(last["resistance"])


def test_levels_never_look_ahead():
    closes = range_market(500, seed=4)
    full = level_series(frame_from_closes(closes), window=5, lookback=150)
    cut = level_series(frame_from_closes(closes[:300]), window=5, lookback=150)
    a, b = full.iloc[:300].to_numpy(float), cut.to_numpy(float)
    assert np.allclose(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1))


def test_the_live_window_finds_exactly_the_same_levels_as_the_whole_history():
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0, 0.01, 1200)))
    df = frame_from_closes(closes)
    full = level_series(df, window=5, lookback=150)
    start = 500  # le bot en direct ne voit que les bougies à partir d'ici
    window = level_series(df.iloc[start:], window=5, lookback=150)
    settled = start + 150 + 5 + 14  # au-delà, la fenêtre contient tout ce dont un niveau dépend
    a = full.iloc[settled:].to_numpy(float)
    b = window.iloc[settled - start:].to_numpy(float)
    assert np.allclose(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1))
    assert np.isfinite(a[:, 0]).mean() > 0.5  # il y a bien des supports à comparer


def test_a_broken_resistance_becomes_a_support():
    closes = np.concatenate([range_market(300, seed=2), np.linspace(111, 122, 30), 121 + np.zeros(20)])
    df = frame_from_closes(closes, spread=0.001)
    last = level_series(df, window=5, lookback=300).iloc[-1]
    assert 108.5 < last["support"] < 112  # l'ancien plafond du range est devenu le plancher le plus proche


def test_no_level_on_a_too_short_or_featureless_history():
    flat = frame_from_closes(np.full(30, 100.0), spread=0.0)
    levels = level_series(flat, window=5, lookback=150)
    assert levels["support"].isna().all() and levels["resistance"].isna().all()
    assert levels_now(frame_from_closes([100.0, 101.0])) == []


def test_round_numbers_follow_the_size_of_the_price():
    assert round_step(68_400) == 1000 and round_levels(68_400) == (68_000, 69_000)
    assert round_levels(3_520) == (3_500, 3_600)
    below, above = round_levels(0.1532)
    assert below == pytest.approx(0.15) and above == pytest.approx(0.16)


def test_levels_stay_fast_on_long_minute_histories():
    closes = 100 * np.exp(np.cumsum(np.random.default_rng(9).normal(0, 0.002, 20_000)))
    df = frame_from_closes(closes)
    start = time.perf_counter()
    level_series(df, window=5, lookback=150)
    assert time.perf_counter() - start < 3.0
