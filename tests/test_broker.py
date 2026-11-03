import pytest

from tradingbot.broker import CcxtBroker


@pytest.fixture
def broker():
    b = CcxtBroker.__new__(CcxtBroker)  # sans connexion réseau
    b.base, b.quote = "BTC", "USDT"
    b.market = {"maker": 0.001, "taker": 0.002}
    return b


def order(side, type_, **extra):
    return {"id": "1", "side": side, "type": type_, "filled": 2.0, "cost": 200.0, "status": "closed", **extra}


def test_reported_fees_are_used(broker):
    fill = broker._to_fill(order("buy", "market", fees=[{"currency": "BTC", "cost": 0.002}]))
    assert fill.qty == pytest.approx(1.998)
    assert fill.quote == pytest.approx(200.0)


def test_missing_fees_are_estimated_with_maker_or_taker_rate(broker):
    assert broker._to_fill(order("buy", "limit")).quote == pytest.approx(200.2)
    assert broker._to_fill(order("sell", "market")).quote == pytest.approx(199.6)


class PublicExchange:
    """Connexion publique simulée : compte les requêtes envoyées à la plateforme."""

    def __init__(self):
        self.markets = {"PEPE/USDT": {"base": "PEPE", "quote": "USDT"}}
        self.calls = []

    def market(self, symbol):
        return self.markets[symbol]

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls.append(("bougies", limit))
        return [[1_700_000_000_000 + i * 60_000, 1.0, 1.1, 0.9, 1.0 + i, 5.0] for i in range(limit)]

    def fetch_ticker(self, symbol):
        self.calls.append(("prix",))
        return {"last": 0.0000123, "close": 0.0000123}

    def fetch_order_book(self, symbol, limit=5):
        self.calls.append(("carnet",))
        return {"bids": [[0.0000122, 1e9]], "asks": [[0.0000124, 1e9]]}


def test_bots_of_one_pair_share_candles_and_prices(monkeypatch):
    import tradingbot.broker as broker_module
    from types import SimpleNamespace
    clock = [100.0]
    monkeypatch.setattr(broker_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    ex = PublicExchange()
    shared = CcxtBroker("binance", "PEPE/USDT", exchange=ex, cache_seconds=5)

    long = shared.fetch_candles("1m", 300)
    short = shared.fetch_candles("1m", 100)  # servi par la requête précédente, mêmes dernières bougies
    assert len(short) == 100 and short["close"].iloc[-1] == long["close"].iloc[-1]
    shared.last_price(), shared.last_price(), shared.best_bid_ask(), shared.best_bid_ask()
    assert ex.calls == [("bougies", 300), ("prix",), ("carnet",)]

    shared.fetch_candles("1m", 600)  # plus long que ce qui est en cache : nouvelle requête
    clock[0] += 6  # le cache a expiré : on redemande les données fraîches
    shared.fetch_candles("1m", 100), shared.last_price()
    assert ex.calls[3:] == [("bougies", 600), ("bougies", 600), ("prix",)]


def test_without_cache_every_call_reaches_the_exchange():
    ex = PublicExchange()
    alone = CcxtBroker("binance", "PEPE/USDT", exchange=ex)
    alone.fetch_candles("1m", 50), alone.fetch_candles("1m", 50), alone.last_price(), alone.last_price()
    assert ex.calls == [("bougies", 50), ("bougies", 50), ("prix",), ("prix",)]
