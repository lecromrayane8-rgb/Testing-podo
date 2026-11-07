"""L'essaim : le direct identique au backtest, la reprise, les cryptos suivies, les re-tests, les arrêts, les agents."""
import json
import queue
import threading
import time
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict

import ccxt
import numpy as np
import pandas as pd
import pytest

import tradingbot.swarm as swarm_module
from tests.conftest import HOUR_MS, frame_from_closes
from tradingbot.data import COLUMNS
from tradingbot.fleet import EXITS, Spec, fleet_running, lookback_for, simulate
from tradingbot.swarm import (
    BAN_S, DETAIL_DIR, ELIMINATE_AFTER, LIBRARY, STATE_FILE, SWARM_FILE, CandleStore, Swarm, SwarmSettings, Retester,
    bot_brief, bot_detail, buckets, features, insights, probability, profile, run, settings_from_env, retest_coin,
    trade_analysis,
)


class FakeMarket:
    """Rejoue des bougies d'une heure : au pas i, la bougie i vient de se clôturer et la i+1 commence."""

    def __init__(self, frames: dict[str, pd.DataFrame], tickers: dict | None = None):
        self.frames, self.i = frames, 0
        self.calls: list[tuple[str, str, int]] = []
        self.tickers = tickers or {}
        self.markets = {s: {"spot": True, "active": True, "quote": "USDT", "base": s.split("/")[0]}
                        for s in list(self.frames) + list(self.tickers)}

    def now_ms(self) -> int:
        df = next(iter(self.frames.values()))
        return int(df["ts"].iloc[self.i]) + HOUR_MS + 2500

    def load_markets(self):
        return self.markets

    def fetch_tickers(self, symbols=None):
        if symbols is None:  # tout le marché : la liste des cryptos agitées
            return self.tickers
        return {s: {"last": float(df["open"].iloc[self.i + 1])} for s, df in self.frames.items() if s in symbols}

    def fetch_ticker(self, symbol):
        return self.fetch_tickers([symbol])[symbol]

    def fetch_ohlcv(self, symbol, timeframe, limit=500):
        self.calls.append((symbol, timeframe, limit))
        df = self.frames[symbol]
        return df.iloc[max(0, self.i + 2 - limit):self.i + 2][COLUMNS].values.tolist()


class FakeTester:
    def __init__(self):
        self.submitted: list[tuple[str, tuple]] = []
        self.results: queue.Queue = queue.Queue()

    def submit(self, symbol, banned=(), verdicts=None):
        self.submitted.append((symbol, tuple(banned)))
        self.verdicts = verdicts
        return True

    def status(self):
        return {"queue": 0, "current": None, "done": len(self.submitted)}


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, symbol="X/USDT", tf="1h", stop_mode="fixe"):
    return Spec("court", symbol, tf, name, side, target, leverage, stop_mode)


def chosen(s: Spec, **extra) -> dict:
    """Une combinaison retenue par un re-test, comme retest_coin la rend."""
    return {**asdict(s), "key": s.key, "family": s.family, "label": "3", "label_text": "Gagnant sur les 3 périodes",
            "trades": 40, "win_rate": 0.55, "mean": 0.002, "sv_n": 30, "sv_mean": 0.002, "study_n": 15,
            "study_mean": 0.002, "valid_n": 15, "valid_mean": 0.002, "test_n": 10, "test_mean": 0.001,
            "total_return": 0.3, "drawdown": -0.1, "score": 2.0, "curve": [[0, 1000.0]], "profile": None, **extra}


def make_swarm(market, folder=None, settings=SwarmSettings(), tester=None):
    return Swarm(market, folder, settings, clock=lambda: market.now_ms() / 1000, tester=tester, read=False,
                 universe_every=1e12)


COMPARED = ("side", "entry_ts", "exit_ts", "reason", "leverage")


# --- le direct, exactement comme le backtest ----------------------------------------------------------------------

