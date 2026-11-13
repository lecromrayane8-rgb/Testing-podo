import json

import numpy as np
import pytest

import main
from tests.conftest import daily_frame, frame_from_closes


def test_robustness_command_uses_long_history_for_daily_bars(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # aucun .env lu
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    requested = []

    def fake_load(exchange_id, symbol, timeframe, days, cache_dir, exchange=None):
        requested.append((timeframe, days))
        rng = np.random.default_rng(len(requested))
        return frame_from_closes(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 1500))))

    monkeypatch.setattr(main, "load_or_fetch", fake_load)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)

    code = main.main(["robustesse", "--symbols", "BTC/USDT", "--timeframes", "1h,1d", "--days", "730"])

    assert code == 0
    assert requested == [("1h", 730), ("1d", main.LONG_TERM_DAYS)]
    saved = json.loads((tmp_path / "data" / "robustesse.json").read_text(encoding="utf-8"))
    assert [r["market"] for r in saved["rows"]] == ["BTC/USDT 1h", "BTC/USDT 1d"]
    assert "BTC/USDT 1d" in (tmp_path / "data" / "tableau-de-bord.html").read_text(encoding="utf-8")


def test_dashboard_command_writes_the_page_without_opening_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    opened = []
    monkeypatch.setattr(main.webbrowser, "open", opened.append)

    assert main.main(["tableau", "--no-open"]) == 0
    assert (tmp_path / "data" / "tableau-de-bord.html").exists() and opened == []


def test_bots_on_a_real_account_cannot_claim_more_than_the_balance(tmp_path):
    from types import SimpleNamespace
    import pytest
    from tradingbot.config import ConfigError

    def bot(capital=None):
        return SimpleNamespace(
            state={"capital": capital}, s=SimpleNamespace(mode="testnet", max_capital=600.0),
            broker=SimpleNamespace(balances=lambda: SimpleNamespace(quote=1000.0)),
        )

    with pytest.raises(ConfigError, match="1200.00"):
        main.check_capital_allocation([bot(), bot()])
    main.check_capital_allocation([bot(600.0), bot()])  # le premier a déjà son capital : 600 suffisent


def test_paper_wallet_of_an_older_version_is_kept(tmp_path, monkeypatch):
    from tests.test_live import settings
    monkeypatch.setattr(main, "CcxtBroker", lambda *args, **kwargs: None)
    s = settings(tmp_path, bots=(("BTC/USDT", "1h"), ("BTC/USDT", "1d")))
    legacy = tmp_path / "paper_wallet_binance_BTC-USDT.json"
    legacy.write_text('{"base": 0.5, "quote": 100.0}', encoding="utf-8")
    first = main.make_broker(main.bot_settings(s)[0])
    second = main.make_broker(main.bot_settings(s)[1])
    assert first.balances().base == 0.5 and not legacy.exists()
    assert second.balances().base == 0.0  # le second bot a son propre compte neuf


def test_robustness_skips_a_market_on_network_error(tmp_path, monkeypatch):
    import ccxt
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    def flaky(exchange_id, symbol, timeframe, days, cache_dir, exchange=None):
        if symbol == "ETH/USDT":
            raise ccxt.NetworkError("timeout")
        return frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0.0002, 0.01, 1500))))

    monkeypatch.setattr(main, "load_or_fetch", flaky)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    assert main.main(["robustesse", "--symbols", "BTC/USDT,ETH/USDT", "--timeframes", "1h"]) == 0
    saved = json.loads((tmp_path / "data" / "robustesse.json").read_text(encoding="utf-8"))
    assert [r["market"] for r in saved["rows"]] == ["BTC/USDT 1h"]


