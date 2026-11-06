"""Le site du bot : tout le bot dans le navigateur, servi par l'ordinateur lui-même (http://127.0.0.1:8765).

`python main.py site` (« Ouvrir le bot » dans la version Windows) ouvre le site. Chaque bouton lance la même
commande que les fichiers .bat, dans un processus à part dont le journal s'affiche en direct ; le radar des
mouvements et les prix se mettent à jour tout seuls ; les réglages courants se changent dans un formulaire.

Ce que le site ne fait jamais : passer en argent réel. Il lance les labos, les tournois (toujours en argent
fictif) et « Mes bots » en argent fictif, testnet ou demo. MODE, les clés API et CONFIRM_LIVE_TRADING ne se
changent que dans le fichier .env, et un bot en argent réel se lance avec « 4 - Lancer le bot ».

Sécurité : le site n'écoute que l'ordinateur lui-même (127.0.0.1), sauf avec --ipad. Un autre site web ouvert
dans le navigateur ne peut pas lui donner d'ordres : chaque action exige un en-tête que seule la page du site
envoie (un autre site devrait en demander l'autorisation au navigateur, et ce site ne la donne jamais), et
l'adresse demandée doit être la sienne (protection contre le « DNS rebinding »). Avec --ipad, les appareils du
réseau local doivent en plus connaître le code affiché dans la fenêtre noire.
"""
from __future__ import annotations

import itertools
import json
import logging
import math
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ccxt

from .broker import atomic_write
from .config import MODES, ConfigError, Settings, parse_bots, parse_dotenv
from .execution import ExecutionParams
from .risk import RiskParams
from .dashboard import FILENAME as DASHBOARD_FILE, write_dashboard
from .data import load_or_fetch, ohlcv_to_frame, timeframe_to_ms
from .desk import DESK_FILE, Desk
from .explain import read_chart
from .indicators import sma
from .lab import ALL_VARIANTS, FUTURES_LAB_FILE, LAB_FILE, LAB_FILES, LIMIT_LAB_FILE, PROMISING, SHORT_LAB_FILE, load_lab
from .prices import DEFAULT_CRYPTOS, DEFAULT_PLATFORMS, board_to_dict, connect, label, short_error, snapshot
from .knowledge import knowledge
from .news import NewsSource, reaction
from .school import school
from .moves import OPTIONS, STUDY_DAYS, round_trip_cost, study
from .portfolio import PORTFOLIO_DIR, PORTFOLIO_LAB_FILE, RETAINED as PORTFOLIO_RETAINED, load as load_portfolio_lab
from .radar import JOURNAL_FILE, STRONG, WINDOWS, MoveJournal, Radar, journal_stats
from .robustness import MIN_TRADES
from .strategy import compute_signals
from .trader import (
    ACCOUNT_FILE as TRADER_ACCOUNT, PROFILES, REPLAY_FILE as TRADER_REPLAY_FILE, TRADER_DIR, summary as trader_summary,
)

log = logging.getLogger(__name__)

PORT = 8765
HEADER = "X-Demande"  # exigé pour toute action : seule la page du site l'envoie
HEADER_VALUE = "site-du-bot"
CODE_COOKIE = "code-du-bot"
CODE_FILE = "site-code.txt"
CALCUL = "calcul"  # un seul calcul lourd à la fois : les labos se partagent le processeur
RETAINED = (PROMISING, "à surveiller")
MAX_LINES = 3000  # lignes de journal gardées par tâche
FINISHED_KEPT = 20  # tâches terminées encore affichées
TRIALS_EVERY_S = 15  # surveillance des essais en argent fictif
RUNNING, DONE, FAILED, STOPPED = "en cours", "terminé", "échec", "arrêté"
MODE_LABELS = {"paper": "argent fictif", "testnet": "testnet", "demo": "démo", "live": "ARGENT RÉEL"}


@dataclass(frozen=True)
class Action:
    key: str
    title: str
    group: str
    description: str
    duration: str = ""
    slot: str = ""  # CALCUL : une seule à la fois
    endless: bool = False  # tourne jusqu'à ce qu'on l'arrête (tournois, bots)
    then: tuple[str, ...] = ()  # lancées toutes seules après une fin réussie


SHORT_LAB = ("labo", "--symbols", "BTC/USDT,ETH/USDT,SOL/USDT", "--timeframes", "1m,5m,15m", "--scanner", "8",
             "--memecoins", "--combinaisons", "--resultats", SHORT_LAB_FILE)
LIMIT_LAB = (*SHORT_LAB[:-2], "--ordres-limites", "--resultats", LIMIT_LAB_FILE)
# Beaucoup de cryptos : plus de trades, donc un verdict plus rapide (les stratégies retenues achètent rarement).
SHORT_TOURNAMENT = ("tournoi", "--labo", f"{SHORT_LAB_FILE},{LIMIT_LAB_FILE}", "--top", "20", "--sans-navigateur")
LONG_TOURNAMENT = ("tournoi", "--avec-marches-du-labo", "--top", "20", "--sans-navigateur")
PORTFOLIO_LAB = ("labo-portefeuille",)  # la règle de la recherche (momentum croisé), la plus rapide : en premier
PORTFOLIO = ("portefeuille",)
FUTURES_LAB = (*SHORT_LAB[:-2], "--futures", "--resultats", FUTURES_LAB_FILE)  # scalping, frais des futures
TRADER = ("trader",)
TRADER_REPLAY = ("trader", "--rejouer")

GROUPS = ("Le plus simple", "Chercher une stratégie", "Faire tourner en argent fictif", "Vérifier")
ACTIONS = {a.key: a for a in (
    Action("pilote", "Pilote automatique", GROUPS[0],
           "Cherche des stratégies sur l'historique réel (les cinq labos, dont le scalping avec les frais des futures "
           "et la règle de portefeuille issue de la recherche), puis lance tout seul, en argent fictif, ton trader, "
           "les tournois et le portefeuille avec ce qui a été retenu. Tu n'as plus qu'à regarder.",
           "2 à 4 h de calcul, puis tout tourne", CALCUL,
           then=("trader", "trader-rejeu", "tournoi-court", "tournoi-long", "portefeuille")),
    Action("trader", "Mon trader", GROUPS[0],
           "Ton trader fictif : il joue les stratégies retenues par le labo sur les 20 cryptos les plus échangées, met "
           "un stop à chaque trade et t'explique chaque achat et chaque vente. Levier possible (argent fictif). Il "
           "relit les labos chaque heure.", "tourne jusqu'à ce que tu l'arrêtes", endless=True),
    Action("recherche", "Recherche de nuit", GROUPS[1],
           "Les cinq labos à la suite : portefeuille, court terme, court terme en ordres limites, scalping avec les "
           "frais des futures, long terme.", "2 à 4 h", CALCUL),
    Action("trader-rejeu", "Rejouer mon trader sur l'historique", GROUPS[1],
           "Les règles de ton trader rejouées sur les derniers mois : des exemples de trades expliqués tout de suite. "
           "Flatteur par nature (ces stratégies ont été choisies sur ce passé) : ce n'est pas une preuve.",
           "1 à 5 min", CALCUL),
    Action("labo-futures", "Labo scalping, frais futures", GROUPS[1],
           "Le labo court terme avec les frais des contrats à terme : 0,05 % par ordre au marché et le financement, "
           "deux fois moins cher qu'au comptant. Argent fictif seulement.", "environ 1 h", CALCUL),
    Action("labo-portefeuille", "Labo portefeuille", GROUPS[1],
           "Une règle issue de la recherche : chaque semaine, garder les 3 ou 5 cryptos qui ont le plus monté parmi "
           "les 30 plus échangées. Testée sur des années de bougies d'un jour, hors échantillon, contre le panier de "
           "toutes les cryptos.", "2 à 5 min", CALCUL),
    Action("labo-court", "Labo court terme", GROUPS[1],
           "Bougies de 1, 5 et 15 min, avec les combinaisons et les impulsions, sur BTC, ETH, SOL, les cryptos les "
           "plus agitées et les memecoins.", "environ 1 h", CALCUL),
    Action("labo-limites", "Labo court terme, ordres limites", GROUPS[1],
           "Le même labo, mais le bot attend son prix au lieu de payer l'écart et le glissement.", "environ 1 h",
           CALCUL),
    Action("labo-long", "Labo long terme", GROUPS[1],
           "De 15 min à 1 jour, sur les cryptos, l'or et l'euro (et tes actions du dossier « actions »).",
           "10 à 20 min", CALCUL),
    Action("robustesse", "Test de robustesse", GROUPS[1],
           "La stratégie choisie dans les réglages, sur 5 cryptos et 4 unités de temps.", "5 à 10 min", CALCUL),
    Action("backtest", "Backtest détaillé", GROUPS[1],
           "La stratégie choisie dans les réglages, sur un seul marché, avec le détail des trades.", "1 min", CALCUL),
    Action("tournoi-court", "Tournoi court terme", GROUPS[2],
           "Les stratégies retenues par les labos court terme s'affrontent sur les cryptos agitées, avec 1000 USDT "
           "fictifs par bot. Le gardien coupe celles qui perdent.", "tourne jusqu'à ce que tu l'arrêtes", endless=True),
    Action("tournoi-long", "Tournoi long terme", GROUPS[2],
           "Les stratégies retenues par le labo long terme, chacune dans son unité de temps, sur beaucoup de cryptos. "
           "À laisser tourner plusieurs semaines.", "tourne jusqu'à ce que tu l'arrêtes", endless=True),
    Action("portefeuille", "Portefeuille momentum", GROUPS[2],
           "Les variantes retenues par le labo portefeuille, avec 1000 USDT fictifs chacune : une rotation par semaine "
           "aux prix réels, frais compris. À laisser tourner plusieurs semaines.", "tourne jusqu'à ce que tu l'arrêtes",
           endless=True),
    Action("bots", "Mes bots", GROUPS[2],
           "Les bots des réglages (BOTS), en argent fictif, testnet ou démo — jamais en argent réel depuis le site.",
           "tourne jusqu'à ce que tu l'arrêtes", endless=True),
    Action("check", "Vérifier la connexion", GROUPS[3], "Accès à la plateforme, soldes et frais du compte.",
           "quelques secondes"),
    Action("telegram", "Tester les alertes Telegram", GROUPS[3],
           "Trouve l'identifiant de discussion et envoie un message de test sur ton téléphone.", "quelques secondes"),
)}
TOURNAMENTS = (  # (action, dossier dans data, titre)
    ("tournoi-court", "tournoi-court-terme", "Tournoi court terme"),
    ("tournoi-long", "tournoi", "Tournoi long terme"),
)


