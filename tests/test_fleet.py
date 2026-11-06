"""Le moteur des bots (fleet.Book) : comptes, stop, objectif, liquidation, vente à découvert, textes et graphique."""
import numpy as np
import pytest

from tests.conftest import HOUR_MS, T0
from tradingbot.execution import FUTURES
from tradingbot.fleet import (
    CAPITAL, LIQ_SAFETY, MAINTENANCE, SIDES, Book, Spec, chart_view, condition, entry_rule, exit_rule, judge,
    lookback_for, mirror, signals_for, simulate, technique,
)
from tradingbot.lab import ALL_VARIANTS
from tradingbot.strategy import STRATEGY_TYPES
from tradingbot.swarm import LIBRARY, new_bot


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, section="court", symbol="X/USDT", tf="1h"):
    return Spec(section, symbol, tf, name, side, target, leverage)


def test_a_long_stopped_out_loses_its_leverage_times_the_move_plus_fees():
    s = spec("Cassure 20/10", "long", 0.0, 3.0)  # stop à 2 ATR
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 1.0)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    price = 100.0 * (1 + FUTURES.slippage)
    assert entry["price"] == pytest.approx(price)
    assert entry["leverage"] == 3 and entry["notional"] == pytest.approx(3000.0)
    assert entry["stop"] == pytest.approx(price - 2.0)
    [exit_] = book.range_bar(T0 + HOUR_MS, 100.0, 100.5, 97.0)
    fill = (price - 2.0) * (1 - FUTURES.slippage)
    qty = 3000.0 / price
    pnl = qty * (fill - price) - qty * fill * FUTURES.fee_rate - 3000.0 * FUTURES.fee_rate
    assert exit_["reason"] == "stop"
    assert exit_["pnl"] == pytest.approx(pnl)
    assert exit_["roi"] == pytest.approx(pnl / 1000.0)
    assert book.s["cash"] == pytest.approx(1000.0 + pnl)
    assert book.s["count"] == 1 and book.s["wins"] == 0


def test_a_short_reaches_its_target_and_pays_maker_fees_and_funding():
    s = spec("Cassure 20/10", "short", 2.0, 5.0)
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 0.5)
    [entry] = book.open_bar(T0 + HOUR_MS, 100.0)
    price = 100.0 * (1 - FUTURES.slippage)  # le vendeur reçoit un peu moins que le graphique
    assert entry["side"] == "short" and entry["stop"] == pytest.approx(price + 1.0)
    assert entry["target"] == pytest.approx(price - 2.0) and entry["leverage"] == 5
    assert book.range_bar(T0 + HOUR_MS, 100.0, 100.2, 99.5) == []
    book.close_bar(T0 + HOUR_MS, 99.8, False, False, 0.5)
    [exit_] = book.range_bar(T0 + 17 * HOUR_MS, 99.0, 99.2, 97.0)  # 16 h après l'achat
    qty = 5000.0 / price
    target = price - 2.0
    funding = 5000.0 * FUTURES.funding_rate_8h * 2
    pnl = qty * (price - target) - qty * target * FUTURES.maker_fee_rate - funding - 5000.0 * FUTURES.fee_rate
    assert exit_["reason"] == "objectif" and exit_["exit_price"] == pytest.approx(target)
    assert exit_["funding"] == pytest.approx(funding)
    assert exit_["pnl"] == pytest.approx(pnl) and exit_["pnl"] > 0
    assert exit_["gross"] == pytest.approx(1 - target / 100.0)


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("risk", [0.002, 0.03, 0.12, 0.25, 0.6])
def test_leverage_is_reduced_so_the_stop_always_comes_before_liquidation(side, risk):
    s = spec("Cassure 20/10", side, 0.0, 10.0)
    book = Book(s, 1000.0, FUTURES)
    atr_value = risk * 100.0 / 2.0  # stop à 2 ATR
    book.close_bar(T0, 100.0, True, False, atr_value)
    [pos] = book.open_bar(T0 + HOUR_MS, 100.0)
    assert 1 <= pos["leverage"] <= 10
    assert pos["leverage"] <= max(1.0, LIQ_SAFETY / (pos["risk"] + MAINTENANCE))
    if pos["leverage"] > 1:
        assert pos["stop"] > pos["liquidation"] if side == "long" else pos["stop"] < pos["liquidation"]


def test_a_gap_through_the_liquidation_price_loses_the_whole_capital():
    s = spec("Cassure 20/10", "long", 0.0, 5.0)
    book = Book(s, 1000.0, FUTURES)
    book.close_bar(T0, 100.0, True, False, 1.0)  # stop à 2 %, liquidation vers −19,5 %
    book.open_bar(T0 + HOUR_MS, 100.0)
    [exit_] = book.range_bar(T0 + 2 * HOUR_MS, 70.0, 71.0, 69.0)  # ouverture à −30 %
    assert exit_["reason"] == "liquidation" and exit_["pnl"] == pytest.approx(-1000.0)
    assert book.s["cash"] == 0.0 and book.s["dead"] == "liquidé"
    book.close_bar(T0 + 2 * HOUR_MS, 70.0, True, False, 1.0)
    assert book.s["pending"] is None  # un bot liquidé ne trade plus