# Le parcours complet (tour après tour, comme en vrai) sur quelques techniques ; les signaux de toutes les techniques,
# dans les deux sens, sont comparés bougie par bougie dans tests/test_fleet.py.
@pytest.mark.parametrize("name,side,target,mode", [
    ("Cassure 20/10", "long", 0.0, "fixe"), ("Cassure 20/10", "short", 2.0, "fixe"),
    ("Repli RSI(2) < 10 + MM200", "long", 2.0, "fixe"), ("Rebond sur support", "short", 2.0, "fixe"),
    ("Stochastique 14/3", "short", 0.0, "fixe"), ("Ichimoku 9/26/52", "long", 2.0, "fixe"),
    ("Cassure 20/10", "long", 0.0, "suiveur"), ("Supertrend 10/3", "short", 0.0, "suiveur"),
    ("EMA 9/21", "long", 2.0, "securise"), ("Momentum 28", "short", 2.0, "securise"),
])
def test_live_bots_take_exactly_the_trades_of_their_backtest(monkeypatch, random_walk, name, side, target, mode):
    monkeypatch.setattr(Swarm, "_retire", lambda self, now_ms: [])  # le bot reste en place jusqu'au bout
    df = random_walk.iloc[:1150].copy()
    s = spec(name, side, target, stop_mode=mode)
    backtest = [t for t in simulate(df, s).s["trades"] if t["reason"] != "fin du test"]
    index = {int(t): i for i, t in enumerate(df["ts"])}
    look = lookback_for(s.params)
    first = next(t for t in backtest if index[t["exit_ts"]] >= look)  # le direct démarre quand le backtest est à plat
    start = index[first["exit_ts"]]
    market = FakeMarket({s.symbol: df})
    market.i = start
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    for i in range(start, len(df) - 1):
        market.i = i
        swarm.cycle(market.now_ms())
    end = int(df["ts"].iloc[-1])
    expected = [t for t in backtest if t["entry_ts"] > int(df["ts"].iloc[start]) and t["exit_ts"] < end]
    live = [t for t in bot["book"]["trades"] if t["exit_ts"] < end]
    assert len(expected) >= 2
    assert [tuple(t[k] for k in COMPARED) for t in live] == [tuple(t[k] for k in COMPARED) for t in expected]
    for a, b in zip(live, expected):
        assert a["price"] == pytest.approx(b["price"], rel=1e-9)
        assert a["exit_price"] == pytest.approx(b["exit_price"], rel=1e-9)
        assert a["net"] == pytest.approx(b["net"], rel=1e-6, abs=1e-9)
        assert a["roi"] == pytest.approx(b["roi"], rel=1e-6, abs=1e-9)
        assert a["diagnosis"]["title"]  # chaque trade du direct est expliqué


@pytest.mark.parametrize("name,side,target,mode", [
    ("Cassure 20/10", "long", 2.0, "fixe"), ("Supertrend 10/3", "short", 0.0, "suiveur"),
    ("Repli RSI(2) < 10 + MM200", "long", 2.0, "securise"),
])
def test_after_a_break_the_bots_catch_up_exactly_like_their_backtest(monkeypatch, random_walk, name, side, target, mode):
    """Le PC éteint 3 jours (ou le réseau coupé) : au retour, les bougies manquées sont rejouées une par une."""
    monkeypatch.setattr(Swarm, "_retire", lambda self, now_ms: [])
    df = random_walk.iloc[:1150].copy()
    s = spec(name, side, target, stop_mode=mode)
    backtest = [t for t in simulate(df, s).s["trades"] if t["reason"] != "fin du test"]
    index = {int(t): i for i, t in enumerate(df["ts"])}
    first = next(t for t in backtest if index[t["exit_ts"]] >= lookback_for(s.params) + 80)
    start = index[first["exit_ts"]]
    market = FakeMarket({s.symbol: df})
    market.i = start
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    inside = next(t for t in backtest if index[t["entry_ts"]] >= start + 30)  # un trade s'ouvre pendant la coupure
    g0 = index[inside["entry_ts"]] - 10
    steps = list(range(start, g0)) + list(range(g0 + 72, len(df) - 1))  # 72 bougies sans aucun tour
    for i in steps:
        market.i = i
        swarm.cycle(market.now_ms())
    end = int(df["ts"].iloc[-1])
    expected = [t for t in backtest if t["entry_ts"] > int(df["ts"].iloc[start]) and t["exit_ts"] < end]
    live = [t for t in bot["book"]["trades"] if t["exit_ts"] < end]
    assert len(expected) >= 2 and inside in expected
    assert [tuple(t[k] for k in COMPARED) for t in live] == [tuple(t[k] for k in COMPARED) for t in expected]
    assert all(a["net"] == pytest.approx(b["net"], rel=1e-6, abs=1e-9) for a, b in zip(live, expected))


