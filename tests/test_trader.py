import json
from datetime import datetime, timezone

import numpy as np
import pytest

from tests.conftest import HOUR_MS, frame_from_closes
from tradingbot.execution import FUTURES, ExecutionParams
from tradingbot.lab import FUTURES_LAB_FILE, LAB_FILE, LIMIT_LAB_FILE, SHORT_LAB_FILE
from tradingbot.strategy import StrategyParams
from tradingbot.trader import (
    Account, Play, Trader, TraderSettings, choose_playbook, replay, side_cost, summary,
)

SPOT = ExecutionParams()  # 0,1 % de frais et 0,05 % de glissement par ordre
NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def lab(path, rows, execution):
    path.write_text(json.dumps({"rows": rows, "execution": execution}), encoding="utf-8")


def row(variant, tf, verdict, exp, trades=80):
    return {"variant": variant, "timeframe": tf, "verdict": verdict, "expectancy_pct": exp, "trades": trades}


def test_the_trader_plays_only_what_the_labs_retained_and_with_fees_no_higher_than_tested(tmp_path):
    spot = {"order_type": "market", "fee_rate": 0.001, "maker_fee_rate": 0.001, "slippage": 0.0005}
    limit = {**spot, "order_type": "limit"}
    lab(tmp_path / LAB_FILE, [row("Momentum 28", "1d", "à surveiller", 0.4), row("MACD 12/26/9", "1d", "instable", 0.9),
                              row("Croisement MM 50/200", "1d", "prometteur", 0.2)], spot)
    lab(tmp_path / LIMIT_LAB_FILE, [row("Cassure 20/10", "15m", "à surveiller", 0.05)], limit)
    lab(tmp_path / FUTURES_LAB_FILE, [row("Rebond sur support", "5m", "à surveiller", 0.03),
                                      row("Momentum 28", "1d", "à surveiller", 0.6)],
        {**spot, "fee_rate": 0.0005, "maker_fee_rate": 0.0002, "slippage": 0.0002, "funding_rate_8h": 0.0001})
    lab(tmp_path / SHORT_LAB_FILE, [row("Inconnue", "5m", "prometteur", 9.0)], spot)
    futures = choose_playbook(tmp_path, TraderSettings(profile="futures", plays=10), SPOT)
    assert [p.key for p in futures] == ["Croisement MM 50/200 (1d)", "Momentum 28 (1d)", "Cassure 20/10 (15m)",
                                        "Rebond sur support (5m)"]  # « prometteur » d'abord, puis le meilleur
    assert next(p for p in futures if p.name == "Momentum 28").expectancy == 0.6  # la meilleure version gardée
    spot_plays = choose_playbook(tmp_path, TraderSettings(profile="spot", plays=10), SPOT)
    assert [p.key for p in spot_plays] == ["Croisement MM 50/200 (1d)", "Momentum 28 (1d)"]  # ni limites ni futures
    assert len(choose_playbook(tmp_path, TraderSettings(plays=1), SPOT)) == 1
    assert choose_playbook(tmp_path / "vide", TraderSettings(), SPOT) == []
    assert side_cost(FUTURES) < side_cost(SPOT)


def play(kind="cassure", tf="1h", **kwargs):
    params = StrategyParams(strategy_type=kind, trend_period=0, atr_period=5, **kwargs)
    return Play("Test", tf, "à surveiller", "Laboratoire long terme", 0.1, 50, custom=params)


def test_each_trade_risks_one_percent_and_leverage_is_capped(tmp_path):
    acc = Account(tmp_path / "c.json", TraderSettings(capital=1000, max_leverage=3), FUTURES, NOW)
    pos, why = acc.open(play(stop_atr_mult=2), "BTC/USDT", 100.0, 0.25, 0, NOW, {})
    assert why == "" and pos["risk"] == pytest.approx(0.005, rel=1e-3)
    assert pos["notional"] == pytest.approx(1000 * 0.01 / pos["risk"], rel=1e-3)  # 2 000 : levier 2
    assert pos["leverage"] == pytest.approx(2.0, rel=1e-2)
    value = acc.value({})  # 1 000 moins les frais du premier achat
    second, _ = acc.open(play(stop_atr_mult=2), "ETH/USDT", 100.0, 0.25, 0, NOW, {})
    assert acc.exposure() == pytest.approx(3 * value)  # plafonné à 3 fois le compte
    assert second["notional"] < pos["notional"]
    none, why = acc.open(play(stop_atr_mult=2), "SOL/USDT", 100.0, 0.25, 0, NOW, {})
    assert none is None and why == "pas assez de marge disponible"
    assert acc.open(play(), "BTC/USDT", 100.0, 1.0, 0, NOW, {})[1] == "déjà une position sur cette crypto"
    spot = Account(None, TraderSettings(profile="spot"), SPOT, NOW)
    pos, _ = spot.open(play(stop_atr_mult=2), "BTC/USDT", 100.0, 0.25, 0, NOW, {})
    assert pos["notional"] <= 1000 + 1e-9  # au comptant : jamais plus que le compte


