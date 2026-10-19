from dataclasses import replace

import numpy as np
import pytest

from tests.conftest import frame_from_closes
from tradingbot.backtest import format_report, run_backtest
from tradingbot.execution import ExecutionParams
from tradingbot.risk import RiskParams
from tradingbot.strategy import StrategyParams

SMALL = StrategyParams(trend_period=50, rsi_period=2, rsi_entry=10, exit_period=5, atr_period=5, stop_atr_mult=3)
LOOSE_RISK = RiskParams(risk_per_trade=0.02, max_position_pct=1.0, daily_loss_limit=0.99, max_drawdown=0.99)
FREE = ExecutionParams(fee_rate=0.0, maker_fee_rate=0.0, slippage=0.0)


def uptrend_with_dip(after_dip):
    closes = list(np.linspace(100, 160, 100))
    closes += [157.0, 154.0]  # repli -> RSI(2) survendu, toujours au-dessus de la MM50
    closes += after_dip
    return frame_from_closes(closes)


def test_dip_then_rebound_is_a_winning_trade():
    df = uptrend_with_dip([156.0, 159.0, 161.0, 162.0])
    result = run_backtest(df, SMALL, LOOSE_RISK, execution=FREE)
    assert len(result.trades) == 1
    trade = result.trades[0]
    signal_bar = 101
    assert trade.entry_time == df.index[signal_bar + 1]
    assert trade.entry_price == df["open"].iloc[signal_bar + 1]  # exécution à l'ouverture suivante
    assert trade.reason == "rebond"
    assert trade.pnl > 0


def test_dip_then_crash_hits_stop():
    df = uptrend_with_dip([140.0, 130.0, 125.0])
    result = run_backtest(df, SMALL, LOOSE_RISK, execution=FREE)
    trade = result.trades[0]
    assert trade.reason == "stop"
    assert trade.pnl < 0


def test_fees_reduce_pnl():
    df = uptrend_with_dip([156.0, 159.0, 161.0, 162.0])
    free = run_backtest(df, SMALL, LOOSE_RISK, execution=FREE).trades[0]
    paid = run_backtest(df, SMALL, LOOSE_RISK, execution=ExecutionParams(fee_rate=0.002, slippage=0.001)).trades[0]
    assert paid.pnl < free.pnl


def test_no_lookahead(random_walk):
    full = run_backtest(random_walk, SMALL, LOOSE_RISK)
    cut = 2000
    partial = run_backtest(random_walk.iloc[:cut], SMALL, LOOSE_RISK)
    horizon = random_walk.index[cut - 2]
    before_full = [(t.entry_time, t.exit_time, t.pnl) for t in full.trades if t.exit_time < horizon]
    before_partial = [(t.entry_time, t.exit_time, t.pnl) for t in partial.trades if t.exit_time < horizon]
    assert len(before_full) > 10
    assert before_full == before_partial


def test_metrics_are_consistent(random_walk):
    result = run_backtest(random_walk, SMALL, LOOSE_RISK, initial_capital=10_000)
    m = result.metrics
    assert m["nb_trades"] == len(result.trades)
    assert 0 <= m["taux_reussite"] <= 1
    assert m["capital_final"] == pytest.approx(10_000 + sum(t.pnl for t in result.trades))
    assert m["drawdown_max"] <= 0
    assert "VERDICT" in format_report(m)


def test_drawdown_guard_stops_new_entries(random_walk):
    tight = RiskParams(risk_per_trade=0.05, max_position_pct=1.0, daily_loss_limit=0.99, max_drawdown=0.02)
    result = run_backtest(random_walk, SMALL, tight)
    assert result.metrics["arret_garde_fou"]
    no_halt = RiskParams(risk_per_trade=0.05, max_position_pct=1.0, daily_loss_limit=0.99, max_drawdown=0.99)
    loose = run_backtest(random_walk, SMALL, no_halt)
    assert len(result.trades) < len(loose.trades)


LIMIT = ExecutionParams(order_type="limit", fee_rate=0.001, maker_fee_rate=0.0, slippage=0.0005)


def test_limit_orders_fill_at_their_price_and_save_fees():
    df = uptrend_with_dip([156.0, 159.0, 161.0, 162.0])
    market = run_backtest(df, SMALL, LOOSE_RISK, execution=replace(LIMIT, order_type="market")).trades[0]
    limit = run_backtest(df, SMALL, LOOSE_RISK, execution=LIMIT).trades[0]
    assert limit.entry_price == df["open"].iloc[102]  # pas de glissement pour un ordre limite
    assert market.entry_price > limit.entry_price
    assert limit.reason == "rebond"
    assert limit.pnl > market.pnl


def test_limit_entry_not_filled_if_price_never_trades_below():
    df = uptrend_with_dip([158.0, 161.0, 163.0, 164.0])
    df.loc[df.index[102], "low"] = df["open"].iloc[102]  # le prix ne repasse jamais sous l'ordre
    skipped = run_backtest(df, SMALL, LOOSE_RISK, execution=LIMIT)
    assert skipped.trades == []
    assert skipped.metrics["entrees_abandonnees"] == 1

    chased = run_backtest(df, SMALL, LOOSE_RISK, execution=replace(LIMIT, limit_entry_fallback="market"))
    assert chased.trades[0].entry_price == pytest.approx(df["open"].iloc[103] * (1 + LIMIT.slippage))


def test_invalid_order_type_is_rejected():
    with pytest.raises(ValueError, match="ORDER_TYPE"):
        ExecutionParams(order_type="limite")