def test_the_live_stop_is_watched_at_the_current_price_between_two_candles():
    closes = np.r_[np.linspace(100, 120, 60), np.full(10, 120.0)]
    df = frame_from_closes(closes)
    s = spec("Cassure 20/10", "long", 0.0, 3.0)
    market = FakeMarket({s.symbol: df})
    market.i = 40
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    swarm.cycle(market.now_ms())
    book = bot["book"]
    assert book["position"] is not None  # nouveau sommet à chaque bougie : il est entré
    stop = book["position"]["stop"]
    market.frames[s.symbol] = df.assign(open=df["open"].where(df.index != df.index[41], stop * 0.99))
    events = swarm.cycle(market.now_ms() + 60_000)  # même bougie en cours, prix sous le stop
    assert book["position"] is None and book["trades"][-1]["reason"] == "stop"
    assert any(e["kind"] == "sortie" for e in events)


def test_candles_are_fetched_whole_once_then_only_the_newest(random_walk):
    s = spec()
    market = FakeMarket({s.symbol: random_walk})
    market.i = 600
    swarm = make_swarm(market)
    swarm.add_bot(chosen(s), market.now_ms())
    for i in range(600, 610):
        market.i = i
        swarm.cycle(market.now_ms())
    limits = [limit for _, _, limit in market.calls]
    assert limits[0] == lookback_for(s.params) and set(limits[1:]) == {5}
    store = CandleStore(market)
    market.i = 700
    full = store.closed(s.symbol, "1h", 400, market.now_ms())
    market.i = 701
    more = store.closed(s.symbol, "1h", 400, market.now_ms())
    assert len(full) == len(more) and int(more["ts"].iloc[-1]) - int(full["ts"].iloc[-1]) == HOUR_MS
    assert int(more["ts"].iloc[-1]) + HOUR_MS <= market.now_ms()  # seulement des bougies terminées


# --- la reprise après un arrêt ----------------------------------------------------------------------------------

def test_a_restart_picks_up_exactly_where_the_swarm_stopped(tmp_path, monkeypatch, random_walk):
    monkeypatch.setattr(Swarm, "_retire", lambda self, now_ms: [])
    df = random_walk.iloc[:1000]
    rows = [chosen(spec("Cassure 20/10", "long", 2.0)), chosen(spec("Supertrend 10/3", "short"))]

    def play(folder, stop_at=None):
        market = FakeMarket({"X/USDT": df})
        market.i = 500
        swarm = make_swarm(market, folder)
        for r in rows:
            swarm.add_bot(r, market.now_ms())
        for i in range(500, 760):
            if i == stop_at:
                swarm.release()
                swarm = make_swarm(market, folder)  # le PC redémarre : tout est relu sur le disque
                assert len(swarm.bots) == 2
            market.i = i
            swarm.cycle(market.now_ms())
        return {k: b["book"]["trades"] for k, b in swarm.bots.items()}

    straight = play(tmp_path / "a")
    resumed = play(tmp_path / "b", stop_at=640)
    assert straight == resumed and sum(len(t) for t in straight.values()) >= 3
    assert (tmp_path / "b" / STATE_FILE).exists() and len(list((tmp_path / "b" / DETAIL_DIR).glob("*.json"))) == 2
    summary = json.loads((tmp_path / "b" / SWARM_FILE).read_text(encoding="utf-8"))
    assert isinstance(summary["coins"], list) and len(summary["bots"]) == 2  # le résumé du site, à part de l'état


def test_a_test_lost_in_a_restart_is_done_again(tmp_path, random_walk):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, tmp_path)
    swarm.state["coins"]["X/USDT"] = {"status": "test en cours", "next_test": market.now_ms() + 10 ** 9,
                                      "followed": True, "moving": True, "amplitude": 0.1}
    swarm.state_dirty = True
    swarm.save()
    tester = FakeTester()
    again = make_swarm(market, tmp_path, tester=tester)
    assert again.state["coins"]["X/USDT"]["status"] == "en attente de test"
    again.cycle(market.now_ms())
    assert tester.submitted == [("X/USDT", ())]


def test_an_old_or_broken_state_file_starts_a_fresh_swarm(tmp_path, random_walk):
    (tmp_path / STATE_FILE).write_text(json.dumps({"version": 1, "slots": []}), encoding="utf-8")
    (tmp_path / SWARM_FILE).write_text("{pas du json", encoding="utf-8")
    (tmp_path / DETAIL_DIR).mkdir()
    (tmp_path / DETAIL_DIR / "abc.json").write_text(json.dumps({"key": "x", "spec": {"technique": "Disparue"}}),
                                                    encoding="utf-8")
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, tmp_path)
    assert swarm.state["coins"] == {} and swarm.bots == {}
    swarm.cycle(market.now_ms())


