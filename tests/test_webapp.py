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
from tradingbot.config import parse_dotenv
from tradingbot.fleet import LOCK_FILE
from tradingbot.swarm import DETAIL_DIR, settings_from_env
from tradingbot.webapp import (
    ACTIONS, FIELDS, HEADER, HEADER_VALUE, Handler, Poller, Site, TaskManager, already_running, bind, clean_value,
    coin_symbol, finite_json, steps_for, swarm_step, update_env,
)

FAKE_BOT = """
import os, subprocess, sys, time
args = sys.argv[1:]
print("commande :", " ".join(args), flush=True)
print("accents : é à ç ≥ ×", flush=True)
if os.environ.get("FAKE_CHILD") and args[0] == "flotte":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    print("petit-enfant", child.pid, flush=True)
if args[0] == "flotte":
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


# --- les tâches ----------------------------------------------------------------------------------------------------

def test_an_action_runs_the_same_command_as_its_launcher_and_streams_its_journal(tmp_path, fake_bot):
    tasks = manager(tmp_path, fake_bot)
    task = tasks.start("check")
    assert wait(lambda: task.status != "en cours")
    lines, total = task.read(0)
    assert task.status == "terminé" and total == len(lines)
    assert lines[0] == "commande : " + " ".join(steps_for("check", tmp_path)[0])
    assert "accents : é à ç ≥ ×" in lines  # UTF-8 de bout en bout
    assert task.read(total)[0] == []  # rien de neuf depuis la dernière lecture
    assert task.to_dict()["status"] == "terminé" and task.to_dict()["last"] == "Terminé."
    failing = manager(tmp_path, fake_bot, FAKE_FAIL="telegram").start("telegram")
    assert wait(lambda: failing.status != "en cours") and failing.status == "échec"


def test_the_site_only_runs_paper_money_commands(tmp_path):
    assert set(ACTIONS) == {"flotte", "check", "telegram"}
    for key in ACTIONS:
        assert all(step[0] not in ("run", "trader", "tournoi") for step in steps_for(key, tmp_path))  # jamais d'ordre
    assert steps_for("flotte", tmp_path) == [("flotte",)] and ACTIONS["flotte"].endless


def test_the_bots_run_once_and_stop_kills_the_whole_tree(tmp_path, fake_bot):
    tasks = manager(tmp_path, fake_bot, FAKE_SLEEP="60", FAKE_CHILD="1")
    bots = tasks.start("flotte")
    assert wait(lambda: any(line.startswith("petit-enfant") for line in bots.read(0)[0]))
    grandchild = int(next(line for line in bots.read(0)[0] if line.startswith("petit-enfant")).split()[1])
    with pytest.raises(ValueError, match="tourne déjà"):
        tasks.start("flotte")
    assert tasks.blocker("check") is None  # une vérification rapide peut tourner pendant les bots
    bots.stop()
    assert wait(lambda: bots.status == "arrêté", timeout=15)
    assert wait(lambda: not alive(grandchild), timeout=15)  # rien ne continue en cachette
    assert tasks.blocker("flotte") is None


# --- les réglages --------------------------------------------------------------------------------------------------

def test_settings_lines_are_changed_in_place_and_checked(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# Mes réglages\nMODE=paper\nFLOTTE_CRYPTOS=40\nEXCHANGE=binance\n", encoding="utf-8")
    update_env(env, {"FLOTTE_CRYPTOS": "60", "TELEGRAM_CHAT_ID": "42"})
    assert env.read_text(encoding="utf-8").splitlines() == [
        "# Mes réglages", "MODE=paper", "FLOTTE_CRYPTOS=60", "EXCHANGE=binance", "TELEGRAM_CHAT_ID=42"]
    fields = webapp.FIELD_KEYS
    assert clean_value(fields["FLOTTE_CAPITAL"], "1500") == "1500.0"
    assert clean_value(fields["EXCHANGE"], "OKX") == "okx"
    assert clean_value(fields["FLOTTE_MOUVEMENT_MIN"], "2,5") == "2.5"
    for key, bad in [("EXCHANGE", "inconnue"), ("TELEGRAM_TOKEN", "pas-un-token"), ("TELEGRAM_CHAT_ID", "12a"),
                     ("FLOTTE_CAPITAL", "-5"), ("FLOTTE_CRYPTOS", "81"), ("FLOTTE_BOTS_PAR_CRYPTO", "0"),
                     ("FLOTTE_LEVIER_LONG", "0"), ("FLOTTE_LEVIER_COURT", "21"), ("FLOTTE_CRYPTOS", "2.5"),
                     ("FLOTTE_MOUVEMENT_MIN", "60")]:
        with pytest.raises(ValueError):
            clean_value(fields[key], bad)


def site(tmp_path, fake_bot, env_text="MODE=paper\n", **kwargs):
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    pristine = {k: v for k, v in os.environ.items() if not k.startswith(("MODE", "FLOTTE_", "DATA_DIR", "TELEGRAM_"))}
    s = Site(tmp_path, pristine, make_exchange=lambda exchange_id: None, port=0, command=fake_bot, **kwargs)
    s.news.get = lambda url: (_ for _ in ()).throw(ConnectionError("hors ligne"))  # jamais internet dans les tests
    s.news.closes = None
    return s


def test_the_site_never_touches_real_money_settings(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    for key in ("MODE", "CONFIRM_LIVE_TRADING", "API_KEY", "API_SECRET", "MAX_CAPITAL", "BOTS"):
        with pytest.raises(ValueError, match="ne se change pas depuis le site"):
            s.save_settings({key: "live"})
    live = site(tmp_path, fake_bot, "MODE=live\nCONFIRM_LIVE_TRADING=OUI\nMAX_CAPITAL=100\n")
    assert live.state()["mode_label"] == "ARGENT RÉEL"  # affiché tel quel : les bots du site restent fictifs


def test_saved_settings_are_used_by_the_next_commands_and_secrets_never_shown(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot, "MODE=paper\nFLOTTE_CRYPTOS=40\n")
    token = "123456789:" + "A" * 30
    saved = s.save_settings({"FLOTTE_CRYPTOS": "30", "TELEGRAM_TOKEN": token})
    assert saved == {"saved": ["FLOTTE_CRYPTOS", "TELEGRAM_TOKEN"], "restarted": False}  # rien ne tournait
    assert "FLOTTE_CRYPTOS=30" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert s.settings().telegram_token == token
    form = s.settings_form(local=True)
    secret = [f for f in form["fields"] if f["key"] == "TELEGRAM_TOKEN"][0]
    assert secret == {**secret, "set": True} and "value" not in secret and token not in json.dumps(form)
    assert s.save_settings({"TELEGRAM_TOKEN": ""})["saved"] == []  # vide : le token enregistré est gardé
    assert s.settings().data_dir == tmp_path / "data"  # « data » à côté du bot, où que le site ait été lancé
    form = {f["key"]: f.get("value", "") for f in s.settings_form(local=True)["fields"]}
    assert form["FLOTTE_CAPITAL"] == "" and form["FLOTTE_CRYPTOS"] == "30"
    s.save_settings(form)  # le formulaire renvoie toutes ses cases : les vides gardent leur valeur
    assert s.settings().telegram_token == token and "FLOTTE_CAPITAL" not in (tmp_path / ".env").read_text("utf-8")


def test_the_securing_switch_is_saved_only_when_it_changes(tmp_path, fake_bot):
    """La liste « oui / non » envoie toujours son choix : inchangé, rien n'est écrit et les bots ne redémarrent pas."""
    s = site(tmp_path, fake_bot, "MODE=paper\n")
    assert s.save_settings({"FLOTTE_SECURISATION": "oui"}) == {"saved": [], "restarted": False}  # déjà le défaut
    assert "FLOTTE_SECURISATION" not in (tmp_path / ".env").read_text(encoding="utf-8")
    assert s.save_settings({"FLOTTE_SECURISATION": "Non"})["saved"] == ["FLOTTE_SECURISATION"]
    assert "FLOTTE_SECURISATION=non" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert s.save_settings({"FLOTTE_SECURISATION": "non"})["saved"] == []
    saved = s.save_settings({"FLOTTE_SECURISATION_SEUIL": "1,5", "FLOTTE_SECURISATION_PART": "30"})
    assert saved["saved"] == ["FLOTTE_SECURISATION_PART", "FLOTTE_SECURISATION_SEUIL"]
    for bad in ({"FLOTTE_SECURISATION": "peut-être"}, {"FLOTTE_SECURISATION_PART": "95"}):
        with pytest.raises(ValueError):
            s.save_settings(bad)
    form = {f["key"]: f for f in s.settings_form(local=True)["fields"]}
    assert form["FLOTTE_SECURISATION"]["kind"] == "switch" and form["FLOTTE_SECURISATION"]["value"] == "non"
    assert "prix d'entrée" in form["FLOTTE_SECURISATION"]["help"] and "R" in form["FLOTTE_SECURISATION_SEUIL"]["help"]
    s.save_settings({f["key"]: f.get("value", "") for f in s.settings_form(local=True)["fields"]})  # tout le formulaire
    assert "FLOTTE_SECURISATION=non" in (tmp_path / ".env").read_text(encoding="utf-8")


