import numpy as np
import pandas as pd

from tests.conftest import frame_from_closes
from tradingbot.indicators import atr, rsi, sma


def test_sma_needs_full_window():
    out = sma(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0 and out.iloc[3] == 3.0


def test_rsi_extremes():
    up = rsi(pd.Series(np.arange(1.0, 30.0)), 14)
    down = rsi(pd.Series(np.arange(30.0, 1.0, -1)), 14)
    flat = rsi(pd.Series([5.0] * 30), 14)
    assert np.isnan(up.iloc[5])
    assert up.iloc[-1] == 100.0
    assert down.iloc[-1] == 0.0
    assert flat.iloc[-1] == 50.0


def test_rsi_bounded(random_walk):
    values = rsi(random_walk["close"], 2).dropna()
    assert values.between(0, 100).all()


def test_atr_constant_range():
    df = frame_from_closes([100.0] * 50, spread=0.01)
    assert abs(atr(df, 14).iloc[-1] - 2.0) < 1e-9