def steps_for(key: str, root: Path) -> list[tuple[str, ...]]:
    """Les commandes du bot qu'une action lance, dans l'ordre."""
    long_lab = ("labo", "--csv-dir", "actions") if any((root / "actions").glob("*.csv")) else ("labo",)
    return {
        "pilote": [PORTFOLIO_LAB, SHORT_LAB, LIMIT_LAB, FUTURES_LAB, long_lab],
        "recherche": [PORTFOLIO_LAB, SHORT_LAB, LIMIT_LAB, FUTURES_LAB, long_lab],
        "trader": [TRADER],
        "trader-rejeu": [TRADER_REPLAY],
        "labo-futures": [FUTURES_LAB],
        "labo-portefeuille": [PORTFOLIO_LAB],
        "portefeuille": [PORTFOLIO],
        "labo-court": [SHORT_LAB],
        "labo-limites": [LIMIT_LAB],
        "labo-long": [long_lab],
        "robustesse": [("robustesse",)],
        "backtest": [("backtest",)],
        "tournoi-court": [SHORT_TOURNAMENT],
        "tournoi-long": [LONG_TOURNAMENT],
        "bots": [("run",)],
        "check": [("check",)],
        "telegram": [("telegram",)],
    }[key]


def program() -> list[str]:
    """La commande du bot : l'exécutable de la version Windows, ou python main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py")]


def iso(t: datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


# --- Processus : une tâche et tout ce qu'elle lance s'arrêtent ensemble ----------------------------------------

def windows_job():
    """Un « job » Windows qui tue tous ses processus quand il se ferme : si la fenêtre du site est fermée, aucun
    labo ni tournoi ne continue en cachette. None si Windows le refuse (la tâche s'arrête alors avec taskkill)."""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount",
                "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            kernel32.CloseHandle(ctypes.c_void_p(job))
            return None
        return job
    except (AttributeError, OSError, ValueError):
        return None


class ProcessGroup:
    """Le processus d'une tâche et ceux qu'il lance (les cœurs d'un labo), arrêtés d'un seul coup."""

    def __init__(self):
        self.windows = sys.platform == "win32"
        self.job = windows_job() if self.windows else None

    def popen_options(self) -> dict:
        if self.windows:
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        return {"start_new_session": True}

    def adopt(self, process: subprocess.Popen) -> None:
        if self.job:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
            if not kernel32.AssignProcessToJobObject(self.job, int(process._handle)):
                log.debug("Processus %s hors du job Windows : arrêt par taskkill", process.pid)

    def kill(self, process: subprocess.Popen) -> None:
        if self.windows:
            if self.job:
                import ctypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
                if kernel32.TerminateJobObject(self.job, 1):
                    return
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def close(self) -> None:
        if self.job:
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(self.job))
            self.job = None


class Task:
    """Une action lancée depuis le site : ses commandes, l'une après l'autre, et leur journal."""

    def __init__(self, tid: int, action: Action, steps: list[tuple[str, ...]], command: list[str], cwd: Path,
                 env: dict[str, str], on_done=None):
        self.id, self.action, self.steps = tid, action, steps
        self.command, self.cwd, self.env, self.on_done = command, cwd, env, on_done
        self.lines: deque[str] = deque(maxlen=MAX_LINES)
        self.total = 0  # numéro de la prochaine ligne : le journal se relit « depuis » un numéro
        self.started = datetime.now(timezone.utc)
        self.finished: datetime | None = None
        self.status = RUNNING
        self.step = 0
        self.failed: list[int] = []
        self.process: subprocess.Popen | None = None
        self.group = ProcessGroup()
        self.stop_requested = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name=f"tache-{tid}", daemon=True)

    def start(self) -> "Task":
        self.thread.start()
        return self

    def emit(self, line: str) -> None:
        with self.lock:
            self.lines.append(line)
            self.total += 1

    def read(self, since: int) -> tuple[list[str], int]:
        with self.lock:
            first = self.total - len(self.lines)
            return list(itertools.islice(self.lines, max(since, first) - first, None)), self.total

    def _run(self) -> None:
        try:
            for i, argv in enumerate(self.steps):
                if self.stop_requested:
                    break
                self.step = i
                if len(self.steps) > 1:
                    self.emit(f"=== Étape {i + 1}/{len(self.steps)} : {' '.join(argv)}")
                try:
                    process = subprocess.Popen(
                        [*self.command, *argv], cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **self.group.popen_options())
                except OSError as exc:
                    self.emit(f"Impossible de lancer le bot : {exc}")
                    self.failed.append(i)
                    continue
                self.group.adopt(process)
                self.process = process
                if self.stop_requested:  # arrêt demandé pendant le lancement
                    self.group.kill(process)
                for raw in process.stdout:
                    self.emit(raw.decode("utf-8", "replace").rstrip("\r\n"))
                if process.wait() != 0 and not self.stop_requested:
                    self.failed.append(i)
                    if len(self.steps) > 1:
                        self.emit(f"Étape {i + 1} en échec (code {process.returncode}) : on passe à la suivante.")
        finally:
            self.finished = datetime.now(timezone.utc)
            status = STOPPED if self.stop_requested else FAILED if self.failed else DONE
            self.emit({STOPPED: "Arrêté. Les positions éventuelles sont reprises au prochain lancement.",
                       FAILED: "Terminé avec une erreur : lis les lignes au-dessus.",
                       DONE: "Terminé."}[status])
            self.group.close()
            if self.on_done:
                try:
                    self.on_done(self, status)
                except Exception as exc:  # la suite (tournois du pilote) ne doit jamais bloquer la fin de la tâche
                    self.emit(f"Suite impossible : {exc}")
            self.status = status  # en dernier : qui attend la fin de la tâche voit tout son journal

    def stop(self) -> None:
        self.stop_requested = True
        process = self.process
        if process is not None and self.status == RUNNING:
            self.group.kill(process)

    def to_dict(self) -> dict:
        end = self.finished or datetime.now(timezone.utc)
        with self.lock:
            last = next((line for line in reversed(self.lines) if line.strip()), "")
        return {"id": self.id, "action": self.action.key, "title": self.action.title, "status": self.status,
                "started": iso(self.started), "finished": iso(self.finished),
                "seconds": int((end - self.started).total_seconds()), "step": self.step + 1,
                "steps": len(self.steps), "last": last[-240:], "endless": self.action.endless,
                "failed": len(self.failed)}


