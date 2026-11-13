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
    BAN_S, DETAIL_DIR, ELIMINATE_AFTER, LIBRARY, REFERENCE_FILE, STATE_FILE, SWARM_FILE, TRIAL_FILE, TRIAL_MIN_DAYS,
    CandleStore, PlatformClock, Swarm, SwarmSettings, Retester, bot_brief, bot_detail, buckets, features, insights,
    per_timeframe, probability, profile, run, settings_from_env, retest_coin, trade_analysis,
)

DAY_MS = 24 * HOUR_MS


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
        self.jobs: list[dict] = []  # tout ce que l'essaim a demandé, dans l'ordre
        self.results: queue.Queue = queue.Queue()

    def submit(self, symbol, banned=(), verdicts=None, keep=(), trial=None):
        self.submitted.append((symbol, tuple(banned)))
        self.jobs.append({"symbol": symbol, "keep": tuple(keep), "trial": trial})
        self.verdicts = verdicts
        return True

    def status(self):
        return {"queue": 0, "current": None, "done": len(self.submitted)}


def spec(name="Cassure 20/10", side="long", target=0.0, leverage=3.0, symbol="X/USDT", tf="1h", stop_mode="fixe"):
    return Spec("court", symbol, tf, name, side, target, leverage, stop_mode)


