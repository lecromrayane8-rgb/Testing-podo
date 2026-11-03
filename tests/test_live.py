import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import ccxt
import numpy as np
import pytest

from tests.conftest import FakeBroker, frame_from_closes
from tradingbot.backtest import run_backtest
from tradingbot.config import ConfigError, Settings
from tradingbot.execution import ExecutionParams
from tradingbot.live import MAX_CONSECUTIVE_FAILURES, Bot, BotLog, StateStore, run_bots
from tradingbot.risk import RiskParams
from tradingbot.strategy import StrategyParams

STRAT = StrategyParams(trend_period=50, rsi_period=2, rsi_entry=10, exit_period=5, atr_period=5, stop_atr_mult=3)
RISK = RiskParams(risk_per_trade=0.02, max_position_pct=1.0, daily_loss_limit=0.99, max_drawdown=0.99)
FREE = ExecutionParams(fee_rate=0.0, maker_fee_rate=0.0, slippage=0.0)


def settings(tmp_path: Path, **overrides) -> Settings:
    base = Settings(
        mode="paper", exchange="binance", symbol="BTC/USDT", timeframe="1h", api_key="", api_secret="",
        api_password="", poll_seconds=1, max_capital=0.0, paper_start_balance=10_000.0, data_dir=tmp_path,
        obsidian_vault=None, live_confirmed=False, strategy=STRAT, risk=RISK, execution=FREE,
    )
    return replace(base, **overrides)


def make_bot(tmp_path, df, notes=None, **overrides):
    broker = FakeBroker(df)
    bot = Bot(
        broker, settings(tmp_path, **overrides), StateStore(tmp_path / "state.json"), tmp_path / "trades.csv", notes
    )
    return bot, broker


def dip_scenario(after):
    return frame_from_closes(list(np.linspace(100, 160, 100)) + [157.0, 154.0] + after)


def test_live_matches_backtest(tmp_path, random_walk):
    """Rejouée bougie par bougie, la boucle live prend exactement les trades du backtest."""
    strat = replace(STRAT, stop_atr_mult=100)  # stops intrabar exclus : le live ne voit que les ouvertures ici
    df = random_walk.iloc[:1500]
    expected = run_backtest(df, strat, RISK, execution=FREE).trades
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
    assert (tmp_path / "trades.csv").read_text(encoding="utf-8").count("rebond") == 1


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


LIMIT = replace(FREE, order_type="limit")


@pytest.mark.parametrize("fallback", ["skip", "market"])
def test_live_limit_orders_match_backtest(tmp_path, random_walk, fallback):
    strat = replace(STRAT, stop_atr_mult=100)
    execution = replace(LIMIT, limit_entry_fallback=fallback, limit_timeout_bars=2)
    df = random_walk.iloc[:1500]
    expected = [t for t in run_backtest(df, strat, RISK, execution=execution).trades if t.reason != "fin du test"]

    bot, broker = make_bot(tmp_path, df, strategy=strat, execution=execution)
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


def test_stop_cancels_pending_limit_sell(tmp_path):
    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    bot, broker = make_bot(tmp_path, df, execution=LIMIT)
    for i in range(95, 105):
        bot.step(broker.at_open(i))
    order = bot.state["order"]
    assert order and order["side"] == "sell"  # sortie « rebond » en attente d'exécution
    broker.price = bot.state["position"]["stop"] - 0.01
    bot.step(int(df["ts"].iloc[104]) + 60_000)
    assert broker.limits[order["id"]]["status"] == "canceled"
    assert broker.orders[-1] == ("sell", pytest.approx(order["qty"]), broker.price)
    assert bot.state["position"] is None and bot.state["order"] is None
    assert "stop" in (tmp_path / "trades.csv").read_text(encoding="utf-8")


def test_post_only_rejection_is_retried_at_new_price(tmp_path):
    df = dip_scenario([156.0])
    bot, broker = make_bot(tmp_path, df, execution=LIMIT)
    broker.reject_post_only = 2
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    assert bot.state["order"]["side"] == "buy"


