from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import FakeBroker, frame_from_closes
from tradingbot.backtest import run_backtest
from tradingbot.config import ConfigError, Settings
from tradingbot.live import Bot, StateStore
from tradingbot.risk import RiskParams
from tradingbot.strategy import StrategyParams

STRAT = StrategyParams(trend_period=50, rsi_period=2, rsi_entry=10, exit_period=5, atr_period=5, stop_atr_mult=3)
RISK = RiskParams(risk_per_trade=0.02, max_position_pct=1.0, daily_loss_limit=0.99, max_drawdown=0.99)


def settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings(
        mode="paper", exchange="binance", symbol="BTC/USDT", timeframe="1h", api_key="", api_secret="",
        api_password="", poll_seconds=1, max_capital=0.0, paper_start_balance=10_000.0, fee_rate=0.0,
        slippage=0.0, data_dir=tmp_path, live_confirmed=False, strategy=STRAT, risk=RISK,
    )
    return replace(base, **overrides)


def make_bot(tmp_path, df, **overrides):
    broker = FakeBroker(df)
    bot = Bot(broker, settings(tmp_path, **overrides), StateStore(tmp_path / "state.json"), tmp_path / "trades.csv")
    return bot, broker


def dip_scenario(after):
    return frame_from_closes(list(np.linspace(100, 160, 100)) + [157.0, 154.0] + after)


def test_live_matches_backtest(tmp_path, random_walk):
    """Rejouée bougie par bougie, la boucle live prend exactement les trades du backtest."""
    strat = replace(STRAT, stop_atr_mult=100)  # stops intrabar exclus : le live ne voit que les ouvertures ici
    df = random_walk.iloc[:1500]
    expected = run_backtest(df, strat, RISK, fee_rate=0.0, slippage=0.0).trades
    expected = [t for t in expected if t.reason != "fin du test"]

    bot, broker = make_bot(tmp_path, df, strategy=strat)
    for i in range(1, len(df)):
        bot.step(broker.at_open(i))

    buys = [o for o in broker.orders if o[0] == "buy"]
    sells = [o for o in broker.orders if o[0] == "sell"]
    assert len(expected) > 10
    assert len(sells) == len(expected)
    for trade, buy, sell in zip(expected, buys, sells):
        assert buy[2] == pytest.approx(trade.entry_price)
        assert sell[2] == pytest.approx(trade.exit_price)
        assert buy[1] == pytest.approx(trade.qty)


def test_buys_on_signal_and_sells_on_rebound(tmp_path):
    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    bot, broker = make_bot(tmp_path, df)
    for i in range(95, 102):
        bot.step(broker.at_open(i))
    assert broker.orders == []  # la bougie 101 (signal) est encore en cours : pas d'achat anticipé
    bot.step(broker.at_open(102))
    assert broker.orders[0][0] == "buy" and bot.state["position"]
    for i in range(103, 106):
        bot.step(broker.at_open(i))
    assert [o[0] for o in broker.orders] == ["buy", "sell"]
    assert bot.state["position"] is None
    assert bot.state["capital"] > 10_000
    assert (tmp_path / "trades.csv").read_text().count("rebond") == 1


def test_stop_triggers_on_live_price(tmp_path):
    df = dip_scenario([150.0, 149.0, 148.0])
    bot, broker = make_bot(tmp_path, df)
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    stop = bot.state["position"]["stop"]
    broker.price = stop - 0.01
    bot.step(int(df["ts"].iloc[102]) + 60_000)
    assert broker.orders[-1][0] == "sell"
    assert bot.state["position"] is None
    assert bot.state["capital"] < 10_000


def test_same_candle_processed_once_and_state_survives_restart(tmp_path):
    df = dip_scenario([150.0, 149.0])
    bot, broker = make_bot(tmp_path, df)
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    now = broker.at_open(102)
    bot.step(now + 5_000)
    bot.step(now + 10_000)
    assert len(broker.orders) == 1

    restarted = Bot(broker, bot.s, StateStore(tmp_path / "state.json"))
    assert restarted.state["position"] == bot.state["position"]
    restarted.step(now + 15_000)
    assert len(broker.orders) == 1


def test_max_capital_limits_what_the_bot_uses(tmp_path):
    df = dip_scenario([150.0])
    bot, broker = make_bot(tmp_path, df, max_capital=500.0)
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    assert bot.state["capital"] == 500.0
    assert broker.orders[0][1] * broker.orders[0][2] <= 500.0 + 1e-6


def test_live_mode_requires_explicit_confirmation(tmp_path):
    keys = dict(api_key="k", api_secret="s")
    with pytest.raises(ConfigError, match="CONFIRM_LIVE_TRADING"):
        settings(tmp_path, mode="live", max_capital=100.0, **keys).validate_for_trading()
    with pytest.raises(ConfigError, match="MAX_CAPITAL"):
        settings(tmp_path, mode="live", live_confirmed=True, **keys).validate_for_trading()
    with pytest.raises(ConfigError, match="API_KEY"):
        settings(tmp_path, mode="testnet").validate_for_trading()
    settings(tmp_path, mode="live", live_confirmed=True, max_capital=100.0, **keys).validate_for_trading()