def chosen(s: Spec, **extra) -> dict:
    """Une combinaison retenue par un re-test, comme retest_coin la rend."""
    return {**asdict(s), "key": s.key, "family": s.family, "label": "3",
            "label_text": "Choisi sur l'étude et la validation",
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


def test_a_candle_is_finished_only_when_the_platform_says_so(random_walk):
    s = spec()
    market = FakeMarket({s.symbol: random_walk})
    market.i = 700
    finished = int(random_walk["ts"].iloc[700])
    running = finished + HOUR_MS  # la bougie en cours : la dernière que rend la plateforme
    store = CandleStore(market)
    # L'horloge du PC avance d'une heure : elle croit la bougie en cours terminée. La plateforme n'a pas ouvert la
    # suivante : elle ne l'est pas.
    assert int(store.closed(s.symbol, "1h", 400, running + HOUR_MS + 5000)["ts"].iloc[-1]) == finished
    # Avec l'heure de la plateforme : terminée quand cette heure a dépassé sa fin, pas avant.
    assert int(store.closed(s.symbol, "1h", 400, running + 60_000, synced=True)["ts"].iloc[-1]) == finished
    assert int(store.closed(s.symbol, "1h", 400, running + HOUR_MS, synced=True)["ts"].iloc[-1]) == running


def test_a_pc_clock_running_ahead_never_makes_a_bot_decide_on_an_unfinished_candle(random_walk):
    s = spec("Cassure 20/10")
    market = FakeMarket({s.symbol: random_walk})
    market.i = 600
    swarm = make_swarm(market)
    bot = swarm.add_bot(chosen(s), market.now_ms())
    ahead = market.now_ms() + HOUR_MS  # l'horloge du PC avance d'une heure
    swarm.cycle(ahead)
    assert bot["book"]["last_ts"] == int(random_walk["ts"].iloc[600])  # la bougie 601, en cours, n'est pas lue
    calls = len(market.calls)
    swarm.cycle(ahead + 5000)  # la bougie attendue n'est pas finie : il redemande bientôt, puis de moins en moins
    assert len(market.calls) == calls + 1 and bot["book"]["last_ts"] == int(random_walk["ts"].iloc[600])
    assert swarm.next_fetch[(s.symbol, "1h")] == ahead + 10_000
    market.i = 601  # la plateforme ouvre la bougie suivante : la 601 est terminée
    swarm.cycle(ahead + 10_000)
    assert bot["book"]["last_ts"] == int(random_walk["ts"].iloc[601])
    assert swarm.next_fetch[(s.symbol, "1h")] == int(random_walk["ts"].iloc[601]) + 2 * HOUR_MS + 2000


def test_the_platform_clock_follows_the_exchange_not_the_pc():
    wall, mono = [1_000.0], [50.0]

    class Exchange:
        def fetch_time(self):
            return 2_000_000.0  # l'heure de la plateforme, en millisecondes

    clock = PlatformClock(Exchange(), clock=lambda: wall[0], monotonic=lambda: mono[0])
    assert not clock.synced and clock.now_ms() == 1_000_000 and clock.due()
    assert clock.sync() and clock.synced and not clock.due()
    assert clock.now_ms() == 2_000_000  # l'horloge du PC retardait de 1000 secondes : on ne s'y fie plus
    wall[0], mono[0] = wall[0] + 30, mono[0] + 30
    assert clock.now_ms() == 2_030_000
    wall[0], mono[0] = wall[0] + 600, mono[0] + 600
    assert clock.due()  # redemandée toutes les dix minutes
    wall[0] += 120  # Windows remet l'horloge du PC à l'heure (ou le PC sort de veille) : on ne sait plus
    assert clock.now_ms() == int(wall[0] * 1000) and not clock.synced and clock.due()
    assert not PlatformClock(object(), clock=lambda: 5.0).sync()  # une plateforme qui ne donne pas l'heure
    slow = PlatformClock(Exchange(), clock=lambda: 5.0, monotonic=iter([0.0, 1.0, 4.0]).__next__)
    assert not slow.sync() and not slow.synced  # trois secondes pour répondre : mesure trop floue

    class Down:
        def fetch_time(self):
            raise ccxt.NetworkError("réseau coupé")

    assert not PlatformClock(Down()).sync()


def test_the_history_of_a_test_never_contains_the_candle_in_progress():
    real_now = 1_700_000_000_000 + 37_000  # l'heure de la plateforme : 37 secondes après le début d'une minute

    class Exchange:
        rateLimit = 0

        def milliseconds(self):
            return real_now + 90_000  # l'horloge du PC avance d'une minute et demie

        def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
            tf = swarm_module.timeframe_to_ms(timeframe)
            first = -(-since // tf) * tf
            return [[ts, 1.0, 1.0, 1.0, 1.0, 1.0] for ts in range(first, real_now + 1, tf)][:limit]

    frames = Retester(lambda name: None, "binance", SwarmSettings())._frames(Exchange(), "X/USDT")
    for tf, df in frames.items():
        tf_ms = swarm_module.timeframe_to_ms(tf)
        assert int(df["ts"].iloc[-1]) == real_now // tf_ms * tf_ms - tf_ms, tf  # la dernière bougie vraiment terminée


def test_the_reference_point_is_saved_once_before_anything_changes(tmp_path, random_walk):
    old = {"version": 2, "created": "2026-11-07T10:00:00+00:00", "bots": [], "coins": [],
           "totals": {"count": 217, "win_rate": 0.36, "pnl_pct": -0.003, "bots": 60, "retired": 40, "value": 99_700.0},
           "ranking": {"strategie": [{"key": "EMA 9/21|15m", "n": 12}]}}
    (tmp_path / SWARM_FILE).write_text(json.dumps(old), encoding="utf-8")  # le résumé laissé par la version d'avant
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, tmp_path)
    saved = json.loads((tmp_path / REFERENCE_FILE).read_text(encoding="utf-8"))
    assert saved["totals"]["count"] == 217 and saved["ranking"]["strategie"][0]["n"] == 12
    assert saved["since"] == old["created"] and saved["saved"] == swarm_module._iso(market.now_ms())
    assert swarm.summary()["reference"] == {"saved": saved["saved"], "count": 217, "win_rate": 0.36, "pnl_pct": -0.003,
                                            "bots": 60, "retired": 40}
    swarm.add_bot(chosen(spec()), market.now_ms())
    swarm.cycle(market.now_ms())
    market.i = 500
    again = make_swarm(market, tmp_path)  # le résumé a changé depuis : le point de référence, jamais
    assert json.loads((tmp_path / REFERENCE_FILE).read_text(encoding="utf-8")) == saved and again.reference == saved
    fresh = make_swarm(market, tmp_path / "neuf")  # une première installation : rien avant, et c'est noté
    assert fresh.reference["totals"] is None and fresh.summary()["reference"]["count"] is None
    assert make_swarm(market).summary()["reference"] is None  # sans dossier (tests) : pas de point de référence


def test_bot_files_are_rewritten_a_few_at_a_time(tmp_path, random_walk, monkeypatch):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, tmp_path)
    for name in ("Cassure 20/10", "Supertrend 10/3", "Momentum 50"):
        swarm.add_bot(chosen(spec(name)), market.now_ms())
    swarm.save()  # nouveaux : tous écrits tout de suite
    assert len(list((tmp_path / DETAIL_DIR).glob("*.json"))) == 3
    written, real = [], Swarm._write

    def write(self, path, payload):
        if path.parent.name == DETAIL_DIR:
            written.append(path.name)
        real(self, path, payload)

    monkeypatch.setattr(Swarm, "_write", write)
    for _ in range(3):
        swarm.save()
    assert len(written) == 3 and len(set(written)) == 3  # une fiche par tour, chacune à son tour


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

