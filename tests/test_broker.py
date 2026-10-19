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
