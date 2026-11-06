import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingbot import webapp
from tradingbot.webapp import (
    ACTIONS, FIELDS, HEADER, HEADER_VALUE, Handler, Poller, Site, TaskManager, already_running, bind, clean_value,
    finite_json, lab_summaries, next_step, steps_for, update_env,
)

FAKE_BOT = """
import os, subprocess, sys, time
args = sys.argv[1:]
print("commande :", " ".join(args), flush=True)
print("accents : é à ç ≥ ×", flush=True)
if os.environ.get("FAKE_CHILD") and args[0] == "labo":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    print("petit-enfant", child.pid, flush=True)
if args[0] == "labo":
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
sys.exit(3 if "--echec" in args or args[0] in os.environ.get("FAKE_FAIL", "").split(",") else 0)
"""


@pytest.fixture
def fake_bot(tmp_path):
    path = tmp_path / "fakebot.py"
    path.write_text(FAKE_BOT, encoding="utf-8")
    return [sys.executable, str(path)]


def manager(tmp_path, fake_bot, **env):
    return TaskManager(tmp_path, {**os.environ, "PYTHONIOENCODING": "utf-8", **env}, fake_bot)


def wait(condition, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.05)
    return False


def alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102  # WAIT_TIMEOUT : il tourne
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")  # un zombie est déjà mort


def test_an_action_runs_the_same_command_as_its_launcher_and_streams_its_journal(tmp_path, fake_bot):
    tasks = manager(tmp_path, fake_bot)
    task = tasks.start("labo-court")
    assert wait(lambda: task.status != "en cours")
    lines, total = task.read(0)
    assert task.status == "terminé" and total == len(lines)
    assert lines[0] == "commande : " + " ".join(steps_for("labo-court", tmp_path)[0])
    assert "accents : é à ç ≥ ×" in lines  # UTF-8 de bout en bout
    assert "--combinaisons" in lines[0] and "laboratoire-court-terme.json" in lines[0]
    assert task.read(total)[0] == []  # rien de neuf depuis la dernière lecture
    assert task.to_dict()["status"] == "terminé" and task.to_dict()["last"] == "Terminé."


def test_the_autopilot_runs_the_five_labs_then_starts_the_trader_the_tournaments_and_the_portfolio(tmp_path, fake_bot):
    tasks = manager(tmp_path, fake_bot)
    pilot = tasks.start("pilote")
    assert wait(lambda: pilot.status != "en cours")
    lines, _ = pilot.read(0)
    steps = [line for line in lines if "=== Étape" in line]
    assert len(steps) == 5 and steps[0].endswith(": labo-portefeuille")  # la plus rapide d'abord
    assert any("--futures" in step for step in steps)  # le scalping avec les frais des futures
    assert any("« Mon trader » lancé automatiquement" in line for line in lines)
    assert any("« Rejouer mon trader sur l'historique » lancé automatiquement" in line for line in lines)  # un calcul
    assert any("« Portefeuille momentum » lancé automatiquement" in line for line in lines)
    started = {t.action.key for t in tasks.tasks.values()}
    assert {"trader", "trader-rejeu", "tournoi-court", "tournoi-long", "portefeuille"} <= started
    tournament = next(t for t in tasks.tasks.values() if t.action.key == "tournoi-court")
    assert wait(lambda: tournament.status != "en cours")
    assert "--sans-navigateur" in tournament.read(0)[0][0]  # le site montre déjà le tableau de bord


def test_a_failing_step_does_not_stop_the_night_research(tmp_path, fake_bot):
    (tmp_path / "actions").mkdir()
    (tmp_path / "actions" / "aapl.csv").write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
    assert steps_for("labo-long", tmp_path) == [("labo", "--csv-dir", "actions")]
    tasks = manager(tmp_path, fake_bot, FAKE_FAIL="labo,labo-portefeuille")
    research = tasks.start("recherche")
    assert wait(lambda: research.status != "en cours")
    assert research.status == "échec" and research.to_dict()["failed"] == 5
    assert sum("on passe à la suivante" in line for line in research.read(0)[0]) == 5
    pilot = tasks.start("pilote")
    assert wait(lambda: pilot.status != "en cours")
    assert {t.action.key for t in tasks.tasks.values()} == {"recherche", "pilote"}  # rien n'a marché : pas de tournoi