def test_a_retest_fills_the_free_places_and_never_stops_a_bot_because_the_ranking_moved(random_walk):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market, settings=SwarmSettings(coins=1, bots_per_coin=2))
    a, b, c = (chosen(spec(n)) for n in ("Cassure 20/10", "Supertrend 10/3", "Momentum 50"))
    events = swarm.apply_test({"symbol": "X/USDT", "tested": 1560, "eligible": 3, "chosen": [a, b, c], "best": [],
                               "holdout": {"n": 12, "total": -0.03, "total_sq": 0.01, "wins": 4}}, market.now_ms())
    assert len(swarm.bots) == 2 and [e["kind"] for e in events] == ["nouveau", "nouveau"]  # au plus 1 x 2 bots
    assert "test final gagnant" in events[0]["text"]
    info = swarm.state["coins"]["X/USDT"]
    assert info["status"] == "actif" and info["holdout"]["n"] == 12
    # Le test suivant classe autrement : A est rafraîchi, B n'est plus dans le classement, C est proposé.
    newer = {**a, "sv_mean": 0.01, "study_mean": 0.011, "label": "1", "label_text": "perdant sur le test final"}
    events = swarm.apply_test({"symbol": "X/USDT", "tested": 1560, "eligible": 2, "chosen": [c], "kept": [newer],
                               "best": []}, market.now_ms() + 1000)
    bot_a, bot_b = swarm.bots[a["key"]], swarm.bots[b["key"]]
    assert bot_a["status"] == "actif" and bot_a["backtest"]["study_mean"] == 0.011 and bot_a["label"] == "1"
    assert bot_b["status"] == "actif" and events == [] and c["key"] not in swarm.bots  # B garde sa place : pas de place pour C
    assert swarm.cycle(market.now_ms()) == [] and set(swarm.bots) == {a["key"], b["key"]}  # personne n'est arrêté
    # Une place se libère (B est arrêté par son garde-fou) : le test suivant la donne à C.
    del swarm.bots[b["key"]]
    events = swarm.apply_test({"symbol": "X/USDT", "tested": 1560, "eligible": 2, "chosen": [c], "kept": [newer],
                               "best": []}, market.now_ms() + 2000)
    assert c["key"] in swarm.bots and [e["kind"] for e in events] == ["nouveau"]
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
    assert result["kept"] == [] and result["trial"] is None and not result["final"]
    for r in result["chosen"]:
        assert r["study_mean"] > 0 and r["valid_mean"] > 0 and not r["liquidated_early"]
        assert r["label"] in ("1", "2", "3") and r["profile"]["overall"]["n"] >= 1 and r["curve"]
        assert r["label_text"].startswith("Choisi sur l'étude et la validation")
    per_tf = {}
    for r in result["chosen"]:
        per_tf[r["timeframe"]] = per_tf.get(r["timeframe"], 0) + 1
    assert all(n <= 2 for n in per_tf.values())
    # Le test final ne choisit rien : il mesure. Celui des combinaisons choisies est rendu à part.
    assert result["holdout"]["n"] == sum(r["test_n"] for r in result["chosen"])
    assert result["holdout"]["total"] == pytest.approx(sum(r["test_n"] * r["test_mean"] for r in result["chosen"] if r["test_n"]))
    assert result["holdout_eligible"]["n"] >= result["holdout"]["n"] and result["eligible"] >= len(result["chosen"])
    assert any(r["label"] == "1" for r in retest_coin("X/USDT", frames, asdict(SwarmSettings(bots_per_coin=20)))["chosen"])
    if result["chosen"]:
        banned = (result["chosen"][0]["key"],)
        again = retest_coin("X/USDT", frames, asdict(SwarmSettings(bots_per_coin=4)), banned)
        assert banned[0] not in {r["key"] for r in again["chosen"]}


def test_the_final_test_measures_and_never_chooses():
    row = {"liquidated": False, "liquidated_early": False, "sv_n": 40, "study_n": 20, "valid_n": 20, "study_mean": 0.002,
           "valid_mean": 0.001, "test_n": 30, "test_mean": -0.01}
    assert swarm_module._eligible(row, "1h")  # perdant sur le test final : choisi quand même, il ne sert qu'à mesurer
    assert swarm_module._eligible({**row, "liquidated": True}, "1h")  # liquidé pendant le test final : pas regardé non plus
    assert not swarm_module._eligible({**row, "liquidated_early": True}, "1h")
    assert not swarm_module._eligible({**row, "valid_mean": -0.001}, "1h")
    assert not swarm_module._eligible({**row, "sv_n": 5}, "1h")
    assert swarm_module._label(row)[0] == "1" and "perdant sur le test final" in swarm_module._label(row)[1]
    assert swarm_module._label({**row, "test_mean": 0.01})[0] == "3"
    assert swarm_module._label({**row, "test_n": 2})[0] == "2"
    assert swarm_module._label(row, eligible=False)[0] == "0"