class TaskManager:
    def __init__(self, root: Path, env: dict[str, str], command: list[str] | None = None):
        self.root, self.env = root, env
        self.command = command or program()
        self.tasks: dict[int, Task] = {}
        self.ids = itertools.count(1)
        self.lock = threading.RLock()

    def all(self) -> list[Task]:
        """Copie de la liste, prise sous le verrou : le pilote peut lancer un tournoi pendant qu'une page la lit."""
        with self.lock:
            return list(self.tasks.values())

    def running(self) -> list[Task]:
        return [t for t in self.all() if t.status == RUNNING]

    def blocker(self, key: str, finishing: "Task | None" = None) -> str | None:
        """Pourquoi l'action ne peut pas démarrer maintenant (None : elle peut). `finishing` : la tâche qui se termine
        et lance la suite (elle compte encore comme en cours, mais ne bloque plus rien)."""
        action = ACTIONS[key]
        for t in self.running():
            if t is finishing:
                continue
            if t.action.key == key:
                return f"« {action.title} » tourne déjà."
            if action.slot and t.action.slot == action.slot:
                return f"Attends la fin de « {t.action.title} » : un seul calcul à la fois (ils se partagent le processeur)."
        return None

    def start(self, key: str, finishing: Task | None = None) -> Task:
        if key not in ACTIONS:
            raise ValueError(f"Action inconnue : {key}")
        with self.lock:
            if reason := self.blocker(key, finishing):
                raise ValueError(reason)
            task = Task(next(self.ids), ACTIONS[key], steps_for(key, self.root), self.command, self.root, self.env,
                        self._finished)
            self.tasks[task.id] = task
            finished = sorted((t for t in self.tasks.values() if t.status != RUNNING), key=lambda t: t.id)
            for old in finished[:-FINISHED_KEPT]:
                del self.tasks[old.id]
        return task.start()

    def _finished(self, task: Task, status: str) -> None:
        if status == STOPPED or len(task.failed) == len(task.steps):
            return
        for key in task.action.then:  # le pilote automatique enchaîne sur le trader, les tournois et le portefeuille
            try:
                self.start(key, finishing=task)
                task.emit(f"→ « {ACTIONS[key].title} » lancé automatiquement.")
            except ValueError as exc:
                task.emit(f"→ « {ACTIONS[key].title} » non lancé : {exc}")

    def get(self, tid: int) -> Task | None:
        with self.lock:
            return self.tasks.get(tid)

    def stop_all(self) -> None:
        for task in self.running():
            task.stop()


# --- Sources rafraîchies tant que quelqu'un les regarde ---------------------------------------------------------

class Poller:
    """Relève une source (radar, prix) toutes les `every` secondes, seulement tant que la page la regarde."""

    def __init__(self, fetch, every: float = 10.0, idle: float = 120.0):
        self.fetch, self.every, self.idle = fetch, every, idle
        self.data, self.error, self.updated = None, None, None
        self.seen = 0.0
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()

    def get(self):
        with self.lock:
            self.seen = time.monotonic()
            if not (self.thread and self.thread.is_alive()):
                self.thread = threading.Thread(target=self._loop, name="releve", daemon=True)
                self.thread.start()
            return self.data, self.error, self.updated

    def _loop(self) -> None:
        while time.monotonic() - self.seen < self.idle:
            try:
                data = self.fetch()
                with self.lock:
                    self.data, self.error, self.updated = data, None, datetime.now(timezone.utc)
            except Exception as exc:  # réseau coupé, plateforme en panne... : affiché sur la page, jamais fatal
                with self.lock:
                    self.error = short_error(exc)
            time.sleep(self.every)


FULL_REFRESH_S = 300  # la liste complète des paires (volumes) toutes les 5 min ; entre deux, les derniers prix


class RadarSource:
    """Le radar du site : allumé dès l'ouverture, il note aussi chaque gros mouvement dans le journal."""

    def __init__(self, make_exchange, exchange_id: str, journal: MoveJournal | None = None):
        self.make_exchange, self.exchange_id = make_exchange, exchange_id
        self.exchange = None
        self.radar = Radar()
        self.journal = journal or MoveJournal(None)
        self.full_at = -math.inf
        self.lock = threading.Lock()

    def _last_prices(self, symbols: list[str]) -> dict[str, float | None]:
        """Une requête légère : le dernier prix des paires suivies, sans le reste du ticker."""
        if self.exchange.has.get("fetchLastPrices"):
            try:
                return {s: (v or {}).get("price") for s, v in self.exchange.fetch_last_prices(symbols).items()}
            except ccxt.ExchangeError:  # pas prévue ou refusée par cette plateforme : le ticker complet
                pass
        return {s: (t or {}).get("last") for s, t in self.exchange.fetch_tickers(symbols).items()}

    def fetch(self) -> int:
        if self.exchange is None:
            exchange = self.make_exchange(self.exchange_id)
            exchange.load_markets()
            self.exchange = exchange
        now = time.time()
        if now - self.full_at >= FULL_REFRESH_S or not self.radar.info:
            tickers = self.exchange.fetch_tickers()  # toutes les paires en une seule requête
            with self.lock:
                self.radar.update_info(self.exchange.markets, tickers)
            prices = {s: t.get("last") or t.get("close") for s, t in tickers.items()}
            self.full_at = now
        else:
            prices = self._last_prices(sorted(self.radar.info))
        with self.lock:
            count = self.radar.add_prices(prices, now)
            self.journal.observe(self.radar.moves(top=None), self.radar.latest, now)
        return count

    def price(self, symbol: str) -> float | None:
        with self.lock:
            return self.radar.latest.get(symbol)

    def follows(self, symbol: str) -> bool:
        with self.lock:
            return symbol in self.radar.info

    def top(self, n: int = 60) -> list[dict]:
        """Les cryptos suivies, de la plus échangée à la moins échangée (pour choisir un graphique)."""
        with self.lock:
            rows = sorted(self.radar.info.items(), key=lambda kv: -kv[1][0])[:n]
            return [{"symbol": sym, "volume_24h": vol, "change_24h": chg, "last": self.radar.latest.get(sym)}
                    for sym, (vol, chg) in rows]

    def view(self, window: int, rising_only: bool, top: int = 25) -> dict:
        with self.lock:
            moves, span = self.radar.moves(window, top, rising_only), self.radar.span
            tracked = len(self.radar.latest)
            pending = len(self.journal.pending)
        return {
            "span": span, "tracked": tracked, "window": window, "windows": list(WINDOWS),
            "strong": {str(w): STRONG[w] for w in WINDOWS}, "pending": pending,
            "moves": [{"symbol": m.symbol, "last": m.last, "changes": {str(w): c for w, c in m.changes.items()},
                       "change_24h": m.change_24h, "volume_24h": m.volume_24h, "strong": m.strong,
                       "rise": m.strong_rise} for m in moves],
        }


class Charts:
    """Les graphiques du site : bougies clôturées, un cache court par crypto et par unité de temps."""

    TTL = {"1m": 15, "5m": 30, "15m": 60, "1h": 60, "4h": 120, "1d": 300}
    TIMEFRAMES = ("15m", "1h", "4h", "1d")
    LIMIT = 400  # assez pour la moyenne sur 200 bougies et les niveaux des 150 dernières

    def __init__(self, make_exchange, exchange_id: str):
        self.make_exchange, self.exchange_id = make_exchange, exchange_id
        self.exchange = None
        self.cache: dict[tuple[str, str], tuple[float, object]] = {}
        self.lock = threading.Lock()

    def candles(self, symbol: str, timeframe: str):
        if timeframe not in self.TTL:
            raise ValueError("Unité de temps inconnue")
        key = (symbol, timeframe)
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.monotonic() < hit[0]:
                return hit[1]
            if self.exchange is None:
                self.exchange = self.make_exchange(self.exchange_id)
            df = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, timeframe, limit=self.LIMIT))
            now_ms = int(time.time() * 1000)
            df = df[df["ts"] + timeframe_to_ms(timeframe) <= now_ms]  # seulement les bougies terminées
            self.cache[key] = (time.monotonic() + self.TTL[timeframe], df)
            if len(self.cache) > 200:
                self.cache.pop(next(iter(self.cache)))
            return df