def test_reset_guard_gives_an_eliminated_strategy_a_fresh_start(tmp_path, monkeypatch):
    from tradingbot.live import StateStore, bot_paths
    from tradingbot.config import Settings
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    s = Settings.from_env()
    state_path, _ = bot_paths(s)
    StateStore(state_path).save({"eliminated": "perd nettement", "perf": {"n": 25, "total": -1.0, "total_sq": 1.0},
                                 "capital": 9000.0})
    assert main.main(["reset-guard"]) == 0
    state = StateStore(state_path).load()
    assert state["eliminated"] is None and state["perf"] is None and state["capital"] == 9000.0


def test_history_is_capped_for_minute_candles():
    assert main.history_days("1m", 730) == 60  # ~86 000 bougies : le labo reste rapide
    assert main.history_days("5m", 730) == 300 and main.history_days("5m", 30) == 30
    assert main.history_days("1h", 730) == 730 and main.history_days("1d", 730) == main.LONG_TERM_DAYS


def lab_file(path, *rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"verdict": "…", "rows": [
        {"variant": v, "timeframe": tf, "verdict": verdict, "expectancy_pct": exp} for v, tf, verdict, exp in rows
    ]}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def test_tournament_picks_only_strategies_worth_watching(tmp_path):
    lab = lab_file(
        tmp_path / "laboratoire.json",
        ("Supertrend 10/3", "4h", "prometteur", 0.6),
        ("Momentum 100", "1h", "à surveiller", 0.4),
        ("Supertrend 10/3", "1h", "à surveiller", 0.3),  # même stratégie : une seule fois si on force 1 min
        ("Ancienne variante", "1h", "à surveiller", 0.2),  # n'existe plus dans le labo
        ("Cassure 20/10", "15m", "perd de l'argent", -0.4),
    )
    assert [(v, tf) for v, tf, _ in main.tournament_picks(lab, None, 6)] == [
        ("Supertrend 10/3", "4h"), ("Momentum 100", "1h"), ("Supertrend 10/3", "1h")]
    assert [(v, tf) for v, tf, _ in main.tournament_picks(lab, "1m", 6)] == [
        ("Supertrend 10/3", "1m"), ("Momentum 100", "1m")]
    assert len(main.tournament_picks(lab, None, 1)) == 1