def test_the_bots_in_place_keep_their_place_in_a_retest(random_walk):
    frames = {"1h": random_walk.iloc[:1400], "15m": random_walk.iloc[1400:2800]}
    settings = asdict(SwarmSettings(bots_per_coin=4))
    first = retest_coin("X/USDT", frames, settings)
    assert len(first["chosen"]) == 4
    # Deux bots en place : un que le test choisirait encore, et un qui ne gagne pas sur cet historique.
    held = first["chosen"][0]
    weak = asdict(spec("Momentum 50", "short", 0.0, 3.0))
    result = retest_coin("X/USDT", frames, settings, keep=({k: held[k] for k in weak}, weak))
    kept = {r["key"]: r for r in result["kept"]}
    assert set(kept) == {held["key"], spec("Momentum 50", "short", 0.0, 3.0).key}
    assert kept[held["key"]]["label"] == held["label"] and kept[held["key"]]["curve"] and kept[held["key"]]["profile"]
    assert len(result["chosen"]) <= 2 and not {r["key"] for r in result["chosen"]} & set(kept)  # seulement les places libres
    for r in result["chosen"]:  # la variété tient compte des bots en place
        assert (r["timeframe"], r["technique"]) != (held["timeframe"], held["technique"])
    assert per_timeframe(8) == 2 and per_timeframe(20) == 5
    rows = [chosen(spec(n, tf=tf), score=s) for n, tf, s in (("Cassure 20/10", "1h", 9.0), ("Supertrend 10/3", "1h", 8.0),
                                                            ("EMA 9/21", "1h", 7.0), ("MACD 12/26/9", "15m", 1.0))]
    taken = [chosen(spec("Momentum 28", tf="1h"))]
    picked = swarm_module._choose(rows, 3, None, taken)
    assert [r["technique"] for r in picked] == ["Cassure 20/10", "MACD 12/26/9"]  # déjà un bot en 1 h : un seul de plus


def test_every_combination_is_measured_once_whatever_the_number_of_tests(random_walk):
    """Les trades de toutes les combinaisons (pas seulement des bots choisis) sont comptés, une seule fois chacun."""
    settings = asdict(SwarmSettings())
    df = random_walk
    start = int(df["ts"].iloc[700])  # la crypto bouge à partir de là

    def test_at(end, done, final=False, active=None):
        trial = {"done": done, "active": active or [[start, None]], "final": final}
        return retest_coin("X/USDT", {"1h": df.iloc[:end]}, settings, trial=trial)["trial"]

    done, total, opened = {}, {}, None
    for end in (900, 1000, 1100):  # trois tests de suite, chacun repart de la fin du précédent
        r = test_at(end, done)
        done, opened = r["done"], r["open"]
        for key, rec in r["stats"].items():
            swarm_module.merge_record(total.setdefault(key, swarm_module.new_record("days" in rec)), rec)
    assert done == {"1h": int(df["ts"].iloc[1099])}
    once = test_at(1100, {})  # le même historique en un seul test
    assert {k: v["n"] for k, v in total.items()} == {k: v["n"] for k, v in once["stats"].items()}
    assert all(total[k]["total"] == pytest.approx(once["stats"][k]["total"]) for k in total)
    assert once["open"] == opened > 0 and once["counted"] == once["stats"]["unite:1h"]["n"]
    # Une combinaison refaite à la main : mêmes trades, mêmes sommes.
    s = Spec("court", "X/USDT", "1h", "Cassure 20/10", "long", 2.0, 3.0)
    trades = [t for t in simulate(df.iloc[:1100], s).s["trades"] if t["entry_ts"] >= start and t["reason"] != "fin du test"]
    rec = once["stats"]["detail:Cassure 20/10|1h|long|objectif 2R"]
    assert rec["n"] == len(trades) >= 3 and rec["total"] == pytest.approx(sum(t["net"] for t in trades))
    assert rec["wins"] == sum(t["net"] > 0 for t in trades) and "days" not in rec
    assert rec["r"] == pytest.approx(sum(t["net"] / t["risk"] for t in trades))
    assert rec["gain"] == pytest.approx(sum(max(t["net"], 0.0) for t in trades))
    # Chaque trade compte une fois dans chaque famille de lignes, et dans le jour de sa sortie.
    n = once["stats"]["unite:1h"]["n"]
    for family in ("detail:", "strategie:", "technique:", "sortie:", "sens:"):
        assert sum(v["n"] for k, v in once["stats"].items() if k.startswith(family)) == n
    assert sum(d[0] for d in once["stats"]["unite:1h"]["days"].values()) == n
    assert len([k for k in once["stats"] if k.startswith("detail:")]) > 200  # des centaines de combinaisons mesurées


