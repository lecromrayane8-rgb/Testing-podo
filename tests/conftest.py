import ccxt
import numpy as np
import pandas as pd
import pytest

from tradingbot.broker import Balances, Fill, OrderStatus
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
    """Rejoue un DataFrame : la bougie `i` est en cours, le prix courant est fixé par le test.

    Les ordres limites sont exécutés comme dans le backtest : à l'ouverture de la bougie i, ceux
    placés avant elle le sont si la bougie i-1 a traversé leur prix.
    """

    def __init__(self, df: pd.DataFrame, quote: float = 10_000.0):
        self.df = df
        self.i = 0
        self.price = float(df["open"].iloc[0])
        self.base = 0.0
        self.quote = quote
        self.orders: list[tuple[str, float, float]] = []
        self.limits: dict[str, dict] = {}
        self.reject_post_only = 0

    def at_open(self, i: int) -> int:
        self.i = i
        self.price = float(self.df["open"].iloc[i])
        prev = self.df.iloc[i - 1]
        for order in self.limits.values():
            if order["status"] == "open" and order["bar"] <= i - 1:
                if (order["side"] == "buy" and prev["low"] < order["price"]) or (
                    order["side"] == "sell" and prev["high"] > order["price"]
                ):
                    self._fill(order)
        return int(self.df["ts"].iloc[i]) + 1000

    def fetch_candles(self, timeframe, limit):
        return self.df.iloc[max(0, self.i + 1 - limit) : self.i + 1]

    def last_price(self):
        return self.price

    def best_bid_ask(self):
        return self.price, self.price

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

    def place_limit(self, side, qty, price):
        if self.reject_post_only:
            self.reject_post_only -= 1
            raise ccxt.OrderImmediatelyFillable("post-only")
        if side == "buy":
            assert qty * price <= self.quote + 1e-6
            self.quote -= qty * price
        else:
            assert qty <= self.base + 1e-12
            self.base -= qty
        order_id = f"L{len(self.limits) + 1}"
        self.limits[order_id] = {"side": side, "qty": qty, "price": price, "bar": self.i, "status": "open"}
        return order_id, price

    def order_status(self, order_id):
        order = self.limits[order_id]
        if order["status"] == "closed":
            notional = order["qty"] * order["price"]
            return OrderStatus(False, order["qty"], Fill(order["qty"], order["price"], notional))
        return OrderStatus(order["status"] == "open", 0.0, None)

    def cancel(self, order_id):
        order = self.limits[order_id]
        if order["status"] == "open":
            if order["side"] == "buy":
                self.quote += order["qty"] * order["price"]
            else:
                self.base += order["qty"]
            order["status"] = "canceled"
        return self.order_status(order_id)

    def _fill(self, order):
        if order["side"] == "buy":
            self.base += order["qty"]
        else:
            self.quote += order["qty"] * order["price"]
        order["status"] = "closed"
        self.orders.append((order["side"], order["qty"], order["price"]))