@pytest.mark.parametrize("written, choice", [("0", "non"), ("false", "non"), ("OFF", "non"), ("no", "non"),
                                             ("1", "oui"), ("True", "oui"), ("", "oui"), ("peut-être", "oui")])
def test_a_switch_written_by_hand_shows_what_the_bots_apply_and_is_not_rewritten(tmp_path, fake_bot, written, choice):
    """Un fichier .env écrit à la main avec « 0 » ou « false » : les bots lisent « non ». La page doit montrer « non »,
    et enregistrer le formulaire tel qu'il est affiché ne doit rien changer (défaut trouvé à la relecture de
    l'étape 1 : la page affichait « oui » et réactivait la sécurisation sans le dire)."""
    line = f"FLOTTE_SECURISATION={written}\n"
    s = site(tmp_path, fake_bot, "MODE=paper\n" + line)
    form = {f["key"]: f for f in s.settings_form(local=True)["fields"]}
    assert form["FLOTTE_SECURISATION"]["value"] == choice
    unreadable = written == "peut-être"  # les bots refusent cette ligne : la page propose la valeur par défaut
    if unreadable:
        with pytest.raises(ValueError):
            settings_from_env(parse_dotenv(tmp_path / ".env"))
    else:
        assert settings_from_env(parse_dotenv(tmp_path / ".env")).secure == (choice == "oui")
    saved = s.save_settings({key: f.get("value", "") for key, f in form.items()})
    assert ("FLOTTE_SECURISATION" in saved["saved"]) == unreadable  # seule une ligne illisible est réécrite : réparée
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert ("FLOTTE_SECURISATION=oui\n" if unreadable else line) in text  # sinon la ligne écrite à la main n'a pas bougé
    assert settings_from_env(parse_dotenv(tmp_path / ".env")).secure == (choice == "oui")