class Market:
    """Bougies de 1 minute pour l'étude et les essais (chacun sa connexion : une étude qui télécharge ne
    retarde jamais la surveillance d'un stop)."""

    def __init__(self, make_exchange, exchange_id: str, cache_dir: Path):
        self.make_exchange, self.exchange_id, self.cache_dir = make_exchange, exchange_id, cache_dir
        self.exchange = None
        self.lock = threading.Lock()

    def _exchange(self):
        if self.exchange is None:
            self.exchange = self.make_exchange(self.exchange_id)
        return self.exchange

    def history(self, symbol: str, days: int):
        with self.lock:
            return load_or_fetch(self.exchange_id, symbol, "1m", days, self.cache_dir, self._exchange())

    def recent(self, symbol: str, limit: int = 60):
        """Les dernières bougies de 1 minute clôturées (celle en cours n'est pas finie : elle est écartée)."""
        with self.lock:
            exchange = self._exchange()
            frame = ohlcv_to_frame(exchange.fetch_ohlcv(symbol, "1m", limit=limit + 1))
            return frame[frame["ts"] + 60_000 <= exchange.milliseconds()]

    def last(self, symbol: str) -> float | None:
        with self.lock:
            ticker = self._exchange().fetch_ticker(symbol)
        return ticker.get("last") or ticker.get("close")


class Studies:
    """Les études demandées depuis le radar : une à la fois, gardées 10 minutes."""

    KEEP_S = 600

    def __init__(self, run):
        self.run = run  # (symbole, fenêtre, prix) -> résultat de moves.study
        self.results: dict[tuple[str, int], dict] = {}
        self.worker: threading.Thread | None = None
        self.lock = threading.Lock()

    def get(self, symbol: str, window: int, price: float | None) -> dict:
        key = (symbol, window)
        with self.lock:
            entry = self.results.get(key)
            if entry and (entry["status"] == "en cours" or time.time() - entry["at"] < (
                    self.KEEP_S if entry["status"] == "prêt" else 30)):
                return entry
            if self.worker and self.worker.is_alive():
                return {"status": "attente", "message": "Une autre étude est en cours : celle-ci suit juste après."}
            self.results[key] = {"status": "en cours", "at": time.time()}
            self.worker = threading.Thread(target=self._work, args=(key, price), name="etude", daemon=True)
            self.worker.start()
            return self.results[key]

    def _work(self, key: tuple[str, int], price: float | None) -> None:
        try:
            entry = {"status": "prêt", "result": self.run(key[0], key[1], price)}
        except Exception as exc:  # réseau coupé, crypto sans historique... : expliqué sur la fiche
            entry = {"status": "erreur", "error": short_error(exc)}
        with self.lock:
            self.results[key] = {**entry, "at": time.time()}


class PricesSource:
    def __init__(self, make_exchange, platforms=DEFAULT_PLATFORMS, bases=DEFAULT_CRYPTOS):
        self.make_exchange, self.platforms, self.bases = make_exchange, list(platforms), list(bases)
        self.exchanges = None
        self.errors: dict[str, str] = {}

    def fetch(self) -> dict:
        if self.exchanges is None:  # la liste des paires de chaque plateforme, une seule fois
            self.exchanges, self.errors = connect(self.platforms, self.make_exchange)
        return board_to_dict(snapshot(self.exchanges, self.bases, self.errors))


# --- Réglages : seulement ceux qui ne touchent ni à l'argent réel ni aux clés ------------------------------------

@dataclass(frozen=True)
class Field:
    key: str
    title: str
    help: str
    kind: str  # bots, money, fee, exchange, secret, chat, path, profile, number, count
    default: str = ""  # ce que le bot utilise quand la ligne est vide
    bounds: tuple[float, float] = (0.0, 0.0)  # number et count : valeurs permises


FIELDS = (
    Field("BOTS", "Mes bots", "Paires et unités de temps, PAIRE@UNITE séparés par des virgules "
          "(ex. BTC/USDT@15m,ETH/USDT@1h).", "bots"),
    Field("PAPER_START_BALANCE", "Capital fictif de chaque bot", "En USDT, pour « Mes bots » en argent fictif "
          "(les tournois donnent 1000 USDT fictifs à chaque bot).", "money", "10000"),
    Field("FEE_RATE", "Frais au marché (taker)", "0.001 = 0,1 % par ordre. Mets les vrais frais de ta plateforme "
          "avant de relancer un labo.", "fee", "0.001"),
    Field("MAKER_FEE_RATE", "Frais des ordres limites (maker)", "Souvent moins chers que les frais au marché.", "fee",
          "0.001"),
    Field("EXCHANGE", "Plateforme des données", "Où le bot lit les prix : binance, okx, kraken, coinbase, bybit...",
          "exchange", "binance"),
    Field("TELEGRAM_TOKEN", "Telegram : token du bot", "Donné par @BotFather quand tu crées ton bot (/newbot).",
          "secret"),
    Field("TELEGRAM_CHAT_ID", "Telegram : identifiant de discussion", "Trouvé par « Tester les alertes Telegram ».",
          "chat"),
    Field("OBSIDIAN_VAULT", "Coffre Obsidian (facultatif)", "Dossier où le bot écrit aussi son journal en notes. "
          "Vide = pas de notes.", "path"),
    Field("TRADER_CAPITAL", "Mon trader : capital fictif", "En USDT. Change-le avant le premier lancement (le compte "
          "garde ensuite son histoire).", "money", "1000"),
    Field("TRADER_PROFILE", "Mon trader : type de compte", "futures (frais des contrats à terme, levier possible) ou "
          "spot (au comptant, sans levier). Toujours en argent fictif.", "profile", "futures"),
    Field("TRADER_LEVERAGE", "Mon trader : levier maximum", "De 1 à 20. Le total des positions peut aller jusqu'à ce "
          "multiple du compte. Le levier ne crée aucun gain : il grossit gains et pertes.", "number", "3", (1, 20)),
    Field("TRADER_RISK", "Mon trader : risque par trade", "Perte si le stop est touché, en part du compte : 0.01 = 1 %. "
          "Entre 0.001 et 0.05.", "number", "0.01", (0.001, 0.05)),
    Field("TRADER_POSITIONS", "Mon trader : positions en même temps", "De 1 à 20.", "count", "5", (1, 20)),
    Field("TRADER_COINS", "Mon trader : cryptos suivies", "Les plus échangées, de 1 à 100.", "count", "20", (1, 100)),
)
FIELD_KEYS = {f.key: f for f in FIELDS}


def clean_value(field: Field, raw: str) -> str:
    """Valeur vérifiée, prête pour .env ; ValueError avec une explication sinon."""
    value = " ".join(str(raw).split())  # jamais de retour à la ligne : une ligne de .env par réglage
    if field.kind == "bots":
        bots = parse_bots(value.replace(" ", ""))
        for symbol, timeframe in bots:
            try:
                timeframe_to_ms(timeframe)
            except (ValueError, ccxt.BaseError):
                raise ValueError(f"Unité de temps invalide pour {symbol} : « {timeframe} » (ex. 15m, 1h, 4h, 1d)") from None
        return ",".join(f"{symbol}@{timeframe}" for symbol, timeframe in bots)
    if field.kind in ("money", "fee"):
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            raise ValueError(f"{field.title} : un nombre est attendu (reçu « {value} »)") from None
        if field.kind == "money" and not 0 < number <= 1e9:
            raise ValueError(f"{field.title} doit être positif")
        if field.kind == "fee" and not 0 <= number <= 0.01:
            raise ValueError(f"{field.title} : entre 0 et 0.01 (0.001 = 0,1 %)")
        return repr(number)
    if field.kind == "profile":
        value = value.lower()
        if value not in PROFILES:
            raise ValueError(f"{field.title} : futures ou spot (reçu « {value} »)")
        return value
    if field.kind in ("number", "count"):
        low, high = field.bounds
        try:
            number = float(value.replace(",", "."))
        except ValueError:
            raise ValueError(f"{field.title} : un nombre est attendu (reçu « {value} »)") from None
        if field.kind == "count" and number != int(number):
            raise ValueError(f"{field.title} : un nombre entier est attendu")
        if not low <= number <= high:
            raise ValueError(f"{field.title} : entre {low:g} et {high:g}")
        return str(int(number)) if field.kind == "count" else repr(number)
    if field.kind == "exchange":
        value = value.lower()
        if value not in ccxt.exchanges:
            raise ValueError(f"Plateforme inconnue : « {value} » (ex. binance, okx, kraken, coinbase, bybit)")
        return value
    if field.kind == "secret":
        if not re.fullmatch(r"\d+:[\w-]{20,}", value):
            raise ValueError("Le token Telegram ressemble à 123456789:ABCdef... (copie-le en entier depuis @BotFather)")
        return value
    if field.kind == "chat":
        if value and not re.fullmatch(r"-?\d+", value):
            raise ValueError("L'identifiant de discussion est un nombre (ex. 123456789)")
        return value
    return value  # chemin de dossier


