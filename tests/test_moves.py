import numpy as np
import pytest

from tradingbot.backtest import run_backtest
from tradingbot.data import ohlcv_to_frame
from tradingbot.execution import ExecutionParams
from tradingbot.moves import OPTIONS, option_params, round_trip_cost, study, trade_plan, verdict
from tradingbot.risk import RiskParams
from tradingbot.robustness import research_risk

MINUTE = 60_000
T0 = 1_700_000_000_000 - 1_700_000_000_000 % MINUTE
EXECUTION = ExecutionParams()  # frais 0,1 % et glissement 0,05 % : un aller-retour coûte 0,3 %


def minutes(closes, spread=0.0005):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    rows = [[T0 + i * MINUTE, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c, 1.0]
            for i, (o, c) in enumerate(zip(opens, closes))]
    return ohlcv_to_frame(rows)


def jumps(n=12_000, every=150, follow=0.0, seed=2):
    """Marche au hasard avec, toutes les `every` minutes, un bond de +2,5 % en 5 minutes, suivi d'une poursuite
    moyenne de `follow` sur les 10 minutes suivantes."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.0008, n)
    for start in range(300, n - 30, every):
        steps[start:start + 5] += 0.005  # +2,5 % en 5 bougies
        steps[start + 5:start + 15] += follow / 10
    return minutes(100 * np.exp(np.cumsum(steps)))


def test_the_study_finds_the_same_moves_and_tests_three_ways_out():
    df = jumps()
    result = study(df, 300, EXECUTION, RiskParams(), equity=1000.0)
    planted = len(range(300, 12_000 - 30, 150))
    assert planted - 5 <= result["events"] <= planted + 15  # les bonds plantés (et quelques-uns du hasard)
    assert result["cost"] == pytest.approx(0.003) and result["threshold"] == 0.02
    assert len(result["path"]["minutes"]) == 60 and len(result["path"]["median"]) == 60
    assert [o["key"] for o in result["options"]] == list(OPTIONS)
    normal = result["options"][1]
    direct = run_backtest(df, option_params(300, "normale"), research_risk(RiskParams()), 10_000.0, EXECUTION)
    expected = [t.return_pct for t in direct.trades if t.reason != "fin du test"]
    assert normal["trades"] == len(expected) and normal["mean"] == pytest.approx(np.mean(expected))  # même moteur
    assert 0 < normal["plan"]["loss_pct"] <= 0.0125  # toucher le stop coûte au plus ~1 % du compte (frais compris)
    assert result["verdict"]["kind"] in ("bad", "neutral")  # des bonds sans suite : pas d'opportunité


def test_moves_that_keep_going_are_seen_as_a_lead_not_a_proof():
    result = study(jumps(follow=0.03), 300, EXECUTION, RiskParams())
    assert result["verdict"]["kind"] == "good" and "À confirmer en argent fictif" in result["verdict"]["text"]
    assert result["path"]["median"][-1] > 0.01  # la courbe médiane monte après le bond


@pytest.mark.parametrize("option, kind, words", [
    ({"trades": 8, "mean": 0.01, "ci_low": -0.01, "ci_high": 0.03}, "few", "Trop peu"),
    ({"trades": 90, "mean": -0.004, "ci_low": -0.006, "ci_high": -0.002}, "bad", "−0,40 %"),
    ({"trades": 90, "mean": 0.004, "ci_low": 0.001, "ci_high": 0.007}, "good", "+0,40 %"),
    ({"trades": 90, "mean": -0.001, "ci_low": -0.004, "ci_high": 0.002}, "neutral", "de −0,40 % à +0,20 %"),
])
def test_the_verdict_says_it_plainly_good_or_bad(option, kind, words):
    result = verdict(option, cost=0.003, days=30)
    assert result["kind"] == kind and words.replace("−", "-") in result["text"]


def test_a_trial_risks_about_one_percent_of_the_account():
    plan = trade_plan(100.0, 1.0, 300, "normale", 1000.0, RiskParams(), EXECUTION)
    assert plan["entry"] == pytest.approx(100.05) and plan["stop"] == pytest.approx(98.05)  # 2 ATR sous l'achat
    assert plan["qty"] == pytest.approx(5.0) and plan["loss_pct"] == pytest.approx(0.0112, abs=0.0005)
    assert trade_plan(100.0, 0.0, 300, "normale", 1000.0, RiskParams(), EXECUTION) is None
    assert round_trip_cost(EXECUTION) == pytest.approx(0.003)
    with pytest.raises(ValueError):
        option_params(120, "normale")