def test_tournament_pits_every_watched_strategy_against_every_coin_in_paper(tmp_path, monkeypatch, caplog):
    import logging
    from tradingbot.broker import PaperBroker
    from tradingbot.scanner import ScanResult
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MODE", "testnet")  # même réglé sur une plateforme, le tournoi reste en argent fictif
    monkeypatch.setenv("MAX_CAPITAL", "200")
    lab_file(tmp_path / "data" / "laboratoire.json",
             ("Supertrend 10/3", "4h", "prometteur", 0.6), ("Momentum 100", "1h", "à surveiller", 0.4),
             ("Cassure 20/10", "15m", "perd de l'argent", -0.4))

    class PublicData:  # données publiques seulement : aucune clé API
        made = []

        def __init__(self, exchange_id, symbol, exchange=None, cache_seconds=0.0):
            if symbol == "GONE/USDT":
                raise ValueError("Paire GONE/USDT introuvable")
            self.symbol, self.exchange, self.cache_seconds = symbol, exchange, cache_seconds
            PublicData.made.append(self)

    scans, runs, opened = [], {}, []
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: "connexion partagée")
    monkeypatch.setattr(main, "CcxtBroker", PublicData)
    monkeypatch.setattr(main, "pick_markets", lambda exchange, top, memecoins: scans.append((top, memecoins)) or [
        ScanResult("PEPE/USDT", 0.21, 3e7, 0.05), ScanResult("GONE/USDT", 0.2, 1e7, 0.0),
        ScanResult("DOGE/USDT", 0.09, 5e8, 0.02)])
    monkeypatch.setattr(main.webbrowser, "open", opened.append)

    def fake_run(bots, poll, after_cycle=None):
        runs.update(bots=bots, poll=poll)
        after_cycle()

    monkeypatch.setattr(main, "run_bots", fake_run)

    assert main.main(["tournoi", "--unite", "1m", "--top", "3", "--capital", "500"]) == 0
    bots = runs["bots"]
    assert scans == [(3, True)] and runs["poll"] <= 15 and len(opened) == 1
    assert sorted(b.name for b in bots) == [
        "DOGE/USDT 1m · Momentum 100", "DOGE/USDT 1m · Supertrend 10/3",
        "PEPE/USDT 1m · Momentum 100", "PEPE/USDT 1m · Supertrend 10/3"]
    assert all(b.s.mode == "paper" and isinstance(b.broker, PaperBroker) for b in bots)
    assert all(b.s.max_capital == 500 and b.broker.balances().quote == 500 for b in bots)
    assert len({b.broker.wallet_path for b in bots}) == 4  # un compte fictif par bot
    assert {d.symbol for d in PublicData.made} == {"PEPE/USDT", "DOGE/USDT"}  # une connexion par crypto
    assert all(d.exchange == "connexion partagée" and d.cache_seconds > 0 for d in PublicData.made)
    pepe = [b for b in bots if b.s.symbol == "PEPE/USDT"]
    assert pepe[0].broker.data is pepe[1].broker.data
    folder = tmp_path / "data" / "tournoi"
    registry = json.loads((folder / "tournoi.json").read_text(encoding="utf-8"))
    assert [m["symbol"] for m in registry["markets"]] == ["PEPE/USDT", "DOGE/USDT"]
    assert [s["variant"] for s in registry["strategies"]] == ["Supertrend 10/3", "Momentum 100"]
    page = (folder / "tableau-de-bord.html").read_text(encoding="utf-8")
    assert "Tournoi en argent fictif" in page and "Momentum 100" in page
    assert "Tournoi : 4 bots, 0 en position, 0 trades clôturés" in caplog.text  # résumé dans la console
    assert main.main(["tournoi", "--unite", "1m", "--top", "3", "--capital", "500"]) == 0
    again = json.loads((folder / "tournoi.json").read_text(encoding="utf-8"))
    assert again["started"] == registry["started"]  # un tournoi relancé garde sa date de départ


def test_tournament_explains_what_is_missing(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert main.main(["tournoi"]) == 1
    assert "Lance d'abord le laboratoire" in caplog.text
    lab_file(tmp_path / "data" / "laboratoire.json", ("Cassure 20/10", "15m", "perd de l'argent", -0.4))
    assert main.main(["tournoi"]) == 0  # rien de retenu : une réponse du labo, pas une panne
    assert "aucune stratégie « à surveiller »" in caplog.text


def test_short_term_lab_keeps_its_own_results_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0.0, 0.01, 1500))))
    monkeypatch.setattr(main, "load_or_fetch", lambda *args, **kwargs: walk)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    assert main.main(["labo", "--symbols", "BTC/USDT", "--timeframes", "1h",
                      "--resultats", "laboratoire-court-terme.json"]) == 0
    assert (tmp_path / "data" / "laboratoire-court-terme.json").exists()
    assert not (tmp_path / "data" / "laboratoire.json").exists()  # le labo long terme n'est pas écrasé


def test_each_lab_has_its_own_tournament_folder():
    assert main.tournament_dir("laboratoire.json") == "tournoi"
    assert main.tournament_dir("laboratoire-court-terme.json") == "tournoi-court-terme"


