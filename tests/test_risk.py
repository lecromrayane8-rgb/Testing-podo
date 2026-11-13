import math

import pytest

from tradingbot.risk import (
    RiskGuard, RiskParams, clustered_bounds, paired_bounds, position_size, student_t, student_tail,
)


def test_position_size_risks_fixed_fraction():
    qty = position_size(10_000, 100.0, 98.0, RiskParams(risk_per_trade=0.01, max_position_pct=1.0))
    assert qty == pytest.approx(50.0)  # 50 * 2 = 100 = 1 % de 10 000


def test_position_size_capped_by_exposure():
    qty = position_size(10_000, 100.0, 99.9, RiskParams(risk_per_trade=0.01, max_position_pct=0.5))
    assert qty == pytest.approx(50.0)


@pytest.mark.parametrize("stop", [100.0, 101.0])
def test_position_size_rejects_invalid_stop(stop):
    assert position_size(10_000, 100.0, stop, RiskParams()) == 0.0


def test_daily_loss_limit_resets_next_day():
    guard = RiskGuard(RiskParams(daily_loss_limit=0.03, max_drawdown=0.5))
    guard.update(10_000, "2024-01-01")
    guard.update(9_650, "2024-01-01")
    assert not guard.can_open()
    guard.update(9_650, "2024-01-02")
    assert guard.can_open()


def test_drawdown_halt_is_permanent_and_persisted():
    params = RiskParams(daily_loss_limit=0.99, max_drawdown=0.15)
    guard = RiskGuard(params)
    guard.update(10_000, "2024-01-01")
    guard.update(8_400, "2024-01-02")
    guard.update(9_900, "2024-01-03")
    assert "drawdown" in guard.blocked_reason()
    restored = RiskGuard.from_dict(params, guard.to_dict())
    assert not restored.can_open()


def test_trade_stats_bounds_match_the_textbook_formula():
    from tradingbot.risk import TradeStats
    import statistics
    returns = [0.02, -0.01, 0.015, -0.005, 0.01]
    stats = TradeStats()
    for r in returns:
        stats.add(r)
    low, high = stats.bounds()
    se = statistics.stdev(returns) / len(returns) ** 0.5
    assert stats.mean == pytest.approx(statistics.mean(returns))
    assert (low, high) == pytest.approx((stats.mean - 1.96 * se, stats.mean + 1.96 * se))
    assert TradeStats.from_dict(stats.to_dict()) == stats


def test_a_clearly_losing_strategy_is_eliminated_but_not_a_noisy_one():
    from tradingbot.risk import TradeStats, elimination_reason, is_candidate
    losing, noisy, winning = TradeStats(), TradeStats(), TradeStats()
    for k in range(40):
        losing.add(-0.004 + (0.002 if k % 2 else -0.002))
        noisy.add(-0.001 + (0.03 if k % 2 else -0.03))
        winning.add(0.004 + (0.002 if k % 2 else -0.002))
    assert elimination_reason(losing, 20).startswith("perd nettement après 40 trades")
    assert elimination_reason(noisy, 20) is None  # perd un peu, mais le hasard peut l'expliquer
    assert elimination_reason(losing, 0) is None  # 0 = jamais d'élimination
    assert is_candidate(winning) and not is_candidate(noisy)


def test_candidate_threshold_hardens_with_the_number_of_bots_compared():
    from tradingbot.risk import TradeStats, is_candidate
    lucky = TradeStats()  # gain moyen de 2,3 écarts-types : convaincant seul, banal parmi 80 bots
    for k in range(30):
        lucky.add(0.0042 + (0.01 if k % 2 else -0.01))
    assert is_candidate(lucky, n_tests=1)
    assert not is_candidate(lucky, n_tests=80)


@pytest.mark.parametrize("alpha,df,expected", [(0.025, 1, 12.706), (0.025, 5, 2.571), (0.025, 10, 2.228),
                                               (0.025, 30, 2.042), (0.005, 5, 4.032), (0.05, 7, 1.895),
                                               (0.0005, 6, 5.959), (0.025, 1000, 1.962)])
def test_student_thresholds_match_the_tables(alpha, df, expected):
    assert student_t(alpha, df) == pytest.approx(expected, abs=2e-3)
    assert student_tail(student_t(alpha, df), df) == pytest.approx(alpha, rel=1e-6)


