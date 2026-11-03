import math

import numpy as np
import pandas as pd
import pytest

from tradingbot.backtest import BacktestResult, Trade
from tradingbot.robustness import ROBUST, bootstrap_means, evaluate, overall_verdict, period_means, verdict_for


def fake_result(returns, days=400):
    """Résultat de backtest avec un trade par jour, aux rendements donnés (en fraction)."""
    index = pd.date_range("2024-01-01", periods=days * 24, freq="h", tz="UTC")
    trades = [
        Trade(index[i * 24], index[i * 24 + 1], 100.0, 100.0 * (1 + r), 1.0, 100.0, 100.0 * (1 + r), "rebond")
        for i, r in enumerate(returns)
    ]
    rets = np.array(returns)
    metrics = {
        "taux_reussite": float((rets > 0).mean()),
        "esperance_pct": 100 * float(rets.mean()),
        "rendement_total": float(rets.sum() / 100),
    }
    return BacktestResult(trades, pd.Series(1.0, index=index), metrics)


def test_bootstrap_interval_contains_true_mean():
    rng = np.random.default_rng(1)
    values = rng.normal(0.5, 2.0, 400)
    low, high = np.quantile(bootstrap_means(values), [0.025, 0.975])
    assert low < 0.5 < high
    assert high - low == pytest.approx(2 * 1.96 * 2.0 / np.sqrt(400), rel=0.2)


def test_period_means_split_trades_by_entry_date():
    result = fake_result([0.01] * 100 + [-0.01] * 100 + [0.0] * 200)
    assert period_means(result, 4) == pytest.approx([1.0, -1.0, 0.0, 0.0])


def test_periods_with_few_trades_are_not_judged():
    result = fake_result([0.01] * 3, days=400)
    assert all(math.isnan(p) for p in period_means(result, 4)[1:])


@pytest.mark.parametrize(
    "nb, exp, low_adj, periods, expected",
    [
        (20, 1.0, 0.5, [1, 1, 1, 1], "trop peu de trades"),
        (200, -0.1, -0.3, [1, 1, 1, 1], "perd de l'argent"),
        (200, 0.2, -0.05, [1, 1, 1, 1], "positif, peut-être de la chance"),
        (200, 0.2, 0.05, [1, -1, -1, 1], "positif, peut-être de la chance"),
        (200, 0.2, 0.05, [1, 1, math.nan, -1], "positif, peut-être de la chance"),
        (200, 0.2, 0.05, [1, 1, 1, -1], ROBUST),
    ],
)
def test_verdicts(nb, exp, low_adj, periods, expected):
    assert verdict_for(nb, exp, low_adj, periods) == expected


def test_testing_many_markets_raises_the_bar():
    returns = [0.0112, -0.0088] * 200  # espérance +0,12 %, écart-type 1 % : passe seul, pas parmi 1000 essais
    alone = evaluate("BTC/USDT 1h", fake_result(returns), n_tests=1)
    among_many = evaluate("BTC/USDT 1h", fake_result(returns), n_tests=1000)
    assert alone.ci_low > 0 and alone.verdict == ROBUST
    assert among_many.ci_low_adjusted < alone.ci_low_adjusted
    assert among_many.verdict != ROBUST


def test_overall_verdict_names_robust_markets():
    strong = evaluate("ETH/USDT 4h", fake_result([0.01, 0.02, -0.005] * 120), n_tests=2)
    losing = evaluate("BTC/USDT 1h", fake_result([-0.01, 0.005] * 150), n_tests=2)
    assert "ETH/USDT 4h" in overall_verdict([strong, losing])
    assert "aucun des 1 marchés" in overall_verdict([losing])