def test_long_term_tournament_runs_on_the_lab_markets_at_their_own_pace(tmp_path, monkeypatch, caplog):
    from tradingbot.scanner import ScanResult
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    data_dir = tmp_path / "data"
    lab_file(data_dir / "laboratoire-court-terme.json", ("Supertrend 10/3", "1m", "perd de l'argent", -0.3))
    payload = lab_file(data_dir / "laboratoire.json", ("Supertrend 10/3", "4h", "à surveiller", 0.5))
    payload["marches"] = ["BTC/USDT", "ETH/USDT", "actions-AAPL"]  # un CSV d'actions ne se trade pas
    (data_dir / "laboratoire.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    folder = data_dir / "tournoi"
    folder.mkdir(parents=True)
    (folder / "tournoi.json").write_text(json.dumps({  # un autre tournoi avait tourné dans ce dossier
        "started": "2026-01-01T00:00:00+00:00", "strategies": [{"variant": "Momentum 100", "timeframe": "1m"}]}),
        encoding="utf-8")

    class PublicData:
        def __init__(self, exchange_id, symbol, exchange=None, cache_seconds=0.0):
            self.symbol = symbol

    runs = {}
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    monkeypatch.setattr(main, "CcxtBroker", PublicData)
    monkeypatch.setattr(main, "pick_markets", lambda *a, **k: [ScanResult("PEPE/USDT", 0.2, 3e7, 0.0)])
    monkeypatch.setattr(main.webbrowser, "open", lambda uri: None)
    monkeypatch.setattr(main, "run_bots", lambda bots, poll, after_cycle=None: runs.update(bots=bots, poll=poll))

    assert main.main(["tournoi", "--avec-marches-du-labo"]) == 0
    assert [b.name for b in runs["bots"]] == [
        "BTC/USDT 4h · Supertrend 10/3", "ETH/USDT 4h · Supertrend 10/3", "PEPE/USDT 4h · Supertrend 10/3"]
    assert runs["poll"] == 30  # bougies de 4 h : le rythme habituel suffit
    registry = json.loads((folder / "tournoi.json").read_text(encoding="utf-8"))
    assert registry["started"] != "2026-01-01T00:00:00+00:00" and registry["lab_file"] == "laboratoire.json"

    assert main.main(["tournoi", "--labo", "laboratoire-court-terme.json", "--unite", "1m"]) == 0
    assert "Le labo (1m) n'a retenu aucune stratégie" in caplog.text
    assert "relance d'abord « 6 - Laboratoire de strategies »" in caplog.text


def test_tournament_rejects_an_unknown_unit_clearly(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    lab_file(tmp_path / "data" / "laboratoire.json", ("Supertrend 10/3", "4h", "à surveiller", 0.5))
    assert main.main(["tournoi", "--unite", "1x"]) == 1
    assert "Unité de temps inconnue : '1x'" in caplog.text


def test_short_term_lab_can_add_the_combos_and_the_tournament_runs_them(tmp_path, monkeypatch):
    from tradingbot.lab import SHORT_TERM_VARIANTS
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(4).normal(0.0, 0.01, 1500))))
    monkeypatch.setattr(main, "load_or_fetch", lambda *args, **kwargs: walk)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    assert main.main(["labo", "--symbols", "BTC/USDT", "--timeframes", "1h", "--combinaisons",
                      "--resultats", "laboratoire-court-terme.json"]) == 0
    saved = json.loads((tmp_path / "data" / "laboratoire-court-terme.json").read_text(encoding="utf-8"))
    assert len(saved["rows"]) == len(SHORT_TERM_VARIANTS)  # variantes, combinaisons et impulsions
    assert all("gross_expectancy_pct" in r for r in saved["rows"])
    combo = {"rows": [{"variant": "Cassure 20/10 + volume x2", "timeframe": "5m", "verdict": "à surveiller"}]}
    assert main.tournament_picks(combo, "1m", 6)[0][:2] == ("Cassure 20/10 + volume x2", "1m")