def test_only_trades_opened_while_the_coin_moved_count_and_the_last_test_closes_the_rest(random_walk):
    settings = asdict(SwarmSettings())
    df = random_walk.iloc[:1100]
    a, b, end = (int(df["ts"].iloc[i]) for i in (800, 950, 1099))
    key = "detail:Cassure 20/10|1h|long|sortie par la règle"
    trades = simulate(df, Spec("court", "X/USDT", "1h", "Cassure 20/10", "long", 0.0, 3.0)).s["trades"]
    during = [t for t in trades if a <= t["entry_ts"] <= b and t["reason"] != "fin du test"]

    def measure(active, final=False):
        return retest_coin("X/USDT", {"1h": df}, settings, trial={"done": {}, "active": active, "final": final})

    window = measure([[a, b]])["trial"]
    assert window["stats"][key]["n"] == len(during) >= 1 and len(during) < len(trades) - 1
    nothing = measure([])["trial"]  # elle n'a jamais bougé : rien à mesurer
    assert nothing["stats"] == {} and nothing["counted"] == 0 and nothing["open"] == 0
    regular, last = measure([[a, end]]), measure([[a, end]], final=True)
    assert regular["trial"]["open"] > 0 and not regular["final"]
    # Le dernier test d'une crypto qui ne bouge plus : les positions ouvertes sont comptées à leur valeur du moment.
    assert last["trial"]["counted"] == regular["trial"]["counted"] + regular["trial"]["open"] and last["trial"]["open"] == 0
    assert last["final"] and last["chosen"] == []  # et il ne choisit aucun bot