# --- les cryptos suivies -----------------------------------------------------------------------------------------

def ticker(amplitude, volume=1e7, change=0.01):
    return {"high": 100 * (1 + amplitude), "low": 100.0, "last": 100.0, "quoteVolume": volume, "percentage": 100 * change}


def test_the_swarm_follows_the_coins_that_move_most_and_puts_calm_ones_to_sleep(random_walk):
    tickers = {"A/USDT": ticker(0.20), "B/USDT": ticker(0.10), "C/USDT": ticker(0.05), "D/USDT": ticker(0.04),
               "E/USDT": ticker(0.50, volume=1e5), "USDC/USDT": ticker(0.30)}
    market = FakeMarket({"C/USDT": random_walk}, tickers)
    market.i = 400
    tester = FakeTester()
    swarm = Swarm(market, None, SwarmSettings(coins=3, min_move=0.03), clock=lambda: market.now_ms() / 1000,
                  tester=tester, read=False, universe_every=600)
    bot = swarm.add_bot(chosen(spec(symbol="C/USDT")), market.now_ms())
    swarm.cycle(market.now_ms())
    coins = swarm.state["coins"]
    assert swarm.state["universe"] == ["A/USDT", "B/USDT", "C/USDT"]  # ni le peu échangé, ni la monnaie stable
    assert all(coins[s]["moving"] for s in swarm.state["universe"]) and "D/USDT" not in coins  # 4e : pas suivie
    assert [s for s, _ in tester.submitted] == ["A/USDT", "B/USDT", "C/USDT"]  # les plus agitées testées d'abord
    assert bot["status"] == "actif"
    tickers["C/USDT"] = ticker(0.02)  # C se calme : encore dans la liste, mais en veille
    tickers["D/USDT"] = ticker(0.01)
    market.i = 401
    events = swarm.cycle(market.now_ms() + 600_000)
    assert bot["status"] == "veille" and any(e["kind"] == "veille" for e in events)
    assert not coins["C/USDT"]["moving"]
    assert "D/USDT" not in coins  # plus suivie et sans bot : oubliée
    swarm.cycle(market.now_ms() + 700_000)
    assert len(tester.submitted) == 3  # pas de nouveau test avant 3 heures


def test_a_bot_on_a_sleeping_coin_never_opens_a_trade(random_walk):
    s = spec("Cassure 20/10")
    market = FakeMarket({s.symbol: random_walk})
    market.i = 400
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    bot["status"] = "veille"
    for i in range(400, 700):
        market.i = i
        swarm.cycle(market.now_ms())
    assert bot["book"]["trades"] == [] and bot["book"]["position"] is None


# --- les re-tests ----------------------------------------------------------------------------------------------

def test_a_retest_creates_bots_keeps_the_good_ones_and_lets_the_others_finish(random_walk):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, settings=SwarmSettings(coins=1, bots_per_coin=2))
    a, b, c = (chosen(spec(n)) for n in ("Cassure 20/10", "Supertrend 10/3", "Momentum 50"))
    events = swarm.apply_test({"symbol": "X/USDT", "tested": 780, "eligible": 3, "chosen": [a, b, c], "best": []},
                              market.now_ms())
    assert len(swarm.bots) == 2 and [e["kind"] for e in events] == ["nouveau", "nouveau"]  # au plus 1 x 2 bots
    assert swarm.state["coins"]["X/USDT"]["status"] == "actif"
    newer = {**a, "sv_mean": 0.01, "study_mean": 0.011, "label": "2"}
    swarm.apply_test({"symbol": "X/USDT", "tested": 780, "eligible": 1, "chosen": [newer], "best": []},
                     market.now_ms() + 1000)
    bot_a, bot_b = swarm.bots[a["key"]], swarm.bots[b["key"]]
    assert bot_a["status"] == "actif" and bot_a["backtest"]["study_mean"] == 0.011 and bot_a["label"] == "2"
    assert bot_b["status"] == "sortie"
    events = swarm.cycle(market.now_ms())
    assert b["key"] not in swarm.bots and any("ne le garde plus" in e["text"] for e in events)
    assert not swarm.state["banned"]  # pas mis de côté : il pourra revenir au prochain test
    swarm.apply_test({"symbol": "X/USDT", "error": "réseau coupé"}, market.now_ms())
    assert swarm.state["coins"]["X/USDT"]["status"] == "test impossible"