def test_few_days_make_a_wide_range_and_many_trades_on_one_day_prove_nothing():
    # Sept jours qui gagnent chacun un peu : la fourchette est nette, et bien plus large qu'avec le 1,96 habituel.
    steady = [(40, 40 * m) for m in (0.004, 0.0045, 0.005, 0.004, 0.0045, 0.005, 0.004)]
    mean, lo, hi = clustered_bounds(steady)
    assert mean == pytest.approx(0.0045, abs=1e-4) and 0 < lo < mean < hi
    spread = math.sqrt(7 / 6 * sum((total - mean * n) ** 2 for n, total in steady)) / 280  # l'écart entre les journées
    assert hi - mean == pytest.approx(2.447 * spread, rel=1e-3)  # 2,447 pour 7 jours, au lieu de 1,96
    assert clustered_bounds(steady, alpha=0.025 / 195)[1] > 0  # même avec un seuil durci pour 195 stratégies
    # Six jours qui perdent un peu et un jour exceptionnel : positif en moyenne, mais rien n'est prouvé.
    lucky = [(40, -0.04)] * 6 + [(40, 2.0)]
    mean, lo, hi = clustered_bounds(lucky)
    assert mean > 0 and lo < 0 < hi
    # Quatre cents trades gagnants le même jour : une seule journée, pas de fourchette du tout.
    mean, lo, hi = clustered_bounds([(400, 4.0)])
    assert mean == pytest.approx(0.01) and math.isnan(lo) and math.isnan(hi)
    assert all(math.isnan(x) for x in clustered_bounds([]))
    assert clustered_bounds([(0, 0.0), (10, 0.1), (10, 0.3)])[0] == pytest.approx(0.02)  # un jour sans trade ne compte pas
    with pytest.raises(ValueError):
        student_t(0.9, 5)


def test_the_gap_between_two_measures_of_the_same_days_is_judged_on_how_it_varies():
    """Deux façons de trader mesurées sur les mêmes journées : une bonne journée l'est pour les deux. La fourchette
    de l'écart vient de ce que l'écart varie d'une journée à l'autre, pas de la dispersion de chaque mesure."""
    days = [-0.004, 0.006, -0.002, 0.008, 0.001, -0.005, 0.003]
    a = [(50, 50 * (m + 0.0005)) for m in days]  # A fait 0,05 % de mieux que B chaque jour, par trade
    b = [(50, 50 * m) for m in days]
    diff, lo, hi = paired_bounds([(na, ta, nb, tb) for (na, ta), (nb, tb) in zip(a, b)])
    assert diff == pytest.approx(0.0005) and lo == pytest.approx(0.0005) and hi == pytest.approx(0.0005)  # écart constant
    assert clustered_bounds(a)[1] < 0 < clustered_bounds(a)[2]  # alors que chaque mesure, seule, ne prouve rien
    # Un écart qui change de signe d'un jour à l'autre : la fourchette contient zéro.
    noisy = [(50, 50 * (m + (0.002 if k % 2 else -0.0015)), 50, 50 * m) for k, m in enumerate(days)]
    diff, lo, hi = paired_bounds(noisy)
    assert lo < 0 < hi and lo < diff < hi
    # La même formule que la fourchette d'une moyenne quand B vaut toujours zéro.
    mean, low, high = clustered_bounds(a)
    assert paired_bounds([(na, ta, na, 0.0) for na, ta in a]) == pytest.approx((mean, low, high))
    # Des nombres de trades différents (la variante sécurisée prend d'autres entrées) : chaque moyenne garde son compte.
    diff, _, _ = paired_bounds([(10, 0.10, 20, 0.10), (30, 0.30, 20, 0.10)])
    assert diff == pytest.approx(0.40 / 40 - 0.20 / 40)
    assert all(math.isnan(x) for x in paired_bounds([]))
    assert all(math.isnan(x) for x in paired_bounds([(0, 0.0, 5, 0.1)]))  # rien d'un côté : pas d'écart
    one = paired_bounds([(5, 0.05, 5, 0.01)])
    assert one[0] == pytest.approx(0.008) and math.isnan(one[1]) and math.isnan(one[2])  # un seul groupe : pas de fourchette