def test_the_swarm_measures_a_coin_while_it_moves_and_closes_its_measure_when_it_stops(random_walk):
    tickers = {"A/USDT": ticker(0.20), "B/USDT": ticker(0.10)}
    market = FakeMarket({"A/USDT": random_walk}, tickers)
    market.i = 400
    tester = FakeTester()
    swarm = Swarm(market, None, SwarmSettings(coins=2, min_move=0.03), clock=lambda: market.now_ms() / 1000,
                  tester=tester, read=False, universe_every=600)
    t0 = market.now_ms()
    swarm.cycle(t0)
    info = swarm.state["coins"]["A/USDT"]
    assert info["moving_since"] == t0 and tester.jobs[0]["symbol"] == "A/USDT"
    assert tester.jobs[0]["trial"] == {"done": {}, "active": [[t0, None]], "final": False}  # elle bouge : on mesure
    day = swarm_module._iso(t0)[:10]

    def result(n, done, final=False, opened=0):
        rec = {"n": n, "total": 0.002 * n, "total_sq": 0.0001 * n, "wins": n, "gain": 0.002 * n, "r": 0.5 * n,
               "days": {day: [n, 0.002 * n, n]}}
        return {"symbol": "A/USDT", "tested": 1560, "eligible": 0, "chosen": [], "kept": [], "best": [], "final": final,
                "trial": {"done": done, "open": opened, "counted": n, "final": final,
                          "stats": {"strategie:EMA 9/21|1h": rec, "unite:1h": json.loads(json.dumps(rec))}}}

    assert info["next_test"] == t0 + 3 * 3_600_000
    tester.results.put(result(3, {"1h": 123}, opened=7))
    swarm.cycle(t0 + 5000)
    assert info["trial_done"] == {"1h": 123} and info["trial_open"] == 7
    assert info["next_test"] == t0 + 5000 + 1_800_000  # son deuxième test vient vite : il comptera ses premiers trades
    info["next_test"] = t0 + 3 * 3_600_000  # (la suite du scénario garde le rythme habituel)
    trial = swarm.summary()["trial"]
    assert trial["n"] == 3 and trial["bots"] == 1560 and trial["coins"] == 1 and trial["positions"] == 7
    assert trial["mean"] == pytest.approx(0.002) and trial["lo"] is None  # un seul jour : pas encore de fourchette
    # A se calme : sa période est close. Si elle ne reprend pas dans l'heure, un dernier test clôt sa mesure.
    tickers["A/USDT"] = ticker(0.01)
    t1, asked = t0 + 600_000, len(tester.jobs)
    swarm.cycle(t1)
    assert info["stretches"] == [[t0, t1]] and info["moving_since"] is None and info["trial_close"]
    swarm.cycle(t1 + 600_000)
    assert len(tester.jobs) == asked  # pas tout de suite : elle peut reprendre
    late = t1 + swarm_module.CLOSE_DELAY_S * 1000
    swarm.cycle(late)
    closing = tester.jobs[-1]
    assert closing == {"symbol": "A/USDT", "keep": (), "trial": {"done": {"1h": 123}, "active": [[t0, t1]], "final": True}}
    asked = len(tester.jobs)
    swarm.cycle(late + 5000)
    assert len(tester.jobs) == asked  # demandé une fois, pas à chaque tour
    tester.results.put(result(1, {"1h": 456}, final=True))
    swarm.cycle(late + 10_000)
    assert info["stretches"] == [] and not info["trial_close"] and info["trial_done"] == {"1h": 456}
    assert swarm.trial["stats"]["strategie:EMA 9/21|1h"]["n"] == 4 and swarm.summary()["trial"]["bots"] == 0
    # Elle se remet à bouger : une nouvelle période commence.
    tickers["A/USDT"] = ticker(0.20)
    t2 = late + 600_000
    swarm.cycle(t2)
    assert info["moving_since"] == t2 and not info["trial_close"]
    # Elle s'arrête dix minutes puis reprend : pas de dernier test pour si peu, les deux périodes sont gardées.
    tickers["A/USDT"] = ticker(0.01)
    swarm.cycle(t2 + 600_000)
    tickers["A/USDT"] = ticker(0.20)
    t2b, asked = t2 + 1_200_000, len(tester.jobs)
    for k in range(7):  # une heure de plus, un tour toutes les dix minutes
        swarm.cycle(t2b + k * 600_000)
    assert info["stretches"] == [[t2, t2 + 600_000]] and info["moving_since"] == t2b and not info["trial_close"]
    assert not any(j["trial"]["final"] for j in tester.jobs[asked:])
    t2 = t2b + 3_600_000  # la suite repart d'ici, avec une seule période en cours
    info["stretches"], info["moving_since"] = [], t2
    # Le PC reste éteint deux heures : on ne sait pas si elle bougeait, la période s'arrête à la dernière fois vue.
    t3 = t2 + 2 * 3_600_000
    swarm.cycle(t3)
    assert info["stretches"] == [[t2, t2]] and info["moving_since"] == t3
    swarm.state["coins"]["A/USDT"]["next_test"] = 0
    swarm.cycle(t3 + 5000)
    assert tester.jobs[-1]["trial"]["active"] == [[t2, t2], [t3, None]] and not tester.jobs[-1]["trial"]["final"]
    # Elle sort de la liste : sa mesure est close avant qu'on l'oublie.
    tickers.update({"C/USDT": ticker(0.50), "D/USDT": ticker(0.40)})
    market.markets.update({s: {"spot": True, "active": True, "quote": "USDT", "base": s[0]} for s in ("C/USDT", "D/USDT")})
    t4 = t3 + 600_000
    swarm.cycle(t4)
    assert {"A/USDT", "B/USDT"} <= set(swarm.state["coins"])  # pas encore oubliées : leur mesure reste à clore
    t5 = t4 + swarm_module.CLOSE_DELAY_S * 1000
    swarm.cycle(t5)
    assert [(j["symbol"], j["trial"]["final"]) for j in tester.jobs[-2:]] == [("A/USDT", True), ("B/USDT", True)]
    tester.results.put(result(0, {"1h": 789}, final=True))
    swarm.cycle(t5 + 5000)
    swarm.cycle(t5 + 600_000)
    assert "A/USDT" not in swarm.state["coins"] and "B/USDT" in swarm.state["coins"]  # B attend encore son dernier test


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
    monkeypatch.setattr(swarm_module, "retest_coin", lambda symbol, frames, settings, banned, verdicts, keep, trial: {
        "symbol": symbol, "tested": len(frames), "eligible": 0, "chosen": [], "best": [], "banned": list(banned),
        "keep": list(keep), "trial": trial})

    class Broken:
        def __init__(self, max_workers):
            pass

        def submit(self, *args):
            raise BrokenProcessPool("processus tué")

    monkeypatch.setattr(swarm_module, "ProcessPoolExecutor", Broken)
    tester = Retester(lambda name: object(), "binance", SwarmSettings(), workers=1)
    assert tester.submit("X/USDT", ("k",), keep=({"a": 1},), trial={"final": False}) and not tester.submit("X/USDT")
    gate.set()
    result = wait_result(tester)  # le calcul reçoit aussi les bots en place et la mesure à l'essai
    assert result == {"symbol": "X/USDT", "tested": 1, "eligible": 0, "chosen": [], "best": [], "banned": ["k"],
                      "keep": [{"a": 1}], "trial": {"final": False}}
    for _ in range(100):
        if tester.status()["queue"] == 0:
            break
        time.sleep(0.02)
    assert tester.status() == {"queue": 0, "current": None, "done": 1}

    def down(self, exchange, symbol):
        raise ccxt.NetworkError("réseau coupé")

    monkeypatch.setattr(Retester, "_frames", down)
    tester.submit("Y/USDT", trial={"final": True})
    assert wait_result(tester) == {"symbol": "Y/USDT", "error": "réseau coupé", "final": True}


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
    assert wait_result(tester) == {"symbol": "X/USDT", "error": "test trop long, le processus de calcul a été remplacé",
                                   "final": False}
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