@pytest.mark.parametrize("problem", ["liquidé", "moitié", "gardien"])
def test_a_losing_bot_is_stopped_and_its_combination_set_aside_for_a_day(random_walk, problem):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    tester = FakeTester()
    swarm = make_swarm(market, tester=tester)
    s = spec()
    bot = swarm.add_bot(chosen(s), market.now_ms())
    book = bot["book"]
    if problem == "liquidé":
        book.update(dead="liquidé", cash=0.0)
    elif problem == "moitié":
        book["cash"] = 400.0
    else:
        book.update(count=ELIMINATE_AFTER, stats={"n": ELIMINATE_AFTER, "total": -0.02 * ELIMINATE_AFTER,
                                                  "total_sq": 0.00041 * ELIMINATE_AFTER})  # nettement perdant
    events = swarm.cycle(market.now_ms())
    assert s.key not in swarm.bots and any(e["kind"] == "arret" for e in events)
    assert swarm.state["banned"][s.key] == pytest.approx(market.now_ms() + BAN_S * 1000, abs=5000)
    totals = swarm.summary()["totals"]
    assert totals["retired"] == 1 and totals["start"] == pytest.approx(1000.0)  # il compte dans le bilan
    swarm.state["coins"]["X/USDT"] = {"moving": True, "followed": True, "next_test": 0}
    swarm.cycle(market.now_ms())
    assert tester.submitted[-1] == ("X/USDT", (s.key,))  # le test ne le reprend pas pendant 24 h
    swarm.state["coins"]["X/USDT"]["next_test"] = 0
    swarm.cycle(market.now_ms() + BAN_S * 1000 + 1)
    assert tester.submitted[-1] == ("X/USDT", ()) and not swarm.state["banned"]


def test_retesting_a_coin_tries_every_combination_and_keeps_varied_winners(random_walk):
    frames = {"1h": random_walk.iloc[:1400], "15m": random_walk.iloc[1400:2800]}
    result = retest_coin("X/USDT", frames, asdict(SwarmSettings(bots_per_coin=4)))
    assert result["tested"] == 2 * len(LIBRARY) * 2 * len(EXITS)  # 2 unités x techniques x 2 sens x 4 sorties
    assert len(result["chosen"]) <= 4 and len(result["best"]) == 12
    for r in result["chosen"]:
        assert r["study_mean"] > 0 and r["valid_mean"] > 0 and not r["liquidated"]
        assert r["label"] in ("2", "3") and r["profile"]["overall"]["n"] >= 1 and r["curve"]
    per_tf = {}
    for r in result["chosen"]:
        per_tf[r["timeframe"]] = per_tf.get(r["timeframe"], 0) + 1
    assert all(n <= 2 for n in per_tf.values())
    if result["chosen"]:
        banned = (result["chosen"][0]["key"],)
        again = retest_coin("X/USDT", frames, asdict(SwarmSettings(bots_per_coin=4)), banned)
        assert banned[0] not in {r["key"] for r in again["chosen"]}


def test_strange_candles_never_stop_the_test_of_a_coin(random_walk, monkeypatch, caplog):
    real = swarm_module.signals_for

    def flaky(df, params, side):
        if params.strategy_type == "supertrend":
            raise IndexError("bougies étranges")
        return real(df, params, side)

    monkeypatch.setattr(swarm_module, "signals_for", flaky)
    result = retest_coin("X/USDT", {"1h": random_walk.iloc[:900], "5m": None}, asdict(SwarmSettings()))
    assert result["tested"] == (len(LIBRARY) - 2) * 2 * len(EXITS)  # les deux Supertrend sautés, le reste testé
    assert "combinaison ignorée" in caplog.text


def wait_result(tester: Retester, timeout=20.0):
    return tester.results.get(timeout=timeout)


