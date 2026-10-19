import numpy as np
import pandas as pd
import pytest

from tradingbot.broker import Balances, Fill
from tradingbot.data import ohlcv_to_frame

HOUR_MS = 3_600_000
T0 = 1_700_000_000_000 - 1_700_000_000_000 % HOUR_MS


def frame_from_closes(closes, spread=0.002, opens=None, lows=None):
    """Bougies 1h construites à partir d'une liste de clôtures."""
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, dtype=float)
    highs = np.maximum(opens, closes) * (1 + spread)
    lows = np.minimum(opens, closes) * (1 - spread) if lows is None else np.asarray(lows, dtype=float)
    rows = [[T0 + i * HOUR_MS, o, h, lo, c, 1.0] for i, (o, h, lo, c) in enumerate(zip(opens, highs, lows, closes))]
    return ohlcv_to_frame(rows)


@pytest.fixture
def random_walk():
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0004, 0.01, 3000)
    return frame_from_closes(100 * np.exp(np.cumsum(returns)))


class FakeBroker:
    """Rejoue un DataFrame : la bougie `i` est en cours, le prix courant est fixé par le test."""

    def __init__(self, df: pd.DataFrame, quote: float = 10_000.0):
        self.df = df
        self.i = 0
        self.price = float(df["open"].iloc[0])
        self.base = 0.0
        self.quote = quote
        self.orders: list[tuple[str, float, float]] = []

    def at_open(self, i: int) -> int:
        self.i = i
        self.price = float(self.df["open"].iloc[i])
        return int(self.df["ts"].iloc[i]) + 1000

    def fetch_candles(self, timeframe, limit):
        return self.df.iloc[max(0, self.i + 1 - limit) : self.i + 1]

    def last_price(self):
        return self.price

    def balances(self):
        return Balances(self.base, self.quote)

    def normalize_qty(self, qty, price):
        return qty

    def market_buy(self, qty):
        cost = qty * self.price
        assert cost <= self.quote + 1e-6
        self.quote -= cost
        self.base += qty
        self.orders.append(("buy", qty, self.price))
        return Fill(qty, self.price, cost)

    def market_sell(self, qty):
        assert qty <= self.base + 1e-12
        self.base -= qty
        self.quote += qty * self.price
        self.orders.append(("sell", qty, self.price))
        return Fill(qty, self.price, qty * self.price)