def test_a_closed_trade_is_counted_explained_and_judged(tmp_path):
    acc = Account(tmp_path / "c.json", TraderSettings(capital=1000, eliminate_after=3), FUTURES, NOW)
    p = play(kind="support", stop_atr_mult=1.5)
    for _ in range(3):
        pos, _ = acc.open(p, "PEPE/USDT", 1.0, 0.01, 0, NOW, {})
        acc.close(pos, pos["stop"] / (1 - FUTURES.slippage), "stop", NOW)
    trades = acc.state["trades"]
    assert len(trades) == 3 and all(t["diagnosis"]["kind"] in ("faux_depart", "stop") for t in trades)
    assert all(t["net"] == pytest.approx(-0.015 - 2 * 0.0007, abs=2e-3) for t in trades)
    assert acc.state["cash"] == pytest.approx(1000 + sum(t["pnl"] for t in trades))
    assert "perd nettement" in acc.eliminated(p, "PEPE/USDT")  # le gardien ne la joue plus sur PEPE
    assert acc.open(p, "PEPE/USDT", 1.0, 0.01, 0, NOW, {})[0] is None
    assert acc.open(p, "DOGE/USDT", 1.0, 0.01, 0, NOW, {})[0] is not None  # mais toujours sur les autres
    acc.save()
    again = Account(tmp_path / "c.json", TraderSettings(), FUTURES, NOW)
    assert len(again.state["trades"]) == 3 and again.state["positions"]


def test_the_account_is_liquidated_below_its_maintenance_margin():
    acc = Account(None, TraderSettings(capital=1000, max_leverage=20, risk_per_trade=0.05), FUTURES, NOW)
    pos, _ = acc.open(play(stop_atr_mult=1), "BTC/USDT", 100.0, 0.1, 0, NOW, {})
    assert pos["notional"] > 15000
    sold = acc.liquidate_if_needed({"BTC/USDT": 93.0}, NOW)  # une chute de 7 % bien au-delà du stop
    assert [t["reason"] for t in sold] == ["liquidation"] and sold[0]["diagnosis"]["kind"] == "liquidation"
    assert acc.liquidate_if_needed({"BTC/USDT": 93.0}, NOW) == []


class ReplayExchange:
    """Rejoue des bougies d'une heure : à la bougie i, le prix est son ouverture et les bougies vont jusqu'à elle."""

    def __init__(self, frames):
        self.frames, self.i = frames, 0

    def fetch_tickers(self, symbols=None):
        return {s: {"last": float(df["open"].iloc[self.i])} for s, df in self.frames.items()}

    def fetch_ohlcv(self, symbol, timeframe, limit):
        df = self.frames[symbol].iloc[max(0, self.i + 1 - limit):self.i + 1]
        return df[["ts", "open", "high", "low", "close", "volume"]].values.tolist()


@pytest.mark.parametrize("kind", ["cassure", "support"])
def test_the_live_trader_takes_exactly_the_trades_of_its_replay(tmp_path, random_walk, kind):
    df = random_walk.iloc[:1200]
    p = play(kind=kind, stop_atr_mult=30, max_bars_in_trade=0)  # un stop jamais atteint : seuls les signaux comptent
    settings = TraderSettings(capital=1000, risk_per_trade=0.05)
    expected = replay({("BTC/USDT", "1h"): df}, [p], settings, FUTURES).state["trades"]
    exchange = ReplayExchange({"BTC/USDT": df})
    account = Account(tmp_path / "c.json", settings, FUTURES, NOW)
    trader = Trader(exchange, account, [p], ["BTC/USDT"])
    for i in range(1, len(df)):
        exchange.i = i
        trader.cycle(datetime.fromtimestamp((int(df["ts"].iloc[i]) + 1000) / 1000, timezone.utc))
    live = account.state["trades"]
    assert len(expected) > 5 and len(live) == len(expected)
    for a, b in zip(live, expected):
        assert a["entry_price"] == pytest.approx(b["entry_price"]) and a["exit_price"] == pytest.approx(b["exit_price"])
        assert a["reason"] == b["reason"]
    assert all(t["why"] and t["diagnosis"]["text"] for t in live)


def test_the_replay_keeps_its_limits_and_explains_every_trade(random_walk):
    frames = {(s, "1h"): random_walk.iloc[k * 300:k * 300 + 1500] for k, s in enumerate(["A/USDT", "B/USDT", "C/USDT"])}
    acc = replay(frames, [play(stop_atr_mult=3, max_bars_in_trade=48)], TraderSettings(max_positions=2), FUTURES)
    trades = acc.state["trades"]
    assert len(trades) > 10 and all(t["reading"] for t in trades)  # la lecture du graphique au signal
    times = sorted([(t["entry_time"], 1) for t in trades] + [(t["exit_time"], -1) for t in trades],
                   key=lambda x: (x[0], x[1]))
    open_now, peak = 0, 0
    for _, step in times:
        open_now += step
        peak = max(peak, open_now)
    assert peak <= 2  # jamais plus de 2 positions à la fois
    view = summary(acc.state)
    assert view["exists"] and view["replay"] and view["count"] == len(trades) and view["lessons"]
    assert view["trades"][0]["exit_time"] >= view["trades"][-1]["exit_time"]  # les plus récents d'abord


def test_settings_are_checked():
    with pytest.raises(ValueError, match="TRADER_PROFILE"):
        TraderSettings(profile="levier")
    with pytest.raises(ValueError, match="TRADER_LEVERAGE"):
        TraderSettings(max_leverage=50)
    with pytest.raises(ValueError, match="TRADER_RISK"):
        TraderSettings(risk_per_trade=0.2)
    assert TraderSettings(profile="spot", max_leverage=5).leverage == 1.0
    assert summary(None) == {"exists": False}


def test_a_trader_without_strategies_just_waits(tmp_path):
    exchange = ReplayExchange({"BTC/USDT": frame_from_closes(np.linspace(100, 110, 50))})
    exchange.i = 49
    account = Account(tmp_path / "c.json", TraderSettings(), FUTURES, NOW)
    assert Trader(exchange, account, [], ["BTC/USDT"]).cycle(NOW) == []
    assert account.state["value"] == 1000 and json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert HOUR_MS == 3_600_000