def test_changing_the_bots_settings_restarts_them(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    s.tasks.env["FAKE_SLEEP"] = "60"
    first = s.tasks.start("flotte")
    assert wait(lambda: first.process is not None)
    assert s.save_settings({"FLOTTE_BOTS_PAR_CRYPTO": "10"})["restarted"] is True
    assert wait(lambda: first.status == "arrêté" and any(t.status == "en cours" and t.id != first.id
                                                         for t in s.tasks.all() if t.action.key == "flotte"))
    assert s.save_settings({"TELEGRAM_CHAT_ID": "42"})["restarted"] is False  # sans rapport avec les bots
    s.tasks.stop_all()


def test_a_source_is_read_only_while_someone_looks_at_it():
    calls = []
    poller = Poller(lambda: calls.append(1) or len(calls), every=0.01, idle=0.3)
    assert poller.get()[0] is None  # premier appel : la lecture démarre
    assert wait(lambda: poller.get()[0] is not None, timeout=5)
    assert wait(lambda: not poller.thread.is_alive(), timeout=5)  # plus personne ne regarde : la lecture s'arrête
    count = len(calls)
    time.sleep(0.1)
    assert len(calls) == count


def test_the_direct_screen_always_says_where_the_bots_are():
    assert swarm_step({}, running=False)["action"] == "flotte"
    assert "à l'arrêt" in swarm_step({"ready": True}, running=False)["title"]
    testing = swarm_step({"ready": True, "totals": {"bots": 0}, "tester": {"done": 3, "queue": 12}}, running=True)
    assert "action" not in testing and "3 crypto(s) testée(s), 12 en attente" in testing["text"]
    live = swarm_step({"ready": True, "totals": {"bots": 250, "coins": 60, "moving": 48, "positions": 31}}, True)
    assert live["title"] == "250 bots tournent en argent fictif" and "31 en position" in live["text"]
    assert "garde sa place" in live["text"] and "à l'essai" not in live["text"]
    measuring = swarm_step({"ready": True, "totals": {"bots": 250}, "trial": {"bots": 93600}}, True)
    assert "93\u202f600 combinaisons sont mesurées à l'essai" in measuring["text"]
    rows = [{"verdict": "recalee"}] * 150 + [{"verdict": None}] * 45
    nothing = swarm_step({"ready": True, "totals": {"bots": 0}, "trial": {"ranking": {"strategie": rows}}}, True)
    assert "Aucun bot" in nothing["title"] and "150 stratégies sur 195 sont recalées" in nothing["text"]
    assert "pas une panne" in nothing["text"] and "action" not in nothing
    # Les bots endormis (leur crypto a quitté la liste) ne « tournent » pas : ils sont dits à part.
    some = swarm_step({"ready": True, "totals": {"bots": 250, "asleep": 40, "coins": 60}}, True)
    assert some["title"] == "210 bots tournent en argent fictif" and "40 bots dorment" in some["text"]
    one = swarm_step({"ready": True, "totals": {"bots": 2, "asleep": 1}}, True)
    assert one["title"] == "1 bot tourne en argent fictif" and "1 bot dort en attendant le retour de sa crypto" in one["text"]
    asleep = swarm_step({"ready": True, "totals": {"bots": 8, "asleep": 8}, "tester": {"done": 1, "queue": 0}}, True)
    assert "teste les cryptos" in asleep["title"] and "8 bots dorment" in asleep["text"]
    assert coin_symbol("sol") == "SOL/USDT" and coin_symbol("PEPE/USDT") == "PEPE/USDT"
    for bad in ("", "../.env", "BTC/EUR", "<script>"):
        with pytest.raises(ValueError):
            coin_symbol(bad)
    assert finite_json({"a": [float("nan"), 1.0, float("inf")]}) == {"a": [None, 1.0, None]}


# --- le serveur -----------------------------------------------------------------------------------------------------

def request(base, path, data=None, headers=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
                                 headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with opener.open(req, timeout=20) as response:
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
    s.tasks.stop_all()


PAGE = {HEADER: HEADER_VALUE}


def test_the_site_serves_its_page_and_only_obeys_its_own_page(server):
    s, base = server
    status, page, headers = request(base, "/")
    assert status == 200 and "Tous les bots" in page and "Les cryptos suivies" in page
    assert "<h1>Les stratégies</h1>" in page and 'href="#strategies"' in page and 'id="rank-source"' in page
    assert "La mesure à l'essai" in page and 'id="trial-facts"' in page  # toutes les combinaisons, sans rien choisir
    # étape 1 : la sécurisation des gains comparée avec et sans, les bots endormis, les zones du graphique
    assert "Sécurisation des gains : avec ou sans ?" in page and 'id="secure-rows"' in page
    assert "'Endormis'" in page and "seuil de sécurisation" in page and "zone du risque" in page
    assert "zone-up" in page and "rectangle : " in page  # la zone qu'une lecture du graphique attend, en rectangle
    assert "la mesure « avec » est repartie de zéro" in page  # la comparaison dit depuis quand elle compare
    # le bot de tendance : son onglet, son test de robustesse, et ses mises en garde
    assert 'href="#tendance"' in page and "<h1>Le bot de tendance</h1>" in page and 'id="trend-robust-rows"' in page
    assert "Jamais de levier sur cette règle" in page and "Le passé ne garantit rien" in page
    assert "Sur huit autres marchés" in page and "C'est une protection, pas une façon de gagner plus" in page
    assert "gagnant sur 3 périodes" not in page and "trois périodes" not in page  # le test final ne choisit plus
    for gone in ("Radar des mouvements", "Mes essais", "Labos", "Mon trader", "Tableau de bord"):
        assert gone not in page  # retirés du site
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    status, body, _ = request(base, "/api/etat")
    state = json.loads(body)
    assert status == 200 and state["mode_label"] == "argent fictif"
    assert {a["key"] for a in state["actions"]} == set(ACTIONS)
    ok = {**PAGE, "Content-Type": "application/json"}
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
    assert request(base, "/api/tableau/bots")[0] == 404
    assert already_running(s.port) and not already_running(1)


def test_the_trend_bot_is_served_to_the_page_only_and_stays_in_paper_money(server):
    import numpy as np
    from tests.test_trend import DailyExchange, days, walk
    from tradingbot import trend
    s, base = server
    frames = {"BTC/USDT": days(np.linspace(100, 900, 420), start=trend.EARLY_MS),
              "ETH/USDT": days(walk(3, 420), start=trend.EARLY_MS)}
    exchange = DailyExchange(frames, n=420)
    s.trend_feed.make_exchange = lambda exchange_id: exchange
    for path in ("/api/tendance", "/api/tendance-graphique?c=BTC"):
        assert request(base, path)[0] == 403  # elles téléchargent : seulement pour la page du site
    status, body, _ = request(base, "/api/tendance", headers=PAGE)
    data = json.loads(body)
    assert status == 200 and [c["name"] for c in data["coins"]] == ["Bitcoin", "Ether"]
    assert data["coins"][0]["level"] == 3 and data["coins"][0]["history"]["rule"]["total"] > 1
    assert not data["coins"][0]["account"]["started"]  # créé à l'instant : il ouvre à la prochaine ouverture du jour
    assert len(data["robustness"]["rows"]) == 6 and "Argent fictif seulement" in data["robustness"]["verdict"]
    status, body, _ = request(base, "/api/tendance-graphique?c=btc", headers=PAGE)
    chart = json.loads(body)
    assert status == 200 and len(chart["candles"]) == 420 and len(chart["lines"]) == 3
    assert chart["orders"][0]["side"] == "achat"
    assert request(base, "/api/tendance-graphique?c=SOL", headers=PAGE)[0] == 400  # seulement le Bitcoin et l'Ether
    assert request(base, "/api/tendance-graphique?c=../.env", headers=PAGE)[0] == 400
    folder = s.data_dir() / "tendance"
    assert (folder / "compte.json").exists() and (folder / "binance_BTC-USDT_1d.csv").exists()
    exchange.calls.clear()
    request(base, "/api/tendance", headers=PAGE)  # la page est gardée 10 secondes : la plateforme n'est pas redemandée
    assert exchange.calls == []
    assert {f.name for f in folder.iterdir()} == {"compte.json", "binance_BTC-USDT_1d.csv", "binance_ETH-USDT_1d.csv"}


def test_the_trend_account_is_dated_from_the_first_launch_of_the_site(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    s._watch_fleet = lambda: None  # pas de bots dans ce test
    s.start_background()
    path = s.data_dir() / "tendance" / "compte.json"
    created = json.loads(path.read_text(encoding="utf-8"))
    assert created["capital"] == 1000.0 and created["since"]
    s.start_background()  # un autre lancement ne déplace pas le départ du compte
    assert json.loads(path.read_text(encoding="utf-8")) == created


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
    handler, sent = fake_handler(s, "/api/bots", headers=host)
    handler.do_GET()
    assert sent[0][0] == 403
    handler, sent = fake_handler(s, f"/?code={s.code}", headers=host)
    handler.do_GET()
    assert sent[0][0] == 303 and f"code-du-bot={s.code}" in sent[0][2]["Set-Cookie"]
    handler, sent = fake_handler(s, "/api/bots", headers={**host, "Cookie": f"code-du-bot={s.code}"})
    handler.do_GET()
    assert sent[0][0] == 200
    handler, sent = fake_handler(s, "/?code=ééé", headers=host)  # code accentué : refusé, sans planter
    handler.do_GET()
    assert sent[0][0] == 403
    assert (tmp_path / "data" / "site-code.txt").read_text(encoding="utf-8") == s.code  # le même code au relancement


def test_the_school_and_the_news_are_served_to_the_page(server):
    from tests.test_news import RSS, fng_payload
    from tradingbot.news import FEEDS, FNG_URL
    s, base = server
    school = json.loads(request(base, "/api/ecole")[1])
    assert len(school["lessons"]) >= 12 and school["lessons"][0]["quiz"]
    pages = {FEEDS[0][1]: RSS, FNG_URL: json.dumps(fng_payload([40] * 400))}
    s.news.get = lambda url: pages[url] if url in pages else (_ for _ in ()).throw(ConnectionError("hors ligne"))
    assert request(base, "/api/actualite")[0] == 403  # seulement depuis la page du site
    request(base, "/api/actualite", headers=PAGE)  # le premier appel lance la relève en arrière-plan
    assert wait(lambda: json.loads(request(base, "/api/actualite", headers=PAGE)[1])["news"])
    page = json.loads(request(base, "/api/actualite", headers=PAGE)[1])
    assert page["fng"]["value"] == 40 and page["fng"]["zone"] == "peur"
    assert any("Cointelegraph" in e for e in page["errors"])  # un site en panne est signalé, pas fatal
    btc = next(n for n in page["news"] if "BTC" in n["coins"])
    assert btc["moves"][0]["coin"] == "BTC"  # prix à la publication inconnu ici : le mouvement reste vide


# --- les bots sur le site ------------------------------------------------------------------------------------------

class ChartExchange:
    def __init__(self, df):
        self.df = df

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return self.df[["ts", "open", "high", "low", "close", "volume"]].iloc[-limit:].values.tolist()


def swarm_files(root, df):
    """Des bots et leur résumé, écrits par le vrai code sur une plateforme fictive."""
    from tests.test_swarm import FakeMarket, chosen, make_swarm, spec
    market = FakeMarket({"X/USDT": df})
    market.i = len(df) - 202
    swarm = make_swarm(market, root / "data" / "bots")
    swarm.read = True
    swarm.state["coins"]["X/USDT"] = {"status": "actif", "amplitude": 0.12, "change": 0.03, "volume": 2e7,
                                      "followed": True, "moving": True, "next_test": market.now_ms() + 3600_000,
                                      "n_tested": 780, "n_eligible": 4, "best": []}
    bots = [swarm.add_bot(chosen(spec("Cassure 20/10", "short", 2.0)), market.now_ms()),
            swarm.add_bot(chosen(spec("Supertrend 10/3", "long")), market.now_ms())]
    for i in range(len(df) - 202, len(df) - 2):
        market.i = i
        swarm.cycle(market.now_ms())
    swarm.release()
    return swarm, bots


def test_the_bots_are_listed_by_coin_and_each_has_its_page_and_chart(server, random_walk):
    s, base = server
    view = json.loads(request(base, "/api/bots")[1])
    assert view["ready"] is False and view["step"]["action"] == "flotte" and view["bots"] == []
    df = random_walk.iloc[:900]
    swarm, (short, long_) = swarm_files(s.root, df)
    view = json.loads(request(base, "/api/bots")[1])
    assert view["ready"] and view["step"]["action"] == "flotte"  # à l'arrêt : le bouton les relance
    assert set(view["ranking"]) >= {"strategie", "sortie", "sens", "unite", "min_trades"}  # l'onglet Stratégies
    trial = view["trial"]  # la mesure à l'essai : une combinaison sur une crypto qui bouge = un bot à l'essai
    assert trial["bots"] == 780 and trial["coins"] == 1 and trial["n"] == 0 and trial["mean"] is None
    assert set(trial["ranking"]) >= {"strategie", "sortie", "sens", "unite", "min_days"} and trial["since"]
    assert view["holdout"] == {"n": 0, "coins": 0, "mean": None, "win": None}
    secure = view["secure"]  # la sécurisation des gains : le réglage, et la comparaison avec / sans (vide au départ)
    assert (secure["on"], secure["r"], secure["part"]) == (True, 1.0, 0.5) and secure["final"]["coins"] == 0
    assert secure["trial"]["total"]["diff"] is None and [u["key"] for u in secure["trial"]["units"]][0] == "1m"
    assert view["totals"]["asleep"] == 0 and all(b["secure_r"] == 1.0 and b["secure_part"] == 0.5 for b in view["bots"])
    assert view["reference"]["saved"] and view["reference"]["count"] is None  # première installation : rien avant
    assert all(b["exit"] and b["stop_mode"] in ("fixe", "suiveur", "securise") for b in view["bots"])
    assert view["totals"]["bots"] == 2 and {b["id"] for b in view["bots"]} == {short["id"], long_["id"]}
    assert view["coins"][0]["coin"] == "X" and view["coins"][0]["bots"] == 2
    coin = json.loads(request(base, "/api/crypto?c=x")[1])
    assert coin["coin"] == "X" and len(coin["bots"]) == 2 and coin["timeframes"] == ["1h"]
    assert coin["info"]["n_tested"] == 780 and coin["news"] == []
    assert request(base, "/api/crypto?c=../../.env")[0] == 400
    page = json.loads(request(base, f"/api/bot?id={short['id']}")[1])
    assert page["side"] == "short" and "vend à découvert" in page["rule"] and page["technique_card"]["title"]
    assert "live" in page and page["exit"] == "objectif 2R"
    assert len(page["trades"]) == len(short["book"]["trades"]) and page["reading"]["sentences"]
    assert request(base, "/api/bot?id=0123456789")[0] == 400  # inconnu
    assert request(base, "/api/bot?id=../etat")[0] == 400
    assert request(base, f"/api/bot-graphique?id={short['id']}")[0] == 403  # un graphique télécharge : la page seule
    s.charts.exchange = ChartExchange(df)
    status, body, _ = request(base, f"/api/bot-graphique?id={short['id']}", headers=PAGE)
    chart = json.loads(body)
    assert status == 200 and len(chart["candles"]) == len(df) and chart["side"] == "short" and chart["lines"]
    status, body, _ = request(base, "/api/crypto-graphique?c=X&unite=1h", headers=PAGE)
    chart = json.loads(body)
    assert status == 200 and len(chart["candles"]) == len(df) and chart["reading"]["sentences"]
    assert {z["kind"] for z in chart["levels"]} <= {"support", "resistance"}
    assert len(chart["trades"]) == sum(len(b["book"]["trades"]) for b in (short, long_))
    assert request(base, "/api/crypto-graphique?c=X&unite=3h", headers=PAGE)[0] == 400


def test_a_bot_page_shows_the_latest_price_status_and_signal(server, random_walk):
    s, base = server
    swarm, (short, _) = swarm_files(s.root, random_walk.iloc[:900])
    summary_path = s.root / "data" / "bots" / "essaim.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    brief = next(b for b in summary["bots"] if b["id"] == short["id"])
    brief.update(status="veille", last_price=123.0, signal={"ts": 1, "entry": True, "exit": False},
                 proba={"p": 0.61, "base": 0.5, "trades": 40, "conditions": ["la tendance de fond hausse"]})
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    page = json.loads(request(base, f"/api/bot?id={short['id']}")[1])
    assert page["status"] == "veille" and page["last_price"] == 123.0 and page["signal"]["entry"] is True
    assert page["proba"]["p"] == 0.61  # le dernier tour, pas le fichier du bot écrit plus tôt
    (s.root / "data" / "bots" / DETAIL_DIR / f"{short['id']}.json").write_text("{abîmé", encoding="utf-8")
    assert request(base, f"/api/bot?id={short['id']}")[0] == 400  # illisible : un message, pas une panne


def test_the_site_keeps_the_bots_running_unless_stopped_by_hand(tmp_path, fake_bot):
    s = site(tmp_path, fake_bot)
    s.tasks.env["FAKE_SLEEP"] = "60"
    task = s.keep_fleet_running()  # les bots démarrent dès l'ouverture du site
    assert task is not None and task.action.key == "flotte" and task.steps == [("flotte",)]
    assert wait(lambda: task.process is not None)
    assert s.keep_fleet_running() is None  # jamais deux fois
    lock = tmp_path / "data" / "bots" / LOCK_FILE
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": task.process.pid, "t": time.time()}), encoding="utf-8")
    task.stop()  # arrêtés à la main (bouton « Arrêter les bots »)
    s.fleet_stopped = True
    assert wait(lambda: task.status == "arrêté")
    assert not s.fleet_running()  # leur signal de vie est encore frais, mais ce sont nos bots, arrêtés
    assert s.keep_fleet_running() is None  # arrêtés à la main : le site ne les relance pas
    s.fleet_stopped = False
    again = s.keep_fleet_running()
    assert again is not None and again.id != task.id
    again.stop()
    assert wait(lambda: again.status == "arrêté")
    lock.write_text(json.dumps({"pid": 1, "t": time.time()}), encoding="utf-8")  # lancés par un lanceur
    assert s.fleet_running() and s.keep_fleet_running() is None
    assert "lancés par un lanceur" in s.blocked("flotte", "paper")


def test_the_bots_settings_stay_within_bounds():
    fields = {f.key: f for f in FIELDS}
    assert set(fields) == {"FLOTTE_CAPITAL", "FLOTTE_CRYPTOS", "FLOTTE_BOTS_PAR_CRYPTO", "FLOTTE_MOUVEMENT_MIN",
                           "FLOTTE_LEVIER_SCALPING", "FLOTTE_LEVIER_COURT", "FLOTTE_LEVIER_LONG", "FLOTTE_SECURISATION",
                           "FLOTTE_SECURISATION_SEUIL", "FLOTTE_SECURISATION_PART", "EXCHANGE", "TELEGRAM_TOKEN",
                           "TELEGRAM_CHAT_ID"}
    assert all(f.help for f in FIELDS)  # une phrase d'explication sous chaque réglage
    # La sécurisation des gains : désactivable, seuil et part bornés.
    switch, level, part = (fields[k] for k in ("FLOTTE_SECURISATION", "FLOTTE_SECURISATION_SEUIL",
                                                 "FLOTTE_SECURISATION_PART"))
    assert (switch.kind, switch.default, level.default, part.default) == ("switch", "oui", "1", "50")
    assert [clean_value(switch, x) for x in ("Oui", "non", "NON ", "1", "0")] == ["oui", "non", "non", "oui", "non"]
    assert clean_value(level, "1,5") == "1.5" and clean_value(part, "0") == "0.0" and clean_value(part, "90") == "90.0"
    for field, bad in ((switch, "peut-être"), (level, "0.2"), (level, "4"), (part, "95"), (part, "-5")):
        with pytest.raises(ValueError):
            clean_value(field, bad)
    assert settings_from_env({"FLOTTE_SECURISATION": clean_value(switch, "non"),
                              "FLOTTE_SECURISATION_SEUIL": clean_value(level, "1,5"),
                              "FLOTTE_SECURISATION_PART": clean_value(part, "30")}).security(True) == (1.5, pytest.approx(0.3))
    assert clean_value(fields["FLOTTE_LEVIER_SCALPING"], "10") == "10.0"
    assert clean_value(fields["FLOTTE_CRYPTOS"], "80") == "80"
    assert clean_value(fields["FLOTTE_BOTS_PAR_CRYPTO"], "20") == "20"
    with pytest.raises(ValueError):
        clean_value(fields["FLOTTE_BOTS_PAR_CRYPTO"], "21")
    assert "à l'essai" in fields["FLOTTE_BOTS_PAR_CRYPTO"].help
    assert fields["FLOTTE_CRYPTOS"].default == "60" and fields["FLOTTE_BOTS_PAR_CRYPTO"].default == "8"