def measured(swarm, name, means, per_day=40, tf="1h"):
    """Ajoute à la mesure à l'essai `per_day` trades par jour pour une stratégie, au gain moyen donné pour chaque
    jour (le dernier : aujourd'hui), comme le ferait le résultat d'un test."""
    now = swarm.time.now_ms()
    days = {}
    for k, m in enumerate(reversed(means)):
        days[swarm_module._iso(now - k * DAY_MS)[:10]] = [per_day, m * per_day, per_day if m > 0 else 0]
    n, total = per_day * len(means), sum(v[1] for v in days.values())
    rec = {"n": n, "total": total, "total_sq": sum(per_day * m * m for m in means), "wins": sum(v[2] for v in days.values()),
           "gain": max(total, 0.0), "r": 0.0, "days": days}
    swarm._merge_trial({}, {"done": {}, "open": 0, "final": False, "stats": {
        f"strategie:{name}|{tf}": rec, f"unite:{tf}": json.loads(json.dumps(rec))}})


def test_the_trial_measure_judges_the_strategies_by_comparing_days(tmp_path, random_walk, monkeypatch):
    monkeypatch.setattr(Swarm, "_on_candles", lambda self, bot, *args: [])  # ici, seuls les verdicts comptent
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    tester = FakeTester()
    swarm = make_swarm(market, tmp_path, tester=tester)
    swarm.state["coins"]["X/USDT"] = {"moving": True, "followed": True, "next_test": market.now_ms() + 10 ** 9}
    bad = spec("Momentum 50", "short", 0.0, stop_mode="suiveur")
    loser = swarm.add_bot(chosen(bad), market.now_ms())
    busy = swarm.add_bot(chosen(spec("Momentum 50", "long", 2.0)), market.now_ms())
    busy["book"]["position"] = {"side": "long", "entry_ts": 0, "entry_mark": 100.0, "price": 100.0, "qty": 1.0,
                                "notional": 100.0, "margin": 100.0, "fee": 0.0, "leverage": 1.0, "stop": 1.0,
                                "target": None, "liquidation": 0.5, "risk": 0.99, "high": 100.0, "low": 100.0, "bars": 1}
    week = TRIAL_MIN_DAYS + 1
    measured(swarm, "EMA 9/21", [0.004 + 0.0005 * (k % 3) for k in range(week)])  # gagne un peu chaque jour
    measured(swarm, "Momentum 50", [-0.004 - 0.0005 * (k % 3) for k in range(week)])  # perd un peu chaque jour
    measured(swarm, "Cassure 20/10", [-0.001] * (week - 1) + [0.05])  # un seul très bon jour : positif en moyenne
    measured(swarm, "MACD 12/26/9", [0.01], per_day=400)  # 400 trades gagnants, mais le même jour
    events = swarm.cycle(market.now_ms())
    assert swarm.state["verdicts"] == {"EMA 9/21|1h": "prouvee", "Momentum 50|1h": "recalee"}
    assert {e["kind"] for e in events} >= {"prouvee", "recalee"}
    assert any("à l'essai" in e["text"] and f"{week} jours" in e["text"] for e in events)
    assert loser["key"] not in swarm.bots  # recalée : ses bots s'arrêtent (celui-ci n'avait pas de position)
    assert any("sa stratégie est recalée" in e["text"] for e in events)
    assert busy["status"] == "sortie"  # celui qui a une position la finit d'abord
    assert swarm.cycle(market.now_ms() + 1000) == []  # un verdict n'est annoncé qu'une fois
    trial = swarm.summary()["trial"]
    rows = {r["technique"]: r for r in trial["ranking"]["strategie"]}
    assert rows["EMA 9/21"]["verdict"] == "prouvee" and rows["EMA 9/21"]["lo"] > 0 and rows["EMA 9/21"]["days"] == week
    assert rows["Momentum 50"]["verdict"] == "recalee" and rows["Momentum 50"]["hi"] < 0
    lucky, same_day = rows["Cassure 20/10"], rows["MACD 12/26/9"]
    assert lucky["mean"] > 0 and lucky["lo"] < 0 and lucky["verdict"] is None  # un bon jour ne prouve rien
    assert same_day["n"] == 400 and same_day["verdict"] is None and same_day["lo"] is None  # un seul jour : pas de fourchette
    assert trial["n"] == sum(r["n"] for r in rows.values()) and trial["days"] == week and trial["ranking"]["min_days"] == 7
    assert rows["EMA 9/21"]["today_n"] == 40 and rows["EMA 9/21"]["week_n"] == 7 * 40
    assert swarm.summary()["ranking"]["strategie"] == []  # le classement des bots en direct reste à part
    assert swarm.summary()["bots"][0]["live"] == "recalee"
    rows = [chosen(spec("Momentum 50", "short"), score=9.0), chosen(spec("Cassure 20/10"), score=5.0),
            chosen(spec("EMA 9/21", "long", 2.0), score=1.0)]
    picked = swarm_module._choose(rows, 2, swarm.state["verdicts"])
    assert [r["technique"] for r in picked] == ["EMA 9/21", "Cassure 20/10"]  # prouvée d'abord, recalée jamais
    swarm.state["coins"]["X/USDT"]["next_test"] = 0
    swarm.cycle(market.now_ms() + 2000)
    assert tester.verdicts == swarm.state["verdicts"]  # le test suivant le sait aussi
    assert tester.jobs[-1]["keep"] == ()  # un bot en sortie ne garde pas sa place
    # La mesure est sur le disque : un redémarrage la retrouve, avec ses verdicts.
    again = make_swarm(market, tmp_path)
    assert again.trial["stats"] == json.loads((tmp_path / TRIAL_FILE).read_text(encoding="utf-8"))["stats"]
    assert again.verdicts() == swarm.state["verdicts"]
    # Le vent tourne : un jour sur deux, la stratégie recalée regagne. Elle ne perd plus nettement : son verdict est
    # levé (sans être prouvée pour autant) et son bot reprend sa place.
    measured(swarm, "Momentum 50", [0.004 if k % 2 else -0.0005 for k in range(week)], per_day=80)
    swarm.cycle(market.now_ms() + 3000)
    assert swarm.state["verdicts"] == {"EMA 9/21|1h": "prouvee"} and busy["status"] == "actif"