def test_a_short_sees_the_chart_upside_down(random_walk):
    p = technique("Cassure 20/10")
    short = signals_for(random_walk, p, "short")
    low = random_walk["low"].rolling(p.breakout_period).min().shift(1)
    high = random_walk["high"].rolling(p.breakout_exit_period).max().shift(1)
    close = random_walk["close"]
    assert short.entry.sum() > 10
    assert np.array_equal(short.entry[50:], (close < low).to_numpy()[50:])
    assert np.array_equal(short.exit[50:], (close > high).to_numpy()[50:])
    flipped = mirror(random_walk)
    assert (flipped["high"] >= flipped["low"]).all()


def test_the_backtest_respects_the_warm_up_and_closes_what_is_left(random_walk):
    s = spec("Croisement MM 20/100", "long", 0.0, 3.0)
    book = simulate(random_walk, s)
    warm = s.params.warmup_bars
    first = int(random_walk["ts"].iloc[warm])
    assert book.s["trades"] and all(t["entry_ts"] >= first for t in book.s["trades"])
    assert book.position is None
    assert book.s["cash"] == pytest.approx(CAPITAL + sum(t["pnl"] for t in book.s["trades"]))


def test_judge_cuts_the_history_like_the_lab(random_walk):
    s = spec("Cassure 20/10", "long", 2.0, 3.0)
    book = simulate(random_walk, s)
    start, end = int(random_walk["ts"].iloc[0]), int(random_walk["ts"].iloc[-1])
    r = judge(book, start, end)
    assert r["study_n"] + r["valid_n"] + r["test_n"] == r["trades"] == len(book.s["trades"])
    assert r["sv_n"] == r["study_n"] + r["valid_n"] and r["key"] == s.key
    assert r["total_return"] == pytest.approx(book.s["cash"] / 1000.0 - 1)
    assert r["drawdown"] <= 0


@pytest.mark.parametrize("name", LIBRARY)
def test_the_live_window_gives_the_signals_of_the_whole_history(random_walk, name):
    """Le direct ne lit que les dernières bougies (lookback_for) : ses signaux doivent être ceux du backtest, qui lit
    tout l'historique. Comparé sur des bougies tirées au hasard, pour chaque technique et dans les deux sens."""
    p = technique(name)
    look = lookback_for(p)
    df = random_walk.iloc[:look + 400]
    picks = np.random.default_rng(3).choice(np.arange(look - 1, len(df)), size=12, replace=False)
    for side in SIDES:
        full = signals_for(df, p, side)
        for i in picks:
            window = signals_for(df.iloc[i - look + 1:i + 1], p, side)
            assert (window.entry[-1], window.exit[-1]) == (full.entry[i], full.exit[i]), (side, i)
            assert window.atr[-1] == pytest.approx(full.atr[i], rel=1e-6)


@pytest.mark.parametrize("family", STRATEGY_TYPES)
@pytest.mark.parametrize("side", SIDES)
def test_every_rule_is_explained_in_both_directions(family, side):
    name = next(n for n in LIBRARY if technique(n).strategy_type == family)
    s = spec(name, side, 2.0)
    text = entry_rule(s) + " " + exit_rule(s)
    assert ("achète" if side == "long" else "vend à découvert") in text
    assert "de le " not in text and "  " not in text and "objectif" in text
    assert condition(s.params, side)


def test_the_library_covers_every_family_and_every_name_is_known():
    assert len(LIBRARY) == len(set(LIBRARY)) >= 39
    assert {technique(n).strategy_type for n in LIBRARY} == set(STRATEGY_TYPES)
    assert all(n in ALL_VARIANTS or technique(n) for n in LIBRARY)


@pytest.mark.parametrize("name", ["Cassure 20/10", "Bollinger rebond 20/2 + MM200", "Keltner 20/2", "Ichimoku 9/26/52",
                                  "Écart à la moyenne 20/2", "Parabolic SAR", "VWAP + EMA 9/21"])
def test_the_chart_shows_the_rule_lines_trades_and_position(random_walk, name):
    s = spec(name, "short", 2.0)
    bot = new_bot({**s.__dict__, "label": "2", "label_text": "test"}, 1000.0, int(random_walk["ts"].iloc[500]))
    view = chart_view(random_walk.iloc[:602], {"slot": bot["id"], "bot": bot}, FUTURES)
    assert len(view["candles"]) == 150
    assert view["lines"] and all(len(ln["values"]) == 150 for ln in view["lines"])
    assert all(t["side"] == "short" for t in view["rule_trades"])
    assert view["position"] is None and view["symbol"] == "X/USDT"