def test_one_heavy_computation_at_a_time_and_stop_kills_the_whole_tree(tmp_path, fake_bot):
    tasks = manager(tmp_path, fake_bot, FAKE_SLEEP="60", FAKE_CHILD="1")
    lab = tasks.start("labo-court")
    assert wait(lambda: any(line.startswith("petit-enfant") for line in lab.read(0)[0]))
    grandchild = int(next(line for line in lab.read(0)[0] if line.startswith("petit-enfant")).split()[1])
    with pytest.raises(ValueError, match="tourne déjà"):
        tasks.start("labo-court")
    with pytest.raises(ValueError, match="un seul calcul à la fois"):
        tasks.start("labo-long")
    assert tasks.blocker("check") is None  # une vérification rapide peut tourner pendant un labo
    lab.stop()
    assert wait(lambda: lab.status == "arrêté", timeout=15)
    assert wait(lambda: not alive(grandchild), timeout=15)  # les cœurs du labo ne continuent pas en cachette
    assert tasks.blocker("labo-long") is None


def test_settings_lines_are_changed_in_place_and_checked(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# Mes réglages\nMODE=paper\nBOTS=BTC/USDT@1h\nFEE_RATE=0.001\nBOTS=ETH/USDT@4h\n", encoding="utf-8")
    update_env(env, {"BOTS": "SOL/USDT@15m", "TELEGRAM_CHAT_ID": "42"})
    assert env.read_text(encoding="utf-8").splitlines() == [
        "# Mes réglages", "MODE=paper", "BOTS=SOL/USDT@15m", "FEE_RATE=0.001", "BOTS=ETH/USDT@4h", "TELEGRAM_CHAT_ID=42"]
    fields = webapp.FIELD_KEYS
    assert clean_value(fields["BOTS"], "btc/usdt@15m, eth/usdt@1h") == "BTC/USDT@15m,ETH/USDT@1h"
    assert clean_value(fields["FEE_RATE"], "0,00075") == "0.00075"
    assert clean_value(fields["EXCHANGE"], "OKX") == "okx"
    for key, bad in [("BOTS", "BTC/USDT"), ("BOTS", "BTC/USDT@1x"), ("FEE_RATE", "0.5"), ("FEE_RATE", "abc"),
                     ("EXCHANGE", "inconnue"), ("TELEGRAM_TOKEN", "pas-un-token"), ("TELEGRAM_CHAT_ID", "12a"),
                     ("PAPER_START_BALANCE", "-5")]:
        with pytest.raises(ValueError):
            clean_value(fields[key], bad)


def site(tmp_path, fake_bot, env_text="MODE=paper\n", **kwargs):
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    pristine = {k: v for k, v in os.environ.items() if k not in ("MODE", "BOTS", "DATA_DIR", "TELEGRAM_TOKEN")}
    return Site(tmp_path, pristine, make_exchange=lambda exchange_id: None, port=0, command=fake_bot, **kwargs)


def test_the_site_never_switches_to_real_money(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    for key in ("MODE", "CONFIRM_LIVE_TRADING", "API_KEY", "API_SECRET", "MAX_CAPITAL"):
        with pytest.raises(ValueError, match="ne se change pas depuis le site"):
            s.save_settings({key: "live"})
    live = site(tmp_path, fake_bot, "MODE=live\nCONFIRM_LIVE_TRADING=OUI\nMAX_CAPITAL=100\n")
    with pytest.raises(ValueError, match="jamais de bot en argent réel"):
        live.launch("bots")
    assert live.state()["mode_label"] == "ARGENT RÉEL"
    assert [a for a in live.state()["actions"] if a["key"] == "bots"][0]["blocked"]


def test_saved_settings_are_used_by_the_next_commands_and_secrets_never_shown(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot, "MODE=paper\nBOTS=BTC/USDT@1h\n")
    assert s.settings().bots == (("BTC/USDT", "1h"),)
    token = "123456789:" + "A" * 30
    assert s.save_settings({"BOTS": "ETH/USDT@4h", "TELEGRAM_TOKEN": token})["saved"] == ["BOTS", "TELEGRAM_TOKEN"]
    assert s.settings().bots == (("ETH/USDT", "4h"),) and s.settings().telegram_token == token
    form = s.settings_form(local=True)
    secret = [f for f in form["fields"] if f["key"] == "TELEGRAM_TOKEN"][0]
    assert secret == {**secret, "set": True} and "value" not in secret and token not in json.dumps(form)
    assert s.save_settings({"TELEGRAM_TOKEN": ""})["saved"] == []  # vide : le token enregistré est gardé
    assert s.settings().data_dir == tmp_path / "data"  # « data » à côté du bot, où que le site ait été lancé
    # Le formulaire renvoie toutes ses cases : celles laissées vides gardent leur valeur (ici celle par défaut).
    form = {f["key"]: f.get("value", "") for f in s.settings_form(local=True)["fields"]}
    assert form["PAPER_START_BALANCE"] == "" and form["EXCHANGE"] == ""
    s.save_settings(form)
    assert s.settings().paper_start_balance == 10_000 and s.settings().exchange == "binance"
    assert s.settings().bots == (("ETH/USDT", "4h"),) and s.settings().telegram_token == token


def test_the_home_page_always_says_what_to_do_next():
    pilot = next_step([{"file": "laboratoire.json", "done": False}], [], [])
    assert pilot["action"] == "pilote"
    labs = [{"file": "laboratoire-court-terme.json", "done": True, "retained": 2},
            {"file": "laboratoire.json", "done": True, "retained": 0}]
    assert next_step(labs, [], [])["action"] == "tournoi-court"
    nothing = next_step([{**lab, "retained": 0} for lab in labs], [], [])
    assert "Aucune stratégie ne gagne après frais" in nothing["title"]
    running = [SimpleNamespace(action=ACTIONS["pilote"])]
    assert "tournois et le portefeuille démarreront tout seuls" in next_step(labs, running, [])["text"]
    tournament = [SimpleNamespace(action=ACTIONS["tournoi-court"])]
    assert next_step(labs, tournament, [{"running": True}])["view"] == "tableau"
    retained = {"lab": {"done": True, "retained": 2}, "books": [], "running": False}
    assert next_step(labs, tournament, [{"running": True}], retained)["action"] == "portefeuille"
    only_portfolio = [{**lab, "done": False} for lab in labs]
    assert next_step(only_portfolio, [], [], retained)["action"] == "portefeuille"  # son labo a suffi
    alone = [SimpleNamespace(action=ACTIONS["portefeuille"])]
    assert next_step(labs[1:], alone, [{"running": False}], {**retained, "running": True})["view"] == "tableau"
    assert next_step(labs, [], [], None, {"plays": 2})["action"] == "trader"  # le trader d'abord
    trading = [SimpleNamespace(action=ACTIONS["trader"])]
    assert next_step(labs[1:], trading, [], None, {"plays": 2})["view"] == "tableau"


def test_lab_results_are_summarised_for_the_home_page(tmp_path):
    rows = [{"variant": "Cassure 20/10", "timeframe": "5m", "trades": 300, "verdict": "à surveiller",
             "gross_expectancy_pct": 0.12, "expectancy_pct": -0.18},
            {"variant": "MACD 12/26/9", "timeframe": "1m", "trades": 900, "verdict": "perd de l'argent",
             "gross_expectancy_pct": float("nan"), "expectancy_pct": -0.3}]
    (tmp_path / "laboratoire-court-terme.json").write_text(json.dumps(
        {"date": "2026-11-05T02:00:00+00:00", "verdict": "VERDICT : une seule.\nDétail", "rows": rows}), encoding="utf-8")
    summary = {s["file"]: s for s in lab_summaries(tmp_path)}
    short = summary["laboratoire-court-terme.json"]
    assert short["retained"] == 1 and short["names"] == ["Cassure 20/10 (5m)"] and short["verdict"] == "une seule."
    assert short["best"] == {"variant": "Cassure 20/10", "timeframe": "5m", "gross": 0.12, "net": -0.18}
    assert summary["laboratoire.json"]["done"] is False
    assert finite_json({"a": [float("nan"), 1.0, float("inf")]}) == {"a": [None, 1.0, None]}


def test_a_source_is_read_only_while_someone_looks_at_it():
    calls = []
    poller = Poller(lambda: calls.append(1) or len(calls), every=0.01, idle=0.3)
    assert poller.get()[0] is None  # premier appel : la lecture démarre
    assert wait(lambda: poller.get()[0] is not None, timeout=5)
    assert wait(lambda: not poller.thread.is_alive(), timeout=5)  # plus personne ne regarde : la lecture s'arrête
    count = len(calls)
    time.sleep(0.1)
    assert len(calls) == count


def request(base, path, data=None, headers=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                 headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with opener.open(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8"), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8"), dict(exc.headers)


@pytest.fixture
def server(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    httpd = bind(s, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield s, f"http://127.0.0.1:{s.port}"
    httpd.shutdown()
    httpd.server_close()


def test_the_site_serves_its_page_and_only_obeys_its_own_page(server):
    s, base = server
    status, page, headers = request(base, "/")
    assert status == 200 and "Prochaine étape" in page and "Radar des mouvements" in page
    assert "frame-src 'self'" in headers["Content-Security-Policy"]
    status, body, _ = request(base, "/api/etat")
    state = json.loads(body)
    assert status == 200 and state["mode_label"] == "argent fictif" and state["next"]["action"] == "pilote"
    assert {a["key"] for a in state["actions"]} == set(ACTIONS)
    ok = {HEADER: HEADER_VALUE, "Content-Type": "application/json"}
    assert request(base, "/api/lancer", {"action": "check"})[0] == 403  # sans l'en-tête de la page
    assert request(base, "/api/lancer", {"action": "check"}, {**ok, "Origin": "http://evil.example"})[0] == 403
    assert request(base, "/api/lancer", {"action": "check"}, {**ok, "Host": "evil.example:80"})[0] == 403
    status, body, _ = request(base, "/api/lancer", {"action": "check"}, {**ok, "Origin": base})
    task = json.loads(body)["task"]
    assert status == 200 and task["title"] == "Vérifier la connexion"
    assert wait(lambda: s.tasks.get(task["id"]).status != "en cours")
    status, body, _ = request(base, f"/api/journal?tache={task['id']}&depuis=0")
    assert status == 200 and json.loads(body)["lines"][0] == "commande : check"
    assert request(base, "/api/lancer", {"action": "inconnue"}, ok)[0] == 400
    assert request(base, "/api/journal?tache=abc")[0] == 400
    assert already_running(s.port) and not already_running(1)


def test_dashboards_are_shown_inside_the_site(server):
    s, base = server
    status, page, _ = request(base, "/tableau/tournoi-court-terme")
    assert status == 200 and "Rien à montrer ici pour l'instant" in page  # pas encore de tournoi
    status, page, _ = request(base, "/tableau/bots")
    assert status == 200 and "Tableau de bord" in page and (s.root / "data" / "tableau-de-bord.html").exists()
    assert "Rien à montrer" in request(base, "/tableau/../../.env")[1]  # seulement les tableaux connus


def fake_handler(s, path, client="192.168.1.20", headers=None):
    handler = Handler.__new__(Handler)
    handler.server = SimpleNamespace(site=s)
    handler.client_address = (client, 50_000)
    handler.headers = Message()
    for key, value in (headers or {}).items():
        handler.headers[key] = value
    handler.path, handler.command = path, "GET"
    sent = []
    handler.send = lambda status, body, content_type, extra=None: sent.append((status, body, extra or {}))
    return handler, sent


def test_devices_on_the_home_wifi_need_the_code(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot, lan_address="192.168.1.10")
    s.port = 8765
    host = {"Host": "192.168.1.10:8765"}
    handler, sent = fake_handler(s, "/", headers=host)
    handler.do_GET()
    assert sent[0][0] == 403 and "Entre le code du bot" in sent[0][1].decode()
    handler, sent = fake_handler(s, "/api/etat", headers=host)
    handler.do_GET()
    assert sent[0][0] == 403
    handler, sent = fake_handler(s, f"/?code={s.code}", headers=host)
    handler.do_GET()
    assert sent[0][0] == 303 and f"code-du-bot={s.code}" in sent[0][2]["Set-Cookie"]
    handler, sent = fake_handler(s, "/api/etat", headers={**host, "Cookie": f"code-du-bot={s.code}"})
    handler.do_GET()
    assert sent[0][0] == 200
    handler, sent = fake_handler(s, "/?code=ééé", headers=host)  # code accentué : refusé, sans planter
    handler.do_GET()
    assert sent[0][0] == 403
    assert (tmp_path / "data" / "site-code.txt").read_text(encoding="utf-8") == s.code  # le même code au relancement


def radar_ready(s, symbols=("PEPE/USDT", "BTC/USDT"), price=1.0):
    markets = {sym: {"symbol": sym, "spot": True, "active": True, "base": sym.split("/")[0], "quote": "USDT"}
               for sym in symbols}
    s.radar.radar.update(markets, {sym: {"last": price, "quoteVolume": 1e8, "percentage": 1.0} for sym in symbols},
                         time.time())


def test_an_opportunity_is_studied_in_the_background_then_shown(server, monkeypatch):
    from tests.test_moves import jumps
    s, base = server
    radar_ready(s, price=100.0)
    monkeypatch.setattr(s.study_market, "history", lambda symbol, days: jumps())
    page = {HEADER: HEADER_VALUE}

    def get(path):
        return request(base, path, headers=page)

    assert request(base, "/api/etude?symbole=PEPE/USDT&fenetre=300")[0] == 403  # un autre site ne peut pas la lancer
    assert get("/api/etude?symbole=XRP/USDT&fenetre=300")[0] == 400  # pas suivie par le radar
    assert get("/api/etude?symbole=PEPE/USDT&fenetre=120")[0] == 400
    first = json.loads(get("/api/etude?symbole=PEPE/USDT&fenetre=300")[1])
    assert first["status"] in ("en cours", "prêt")
    assert wait(lambda: json.loads(get("/api/etude?symbole=PEPE/USDT&fenetre=300")[1])["status"] == "prêt")
    result = json.loads(get("/api/etude?symbole=PEPE/USDT&fenetre=300")[1])["result"]
    assert result["symbol"] == "PEPE/USDT" and len(result["options"]) == 3 and result["verdict"]["text"]
    radar = json.loads(request(base, "/api/radar?fenetre=300")[1])
    assert radar["journal"]["rows"][0]["window"] == 60 and radar["journal"]["cost"] == pytest.approx(0.003)


def test_trials_are_opened_watched_and_sold_through_the_site(server, monkeypatch):
    from tests.test_desk import calm
    s, base = server
    radar_ready(s, price=100.0)
    candles = calm(price=100.0)
    monkeypatch.setattr(s.desk_market, "recent", lambda symbol, limit=60: candles)
    ok = {HEADER: HEADER_VALUE, "Content-Type": "application/json"}
    assert request(base, "/api/essais/ouvrir", {"symbole": "PEPE/USDT", "fenetre": 300, "option": "tout"}, ok)[0] == 400
    status, body, _ = request(base, "/api/essais/ouvrir", {"symbole": "PEPE/USDT", "fenetre": 300, "option": "normale"}, ok)
    position = json.loads(body)["position"]
    assert status == 200 and position["symbol"] == "PEPE/USDT" and position["stop"] < 100.0
    summary = json.loads(request(base, "/api/essais")[1])
    assert summary["positions"][0]["price"] == 100.0 and summary["stats"]["n"] == 0
    assert s.check_trials() == []  # au-dessus du stop, rien ne bouge
    radar_ready(s, price=position["stop"] * 0.99)  # le prix passe sous le stop
    closed = s.check_trials()
    assert closed and closed[0]["reason"] == "stop"
    status, body, _ = request(base, "/api/essais/ouvrir", {"symbole": "BTC/USDT", "fenetre": 60, "option": "rapide"}, ok)
    trade = json.loads(request(base, "/api/essais/vendre", {"id": json.loads(body)["position"]["id"]}, ok)[1])["trade"]
    assert trade["reason"] == "main"
    assert json.loads(request(base, "/api/essais")[1])["stats"]["n"] == 2
    assert request(base, "/api/essais/zero", {}, ok)[0] == 200
    assert json.loads(request(base, "/api/essais")[1])["equity"] == 1000.0
    assert request(base, "/api/essais/zero", {})[0] == 403  # comme toute action : seulement depuis la page du site


def test_the_site_explains_each_technique_with_its_sources(server):
    s, base = server
    status, body, _ = request(base, "/api/savoir")
    data = json.loads(body)
    assert status == 200 and len(data["entries"]) >= 10
    assert set(data["families_covered"]) == set(data["all_families"])
    assert all(src["url"].startswith("https://scispace.com/papers/") for e in data["entries"] for src in e["sources"])


def test_the_portfolio_is_summarised_for_the_home_page(tmp_path):
    from tradingbot.webapp import portfolio_summary
    empty = portfolio_summary(tmp_path, False)
    assert empty == {"lab": {"done": False, "date": None, "tested": 0, "retained": 0, "coins": 0, "names": [],
                             "best": None}, "books": [], "running": False}
    rows = [{"variant": "Momentum croisé 28 j, 5 cryptos", "verdict": "perd de l'argent", "mean_pct": 0.9,
             "basket_pct": 0.2},
            {"variant": "Momentum croisé 14 j, 3 cryptos", "verdict": "à surveiller", "mean_pct": 0.4,
             "basket_pct": float("nan")}]
    (tmp_path / "laboratoire-portefeuille.json").write_text(json.dumps(
        {"date": "2026-11-06T02:00:00+00:00", "rows": rows, "univers": ["A/USDT", "B/USDT"]}), encoding="utf-8")
    (tmp_path / "portefeuille").mkdir()
    (tmp_path / "portefeuille" / "momentum.json").write_text(json.dumps(
        {"variant": "Momentum croisé 14 j, 3 cryptos", "start": 1000, "value": 1012.5, "holdings": {"SOL/USDT": 2.0},
         "next": "2026-11-13T00:10:00+00:00", "since": "2026-11-06T09:00:00+00:00", "rotations": [{}]}),
        encoding="utf-8")
    (tmp_path / "portefeuille" / "abime.json").write_text("{pas du json", encoding="utf-8")
    summary = portfolio_summary(tmp_path, True)
    assert summary["lab"]["retained"] == 1 and summary["lab"]["coins"] == 2
    assert summary["lab"]["best"] == {"variant": "Momentum croisé 14 j, 3 cryptos", "mean": 0.4, "basket": None,
                                      "verdict": "à surveiller"}  # la meilleure des retenues, sans NaN
    [book] = summary["books"]
    assert book["holdings"] == ["SOL"] and book["pnl_pct"] == pytest.approx(1.25) and book["rotations"] == 1
    assert book["retained"]  # toujours retenue par le dernier labo
    json.dumps(summary, allow_nan=False)


class ChartExchange:
    def __init__(self, df):
        self.df = df

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return self.df[["ts", "open", "high", "low", "close", "volume"]].iloc[-limit:].values.tolist()


def test_a_chart_shows_its_levels_its_reading_and_what_the_trader_strategies_say(server):
    from tests.conftest import frame_from_closes
    from tests.test_levels import range_market
    s, base = server
    radar_ready(s)
    s.charts.exchange = ChartExchange(frame_from_closes(range_market(400), spread=0.002))
    (s.root / "data" / "trader").mkdir(parents=True)
    (s.root / "data" / "trader" / "compte.json").write_text(json.dumps({"version": 1, "playbook": [
        {"name": "Rebond sur support", "timeframe": "4h", "key": "Rebond sur support (4h)", "status": "à surveiller",
         "why": "Le prix est descendu sur un support solide."}], "trades": [], "positions": []}), encoding="utf-8")
    assert request(base, "/api/graphique?symbole=BTC/USDT&unite=4h")[0] == 403  # seulement depuis la page
    page = {HEADER: HEADER_VALUE}
    assert request(base, "/api/graphique?symbole=XRP/USDT&unite=4h", headers=page)[0] == 400  # pas suivie
    assert request(base, "/api/graphique?symbole=BTC/USDT&unite=3h", headers=page)[0] == 400
    status, body, _ = request(base, "/api/graphique?symbole=BTC/USDT&unite=4h", headers=page)
    chart = json.loads(body)
    assert status == 200 and len(chart["candles"]) == 150 and len(chart["ma50"]) == 150
    kinds = {z["kind"] for z in chart["levels"]}
    assert kinds == {"support", "resistance"} and all(z["touches"] >= 2 for z in chart["levels"])
    assert chart["reading"]["sentences"] and chart["plays"][0]["signal"] in ("achat", "vente", "rien")
    markets = json.loads(request(base, "/api/marches")[1])
    assert [m["symbol"] for m in markets["markets"]] and markets["timeframes"] == ["15m", "1h", "4h", "1d"]


def test_the_trader_is_shown_with_its_replay_and_its_settings(server):
    s, base = server
    view = json.loads(request(base, "/api/trader")[1])
    assert view["live"]["exists"] is False and view["replay"]["exists"] is False
    assert view["settings"]["profile"] == "futures" and view["profiles"] == ["futures", "spot"]
    (s.root / "data" / "trader").mkdir(parents=True)
    (s.root / "data" / "trader" / "rejeu.json").write_text(json.dumps({"version": 1, "replay": True, "start": 1000,
                                                                      "value": 1100, "trades": []}), encoding="utf-8")
    replay = json.loads(request(base, "/api/trader")[1])["replay"]
    assert replay["exists"] and replay["replay"] and replay["pnl_pct"] == pytest.approx(10)


def test_the_trader_settings_stay_in_paper_money_and_within_bounds():
    fields = {f.key: f for f in FIELDS}
    assert clean_value(fields["TRADER_PROFILE"], "Spot") == "spot"
    assert clean_value(fields["TRADER_LEVERAGE"], "5") == "5.0"
    assert clean_value(fields["TRADER_POSITIONS"], "8") == "8"
    for key, bad in [("TRADER_PROFILE", "live"), ("TRADER_LEVERAGE", "50"), ("TRADER_RISK", "0.2"),
                     ("TRADER_POSITIONS", "2.5"), ("TRADER_COINS", "0")]:
        with pytest.raises(ValueError):
            clean_value(fields[key], bad)