def update_env(path: Path, changes: dict[str, str]) -> None:
    """Change ces lignes de .env (la première, si une clé est écrite deux fois), sans toucher aux autres."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.partition("=")[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in changes and key not in done:
            lines[i] = f"{key}={changes[key]}"
            done.add(key)
    lines += [f"{key}={value}" for key, value in changes.items() if key not in done]
    atomic_write(path, "\n".join(lines) + "\n")


# --- Résumés pour l'accueil --------------------------------------------------------------------------------------

def finite(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def finite_json(value):
    """NaN et infini deviennent null : le JSON du navigateur ne les connaît pas."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    return value


def same(a: str | None, b: str | None) -> bool:
    """Comparaison d'un code sans fuite de temps (et sans planter sur des caractères accentués)."""
    return bool(a) and bool(b) and secrets.compare_digest(str(a).encode(), str(b).encode())


def lab_summaries(data_dir: Path) -> list[dict]:
    out = []
    for name, title in LAB_FILES:
        lab = load_lab(data_dir / name)
        rows = (lab or {}).get("rows") or []
        if not rows:
            out.append({"file": name, "title": title, "done": False})
            continue
        retained = [r for r in rows if r.get("verdict") in RETAINED]
        judged = [r for r in rows if (r.get("trades") or 0) >= MIN_TRADES
                  and finite(r.get("gross_expectancy_pct")) is not None]
        best = max(judged, key=lambda r: finite(r["gross_expectancy_pct"])) if judged else None
        verdict = str(lab.get("verdict") or "").split("\n")[0].removeprefix("VERDICT : ")
        out.append({
            "file": name, "title": title, "done": True, "date": lab.get("date"), "verdict": verdict,
            "retained": len(retained), "tested": len(rows),
            "names": [f"{r['variant']} ({r.get('timeframe', '?')})" for r in retained[:3]],
            "best": {"variant": best["variant"], "timeframe": best.get("timeframe"),
                     "gross": finite(best["gross_expectancy_pct"]), "net": finite(best.get("expectancy_pct"))}
            if best else None,
        })
    return out


