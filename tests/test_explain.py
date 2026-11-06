import numpy as np
import pytest

from tests.conftest import frame_from_closes
from tests.test_levels import range_market
from tradingbot.explain import KINDS, diagnose, lessons, pct, price, read_chart, rule_sentence
from tradingbot.lab import ALL_VARIANTS
from tradingbot.strategy import STRATEGY_TYPES, StrategyParams


def test_numbers_are_written_the_french_way():
    assert pct(0.0123) == "+1,2 %" and pct(-0.0081, 2) == "−0,81 %" and pct(0) == "0,0 %" and pct(None) == "—"
    assert [price(x) for x in (68412.5, 3520.44, 130.0, 134.52, 0.1532, 0.0000245)] == [
        "68 412", "3 520", "130", "134,52", "0,1532", "0,0000245"]


def test_an_uptrend_is_read_as_an_uptrend():
    df = frame_from_closes(100 * np.exp(np.cumsum(np.full(400, 0.002) + np.random.default_rng(1).normal(0, 0.004, 400))))
    reading = read_chart(df)
    assert reading["trend"] == "hausse" and reading["sentences"][0].startswith("Tendance de fond : hausse")
    assert reading["rsi"] > 50


def test_a_range_shows_its_support_its_resistance_and_a_trader_scenario():
    df = frame_from_closes(range_market(400), spread=0.002)
    reading = read_chart(df)
    assert reading["support"]["touches"] >= 2 and reading["resistance"]["touches"] >= 2
    assert reading["support"]["distance"] < 0 < reading["resistance"]["distance"]
    plan = reading["plan"]
    assert plan and plan["stop"] < reading["support"]["price"] < plan["target"] and plan["ratio"] > 0
    assert any(s.startswith("Scénario d'un trader") for s in reading["sentences"])
    assert any("Chiffres ronds" in s for s in reading["sentences"])


def test_a_short_history_says_it_cannot_judge_the_trend_yet():
    reading = read_chart(frame_from_closes(np.linspace(100, 110, 60)))
    assert reading["trend"] is None and "Pas encore assez d'historique" in reading["sentences"][0]


def test_every_family_and_every_lab_variant_explains_why_it_buys():
    for kind in STRATEGY_TYPES:
        assert rule_sentence(StrategyParams(strategy_type=kind)).endswith(".")
    for name, params in ALL_VARIANTS.items():
        assert len(rule_sentence(params)) > 30, name
    text = rule_sentence(StrategyParams(strategy_type="support", trend_period=200, volume_mult=2.0))
    assert "tendance de fond haussière" in text and "2 fois sa moyenne" in text


@pytest.mark.parametrize("trade, kind", [
    ({"reason": "stop", "net": -0.012, "gross": -0.009, "family": "support", "mfe": 0.001, "risk": 0.011}, "faux_depart"),
    ({"reason": "stop", "net": -0.012, "gross": -0.009, "family": "support", "mfe": 0.02, "risk": 0.011}, "gain_rendu"),
    ({"reason": "stop", "net": -0.012, "gross": -0.009, "family": "cassure", "mfe": 0.005, "risk": 0.011}, "stop"),
    ({"reason": "fin de tendance", "net": -0.001, "gross": 0.002, "fees": 0.003}, "frais"),
    ({"reason": "fin de tendance", "net": 0.03, "gross": 0.033, "mfe": 0.035, "fees": 0.003}, "gagne"),
    ({"reason": "fin de tendance", "net": 0.004, "gross": 0.007, "mfe": 0.05, "fees": 0.003}, "gain_partiel"),
    ({"reason": "temps", "net": -0.004, "gross": -0.001, "bars": 48}, "temps"),
    ({"reason": "fin de tendance", "net": -0.02, "gross": -0.017, "family": "momentum"}, "sortie_regle"),
    ({"reason": "liquidation", "net": -0.33, "gross": -0.33}, "liquidation"),
    ({"reason": "fin du test", "net": 0.01, "gross": 0.012}, "ouvert"),
])
def test_each_finished_trade_gets_a_plain_diagnosis(trade, kind):
    d = diagnose(trade)
    assert d["kind"] == kind and d["title"] == KINDS[kind] and d["text"]
    assert kind == "ouvert" or d["lesson"]


def trades(strategy, n, win_rate, trend=None, symbol="BTC/USDT", net_win=0.02, net_loss=-0.01):
    wins = round(n * win_rate)
    return [{"strategy": strategy, "symbol": symbol, "trend": trend, "net": net_win if i < wins else net_loss,
             "kind": "gagne" if i < wins else "faux_depart"} for i in range(n)]


def test_lessons_count_their_trades_and_warn_when_they_are_too_few():
    few = lessons(trades("Rebond sur support", 6, 0.5))
    assert len(few) == 1 and "6 trades, 50 % gagnants" in few[0]["text"] and "Trop peu de trades" in few[0]["text"]
    assert "Faux départ" in few[0]["text"]


def test_a_trend_lesson_needs_enough_trades_on_each_side_and_a_clear_gap():
    clear = trades("Rebond sur support", 10, 0.7, "hausse") + trades("Rebond sur support", 10, 0.2, "baisse")
    texts = [x["text"] for x in lessons(clear)]
    assert any("70 % du temps quand la tendance de fond monte, contre 20 %" in t for t in texts)
    small = trades("Rebond sur support", 5, 0.8, "hausse") + trades("Rebond sur support", 5, 0.2, "baisse")
    assert not any("tendance de fond monte" in x["text"] for x in lessons(small))
    close = trades("Rebond sur support", 10, 0.5, "hausse") + trades("Rebond sur support", 10, 0.4, "baisse")
    assert not any("tendance de fond monte" in x["text"] for x in lessons(close))


def test_the_best_and_worst_coin_need_five_trades_each():
    mixed = trades("Cassure", 6, 0.8, symbol="SOL/USDT") + trades("Cassure", 6, 0.2, symbol="DOGE/USDT") + \
        trades("Cassure", 3, 1.0, symbol="PEPE/USDT")
    coin = next(x["text"] for x in lessons(mixed) if "meilleure crypto" in x["text"])
    assert "meilleure crypto : SOL" in coin and "la moins bonne : DOGE" in coin and "PEPE" not in coin