@pytest.mark.parametrize("fallback, expected_orders", [("skip", []), ("market", ["buy"])])
def test_post_only_rejected_three_times_uses_fallback(tmp_path, fallback, expected_orders):
    df = dip_scenario([156.0])
    bot, broker = make_bot(tmp_path, df, execution=replace(LIMIT, limit_entry_fallback=fallback))
    broker.reject_post_only = 3
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    assert bot.state["order"] is None
    assert [o[0] for o in broker.orders] == expected_orders


def test_pending_limit_order_survives_restart(tmp_path):
    df = dip_scenario([156.0, 159.0])
    bot, broker = make_bot(tmp_path, df, execution=LIMIT)
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    assert bot.state["order"]

    restarted = Bot(broker, bot.s, StateStore(tmp_path / "state.json"))
    restarted.step(broker.at_open(103))
    assert restarted.state["order"] is None
    assert restarted.state["position"]["entry_price"] == df["open"].iloc[102]


class StubBot:
    """Bot minimal pour tester la boucle : `step` applique le comportement donné."""

    def __init__(self, name, behaviour):
        self.name = name
        self.behaviour = behaviour
        self.calls = 0
        self.s = SimpleNamespace(mode="paper", exchange="binance")
        self.ex = SimpleNamespace(order_type="market")
        self.log = BotLog(logging.getLogger("tradingbot.test"), {"bot": name})

    def step(self):
        self.calls += 1
        self.behaviour()


def ok():
    pass


def network_down():
    raise ccxt.NetworkError("coupure")


def bug():
    raise RuntimeError("bug")


def test_a_failing_bot_never_stops_the_others():
    healthy, flaky = StubBot("BTC/USDT 1h", ok), StubBot("ETH/USDT 1h", network_down)
    refreshed = []
    run_bots([healthy, flaky], poll_seconds=0, after_cycle=lambda: refreshed.append(1), sleep=lambda s: None, cycles=3)
    assert healthy.calls == 3 and flaky.calls == 3
    assert len(refreshed) == 3


def test_a_bot_with_repeated_bugs_is_set_aside():
    healthy, broken = StubBot("BTC/USDT 1h", ok), StubBot("BTC/USDT 15m", bug)
    run_bots([healthy, broken], poll_seconds=0, sleep=lambda s: None, cycles=8)
    assert broken.calls == MAX_CONSECUTIVE_FAILURES
    assert healthy.calls == 8


def test_all_bots_broken_stops_the_loop():
    with pytest.raises(RuntimeError, match="Tous les bots"):
        run_bots([StubBot("BTC/USDT 1h", bug)], poll_seconds=0, sleep=lambda s: None)


def test_a_dashboard_failure_never_stops_trading():
    def broken_dashboard():
        raise ValueError("rendu impossible")

    bot = StubBot("BTC/USDT 1h", ok)
    run_bots([bot], poll_seconds=0, after_cycle=broken_dashboard, sleep=lambda s: None, cycles=2)
    assert bot.calls == 2


def test_bad_api_keys_stop_everything():
    def refused():
        raise ccxt.AuthenticationError("clé refusée")

    with pytest.raises(ccxt.AuthenticationError):
        run_bots([StubBot("BTC/USDT 1h", refused)], poll_seconds=0, sleep=lambda s: None, cycles=5)


def test_state_records_what_the_dashboard_needs(tmp_path):
    df = dip_scenario([156.0])
    bot, broker = make_bot(tmp_path, df)
    for i in range(95, 103):
        bot.step(broker.at_open(i))
    state = bot.state
    assert state["initial_capital"] == 10_000.0
    assert state["equity"] == pytest.approx(bot.equity(broker.price))
    assert state["last_price"] == broker.price and state["updated_at"]


def test_trade_journal_from_an_older_version_keeps_its_columns(tmp_path):
    """Un journal sans colonne « cout » ne doit pas voir ses nouvelles lignes décalées."""
    import csv as _csv
    old = tmp_path / "trades.csv"
    old.write_text("entree,sortie,prix_entree,prix_sortie,quantite,pnl,raison\n", encoding="utf-8")
    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    bot, broker = make_bot(tmp_path, df)
    for i in range(95, 106):
        bot.step(broker.at_open(i))
    rows = list(_csv.DictReader(old.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["raison"] == "rebond" and float(rows[0]["pnl"]) > 0