def test_the_tester_works_apart_and_falls_back_when_the_process_pool_breaks(monkeypatch, random_walk):
    gate = threading.Event()

    def frames(self, exchange, symbol):
        gate.wait(10)  # le téléchargement prend du temps
        return {"1h": random_walk.iloc[:600]}

    monkeypatch.setattr(Retester, "_frames", frames)
    monkeypatch.setattr(swarm_module, "retest_coin", lambda symbol, frames, settings, banned=(), verdicts=None: {
        "symbol": symbol, "tested": len(frames), "eligible": 0, "chosen": [], "best": [], "banned": list(banned)})

    class Broken:
        def __init__(self, max_workers):
            pass

        def submit(self, *args):
            raise BrokenProcessPool("processus tué")

    monkeypatch.setattr(swarm_module, "ProcessPoolExecutor", Broken)
    tester = Retester(lambda name: object(), "binance", SwarmSettings(), workers=1)
    assert tester.submit("X/USDT", ("k",)) and not tester.submit("X/USDT")  # pas deux fois la même crypto
    gate.set()
    result = wait_result(tester)
    assert result == {"symbol": "X/USDT", "tested": 1, "eligible": 0, "chosen": [], "best": [], "banned": ["k"]}
    for _ in range(100):
        if tester.status()["queue"] == 0:
            break
        time.sleep(0.02)
    assert tester.status() == {"queue": 0, "current": None, "done": 1}

    def down(self, exchange, symbol):
        raise ccxt.NetworkError("réseau coupé")

    monkeypatch.setattr(Retester, "_frames", down)
    tester.submit("Y/USDT")
    assert wait_result(tester) == {"symbol": "Y/USDT", "error": "réseau coupé"}


def test_a_stuck_test_never_freezes_the_tests_that_follow(monkeypatch, random_walk):
    from concurrent.futures import Future
    monkeypatch.setattr(Retester, "_frames", lambda self, exchange, symbol: {"1h": random_walk.iloc[:600]})
    monkeypatch.setattr(swarm_module, "RETEST_TIMEOUT_S", 0.2)
    pools = []

    class Stuck:  # un processus de calcul qui ne rend jamais la main
        def __init__(self, max_workers):
            pools.append(self)
            self.closed = False

        def submit(self, *args):
            return Future()

        def shutdown(self, wait=True, cancel_futures=False):
            self.closed = True

    monkeypatch.setattr(swarm_module, "ProcessPoolExecutor", Stuck)
    tester = Retester(lambda name: object(), "binance", SwarmSettings(), workers=1)
    tester.submit("X/USDT")
    assert wait_result(tester) == {"symbol": "X/USDT", "error": "test trop long, le processus de calcul a été remplacé"}
    tester.submit("Y/USDT")
    assert wait_result(tester)["error"]  # le suivant passe aussi, sans attendre indéfiniment
    assert len(pools) == 3 and pools[0].closed and pools[1].closed  # chaque calcul bloqué est remplacé


def test_a_coin_that_leaves_the_list_frees_its_places_after_six_hours(random_walk, monkeypatch, caplog):
    monkeypatch.setattr(Swarm, "_on_candles", lambda self, bot, *args: [])  # ici, seule la liste des cryptos compte
    tickers = {"A/USDT": ticker(0.20), "X/USDT": ticker(0.10)}
    market = FakeMarket({"X/USDT": random_walk}, tickers)
    market.i = 400
    swarm = Swarm(market, None, SwarmSettings(coins=2), clock=lambda: market.now_ms() / 1000, read=False,
                  universe_every=600)
    idle = swarm.add_bot(chosen(spec("Cassure 20/10")), market.now_ms())
    busy = swarm.add_bot(chosen(spec("Supertrend 10/3")), market.now_ms())
    busy["book"]["position"] = {"side": "long", "entry_ts": 0, "entry_mark": 100.0, "price": 100.0, "qty": 1.0,
                                "notional": 100.0, "margin": 100.0, "fee": 0.0, "leverage": 1.0, "stop": 1.0,
                                "target": None, "liquidation": 0.5, "risk": 0.99, "high": 100.0, "low": 100.0,
                                "bars": 1}
    swarm.cycle(market.now_ms())
    tickers["B/USDT"], tickers["C/USDT"] = ticker(0.30), ticker(0.25)  # deux cryptos plus agitées passent devant
    market.markets.update({s: {"spot": True, "active": True, "quote": "USDT", "base": s[0]} for s in ("B/USDT", "C/USDT")})
    t = market.now_ms() + 600_000
    swarm.cycle(t)
    assert not swarm.state["coins"]["X/USDT"]["followed"] and idle["key"] in swarm.bots  # pas tout de suite
    events = swarm.cycle(t + 6 * 3600_000)
    assert idle["key"] not in swarm.bots and busy["key"] in swarm.bots  # celui qui a une position la garde
    assert any("plus parmi les plus agitées" in e["text"] for e in events) and not swarm.state["banned"]
    market.fetch_ohlcv = lambda *args, **kwargs: (_ for _ in ()).throw(ccxt.NetworkError("coupé"))
    for k in range(5):  # la crypto ne répond plus : un avertissement, pas une ligne par minute
        swarm.next_fetch.clear()
        swarm.cycle(t + 6 * 3600_000 + k * 60_000)
    assert caplog.text.count("bougies indisponibles") == 1