def test_tournament_runs_with_the_orders_and_fees_of_its_lab(tmp_path, monkeypatch, caplog):
    import logging
    from tradingbot.scanner import ScanResult
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    data_dir = tmp_path / "data"
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(6).normal(0.0, 0.01, 1500))))
    monkeypatch.setattr(main, "load_or_fetch", lambda *args, **kwargs: walk)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    assert main.main(["labo", "--symbols", "BTC/USDT", "--timeframes", "1h", "--ordres-limites",
                      "--resultats", "laboratoire-court-terme.json"]) == 0
    saved = json.loads((data_dir / "laboratoire-court-terme.json").read_text(encoding="utf-8"))
    assert saved["execution"]["order_type"] == "limit" and "ordres limites" in caplog.text

    saved["rows"] = [{"variant": "Supertrend 10/3", "timeframe": "15m", "verdict": "à surveiller"}]
    (data_dir / "laboratoire-court-terme.json").write_text(json.dumps(saved), encoding="utf-8")

    class PublicData:
        def __init__(self, exchange_id, symbol, exchange=None, cache_seconds=0.0):
            self.symbol = symbol

    runs = {}
    monkeypatch.setattr(main, "CcxtBroker", PublicData)
    monkeypatch.setattr(main, "pick_markets", lambda *a, **k: [ScanResult("PEPE/USDT", 0.2, 3e7, 0.0)])
    monkeypatch.setattr(main.webbrowser, "open", lambda uri: None)
    monkeypatch.setattr(main, "run_bots", lambda bots, poll, after_cycle=None: runs.update(bots=bots))
    assert main.main(["tournoi", "--labo", "laboratoire-court-terme.json"]) == 0
    (bot,) = runs["bots"]
    assert bot.name == "PEPE/USDT 15m · Supertrend 10/3" and bot.s.execution.order_type == "limit"
    assert bot.s.data_dir == data_dir / "tournoi-court-terme"


def test_tournament_merges_both_short_term_labs_with_their_own_orders(tmp_path, monkeypatch):
    from tradingbot.execution import ExecutionParams
    from tradingbot.scanner import ScanResult
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    data_dir = tmp_path / "data"
    market = lab_file(data_dir / "laboratoire-court-terme.json", ("Supertrend 10/3", "15m", "à surveiller", 0.10),
                      ("Momentum 100", "5m", "à surveiller", 0.05))
    market["execution"] = {"order_type": "market"}
    limits = lab_file(data_dir / "laboratoire-court-terme-limites.json",
                      ("Supertrend 10/3", "15m", "à surveiller", 0.20), ("Cassure 20/10", "15m", "perd de l'argent", -0.1))
    limits["execution"] = {"order_type": "limit", "maker_fee_rate": 0.00075}
    for name, payload in (("laboratoire-court-terme.json", market), ("laboratoire-court-terme-limites.json", limits)):
        (data_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    picks = main.merge_picks([("a", market), ("b", limits)], None, 6, ExecutionParams())
    assert [(v, tf, ex.order_type) for v, tf, _, ex in picks] == [
        ("Supertrend 10/3", "15m", "limit"), ("Momentum 100", "5m", "market")]  # la meilleure version gagne

    class PublicData:
        def __init__(self, exchange_id, symbol, exchange=None, cache_seconds=0.0):
            self.symbol = symbol

    runs = {}
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    monkeypatch.setattr(main, "CcxtBroker", PublicData)
    monkeypatch.setattr(main, "pick_markets", lambda *a, **k: [ScanResult("PEPE/USDT", 0.2, 3e7, 0.0)])
    monkeypatch.setattr(main.webbrowser, "open", lambda uri: None)
    monkeypatch.setattr(main, "run_bots", lambda bots, poll, after_cycle=None: runs.update(bots=bots))
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["tournoi", "--labo", "laboratoire-court-terme.json,laboratoire-court-terme-limites.json"]) == 0
    orders = {b.name: (b.s.execution.order_type, b.s.execution.maker_fee_rate) for b in runs["bots"]}
    assert orders == {"PEPE/USDT 15m · Supertrend 10/3": ("limit", 0.00075), "PEPE/USDT 5m · Momentum 100": ("market", 0.001)}
    assert all(b.s.data_dir == data_dir / "tournoi-court-terme" for b in runs["bots"])


