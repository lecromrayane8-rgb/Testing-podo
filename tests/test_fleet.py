import math

import numpy as np
import pandas as pd
import pytest

from tests.conftest import HOUR_MS, T0, frame_from_closes
from tradingbot.data import COLUMNS
from tradingbot.execution import FUTURES
from tradingbot.fleet import (
    CAPITAL, LIQ_SAFETY, MAINTENANCE, SECTION_KEYS, SECTIONS, SIDES, Book, Fleet, FleetSettings, Spec, chart_view,
    choose, condition, entry_rule, exit_rule, fleet_view, label, lookback_for, mirror, select, settings_from_env,
    signals_for, simulate, technique,
)
from tradingbot.lab import ALL_VARIANTS
from tradingbot.strategy import STRATEGY_TYPES


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, section="court", symbol="X/USDT", tf="1h"):
    return Spec(section, symbol, tf, name, side, target, leverage)


# --- le moteur ------------------------------------------------------------------------------------------------------

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


# --- le direct, exactement comme le backtest -------------------------------------------------------------------------

class FakeMarket:
    """Rejoue des bougies d'une heure : au pas i, la bougie i vient de se clôturer et la i+1 commence."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames, self.i = frames, 0
        self.calls = 0

    def now_ms(self) -> int:
        df = next(iter(self.frames.values()))
        return int(df["ts"].iloc[self.i]) + HOUR_MS + 2500

    def fetch_tickers(self, symbols=None):
        return {s: {"last": float(df["open"].iloc[self.i + 1])} for s, df in self.frames.items()}

    def fetch_ticker(self, symbol):
        return self.fetch_tickers()[symbol]

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        self.calls += 1
        df = self.frames[symbol]
        return df.iloc[max(0, self.i + 2 - limit):self.i + 2][COLUMNS].values.tolist()


def one_bot_selection(s: Spec, bench=()):
    row = {"section": s.section, "symbol": s.symbol, "timeframe": s.timeframe, "technique": s.technique,
           "side": s.side, "target_r": s.target_r, "leverage": s.leverage, "label": "2", "label_text": "test"}
    return {"id": "choix-1", "settings": {"capital": 1000.0},
            "sections": [{"key": s.section, "title": SECTION_KEYS[s.section].title, "timeframes": [s.timeframe],
                          "leverage": s.leverage, "tested": 1, "eligible": 1, "bots": [row], "bench": list(bench)}]}


COMPARED = ("side", "entry_ts", "exit_ts", "reason", "leverage")


@pytest.mark.parametrize("name,side,target", [
    ("Cassure 20/10", "long", 0.0), ("Cassure 20/10", "short", 2.0), ("Repli RSI(2) < 10 + MM200", "long", 2.0),
    ("Supertrend 10/3", "short", 0.0), ("Rebond sur support", "long", 2.0), ("Croisement MM 20/100", "short", 2.0),
    ("Bollinger rebond 20/2 + MM200", "short", 0.0), ("MACD 12/26/9", "long", 2.0),
])
def test_live_bots_take_exactly_the_trades_of_their_backtest(monkeypatch, random_walk, name, side, target):
    monkeypatch.setattr(Fleet, "retire_reason", lambda self, book: None)  # le bot reste en place jusqu'au bout
    df = random_walk.iloc[:1150].copy()
    s = spec(name, side, target, 3.0)
    backtest = [t for t in simulate(df, s).s["trades"] if t["reason"] != "fin du test"]
    index = {int(t): i for i, t in enumerate(df["ts"])}
    look = lookback_for(s.params)
    first = next(t for t in backtest if index[t["exit_ts"]] >= look)  # le direct démarre quand le backtest est à plat
    start = index[first["exit_ts"]]
    market = FakeMarket({s.symbol: df})
    market.i = start
    fleet = Fleet(market, None, one_bot_selection(s), clock=lambda: market.now_ms() / 1000, read=False)
    for i in range(start, len(df) - 1):
        market.i = i
        fleet.cycle(market.now_ms())
    live = fleet.state["slots"][0]["bot"]["book"]["trades"]
    end = int(df["ts"].iloc[-1])
    expected = [t for t in backtest if t["entry_ts"] > int(df["ts"].iloc[start]) and t["exit_ts"] < end]
    live = [t for t in live if t["exit_ts"] < end]
    assert len(expected) >= 2
    assert [tuple(t[k] for k in COMPARED) for t in live] == [tuple(t[k] for k in COMPARED) for t in expected]
    for a, b in zip(live, expected):
        assert a["price"] == pytest.approx(b["price"], rel=1e-9)
        assert a["exit_price"] == pytest.approx(b["exit_price"], rel=1e-9)
        assert a["net"] == pytest.approx(b["net"], rel=1e-6, abs=1e-9)  # le capital diffère : pas les rendements
        assert a["roi"] == pytest.approx(b["roi"], rel=1e-6, abs=1e-9)


def test_the_live_stop_is_watched_at_the_current_price_between_two_candles():
    closes = np.r_[np.linspace(100, 120, 60), np.full(10, 120.0)]
    df = frame_from_closes(closes)
    s = spec("Cassure 20/10", "long", 0.0, 3.0)
    market = FakeMarket({s.symbol: df})
    market.i = 40
    fleet = Fleet(market, None, one_bot_selection(s), clock=lambda: market.now_ms() / 1000, read=False)
    fleet.cycle(market.now_ms())
    book = fleet.state["slots"][0]["bot"]["book"]
    assert book["position"] is not None  # nouveau sommet à chaque bougie : il est entré
    stop = book["position"]["stop"]
    market.frames[s.symbol] = df.assign(open=df["open"].where(df.index != df.index[41], stop * 0.99))
    events = fleet.cycle(market.now_ms() + 60_000)  # même bougie en cours, prix sous le stop
    assert book["position"] is None and book["trades"][-1]["reason"] == "stop"
    assert any(e["kind"] == "sortie" for e in events)


# --- le choix --------------------------------------------------------------------------------------------------------

def row(symbol, tech, side="long", score=1.0, study=0.001, valid=0.001, test=0.001, n=60, target=0.0, liq=False):
    family = technique(tech).strategy_type
    return {"section": "court", "symbol": symbol, "timeframe": "1h", "technique": tech, "side": side,
            "target_r": target, "leverage": 3.0, "key": f"{symbol}|1h|{tech}|{side}|{target:g}", "family": family,
            "trades": n, "sv_n": n, "study_n": n // 2, "valid_n": n // 2, "test_n": 12, "study_mean": study,
            "valid_mean": valid, "sv_mean": (study + valid) / 2, "test_mean": test, "score": score,
            "liquidated": liq, "total_return": 0.1, "drawdown": -0.2}


def test_the_choice_prefers_winners_on_both_periods_with_different_coins_and_techniques():
    rows = [
        row("A/USDT", "Cassure 20/10", score=9.0), row("A/USDT", "Supertrend 10/3", score=8.0),
        row("B/USDT", "Cassure 20/10", score=7.0), row("C/USDT", "Supertrend 10/3", score=6.0),
        row("D/USDT", "Momentum 50", score=5.0), row("E/USDT", "Cassure 55/20", score=4.0),
        row("F/USDT", "Momentum 50", score=3.0),
        row("G/USDT", "Rebond sur support", score=20.0, study=-0.001),  # perd sur l'étude : pas en premier
        row("H/USDT", "MACD 12/26/9", score=30.0, liq=True),  # liquidé dans le backtest : jamais
        row("A/USDT", "Cassure 20/10", score=8.5, target=2.0),
    ]
    chosen, bench = choose(rows, SECTION_KEYS["court"])
    assert [r["symbol"] for r in chosen] == ["A/USDT", "B/USDT", "C/USDT", "D/USDT", "E/USDT"]  # dans l'ordre du classement
    assert len({r["symbol"] for r in chosen}) == 5
    assert all(r["symbol"] != "H/USDT" for r in chosen + bench)
    assert all(not (r["symbol"] == "A/USDT" and r["technique"] == "Cassure 20/10") for r in bench)
    assert bench[0]["symbol"] == "A/USDT" and bench[0]["technique"] == "Supertrend 10/3"
    assert label(chosen[0], SECTION_KEYS["court"])[0] == "3"
    assert label(row("Z/USDT", "Momentum 50", test=-0.01), SECTION_KEYS["court"])[0] == "2"
    assert label(row("Z/USDT", "Momentum 50", valid=-0.01), SECTION_KEYS["court"])[0] == "essai"


def test_the_choice_fills_every_seat_even_when_nothing_wins():
    rows = [row(f"{c}/USDT", "Momentum 50", score=-i, study=-0.002, valid=-0.001) for i, c in enumerate("ABCDEFG")]
    chosen, bench = choose(rows, SECTION_KEYS["court"])
    assert len(chosen) == 5 and len(bench) == 2
    assert all(label(r, SECTION_KEYS["court"])[0] == "essai" for r in chosen)


def test_select_backtests_every_combination_and_keeps_five_bots_per_team(monkeypatch, random_walk):
    small = tuple(Spec_section for Spec_section in SECTIONS)
    import tradingbot.fleet as fleet_module
    fast = []
    for sec in small:
        fast.append(fleet_module.Section(sec.key, sec.title, sec.timeframes, sec.leverage, sec.days, 5,
                                         ("Cassure 20/10", "Supertrend 10/3", "Repli RSI(2) < 10 + MM200"), sec.blurb))
    monkeypatch.setattr(fleet_module, "SECTIONS", tuple(fast))
    monkeypatch.setattr(fleet_module, "SECTION_KEYS", {s.key: s for s in fast})
    datasets = {}
    rng = np.random.default_rng(11)
    for sec in fast:
        for k in range(6):
            closes = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 900)))
            datasets[(sec.key, f"C{k}/USDT", sec.timeframes[0])] = frame_from_closes(closes)
    selection = select(datasets, FleetSettings(), workers=1)
    assert selection["tested"] == 3 * 6 * 3 * 2 * 2
    for sec in selection["sections"]:
        assert len(sec["bots"]) == 5 and len({b["symbol"] for b in sec["bots"]}) == 5
        assert sec["leverage"] == FleetSettings().leverage(sec["key"])
        for b in sec["bots"]:
            assert b["label"] in ("3", "2", "essai") and b["backtest"]["curve"]
        keys = {b["key"] for b in sec["bots"]}
        assert not keys & {b["key"] for b in sec["bench"]}


# --- remplacements, vue du site, textes ------------------------------------------------------------------------------

def test_a_dead_bot_is_replaced_by_the_next_of_its_team_on_another_coin(random_walk):
    s = spec("Cassure 20/10", "long", 0.0, 3.0)
    bench = [{**one_bot_selection(s)["sections"][0]["bots"][0]},  # déjà utilisé : sauté
             {"section": "court", "symbol": "Y/USDT", "timeframe": "1h", "technique": "Supertrend 10/3",
              "side": "short", "target_r": 2.0, "leverage": 3.0, "label": "essai", "label_text": "à l'essai"}]
    market = FakeMarket({"X/USDT": random_walk, "Y/USDT": random_walk})
    market.i = 500
    fleet = Fleet(market, None, one_bot_selection(s, bench), clock=lambda: market.now_ms() / 1000, read=False)
    fleet.state["slots"][0]["bot"]["book"]["dead"] = "liquidé"
    fleet.state["slots"][0]["bot"]["book"]["cash"] = 0.0
    events = fleet.cycle(market.now_ms())
    slot = fleet.state["slots"][0]
    assert slot["bot"]["spec"]["symbol"] == "Y/USDT" and slot["bot"]["spec"]["side"] == "short"
    assert slot["retired"][0]["reason"] == "liquidé"
    assert any(e["kind"] == "remplacement" for e in events)
    view = fleet_view(fleet.selection, fleet.state, running=True)
    totals = view["totals"]
    assert totals["start"] == pytest.approx(2000.0)  # le bot liquidé compte dans le bilan
    assert totals["retired"] == 1 and view["sections"][0]["bots"][0]["coin"] == "Y"


def test_a_new_choice_replaces_the_old_team_and_keeps_it_aside(tmp_path, random_walk):
    s = spec()
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    fleet = Fleet(market, tmp_path, one_bot_selection(s), clock=lambda: market.now_ms() / 1000, read=False)
    fleet.cycle(market.now_ms())
    newer = one_bot_selection(spec("Supertrend 10/3"))
    newer["id"] = "choix-2"
    again = Fleet(market, tmp_path, newer, clock=lambda: market.now_ms() / 1000, read=False)
    assert again.state["selection"] == "choix-2"
    assert again.state["slots"][0]["bot"]["spec"]["technique"] == "Supertrend 10/3"
    assert list(tmp_path.glob("etat-*.json"))


@pytest.mark.parametrize("family", STRATEGY_TYPES)
@pytest.mark.parametrize("side", SIDES)
def test_every_rule_is_explained_in_both_directions(family, side):
    name = next(n for n, p in {**ALL_VARIANTS}.items() if p.strategy_type == family)
    s = spec(name, side, 2.0)
    text = entry_rule(s) + " " + exit_rule(s)
    assert ("achète" if side == "long" else "vend à découvert") in text
    assert "de le " not in text and "  " not in text and "objectif" in text
    assert condition(s.params, side)


def test_the_chart_shows_the_rule_lines_trades_and_position(random_walk):
    s = spec("Cassure 20/10", "short", 2.0)
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 600
    fleet = Fleet(market, None, one_bot_selection(s), clock=lambda: market.now_ms() / 1000, read=False)
    fleet.cycle(market.now_ms())
    view = chart_view(random_walk.iloc[:602], fleet.state["slots"][0], FUTURES)
    assert len(view["candles"]) == 150
    assert {ln["key"] for ln in view["lines"]} == {"in", "out"}
    assert all(len(ln["values"]) == 150 for ln in view["lines"])
    assert view["rule_trades"] and all(t["side"] == "short" for t in view["rule_trades"])


def test_settings_are_read_and_checked():
    s = settings_from_env({"FLOTTE_CAPITAL": "500", "FLOTTE_LEVIER_SCALPING": "10"})
    assert s.capital == 500 and s.leverage("scalping") == 10 and s.leverage("long") == 1
    with pytest.raises(ValueError):
        settings_from_env({"FLOTTE_LEVIER_COURT": "50"})
    with pytest.raises(ValueError):
        settings_from_env({"FLOTTE_CAPITAL": "beaucoup"})


def test_every_technique_of_every_team_exists_and_teams_cover_all_families():
    families = set()
    for sec in SECTIONS:
        assert len(sec.techniques) == len(set(sec.techniques)) == 15
        for name in sec.techniques:
            families.add(technique(name).strategy_type)
        assert set(dict(sec.days)) == set(sec.timeframes)
    assert families == set(STRATEGY_TYPES)
    assert not math.isnan(sum(sec.leverage for sec in SECTIONS))


def test_the_loop_waits_longer_while_the_network_is_down_and_frees_its_place_when_it_stops(tmp_path, caplog):
    import ccxt

    from tradingbot.fleet import fleet_running, run

    class Down:
        def fetch_tickers(self, symbols=None):
            raise ccxt.NetworkError("réseau coupé")

        def fetch_ohlcv(self, symbol, timeframe, limit=500):
            raise ccxt.NetworkError("réseau coupé")

    fleet = Fleet(Down(), tmp_path, one_bot_selection(spec()), read=False)
    assert fleet_running(tmp_path)  # le signal de vie est écrit dès le départ
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 6:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(fleet, seconds=5, sleep=sleep)
    assert sleeps == [10, 20, 40, 60, 60, 60]  # de plus en plus tard, une minute au plus
    assert caplog.text.count("ils réessaient tout seuls") == 2  # pas une ligne par tour raté
    assert not fleet_running(tmp_path)  # arrêtés : la place est libre pour un nouveau lancement


def test_strange_candles_on_one_coin_never_stop_the_whole_choice(random_walk, monkeypatch):
    import tradingbot.fleet as fleet_module
    real = fleet_module.signals_for

    def flaky(df, params, side):
        if params.strategy_type == "supertrend":
            raise IndexError("bougies étranges")
        return real(df, params, side)

    monkeypatch.setattr(fleet_module, "signals_for", flaky)
    rows = fleet_module._dataset_job(("court", "X/USDT", "1h", random_walk.iloc[:900], ("Cassure 20/10", "Supertrend 10/3"),
                                      3.0, 1000.0, FUTURES))
    assert rows and {r["technique"] for r in rows} == {"Cassure 20/10"}


def test_a_bot_that_fails_on_its_candles_never_blocks_the_others(random_walk, monkeypatch):
    s1, s2 = spec("Cassure 20/10"), spec("Supertrend 10/3", symbol="Y/USDT")
    selection = one_bot_selection(s1)
    selection["sections"][0]["bots"].append({**selection["sections"][0]["bots"][0], "symbol": "Y/USDT",
                                             "technique": "Supertrend 10/3"})
    market = FakeMarket({"X/USDT": random_walk, "Y/USDT": random_walk})
    market.i = 500
    fleet = Fleet(market, None, selection, clock=lambda: market.now_ms() / 1000, read=False)
    real = Fleet._on_candles

    def broken(self, slot, bot, book, closed, price, at):
        if bot["spec"]["symbol"] == "X/USDT":
            raise IndexError("bougie étrange")
        return real(self, slot, bot, book, closed, price, at)

    monkeypatch.setattr(Fleet, "_on_candles", broken)
    fleet.cycle(market.now_ms())
    books = [slot["bot"]["book"] for slot in fleet.state["slots"]]
    assert books[0]["last_ts"] is None and books[1]["last_ts"] is not None  # le second bot a avancé
    assert s2.symbol == fleet.state["slots"][1]["bot"]["spec"]["symbol"]