def test_live_results_rank_the_strategies_and_feed_back_into_the_choice(random_walk):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    tester = FakeTester()
    swarm = make_swarm(market, tester=tester)
    good, bad = spec("EMA 9/21", "long", 2.0), spec("Momentum 50", "short", 0.0, stop_mode="suiveur")
    loser = swarm.add_bot(chosen(bad), market.now_ms())
    for k in range(40):  # 40 trades en direct, toutes cryptos réunies
        swarm._learn(good, {"net": 0.010 + 0.002 * (k % 3)})
        swarm._learn(bad, {"net": -0.010 - 0.002 * (k % 3)})
    events = swarm.cycle(market.now_ms())
    assert swarm.state["verdicts"] == {"EMA 9/21|1h": "prouvee", "Momentum 50|1h": "recalee"}
    assert {e["kind"] for e in events} >= {"prouvee", "recalee"}
    assert loser["key"] not in swarm.bots  # recalée : ses bots s'arrêtent (celui-ci n'avait pas de position)
    assert swarm.cycle(market.now_ms() + 1000) == []  # un verdict n'est annoncé qu'une fois
    ranking = swarm.summary()["ranking"]
    top = ranking["strategie"][0]
    assert top["technique"] == "EMA 9/21" and top["n"] == 40 and top["today_n"] == 40 and top["week_n"] == 40
    assert top["verdict"] == "prouvee" and top["lo"] > 0 and ranking["strategie"][-1]["verdict"] == "recalee"
    assert {r["key"] for r in ranking["sortie"]} == {"objectif 2R", "stop suiveur"}
    assert {r["key"] for r in ranking["sens"]} == {"long", "short"} and ranking["min_trades"] == 30
    rows = [chosen(spec("Momentum 50", "short"), score=9.0), chosen(spec("Cassure 20/10"), score=5.0),
            chosen(spec("EMA 9/21", "long", 2.0), score=1.0)]
    picked = swarm_module._choose(rows, 2, swarm.state["verdicts"])
    assert [r["technique"] for r in picked] == ["EMA 9/21", "Cassure 20/10"]  # prouvée d'abord, recalée jamais
    swarm.state["coins"]["X/USDT"] = {"moving": True, "followed": True, "next_test": 0}
    swarm.cycle(market.now_ms() + 2000)
    assert tester.verdicts == swarm.state["verdicts"]  # le test suivant le sait aussi


# --- les agents d'analyse --------------------------------------------------------------------------------------

def test_the_agents_say_where_a_strategy_wins_and_estimate_its_chances(random_walk):
    df = random_walk.iloc[:1500]
    feats = features(df)
    assert set(feats.columns) == {"trend", "atr_pct", "rsi", "vol_ratio", "hour"}
    rows = feats.to_dict("records")
    trades = []
    for i in range(260, 1490, 7):  # gagne quand la tendance de fond monte, perd sinon
        up = rows[i - 1]["trend"] == "hausse"
        trades.append({"entry_ts": int(df["ts"].iloc[i]), "net": 0.01 if up else -0.01, "reason": "stop"})
    prof = profile(trades, feats, HOUR_MS)
    assert prof["overall"]["n"] == len(trades)
    trend = prof["groups"]["trend"]
    assert trend["hausse"]["win"] == 1.0 and trend.get("baisse", {"win": 0})["win"] == 0.0
    found = insights(prof)
    assert any("« hausse »" in x for x in found["wins"]) and found["losses"]
    good = probability(prof, {"trend": "hausse"})
    bad = probability(prof, {"trend": "baisse"})
    assert bad["p"] < prof["overall"]["win"] < good["p"] < 1.0  # tiré vers la moyenne : jamais une certitude
    assert "pas une promesse" in good["text"]
    assert probability(None, {}) is None
    why = trade_analysis({"pnl": 5.0, "context": {"trend": "hausse"}}, prof)
    assert why and "gagné, comme souvent" in why[0]
    assert buckets({"trend": None, "atr_pct": float("nan"), "rsi": 25.0, "vol_ratio": 2.0, "hour": 15}, None) == {
        "rsi": "survendu (sous 30)", "volume": "fort", "session": "Amérique (14-22 h UTC)"}