def test_a_finished_lab_sends_its_verdict_as_an_alert(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(8).normal(0.0, 0.01, 1500))))
    monkeypatch.setattr(main, "load_or_fetch", lambda *args, **kwargs: walk)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    awake = []
    monkeypatch.setattr(main, "keep_awake", lambda: awake.append(True) or True)
    assert main.main(["labo", "--symbols", "BTC/USDT", "--timeframes", "1h", "--coeurs", "1"]) == 0
    done = [r for r in caplog.records if r.getMessage().startswith("Labo terminé")]
    assert len(done) == 1 and getattr(done[0], "alert", False) and "VERDICT" in done[0].getMessage()
    assert awake == [True]


def trending_coins(n=8, days=800, seed=2):
    rng = np.random.default_rng(seed)
    return {f"C{k}/USDT": daily_frame(100 * np.exp(np.cumsum(rng.normal(d, 0.01, days))))
            for k, d in enumerate(np.linspace(-0.002, 0.004, n))}


def test_the_portfolio_lab_tests_the_most_traded_coins(tmp_path, monkeypatch, caplog):
    import logging
    from tradingbot.scanner import ScanResult
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    frames, asked = trending_coins(), []
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: "connexion")
    monkeypatch.setattr(main, "by_volume", lambda exchange, top: asked.append(top) or [
        ScanResult(s, 0.1, 1e8, 0.0) for s in frames])
    monkeypatch.setattr(main, "load_or_fetch", lambda ex, symbol, tf, days, cache, exchange=None: (
        asked.append((tf, days)) or frames[symbol]))
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["labo-portefeuille", "--cryptos", "8"]) == 0
    saved = json.loads((tmp_path / "data" / "laboratoire-portefeuille.json").read_text(encoding="utf-8"))
    assert asked[0] == 8 and set(asked[1:]) == {("1d", main.LONG_TERM_DAYS)}
    assert saved["univers"] == sorted(frames) and len(saved["rows"]) == 6
    assert saved["cout"] == pytest.approx(0.0015) and saved["jours"] == 800
    done = [r for r in caplog.records if r.getMessage().startswith("Labo portefeuille terminé")]
    assert len(done) == 1 and getattr(done[0], "alert", False) and "VERDICT" in done[0].getMessage()


def test_the_portfolio_lab_needs_enough_coins(tmp_path, monkeypatch):
    from tradingbot.scanner import ScanResult
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    frames = trending_coins(n=3)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    monkeypatch.setattr(main, "by_volume", lambda exchange, top: [ScanResult(s, 0.1, 1e8, 0.0) for s in frames])
    monkeypatch.setattr(main, "load_or_fetch", lambda ex, symbol, *a, **k: frames[symbol])
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["labo-portefeuille"]) == 1
    assert not (tmp_path / "data" / "laboratoire-portefeuille.json").exists()


class DailyExchange:
    """Une plateforme qui rejoue des bougies d'un jour : derniers prix et clôtures terminées."""

    def __init__(self, frames):
        self.frames = frames
        self.markets = {s: {"symbol": s, "base": s.split("/")[0], "quote": "USDT", "spot": True, "active": True}
                        for s in frames}

    def load_markets(self):
        return self.markets

    def milliseconds(self):
        return int(max(df["ts"].iloc[-1] for df in self.frames.values())) + 86_400_000 + 1

    def fetch_tickers(self, symbols=None):
        return {s: {"last": float(df["close"].iloc[-1])} for s, df in self.frames.items() if symbols is None or s in symbols}

    def fetch_ohlcv(self, symbol, timeframe, limit):
        assert timeframe == "1d"
        return self.frames[symbol][["ts", "open", "high", "low", "close", "volume"]].iloc[-limit:].values.tolist()


