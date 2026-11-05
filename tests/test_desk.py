import numpy as np
import pytest

from tests.test_moves import MINUTE, T0, minutes
from tradingbot.desk import MAX_OPEN, Desk
from tradingbot.execution import ExecutionParams
from tradingbot.risk import RiskParams

EXECUTION = ExecutionParams()


def calm(n=60, price=100.0, seed=1):
    rng = np.random.default_rng(seed)
    return minutes(price * np.exp(np.cumsum(rng.normal(0, 0.001, n))))


def desk(tmp_path):
    return Desk(tmp_path / "essais.json", EXECUTION, RiskParams())


def test_a_trial_is_bought_with_its_risk_known_and_sold_at_the_stop(tmp_path):
    d = desk(tmp_path)
    candles = calm()
    price = float(candles["close"].iloc[-1])
    plan = d.plan("PEPE/USDT", 300, "normale", price, candles)
    position = d.open("PEPE/USDT", 300, "normale", price, candles, now=1_000.0)
    assert position["stop"] == pytest.approx(plan["stop"]) and position["stop"] < price
    assert d.state["cash"] == pytest.approx(1000.0 - position["cost"])
    assert 0 < position["risk"] <= 12.5  # toucher le stop coûte au plus ~1 % des 1000 USDT fictifs, frais compris
    assert d.check({"PEPE/USDT": price}, {"PEPE/USDT": candles}, 1_010.0) == []  # rien à faire encore
    trade = d.check({"PEPE/USDT": position["stop"] * 0.999}, {}, 1_020.0)[0]
    assert trade["reason"] == "stop" and trade["pnl"] < 0 and abs(trade["pnl"]) <= 13
    assert d.state["positions"] == [] and d.state["cash"] == pytest.approx(1000.0 + trade["pnl"])


def test_a_trial_follows_the_exit_rules_of_its_option(tmp_path):
    d = desk(tmp_path)
    candles = calm()
    price = float(candles["close"].iloc[-1])
    d.open("BTC/USDT", 300, "rapide", price, candles, now=0.0)  # au plus 5 minutes
    later = calm(65)  # 5 bougies de 1 minute clôturées depuis l'achat
    assert d.check({"BTC/USDT": price}, {"BTC/USDT": later}, 400.0)[0]["reason"] == "temps"
    d.open("ETH/USDT", 300, "longue", price, minutes([price] * 60), now=0.0)  # stop à 3 ATR, bien plus bas
    falling = minutes([price] * 60 + [price * 0.998])  # la dernière clôture passe sous les plus bas des 15 d'avant
    trade = d.check({"ETH/USDT": price * 0.999}, {"ETH/USDT": falling}, 200.0)
    assert trade and trade[0]["reason"] == "essoufflement"


def test_trials_can_be_sold_by_hand_limited_and_reset(tmp_path):
    d = desk(tmp_path)
    candles = calm()
    price = float(candles["close"].iloc[-1])
    d.open("PEPE/USDT", 60, "normale", price, candles, now=0.0)
    with pytest.raises(ValueError, match="déjà ouvert sur PEPE/USDT"):
        d.open("PEPE/USDT", 60, "normale", price, candles, now=1.0)
    for i in range(MAX_OPEN - 1):
        d.open(f"C{i}/USDT", 60, "normale", price, candles, now=2.0)
    with pytest.raises(ValueError, match="Déjà 5 essais ouverts"):
        d.open("X/USDT", 60, "normale", price, candles, now=3.0)
    trade = d.sell(d.state["positions"][0]["id"], price * 1.01, now=600.0)
    assert trade["reason"] == "main" and trade["minutes"] == 10.0
    summary = Desk(tmp_path / "essais.json", EXECUTION, RiskParams()).summary({"C0/USDT": price})  # relu du disque
    assert summary["stats"]["n"] == 1 and summary["trades"][0]["reason_text"] == "vendu à la main"
    assert len(summary["positions"]) == MAX_OPEN - 1 and summary["positions"][0]["pnl"] is not None
    assert summary["curve"][0]["equity"] == pytest.approx(1000.0 + trade["pnl"])
    d.reset(now=700.0)
    assert d.summary({})["equity"] == 1000.0 and d.state["positions"] == []


def test_a_trial_needs_recent_candles_to_place_its_stop(tmp_path):
    d = desk(tmp_path)
    with pytest.raises(ValueError, match="Impossible de placer le stop"):
        d.open("PEPE/USDT", 300, "normale", 1.0, minutes([1.0] * 5), now=0.0)
    assert MINUTE == 60_000 and T0 % MINUTE == 0