def tournament_summaries(data_dir: Path, running: set[str]) -> list[dict]:
    out = []
    for key, folder, title in TOURNAMENTS:
        try:
            registry = json.loads((data_dir / folder / "tournoi.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            registry = {}
        out.append({"action": key, "folder": folder, "title": title, "running": key in running,
                    "started": registry.get("started"), "strategies": len(registry.get("strategies") or []),
                    "markets": len(registry.get("markets") or []),
                    "dashboard": (data_dir / folder / DASHBOARD_FILE).exists()})
    return out


def portfolio_summary(data_dir: Path, running: bool) -> dict:
    """Le labo portefeuille (ce qu'il a retenu) et les portefeuilles fictifs (valeur, cryptos gardées)."""
    lab = load_portfolio_lab(data_dir / PORTFOLIO_LAB_FILE) or {}
    rows = [r for r in lab.get("rows") or [] if isinstance(r, dict)]
    retained = [r for r in rows if r.get("verdict") in PORTFOLIO_RETAINED]
    best = (retained or rows or [None])[0]
    books = []
    for path in sorted((data_dir / PORTFOLIO_DIR).glob("*.json")):
        try:
            book = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        start, value = finite(book.get("start")), finite(book.get("value"))
        books.append({"variant": book.get("variant"), "start": start, "value": value,
                      "retained": any(r.get("variant") == book.get("variant") for r in retained),
                      "pnl_pct": 100 * (value / start - 1) if start and value is not None else None,
                      "holdings": sorted(s.split("/")[0] for s in book.get("holdings") or {}),
                      "next": book.get("next"), "since": book.get("since"),
                      "rotations": len(book.get("rotations") or [])})
    return {"lab": {"done": bool(rows), "date": lab.get("date"), "tested": len(rows), "retained": len(retained),
                    "coins": len(lab.get("univers") or []), "names": [r.get("variant") for r in retained[:3]],
                    "best": {"variant": best.get("variant"), "mean": finite(best.get("mean_pct")),
                             "basket": finite(best.get("basket_pct")), "verdict": best.get("verdict")}
                    if best else None},
            "books": books, "running": running}


def next_step(labs: list[dict], running: list[Task], tournaments: list[dict], portfolio: dict | None = None,
              trader: dict | None = None) -> dict:
    """Une seule chose à faire maintenant, en une phrase."""
    keys = {t.action.key for t in running}
    portfolio = portfolio or {"lab": {"done": False, "retained": 0}, "books": [], "running": False}
    trader = trader or {"plays": 0}
    computing = next((t for t in running if t.action.slot == CALCUL), None)
    if computing:
        then = " Les tournois et le portefeuille démarreront tout seuls à la fin." if computing.action.then else ""
        return {"title": f"{computing.action.title} : le bot calcule",
                "text": "Il teste les stratégies sur l'historique réel. Tu peux fermer le navigateur, mais garde la "
                        f"fenêtre noire ouverte et l'ordinateur allumé.{then}", "view": "journal"}
    done = [lab for lab in labs if lab["done"]]
    if not done and not portfolio["lab"]["done"]:
        return {"title": "Lance le pilote automatique",
                "text": "Le bot cherche, sur l'historique réel, des stratégies qui gagnent après frais (1 à 3 h), "
                        "puis les fait tourner en argent fictif. Aucun argent réel n'est engagé.", "action": "pilote"}
    short = sum(lab["retained"] for lab in done if lab["file"] in (SHORT_LAB_FILE, LIMIT_LAB_FILE))
    long_ = sum(lab["retained"] for lab in done if lab["file"] == LAB_FILE)
    if trader["plays"] and "trader" not in keys:
        return {"title": "Lance ton trader",
                "text": f"Les labos ont retenu {trader['plays']} stratégie(s) jouable(s). Ton trader fictif les joue sur "
                        "les cryptos les plus échangées et t'explique chaque trade. Aucun argent réel.",
                "action": "trader"}
    if short and "tournoi-court" not in keys:
        return {"title": "Lance le tournoi court terme",
                "text": f"Les labos court terme ont retenu {short} stratégie(s). Le tournoi les fait tourner en argent "
                        "fictif, en direct, pour vérifier qu'elles tiennent hors de l'historique.",
                "action": "tournoi-court"}
    if long_ and "tournoi-long" not in keys:
        return {"title": "Lance le tournoi long terme",
                "text": f"Le labo long terme a retenu {long_} stratégie(s). Le tournoi les fait tourner en argent "
                        "fictif pendant plusieurs semaines.", "action": "tournoi-long"}
    if portfolio["lab"]["retained"] and "portefeuille" not in keys:
        return {"title": "Lance le portefeuille momentum",
                "text": f"Le labo portefeuille a retenu {portfolio['lab']['retained']} variante(s) de la règle issue de "
                        "la recherche. Le portefeuille l'applique en argent fictif, une rotation par semaine.",
                "action": "portefeuille"}
    if any(t["running"] for t in tournaments) or portfolio["running"] or "trader" in keys:
        return {"title": "Tout tourne en argent fictif : laisse le temps faire",
                "text": "Une stratégie n'est « candidate au testnet » qu'après 30 trades nettement positifs, frais "
                        "compris ; le portefeuille, lui, se juge sur des semaines. Le gardien coupe tout seul ce qui "
                        "perd. Regarde l'accueil et le tableau de bord de temps en temps.", "view": "tableau"}
    return {"title": "Aucune stratégie ne gagne après frais pour l'instant",
            "text": "C'est la réponse honnête du labo : sur ces marchés et ces unités de temps, rien ne bat les frais. "
                    "Relance une recherche dans quelques semaines, les marchés changent. N'engage pas d'argent réel.",
            "action": "pilote"}


# --- Le site ------------------------------------------------------------------------------------------------------

class Site:
    def __init__(self, root: Path, pristine_env: dict[str, str], make_exchange, port: int = PORT,
                 lan_address: str | None = None, command: list[str] | None = None):
        self.root, self.pristine = root, dict(pristine_env)
        self.env_path = root / ".env"
        self.make_exchange = make_exchange
        self.port, self.lan_address = port, lan_address
        self.settings_error: str | None = None
        # Les commandes relisent .env elles-mêmes : elles reçoivent l'environnement d'avant son chargement.
        child_env = {**self.pristine, "TRADINGBOT_SITE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        self.tasks = TaskManager(root, child_env, command)
        self.dashboard_lock = threading.Lock()
        settings = self.settings()
        exchange_id = settings.exchange if settings else "binance"
        data_dir = self.data_dir()
        self.radar = RadarSource(make_exchange, exchange_id, MoveJournal(data_dir / JOURNAL_FILE))
        self.radar_poller = Poller(self.radar.fetch, every=10.0, idle=math.inf)  # toujours allumé : il se remplit
        self.prices_poller = Poller(PricesSource(make_exchange).fetch, every=10.0)
        execution = settings.execution if settings else ExecutionParams()
        self.desk = Desk(data_dir / DESK_FILE, execution, settings.risk if settings else RiskParams())
        self.study_market = Market(make_exchange, exchange_id, data_dir / "cache")
        self.desk_market = Market(make_exchange, exchange_id, data_dir / "cache")
        self.studies = Studies(self._study)
        self.charts = Charts(make_exchange, exchange_id)
        self.news = NewsSource(data_dir / "cache", closes=self._btc_closes, known=self._known_bases)
        self.news_poller = Poller(self.news.fetch, every=600.0, idle=900.0)  # tant que la page Actualité est ouverte
        self.pub_prices: dict[tuple[str, str], float | None] = {}
        self.code = self._code() if lan_address else None

    def start_background(self) -> None:
        """Ce qui tourne tant que le site est ouvert : le radar (et son journal) et la surveillance des essais."""
        self.radar_poller.get()
        threading.Thread(target=self._watch_trials, name="essais", daemon=True).start()

    def _watch_trials(self) -> None:
        while True:
            try:
                self.check_trials()
            except Exception as exc:  # un réseau coupé ne doit pas arrêter la surveillance des autres essais
                log.warning("Surveillance des essais : %s", short_error(exc))
            time.sleep(TRIALS_EVERY_S)

    def check_trials(self, now: float | None = None) -> list[dict]:
        """Revend les essais arrivés à leur règle de sortie (stop, essoufflement, temps maximum)."""
        symbols = self.desk.symbols()
        if not symbols:
            return []
        prices = {s: self.radar.price(s) or self.desk_market.last(s) for s in symbols}
        candles = {s: self.desk_market.recent(s) for s in symbols}
        return self.desk.check(prices, candles, now or time.time())

    def _study(self, symbol: str, window: int, price: float | None) -> dict:
        settings = self.settings()
        execution = settings.execution if settings else ExecutionParams()
        df = self.study_market.history(symbol, STUDY_DAYS)
        price = price or float(df["close"].iloc[-1])
        return {"symbol": symbol, **study(df, window, execution, self.desk.risk,
                                          equity=self.desk.equity({symbol: price}), price=price)}

    def journal_view(self) -> dict:
        settings = self.settings()
        cost = round_trip_cost(settings.execution if settings else ExecutionParams())
        records = self.radar.journal.records()
        return {"since": records[0]["t"] if records else None, "count": len(records), "cost": cost,
                "rows": journal_stats(records, cost)}

    def price_of(self, symbol: str) -> float:
        price = self.radar.price(symbol) or self.desk_market.last(symbol)
        if not price:
            raise ValueError(f"Prix de {symbol} indisponible pour l'instant : réessaie dans quelques secondes.")
        return float(price)

    def trial_symbol(self, raw) -> str:
        symbol = str(raw or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}/[A-Z0-9]{2,10}", symbol):
            raise ValueError("Crypto inconnue")
        if not self.radar.follows(symbol):
            raise ValueError(f"{symbol} n'est pas suivie par le radar (pas assez échangée, ou radar en démarrage).")
        return symbol

    def open_trial(self, body: dict) -> dict:
        symbol = self.trial_symbol(body.get("symbole"))
        window, option = int(body.get("fenetre") or 0), str(body.get("option") or "")
        if window not in STRONG or option not in OPTIONS:
            raise ValueError("Option inconnue")
        price = self.price_of(symbol)
        return self.desk.open(symbol, window, option, price, self.desk_market.recent(symbol), time.time())

    def trials(self) -> dict:
        prices = {s: p for s in self.desk.symbols() if (p := self.radar.price(s))}
        return self.desk.summary(prices)

    def _btc_closes(self):
        """Les clôtures journalières du Bitcoin (cache du labo long terme), pour l'étude de l'indice peur et avidité."""
        settings = self.settings()
        exchange_id = settings.exchange if settings else "binance"
        df = load_or_fetch(exchange_id, "BTC/USDT", "1d", 3000, self.data_dir() / "cache", self.make_exchange(exchange_id))
        return df["close"].astype(float)

    def _known_bases(self) -> set[str]:
        with self.radar.lock:
            return {s.split("/")[0] for s in self.radar.radar.info}

    def _price_then(self, base: str, published: str | None) -> float | None:
        """Le prix d'une crypto au moment d'une nouvelle (ouverture de la bougie de 5 min), gardé une fois trouvé."""
        symbol = f"{base}/USDT"
        key = (symbol, published or "")
        if key in self.pub_prices:
            return self.pub_prices[key]
        price = None
        try:
            when = int(datetime.fromisoformat(published).timestamp() * 1000) if published else None
            if when and self.radar.follows(symbol) and time.time() * 1000 - when < 3 * 86_400_000:
                if self.charts.exchange is None:
                    self.charts.exchange = self.make_exchange(self.charts.exchange_id)
                rows = self.charts.exchange.fetch_ohlcv(symbol, "5m", since=when - when % 300_000, limit=1)
                price = float(rows[0][1]) if rows else None
        except Exception as exc:  # une crypto qui ne répond pas : pas de mouvement affiché pour elle
            log.debug("Prix de %s à la publication introuvable : %s", symbol, short_error(exc))
        self.pub_prices[key] = price
        return price

    def news_view(self) -> dict:
        data, error, updated = self.news_poller.get()
        if not data:
            return {"news": [], "fng": None, "errors": [error] if error else [], "updated": iso(updated)}
        news = [dict(n) for n in data["news"]]
        budget = [25]  # au plus 25 recherches de prix par demande ; les suivantes viendront aux demandes d'après

        def then(base, published):
            key = (f"{base}/USDT", published or "")
            if key not in self.pub_prices:
                if budget[0] <= 0:
                    return None
                budget[0] -= 1
            return self._price_then(base, published)

        reaction(news, then, lambda base: self.radar.price(f"{base}/USDT"))
        return {"news": news, "fng": data["fng"], "errors": data["errors"] + ([error] if error else []),
                "updated": iso(updated)}

    def trader_settings(self):
        from .trader import TraderSettings, settings_from_env
        try:
            return settings_from_env({**parse_dotenv(self.env_path), **self.pristine})
        except ValueError:
            return TraderSettings()

    def playable(self, data_dir: Path) -> int:
        """Combien de stratégies des labos le trader peut jouer avec ses frais."""
        from .trader import choose_playbook
        settings = self.settings()
        return len(choose_playbook(data_dir, self.trader_settings(), settings.execution if settings else
                                   ExecutionParams()))

    def trader_view(self) -> dict:
        folder = self.data_dir() / TRADER_DIR
        def load(name):
            try:
                return json.loads((folder / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
        running = any(t.action.key == "trader" for t in self.tasks.running())
        return {"live": {**trader_summary(load(TRADER_ACCOUNT)), "running": running},
                "replay": trader_summary(load(TRADER_REPLAY_FILE)),
                "settings": asdict(self.trader_settings()), "profiles": list(PROFILES)}

    def chart(self, symbol: str, timeframe: str) -> dict:
        """Un graphique comme un trader le lit : bougies, supports et résistances, moyennes, lecture et signaux."""
        df = self.charts.candles(symbol, timeframe)
        if len(df) < 30:
            raise ValueError("Pas assez d'historique pour ce graphique.")
        settings = self.settings()
        ex = settings.execution if settings else ExecutionParams()
        reading = read_chart(df, fees=2 * (ex.fee_rate + ex.slippage))
        last = float(df["close"].iloc[-1])
        shown = df.iloc[-150:]
        def series(values):
            return [None if not math.isfinite(v) else float(v) for v in values.iloc[-150:].tolist()]
        levels = [{**z, "kind": "support" if z["price"] < last else "resistance"}
                  for z in reading.pop("levels") if z["touches"] >= 2]
        state = None
        try:
            state = json.loads((self.data_dir() / TRADER_DIR / TRADER_ACCOUNT).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        plays = []
        for play in (state or {}).get("playbook") or []:
            if play.get("timeframe") != timeframe or play.get("name") not in ALL_VARIANTS:
                continue
            row = compute_signals(df, ALL_VARIANTS[play["name"]]).iloc[-1]
            plays.append({"key": play["key"], "status": play.get("status"), "why": play.get("why"),
                          "signal": "achat" if row.entry else "vente" if row.exit else "rien"})
        start = int(shown["ts"].iloc[0])
        def stamp(iso_text):
            try:
                return int(datetime.fromisoformat(iso_text).timestamp() * 1000)
            except (TypeError, ValueError):
                return None
        trades = [t for t in (state or {}).get("trades") or [] if t.get("symbol") == symbol
                  and t.get("timeframe") == timeframe and (stamp(t.get("exit_time")) or 0) >= start][-10:]
        position = next((pos for pos in (state or {}).get("positions") or [] if pos.get("symbol") == symbol), None)
        return {"symbol": symbol, "timeframe": timeframe, "last": last,
                "candles": shown[["ts", "open", "high", "low", "close", "volume"]].values.tolist(),
                "ma50": series(sma(df["close"], 50)), "ma200": series(sma(df["close"], 200)),
                "levels": levels, "reading": reading, "plays": plays, "position": position,
                "trades": [{"entry": stamp(t["entry_time"]), "exit": stamp(t["exit_time"]),
                            "entry_price": t["entry_price"], "exit_price": t["exit_price"], "net": t["net"],
                            "title": (t.get("diagnosis") or {}).get("title"), "play": t["play"]} for t in trades]}

    def settings(self) -> Settings | None:
        """Réglages relus à chaque demande (le formulaire ou le Bloc-notes ont pu les changer) ; comme pour les
        commandes, une variable d'environnement passe avant la ligne de .env."""
        try:
            settings = Settings.from_env({**parse_dotenv(self.env_path), **self.pristine})
            self.settings_error = None
        except (ValueError, OSError) as exc:
            self.settings_error = str(exc)
            return None
        if not settings.data_dir.is_absolute():  # « data » : à côté du bot, où que le site ait été lancé
            settings = replace(settings, data_dir=self.root / settings.data_dir)
        return settings

    def data_dir(self) -> Path:
        settings = self.settings()
        return settings.data_dir if settings else self.root / "data"

    def _code(self) -> str:
        path = self.data_dir() / CODE_FILE
        try:
            code = path.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"\d{6}", code):
                return code
        except OSError:
            pass
        code = f"{secrets.randbelow(10 ** 6):06d}"
        atomic_write(path, code)
        return code

    @property
    def hosts(self) -> set[str]:
        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if self.lan_address:
            hosts.add(f"{self.lan_address}:{self.port}")
        return hosts

    def state(self) -> dict:
        settings = self.settings()
        data_dir = settings.data_dir if settings else self.root / "data"
        running = self.tasks.running()
        labs = lab_summaries(data_dir)
        tournaments = tournament_summaries(data_dir, {t.action.key for t in running})
        portfolio = portfolio_summary(data_dir, any(t.action.key == "portefeuille" for t in running))
        trader = {"plays": self.playable(data_dir), "running": any(t.action.key == "trader" for t in running)}
        mode = settings.mode if settings else "?"
        return {
            "mode": mode, "mode_label": MODE_LABELS.get(mode, mode), "exchange": settings.exchange if settings else "?",
            "settings_error": self.settings_error,
            "next": next_step(labs, running, tournaments, portfolio, trader), "trader": trader,
            "tasks": [t.to_dict() for t in sorted(self.tasks.all(), key=lambda t: -t.id)],
            "actions": [{"key": a.key, "title": a.title, "group": a.group, "description": a.description,
                         "duration": a.duration, "blocked": self.blocked(a.key, mode)} for a in ACTIONS.values()],
            "groups": list(GROUPS), "labs": labs, "tournaments": tournaments, "portfolio": portfolio,
        }

    def blocked(self, key: str, mode: str) -> str | None:
        if key == "bots" and mode == "live":
            return ("MODE=live dans les réglages : le site ne lance jamais de bot en argent réel. "
                    "Utilise « 4 - Lancer le bot » si tu l'as vraiment décidé.")
        if key == "bots" and mode not in MODES:
            return "MODE invalide dans les réglages."
        return self.tasks.blocker(key)

    def launch(self, key: str) -> dict:
        settings = self.settings()
        if settings is None:
            raise ValueError(f"Réglages invalides, corrige-les d'abord : {self.settings_error}")
        if key not in ACTIONS:
            raise ValueError(f"Action inconnue : {key}")
        if reason := self.blocked(key, settings.mode):
            raise ValueError(reason)
        return self.tasks.start(key).to_dict()

    def dashboard(self, which: str) -> str | None:
        """La page du tableau de bord demandé (les bots des réglages, ou un tournoi) ; None s'il n'existe pas."""
        settings = self.settings()
        data_dir = settings.data_dir if settings else self.root / "data"
        if which == "bots":
            if settings is None:
                return None
            with self.dashboard_lock:  # deux onglets qui demandent la page en même temps : un seul fichier écrit
                path = write_dashboard(settings)
        else:
            folders = {folder for _, folder, _ in TOURNAMENTS}
            if which not in folders:
                return None
            path = data_dir / which / DASHBOARD_FILE
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def settings_form(self, local: bool) -> dict:
        values = parse_dotenv(self.env_path)
        settings = self.settings()
        fields = []
        for f in FIELDS:
            current = values.get(f.key, "")
            item = {"key": f.key, "title": f.title, "help": f.help, "kind": f.kind, "default": f.default}
            if f.kind == "secret":
                item["set"] = bool(current)  # jamais renvoyé : un token ne s'affiche pas sur une page
            else:
                item["value"] = current
            fields.append(item)
        mode = settings.mode if settings else values.get("MODE", "paper")
        return {"fields": fields, "mode": mode, "mode_label": MODE_LABELS.get(mode, mode), "local": local,
                "error": self.settings_error}

    def save_settings(self, changes: dict) -> dict:
        cleaned = {}
        for key, raw in changes.items():
            field = FIELD_KEYS.get(key)
            if field is None:
                raise ValueError(f"Ce réglage ne se change pas depuis le site : {key}")
            if not str(raw).strip() and field.kind in ("secret", "money", "fee", "exchange", "profile", "number",
                                                       "count"):
                continue  # vide : on garde la valeur actuelle (le token enregistré, ou la valeur par défaut)
            cleaned[key] = clean_value(field, raw)
        if not self.env_path.exists() and (self.root / ".env.example").exists():
            atomic_write(self.env_path, (self.root / ".env.example").read_text(encoding="utf-8"))
        if cleaned:
            update_env(self.env_path, cleaned)
        if self.settings() is None:
            raise ConfigError(f"Réglages enregistrés, mais invalides : {self.settings_error}")
        return {"saved": sorted(cleaned)}


def open_in_editor(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["notepad.exe", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Handler(BaseHTTPRequestHandler):
    server_version = "TradingBot"
    protocol_version = "HTTP/1.1"

    @property
    def site(self) -> Site:
        return self.server.site  # type: ignore[attr-defined]

    def log_message(self, fmt, *args) -> None:  # le journal du site reste lisible : pas une ligne par requête
        log.debug("site %s - %s", self.address_string(), fmt % args)

    # --- réponses ---
    def send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, payload, status: int = 200) -> None:
        body = json.dumps(finite_json(payload), ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send(status, body, "application/json; charset=utf-8")

    def html(self, page: str, status: int = 200, extra: dict | None = None) -> None:
        self.send(status, page.encode("utf-8"), "text/html; charset=utf-8", extra)

    def fail(self, status: int, message: str) -> None:
        self.json({"ok": False, "error": message}, status)

    # --- qui a le droit ---
    @property
    def local(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def cookie_code(self) -> str | None:
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == CODE_COOKIE:
                return value
        return None

    def allowed(self, action: bool) -> bool:
        if self.headers.get("Host") not in self.site.hosts:
            self.fail(403, "Adresse inconnue : ouvre le site par http://127.0.0.1 (ou l'adresse affichée).")
            return False
        if not self.local and not same(self.cookie_code(), self.site.code):
            self.fail(403, "Code manquant : ouvre l'adresse complète affichée dans la fenêtre du bot.")
            return False
        if action:
            if self.headers.get(HEADER) != HEADER_VALUE:
                self.fail(403, "Action refusée : elle doit venir de la page du site.")
                return False
            origin = self.headers.get("Origin")
            if origin and origin.removeprefix("http://") not in self.site.hosts:
                self.fail(403, "Action refusée : elle vient d'un autre site.")
                return False
        return True

    # --- routes ---
    def do_GET(self) -> None:  # noqa: N802 (nom imposé par http.server)
        try:
            self.route_get()
        except ValueError as exc:
            self.fail(400, str(exc))

    def route_get(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/api/ping":
            if self.headers.get("Host") in self.site.hosts:
                self.json({"site": "tradingbot", "lan": bool(self.site.lan_address)})
            else:
                self.fail(403, "Adresse inconnue")
            return
        if url.path == "/" and not self.local:  # un appareil du réseau local (option --ipad)
            if same((query.get("code") or [""])[0], self.site.code):  # code bon : retenu un an par l'appareil
                self.send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": (
                    f"{CODE_COOKIE}={self.site.code}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict")})
                return
            if not same(self.cookie_code(), self.site.code):
                from .sitepage import code_page
                self.html(code_page(), 403)
                return
        if not self.allowed(action=False):
            return
        if url.path in ("/", "/index.html"):
            from .sitepage import render_page
            self.html(render_page(), extra={"Content-Security-Policy": (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; frame-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'")})
        elif url.path == "/api/etat":
            self.json(self.site.state())
        elif url.path == "/api/journal":
            task = self.site.tasks.get(int((query.get("tache") or ["0"])[0] or 0))
            if task is None:
                self.fail(404, "Tâche introuvable")
                return
            lines, total = task.read(int((query.get("depuis") or ["0"])[0] or 0))
            self.json({"lines": lines, "next": total, "task": task.to_dict()})
        elif url.path == "/api/radar":
            window = int((query.get("fenetre") or ["300"])[0])
            window = window if window in WINDOWS else 300
            rising = (query.get("hausses") or ["0"])[0] == "1"
            _, error, updated = self.site.radar_poller.get()
            view = self.site.radar.view(window, rising)
            self.json({**view, "error": error, "updated": iso(updated), "exchange": label(self.site.radar.exchange_id),
                       "journal": self.site.journal_view()})
        elif url.path == "/api/etude":
            if self.headers.get(HEADER) != HEADER_VALUE:  # une étude télécharge : seulement à la demande de la page
                self.fail(403, "Étude refusée : elle doit venir de la page du site.")
                return
            symbol = self.site.trial_symbol((query.get("symbole") or [""])[0])
            window = int((query.get("fenetre") or ["300"])[0])
            if window not in WINDOWS:
                raise ValueError("Fenêtre inconnue")
            self.json(self.site.studies.get(symbol, window, self.site.radar.price(symbol)))
        elif url.path == "/api/essais":
            self.json(self.site.trials())
        elif url.path == "/api/savoir":
            self.json(knowledge(self.site.data_dir()))
        elif url.path == "/api/trader":
            self.json(self.site.trader_view())
        elif url.path == "/api/ecole":
            self.json(school(self.site.data_dir()))
        elif url.path == "/api/actualite":
            self.json(self.site.news_view())
        elif url.path == "/api/marches":
            self.json({"markets": self.site.radar.top(60), "timeframes": list(Charts.TIMEFRAMES)})
        elif url.path == "/api/graphique":
            if self.headers.get(HEADER) != HEADER_VALUE:  # un graphique télécharge : seulement à la demande de la page
                self.fail(403, "Graphique refusé : il doit venir de la page du site.")
                return
            symbol = self.site.trial_symbol((query.get("symbole") or [""])[0])
            self.json(self.site.chart(symbol, (query.get("unite") or ["4h"])[0]))
        elif url.path == "/api/prix":
            data, error, updated = self.site.prices_poller.get()
            self.json({"board": data, "error": error, "updated": iso(updated)})
        elif url.path == "/api/reglages":
            self.json(self.site.settings_form(self.local))
        elif url.path.startswith("/tableau/"):
            page = self.site.dashboard(url.path.removeprefix("/tableau/"))
            if page is None:
                from .sitepage import empty_dashboard
                self.html(empty_dashboard())
            else:
                self.html(page)
        else:
            self.fail(404, "Page introuvable")

    def do_POST(self) -> None:  # noqa: N802
        if not self.allowed(action=True):
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 100_000:
                self.fail(413, "Demande trop grosse")
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("Demande illisible")
        except ValueError:
            self.fail(400, "Demande illisible")
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/lancer":
                self.json({"ok": True, "task": self.site.launch(str(body.get("action", "")))})
            elif path == "/api/arreter":
                task = self.site.tasks.get(int(body.get("tache") or 0))
                if task is None:
                    self.fail(404, "Tâche introuvable")
                    return
                task.stop()
                self.json({"ok": True})
            elif path == "/api/reglages":
                values = body.get("values")
                if not isinstance(values, dict):
                    raise ValueError("Demande illisible")
                self.json({"ok": True, **self.site.save_settings(values)})
            elif path == "/api/essais/ouvrir":
                self.json({"ok": True, "position": self.site.open_trial(body)})
            elif path == "/api/essais/vendre":
                tid = int(body.get("id") or 0)
                symbol = next((p["symbol"] for p in self.site.desk.state["positions"] if p["id"] == tid), None)
                if symbol is None:
                    raise ValueError("Cet essai n'est plus ouvert.")
                self.json({"ok": True, "trade": self.site.desk.sell(tid, self.site.price_of(symbol), time.time())})
            elif path == "/api/essais/zero":
                self.site.desk.reset(time.time())
                self.json({"ok": True})
            elif path == "/api/ouvrir-reglages":
                if not self.local:
                    raise ValueError("Le fichier .env s'ouvre seulement sur l'ordinateur du bot.")
                if not self.site.env_path.exists() and (self.site.root / ".env.example").exists():
                    atomic_write(self.site.env_path, (self.site.root / ".env.example").read_text(encoding="utf-8"))
                open_in_editor(self.site.env_path)
                self.json({"ok": True})
            else:
                self.fail(404, "Action introuvable")
        except (ValueError, TypeError) as exc:
            self.fail(400, str(exc))
        except OSError as exc:
            self.fail(500, f"Impossible : {exc}")


class SiteServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"  # sous Windows, cette option laisserait deux sites sur un port

    def __init__(self, address, site: Site):
        self.site = site
        super().__init__(address, Handler)


def running_site(port: int) -> dict | None:
    """Le site du bot qui répond déjà sur ce port (lancé deux fois), ou None."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais par un proxy
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/ping", timeout=1) as response:
            info = json.loads(response.read())
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) and info.get("site") == "tradingbot" else None


def already_running(port: int) -> bool:
    return running_site(port) is not None


def lan_ip() -> str | None:
    """L'adresse de l'ordinateur sur le Wi-Fi de la maison (aucun paquet n'est envoyé pour la trouver)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def bind(site: Site, host: str, port: int, attempts: int = 10) -> SiteServer:
    """Le premier port libre à partir de `port` (0 : n'importe lequel, pour les tests)."""
    last: OSError | None = None
    for candidate in ([0] if port == 0 else range(port, port + attempts)):
        try:
            server = SiteServer((host, candidate), site)
            site.port = server.server_port
            return server
        except OSError as exc:
            last = exc
    raise ValueError(f"Aucun port libre pour le site ({port} à {port + attempts - 1}) : {last}")


def stop_serving(signum, frame) -> None:
    raise KeyboardInterrupt


def serve(root: Path, pristine_env: dict[str, str], make_exchange, port: int = PORT, open_browser: bool = True,
          lan: bool = False) -> int:
    running = running_site(port)
    if running and (running.get("lan") or not lan):  # un seul site : deux sites lanceraient deux labos à la fois
        print(f"Le site du bot tourne déjà : je l'ouvre (http://127.0.0.1:{port}/).")
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return 0
    if running:
        raise ValueError("Le site du bot tourne déjà, sans l'accès iPad : ferme sa fenêtre noire, puis relance "
                         "« Ouvrir le bot sur iPad ou telephone ».")
    address = lan_ip() if lan else None
    if lan and not address:
        raise ValueError("Adresse sur le réseau local introuvable : vérifie que l'ordinateur est connecté au Wi-Fi.")
    site = Site(root, pristine_env, make_exchange, port, address)
    server = bind(site, "0.0.0.0" if lan else "127.0.0.1", port)
    site.start_background()  # le radar se remplit dès maintenant, et les essais sont surveillés
    url = f"http://127.0.0.1:{site.port}/"
    print("=" * 78)
    print(f"  LE SITE DU BOT EST OUVERT : {url}")
    if address:
        print(f"  Sur l'iPad ou le téléphone (même Wi-Fi) : http://{address}:{site.port}/?code={site.code}")
        print("  Si Windows demande l'autorisation du pare-feu, accepte pour les réseaux PRIVÉS seulement.")
    print("  Garde cette fenêtre ouverte : la fermer arrête le site et tout ce qu'il a lancé.")
    print("=" * 78, flush=True)
    if open_browser:
        webbrowser.open(url)
    for name in ("SIGTERM", "SIGHUP"):  # Linux et Mac : terminal fermé ou arrêt demandé, on arrête aussi les tâches
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), stop_serving)
            except ValueError:  # hors du fil principal (tests)
                pass
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("Arrêt du site.")
    finally:
        site.tasks.stop_all()
        server.server_close()
    return 0