def portfolio_lab(path, verdicts, universe):
    rows = [{"variant": name, "verdict": verdict} for name, verdict in verdicts.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rows": rows, "univers": universe}), encoding="utf-8")


def test_the_paper_portfolio_runs_only_what_the_lab_retained(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    frames = trending_coins(days=60)
    portfolio_lab(data / "laboratoire-portefeuille.json", {
        "Momentum croisé 7 j, 3 cryptos": "à surveiller", "Momentum croisé 28 j, 5 cryptos": "perd de l'argent",
    }, [*frames, "DISPARUE/USDT"])
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: DailyExchange(frames))
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["portefeuille", "--une-fois", "--capital", "500"]) == 0
    books = list((data / "portefeuille").glob("*.json"))
    assert len(books) == 1
    state = json.loads(books[0].read_text(encoding="utf-8"))
    assert state["variant"] == "Momentum croisé 7 j, 3 cryptos" and state["start"] == 500
    assert len(state["rotations"]) == 1 and len(state["holdings"]) == 3 and state["next"]
    assert 495 < state["value"] < 500  # frais et glissement de l'achat, rien d'autre
    alerts = [r.getMessage() for r in caplog.records if getattr(r, "alert", False)]
    assert any("rotation" in m for m in alerts)
    assert main.main(["portefeuille", "--une-fois"]) == 0  # la semaine n'est pas finie : aucune rotation de plus
    assert len(json.loads(books[0].read_text(encoding="utf-8"))["rotations"]) == 1


def test_no_paper_portfolio_without_a_retained_variant(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    assert main.main(["portefeuille", "--une-fois"]) == 1  # le labo n'a jamais tourné
    assert "labo portefeuille" in caplog.text.lower()
    portfolio_lab(data / "laboratoire-portefeuille.json", {"Momentum croisé 7 j, 3 cryptos": "instable"}, ["A/USDT"])
    assert main.main(["portefeuille", "--une-fois"]) == 0  # une réponse, pas une panne
    assert "aucune variante" in caplog.text and not (data / "portefeuille").exists()


def test_the_trader_command_plays_the_lab_strategies_once_and_saves_its_account(tmp_path, monkeypatch, caplog):
    import logging
    from tests.test_trader import ReplayExchange
    from tradingbot.scanner import ScanResult
    caplog.set_level(logging.INFO, logger="tradingbot")
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("TRADER_LEVERAGE", "2")
    data.mkdir()
    (data / "laboratoire.json").write_text(json.dumps({"rows": [
        {"variant": "Momentum 28", "timeframe": "1h", "verdict": "à surveiller", "expectancy_pct": 0.3, "trades": 60}],
        "execution": {"order_type": "market", "fee_rate": 0.001, "maker_fee_rate": 0.001, "slippage": 0.0005}}),
        encoding="utf-8")
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.01, 400))))
    exchange = ReplayExchange({"BTC/USDT": walk})
    exchange.i = len(walk) - 1
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: exchange)
    monkeypatch.setattr(main, "by_volume", lambda exchange, top: [ScanResult("BTC/USDT", 0.1, 1e9, 0.0)])
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["trader", "--une-fois"]) == 0
    state = json.loads((data / "trader" / "compte.json").read_text(encoding="utf-8"))
    assert state["settings"]["max_leverage"] == 2 and state["playbook"][0]["key"] == "Momentum 28 (1h)"
    assert state["universe"] == ["BTC/USDT"] and state["value"] == pytest.approx(1000)
    start = [r for r in caplog.records if r.getMessage().startswith("Trader fictif")]
    assert start and getattr(start[0], "alert", False)


def test_the_trader_replay_shows_explained_trades_and_says_it_is_not_a_proof(tmp_path, monkeypatch, capsys):
    from tradingbot.scanner import ScanResult
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data))
    data.mkdir()
    (data / "laboratoire.json").write_text(json.dumps({"rows": [
        {"variant": "Cassure 20/10", "timeframe": "1h", "verdict": "à surveiller", "expectancy_pct": 0.3,
         "trades": 60}]}), encoding="utf-8")
    walk = frame_from_closes(100 * np.exp(np.cumsum(np.random.default_rng(4).normal(0, 0.01, 1500))))
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    monkeypatch.setattr(main, "by_volume", lambda exchange, top: [ScanResult(s, 0.1, 1e9, 0.0)
                                                                  for s in ("BTC/USDT", "ETH/USDT")])
    monkeypatch.setattr(main, "load_or_fetch", lambda ex, symbol, tf, days, cache, exchange=None: walk)
    monkeypatch.setattr(main, "keep_awake", lambda: True)
    assert main.main(["trader", "--rejouer"]) == 0
    state = json.loads((data / "trader" / "rejeu.json").read_text(encoding="utf-8"))
    assert state["replay"] and state["trades"] and all(t["diagnosis"]["text"] for t in state["trades"])
    assert "ce n'est pas une preuve" in capsys.readouterr().out


