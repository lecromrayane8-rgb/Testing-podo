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