def test_live_trades_of_the_bots_are_ranked_apart(random_walk):
    market = FakeMarket({"X/USDT": random_walk})
    market.i = 400
    swarm = make_swarm(market)
    good, bad = spec("EMA 9/21", "long", 2.0), spec("Momentum 50", "short", 0.0, stop_mode="suiveur")
    for k in range(40):  # 40 trades en direct, toutes cryptos réunies
        swarm._learn(good, {"net": 0.010 + 0.002 * (k % 3)})
        swarm._learn(bad, {"net": -0.010 - 0.002 * (k % 3)})
    assert swarm.cycle(market.now_ms()) == [] and swarm.state["verdicts"] == {}  # le direct des bots ne rend plus de verdict
    ranking = swarm.summary()["ranking"]
    top = ranking["strategie"][0]
    assert top["technique"] == "EMA 9/21" and top["n"] == 40 and top["today_n"] == 40 and top["week_n"] == 40
    assert top["verdict"] is None and top["lo"] > 0
    assert {r["key"] for r in ranking["sortie"]} == {"objectif 2R", "stop suiveur"}
    assert {r["key"] for r in ranking["sens"]} == {"long", "short"} and ranking["min_trades"] == 30


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
                {"FLOTTE_BOTS_PAR_CRYPTO": "21"}, {"FLOTTE_MOUVEMENT_MIN": "80"}):
        with pytest.raises(ValueError):
            settings_from_env(bad)
