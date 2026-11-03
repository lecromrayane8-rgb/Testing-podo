import pytest

from tradingbot.risk import RiskGuard, RiskParams, position_size


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
