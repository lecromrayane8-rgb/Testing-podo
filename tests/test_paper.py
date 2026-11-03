import ccxt
import pytest

from tradingbot.broker import PaperBroker
from tradingbot.execution import ExecutionParams


class Market:
    def __init__(self):
        self.last = 100.0
        self.bid, self.ask = 100.0, 100.1

    def last_price(self):
        return self.last

    def best_bid_ask(self):
        return self.bid, self.ask

    def price_to_precision(self, price):
        return round(price, 2)

    def normalize_qty(self, qty, price):
        return qty


@pytest.fixture
def paper(tmp_path):
    market = Market()
    broker = PaperBroker(market, tmp_path / "wallet.json", 1_000.0, ExecutionParams(maker_fee_rate=0.001))
    return broker, market


def test_limit_buy_fills_only_when_price_trades_through(paper):
    broker, market = paper
    order_id, price = broker.place_limit("buy", 1.0, 100.0)
    assert broker.balances().quote == pytest.approx(1_000 - 100.1)  # fonds bloqués, frais maker inclus
    assert broker.order_status(order_id).open  # au même prix : pas forcément servi
    market.last = 99.9
    status = broker.order_status(order_id)
    assert not status.open and status.fill.price == 100.0
    assert broker.balances().base == 1.0


def test_cancel_releases_funds(paper):
    broker, _ = paper
    order_id, _ = broker.place_limit("buy", 1.0, 99.0)
    status = broker.cancel(order_id)
    assert not status.open and status.fill is None
    assert broker.balances().quote == pytest.approx(1_000.0)


def test_post_only_rejects_orders_that_would_cross(paper):
    broker, _ = paper
    with pytest.raises(ccxt.OrderImmediatelyFillable):
        broker.place_limit("buy", 1.0, 100.1)


def test_limit_sell_pays_maker_fee(paper):
    broker, market = paper
    broker.market_buy(2.0)
    quote_before = broker.balances().quote
    order_id, _ = broker.place_limit("sell", 2.0, 101.0)
    market.last = 101.5
    assert broker.order_status(order_id).fill.quote == pytest.approx(2 * 101 * 0.999)
    assert broker.balances().quote == pytest.approx(quote_before + 2 * 101 * 0.999)


def test_market_orders_pay_the_spread(paper):
    broker, market = paper  # acheteurs à 100,0, vendeurs à 100,1
    slip = broker.execution.slippage
    assert broker.market_buy(1.0).price == pytest.approx(100.1 * (1 + slip))  # on achète au vendeur
    assert broker.market_sell(1.0).price == pytest.approx(100.0 * (1 - slip))  # on vend à l'acheteur


def test_market_order_falls_back_to_last_price_without_order_book(paper):
    broker, market = paper

    def no_book():
        raise ccxt.NetworkError("carnet indisponible")

    market.best_bid_ask = no_book
    assert broker.market_buy(1.0).price == pytest.approx(100.0 * (1 + broker.execution.slippage))