def test_without_a_retained_strategy_the_replay_has_nothing_to_show(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    assert main.main(["trader", "--rejouer"]) == 0
    assert "rien à rejouer" in caplog.text


def test_the_bots_command_runs_the_swarm_in_paper_money_once_at_a_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FLOTTE_CRYPTOS", "25")
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: None)
    monkeypatch.setattr(main, "keep_awake", lambda: None)
    runs = []

    def fake_run(swarm, seconds, once):
        runs.append((swarm, seconds, once))
        assert main.fleet_running(tmp_path / "data" / "bots")  # le signal de vie est écrit avant le premier tour

    monkeypatch.setattr(main, "run_swarm", fake_run)
    assert main.main(["flotte", "--une-fois", "--secondes", "3"]) == 0
    swarm, seconds, once = runs[0]
    assert once and seconds == 3 and swarm.settings.coins == 25 and swarm.settings.max_bots == 25 * 8
    assert swarm.tester is not None and swarm.mood is main.fetch_mood
    assert main.main(["flotte"]) == 1  # ils tournent déjà (le signal de vie est récent) : jamais deux fois
    swarm.release()
    monkeypatch.setenv("FLOTTE_LEVIER_COURT", "50")
    assert main.main(["flotte"]) == 1  # réglage hors bornes : refusé avec une explication


def test_the_trend_command_shows_the_rule_and_its_robustness_gate(tmp_path, monkeypatch, capsys):
    from tests.test_trend import DailyExchange as TrendExchange, days, walk
    from tradingbot import trend
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    frames = {"BTC/USDT": days(walk(1, 700, drift=0.002), start=trend.EARLY_MS),
              "ETH/USDT": days(walk(2, 700), start=trend.EARLY_MS)}
    exchange = TrendExchange(frames, n=700)
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: exchange)
    assert main.main(["tendance"]) == 0
    out = capsys.readouterr().out
    assert "Bitcoin à" in out and "Ether à" in out and "Compte fictif créé le" in out and "acheter et garder" in out
    folder = tmp_path / "data" / "tendance"
    assert (folder / "compte.json").exists() and (folder / "binance_BTC-USDT_1d.csv").exists()
    assert not (folder / "robustesse.json").exists()  # la commande ne juge pas : c'est la porte « robustesse » qui le fait
    assert main.main(["robustesse", "--tendance"]) == 0
    out = capsys.readouterr().out
    assert "BTC moy. 50 j" in out and "ETH moy. 200 j" in out and "VERDICT : " in out and "chaque SORTIE" in out
    saved = json.loads((folder / "robustesse.json").read_text(encoding="utf-8"))
    assert len(saved["rows"]) == 6 and saved["verdict"].startswith("VERDICT : ")
    assert not (tmp_path / "data" / "robustesse.json").exists()  # le test de la stratégie du bot réel n'est pas remplacé


def test_the_trend_command_fails_cleanly_without_network(tmp_path, monkeypatch, capsys):
    from tests.test_trend import DailyExchange as TrendExchange
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    exchange = TrendExchange({}, n=0)
    exchange.down = True
    monkeypatch.setattr(main, "make_exchange", lambda exchange_id: exchange)
    assert main.main(["tendance"]) == 1 and "pas assez de bougies" in capsys.readouterr().out
    assert main.main(["robustesse", "--tendance"]) == 1