def test_the_site_reads_a_short_brief_and_a_full_page_for_each_bot(random_walk):
    s = spec("Cassure 20/10", "long", 2.0)
    market = FakeMarket({s.symbol: random_walk})
    market.i = 600
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    for i in range(600, 800):
        market.i = i
        swarm.cycle(market.now_ms())
    brief = bot_brief(bot)
    assert brief["coin"] == "X" and brief["tf_label"] == "1 h" and brief["count"] == len(bot["book"]["trades"]) > 0
    assert brief["value"] == pytest.approx(1000.0 + sum(t["pnl"] for t in bot["book"]["trades"])
                                           + (brief["position"]["pnl"] if brief["position"] else 0.0))
    page = bot_detail(bot)
    assert page["trades"][0]["exit_ts"] >= page["trades"][-1]["exit_ts"]  # le plus récent d'abord
    assert page["rule"].startswith("Il achète") and page["insights"] == {"wins": [], "losses": []}
    summary = swarm.summary()
    assert summary["totals"]["bots"] == 1 and summary["max_bots"] == SwarmSettings().max_bots
    assert summary["totals"]["value"] == pytest.approx(brief["value"])


# --- la boucle, les réglages ------------------------------------------------------------------------------------

def test_the_loop_waits_longer_while_the_network_is_down_and_frees_its_place_when_it_stops(tmp_path, caplog):
    class Down:
        markets = {}

        def load_markets(self):
            raise ccxt.NetworkError("réseau coupé")

        def fetch_tickers(self, symbols=None):
            raise ccxt.NetworkError("réseau coupé")

        def fetch_ohlcv(self, symbol, timeframe, limit=500):
            raise ccxt.NetworkError("réseau coupé")

    swarm = Swarm(Down(), tmp_path, SwarmSettings(), read=False)
    swarm.add_bot(chosen(spec()), int(time.time() * 1000))
    assert fleet_running(tmp_path)  # le signal de vie est écrit dès le départ
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 6:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(swarm, seconds=5, sleep=sleep)
    assert sleeps == [10, 20, 40, 60, 60, 60]  # de plus en plus tard, une minute au plus
    assert caplog.text.count("ils réessaient tout seuls") == 2  # pas une ligne par tour raté
    assert not fleet_running(tmp_path)  # arrêtés : la place est libre pour un nouveau lancement


def test_a_bot_that_fails_on_its_candles_never_blocks_the_others(random_walk, monkeypatch):
    market = FakeMarket({"X/USDT": random_walk, "Y/USDT": random_walk})
    market.i = 500
    swarm = make_swarm(market)
    x = swarm.add_bot(chosen(spec("Cassure 20/10")), market.now_ms())
    y = swarm.add_bot(chosen(spec("Supertrend 10/3", symbol="Y/USDT")), market.now_ms())
    real = Swarm._on_candles

    def broken(self, bot, *args):
        if bot["spec"]["symbol"] == "X/USDT":
            raise IndexError("bougie étrange")
        return real(self, bot, *args)

    monkeypatch.setattr(Swarm, "_on_candles", broken)
    swarm.cycle(market.now_ms())
    assert x["book"]["last_ts"] is None and y["book"]["last_ts"] is not None  # le second bot a avancé


def test_settings_are_read_and_checked():
    s = settings_from_env({"FLOTTE_CAPITAL": "500", "FLOTTE_LEVIER_SCALPING": "10", "FLOTTE_CRYPTOS": "30",
                           "FLOTTE_BOTS_PAR_CRYPTO": "10", "FLOTTE_MOUVEMENT_MIN": "2,5"})
    assert s.capital == 500 and s.leverage("1m") == 10 and s.leverage("4h") == 1 and s.leverage("15m") == 3
    assert s.max_bots == 300 and s.min_move == pytest.approx(0.025)
    assert SwarmSettings().max_bots >= 400  # des centaines de bots au plus, par défaut
    for bad in ({"FLOTTE_LEVIER_COURT": "50"}, {"FLOTTE_CAPITAL": "beaucoup"}, {"FLOTTE_CRYPTOS": "0"},
                {"FLOTTE_BOTS_PAR_CRYPTO": "11"}, {"FLOTTE_MOUVEMENT_MIN": "80"}):
        with pytest.raises(ValueError):
            settings_from_env(bad)
