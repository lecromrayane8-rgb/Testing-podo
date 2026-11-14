"""Le site du bot : tes bots dans le navigateur, servis par l'ordinateur lui-même (http://127.0.0.1:8765).

`python main.py site` (« Ouvrir le bot » dans la version Windows) ouvre le site et lance tout seul l'essaim de bots en
argent fictif (`main.py flotte`, dans un processus à part dont le journal s'affiche en direct) ; s'il s'arrête, le site
le relance. Pages : Direct (tous les bots), Cryptos (clic : les bots d'une crypto), la page de chaque bot (graphique
zoomable, stop, objectif, analyses), l'actualité et les prix ; sous « Plus » : l'école, les réglages et le journal.

Ce que le site ne fait jamais : passer en argent réel. Les bots sont en argent fictif. MODE, les clés API et
CONFIRM_LIVE_TRADING ne se changent que dans le fichier .env, et un bot en argent réel se lance seulement avec
« 4 - Lancer le bot », hors du site.

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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ccxt

from . import trend
from .broker import atomic_write
from .config import ConfigError, Settings, parse_dotenv
from .data import load_or_fetch, ohlcv_to_frame, timeframe_to_ms
from .explain import read_chart
from .fleet import (
    FLEET_DIR, LOCK_FILE, MAX_SECURE_PART, chart_view, fleet_running, load_json as load_fleet_json,
)
from .knowledge import ENTRIES as KNOWLEDGE
from .news import NewsSource, reaction
from .prices import DEFAULT_CRYPTOS, DEFAULT_PLATFORMS, board_to_dict, connect, short_error, snapshot
from .school import school
from .swarm import DETAIL_DIR, MAX_BOTS_PER_COIN, MAX_COINS, SECURE_R_BOUNDS, SWARM_FILE, bot_detail

log = logging.getLogger(__name__)

PORT = 8765
HEADER = "X-Demande"  # exigé pour toute action : seule la page du site l'envoie
HEADER_VALUE = "site-du-bot"
CODE_COOKIE = "code-du-bot"
CODE_FILE = "site-code.txt"
CALCUL = "calcul"  # un seul calcul lourd à la fois
MAX_LINES = 3000  # lignes de journal gardées par tâche
FINISHED_KEPT = 20  # tâches terminées encore affichées
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



FLEET = ("flotte",)

GROUPS = ("Les bots", "Vérifier")
ACTIONS = {a.key: a for a in (
    Action("flotte", "Mes bots", GROUPS[0],
           "L'essaim de bots en argent fictif : les cryptos qui bougent le plus, toutes les stratégies retestées en "
           "continu sur chacune, et un bot pour chaque combinaison gagnante. Le site le lance tout seul.",
           "tourne en continu", endless=True),
    Action("check", "Vérifier la connexion", GROUPS[1], "Accès à la plateforme, soldes et frais du compte.",
           "quelques secondes"),
    Action("telegram", "Tester les alertes Telegram", GROUPS[1],
           "Trouve l'identifiant de discussion et envoie un message de test sur ton téléphone.", "quelques secondes"),
)}


def steps_for(key: str, root: Path) -> list[tuple[str, ...]]:
    """Les commandes du bot qu'une action lance, dans l'ordre."""
    return {"flotte": [FLEET], "check": [("check",)], "telegram": [("telegram",)]}[key]


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
    """Relève une source (prix, actualité) toutes les `every` secondes, seulement tant qu'une page la regarde."""

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

    def candles(self, symbol: str, timeframe: str, limit: int | None = None):
        if timeframe not in self.TTL:
            raise ValueError("Unité de temps inconnue")
        limit = min(int(limit or self.LIMIT), 1000)
        key = (symbol, timeframe, limit)
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.monotonic() < hit[0]:
                return hit[1]
            if self.exchange is None:
                self.exchange = self.make_exchange(self.exchange_id)
            df = ohlcv_to_frame(self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit))
            now_ms = int(time.time() * 1000)
            df = df[df["ts"] + timeframe_to_ms(timeframe) <= now_ms]  # seulement les bougies terminées
            self.cache[key] = (time.monotonic() + self.TTL[timeframe], df)
            if len(self.cache) > 200:
                self.cache.pop(next(iter(self.cache)))
            return df


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
    kind: str  # money, fee, exchange, secret, chat, path, profile, number, count, switch (oui ou non)
    default: str = ""  # ce que le bot utilise quand la ligne est vide
    bounds: tuple[float, float] = (0.0, 0.0)  # number et count : valeurs permises


FIELDS = (
    Field("FLOTTE_CAPITAL", "Capital fictif de chaque bot", "En USDT. Pour les bots créés ensuite (ceux qui tournent "
          "gardent le leur).", "money", "1000"),
    Field("FLOTTE_CRYPTOS", "Cryptos suivies", f"Les plus agitées du moment, de 1 à {MAX_COINS}. Plus il y en a, plus il "
          "y a de bots (et de calcul).", "count", "60", (1, MAX_COINS)),
    Field("FLOTTE_BOTS_PAR_CRYPTO", "Bots au plus par crypto", f"De 1 à {MAX_BOTS_PER_COIN}. Seules les combinaisons qui "
          "gagnent sur leur historique deviennent des bots ; toutes les autres sont mesurées à l'essai, sans limite.",
          "count", "8", (1, MAX_BOTS_PER_COIN)),
    Field("FLOTTE_MOUVEMENT_MIN", "Mouvement minimum (%)", "Amplitude sur 24 h en dessous de laquelle une crypto passe en "
          "veille (ses bots n'ouvrent plus de trade). 3 = 3 %.", "number", "3", (0, 50)),
    Field("FLOTTE_LEVIER_SCALPING", "Levier du scalping (1 et 5 min)", "De 1 à 20. Réduit pour un trade dont le stop "
          "est loin : le stop passe toujours avant la liquidation. Le levier grossit gains et pertes.", "number", "5",
          (1, 20)),
    Field("FLOTTE_LEVIER_COURT", "Levier du court terme (15 min et 1 h)", "De 1 à 20.", "number", "3", (1, 20)),
    Field("FLOTTE_LEVIER_LONG", "Levier du long terme (4 h)", "De 1 à 20.", "number", "1", (1, 20)),
    Field("FLOTTE_SECURISATION", "Sécurisation des gains", "Quand un trade a assez avancé, le bot encaisse une part "
          "de la position et passe le stop du reste au prix d'entrée : ce trade ne peut presque plus perdre, mais il "
          "rapporte moins s'il s'envole. Les deux façons restent mesurées et comparées (onglet Stratégies).",
          "switch", "oui"),
    Field("FLOTTE_SECURISATION_SEUIL", "Sécurisation : à partir de quel gain (en R)", "De 0,5 à 3. 1 = dès que le "
          "trade a gagné autant que ce qu'il risquait (R : la distance entre l'entrée et le stop de départ).",
          "number", "1", SECURE_R_BOUNDS),
    Field("FLOTTE_SECURISATION_PART", "Sécurisation : part encaissée (%)", f"De 0 à {100 * MAX_SECURE_PART:g}. 50 = "
          "la moitié de la position est vendue au seuil ; 0 = rien n'est vendu, seul le stop passe au prix d'entrée.",
          "number", "50", (0, 100 * MAX_SECURE_PART)),
    Field("EXCHANGE", "Plateforme des données", "Où le bot lit les prix : binance, okx, kraken, coinbase, bybit...",
          "exchange", "binance"),
    Field("TELEGRAM_TOKEN", "Telegram : token du bot", "Donné par @BotFather quand tu crées ton bot (/newbot).",
          "secret"),
    Field("TELEGRAM_CHAT_ID", "Telegram : identifiant de discussion", "Trouvé par « Tester les alertes Telegram ».",
          "chat"),
)
FIELD_KEYS = {f.key: f for f in FIELDS}


def switch_value(field: Field, raw: str | None) -> str | None:
    """Le choix d'une case oui/non tel que les bots le lisent : « oui » ou « non », quelle que soit l'écriture du
    fichier .env (0, false, off, no… valent « non ») ; la valeur par défaut si la ligne est vide. None si elle est
    illisible : les bots la refusent, et n'importe quel choix enregistré depuis le site la répare."""
    if not str(raw or "").strip():
        return field.default
    try:
        return clean_value(field, raw)
    except ValueError:
        return None


def clean_value(field: Field, raw: str) -> str:
    """Valeur vérifiée, prête pour .env ; ValueError avec une explication sinon."""
    value = " ".join(str(raw).split())  # jamais de retour à la ligne : une ligne de .env par réglage
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
    if field.kind == "switch":
        answer = value.lower()
        if answer in ("oui", "o", "1", "true", "on", "yes"):
            return "oui"
        if answer in ("non", "n", "0", "false", "off", "no"):
            return "non"
        raise ValueError(f"{field.title} : oui ou non (reçu « {value} »)")
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


def coin_symbol(raw) -> str:
    """« SOL » -> « SOL/USDT » ; tout le reste est refusé."""
    coin = str(raw or "").strip().upper().removesuffix("/USDT")
    if not re.fullmatch(r"[A-Z0-9]{1,20}", coin):
        raise ValueError("Crypto inconnue")
    return f"{coin}/USDT"


def swarm_step(data: dict, running: bool) -> dict:
    """Ce que dit le haut de l'écran Direct : où en sont les bots, et le bouton utile."""
    totals = data.get("totals") or {}
    tester = data.get("tester") or {}
    if not running:
        if not data.get("ready"):
            return {"title": "Lance tes bots", "action": "flotte",
                    "text": "Le bot va suivre les cryptos qui bougent le plus, tester toutes ses stratégies sur chacune "
                            "(à l'achat et à la vente à découvert), lancer des bots sur les mieux classées et mesurer "
                            "toutes les autres à l'essai, en argent fictif. Aucun argent réel."}
        return {"title": "Tes bots sont à l'arrêt", "action": "flotte",
                "text": "Relance-les : ils reprennent exactement où ils en étaient (positions, capital, trades)."}
    asleep = int(totals.get("asleep") or 0)
    awake = int(totals.get("bots") or 0) - asleep
    sleeping = (f" {asleep} bot{'s' if asleep > 1 else ''} dor{'ment' if asleep > 1 else 't'} en attendant le retour de "
                f"{'leur' if asleep > 1 else 'sa'} crypto dans la liste.") if asleep else ""
    if not awake:
        rows = ((data.get("trial") or {}).get("ranking") or {}).get("strategie") or []
        failed = sum(1 for r in rows if r.get("verdict") == "recalee")
        if failed and failed >= len(rows) / 2:  # ce n'est pas une panne : il faut le dire
            return {"title": "Aucun bot en ce moment : les stratégies perdent à l'essai",
                    "text": f"{failed} stratégies sur {len(rows)} sont recalées : mesurées sur toutes les cryptos, elles "
                            "perdent nettement, frais compris, et leurs bots se sont arrêtés. Ce n'est pas une panne. "
                            "Toutes les combinaisons restent mesurées à l'essai : des bots renaîtront dès qu'une "
                            "stratégie ne perdra plus."}
        return {"title": "Le labo en direct teste les cryptos",
                "text": f"{tester.get('done', 0)} crypto(s) testée(s), {tester.get('queue', 0)} en attente. Chaque test "
                        "essaie des centaines de combinaisons sur l'historique récent ; un bot naît dès qu'une "
                        f"combinaison gagne, frais compris, sur l'étude et la validation. Compte quelques minutes.{sleeping}"}
    trial = (data.get("trial") or {}).get("bots") or 0
    measured = f" {trial:,} combinaisons sont mesurées à l'essai.".replace(",", "\u202f") if trial else ""
    return {"title": f"{awake} bot{'s' if awake > 1 else ''} tourne{'nt' if awake > 1 else ''} en argent fictif",
            "text": f"Sur {totals.get('coins', 0)} cryptos suivies, dont {totals.get('moving', 0)} assez agitées. "
                    f"{totals.get('positions', 0)} en position. Chaque crypto est retestée toutes les 3 heures : un bot "
                    f"garde sa place, les places libres en reçoivent de nouveaux.{measured}{sleeping} Rien ne part jamais "
                    "sur une plateforme."}


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
        settings = self.settings()
        self.exchange_id = settings.exchange if settings else "binance"
        data_dir = self.data_dir()
        self.prices_poller = Poller(PricesSource(make_exchange).fetch, every=10.0)
        self.charts = Charts(make_exchange, self.exchange_id)
        self.news = NewsSource(data_dir / "cache", closes=self._btc_closes, known=self._known_bases)
        self.news_poller = Poller(self.news.fetch, every=600.0, idle=900.0)  # tant que la page Actualité est ouverte
        self.pub_prices: dict[tuple[str, str], float | None] = {}
        self.now_prices: tuple[float, dict[str, float]] = (0.0, {})
        self.markets: set[str] | None = None
        self.lock = threading.Lock()
        self.code = self._code() if lan_address else None
        self.fleet_stopped = False  # arrêtés à la main : le site ne les relance plus tout seul
        # Le bot de tendance : ses bougies d'un jour, sa page (refaite toutes les 10 s au plus), son test de robustesse.
        self.trend_feed = trend.Feed(make_exchange, self.exchange_id, data_dir / trend.FOLDER)
        self.trend_funding = trend.Funding(make_exchange, data_dir / trend.FOLDER)  # le vrai coût des nuits d'emprunt
        self.trend_cache: dict = {}
        self.trend_page: tuple[float, dict | None] = (-math.inf, None)
        self.trend_lock = threading.Lock()
        self.fleet_files: dict[str, dict] = {}  # dernière lecture réussie (un fichier remplacé à l'instant reste lisible)

    def start_background(self) -> None:
        """Ce qui tourne tant que le site est ouvert : les bots, relancés tout seuls s'ils s'arrêtent."""
        try:  # le compte fictif du bot de tendance est daté du premier lancement, même si son onglet reste fermé
            trend.account_since(self.data_dir() / trend.FOLDER)
        except OSError as exc:
            log.warning("Compte du bot de tendance : %s", short_error(exc))
        threading.Thread(target=self._watch_fleet, name="bots", daemon=True).start()

    def _watch_fleet(self) -> None:
        while True:
            try:
                self.keep_fleet_running()
            except Exception as exc:  # jamais fatal : le bouton « Mes bots » reste là
                log.warning("Relance des bots : %s", short_error(exc))
            time.sleep(20)

    def keep_fleet_running(self) -> "Task | None":
        """Les bots tournent tant que le site est ouvert, sauf si on les a arrêtés à la main."""
        if self.fleet_stopped or self.settings() is None or self.fleet_running():
            return None
        return self.tasks.start("flotte")

    # --- les bots ---
    def fleet_folder(self) -> Path:
        return self.data_dir() / FLEET_DIR

    def fleet_file(self, name: str) -> dict | None:
        """Le résumé des bots ; si le fichier est en train d'être remplacé, la dernière version lue."""
        path = self.fleet_folder() / name
        data = load_fleet_json(path, tries=3)
        if data is not None:
            self.fleet_files[name] = data
            return data
        return self.fleet_files.get(name) if path.exists() else None

    def fleet_running(self) -> bool:
        if any(t.action.key == "flotte" for t in self.tasks.running()):
            return True
        lock = load_fleet_json(self.fleet_folder() / LOCK_FILE, tries=2) or {}
        ended = {t.process.pid for t in self.tasks.all() if t.action.key == "flotte" and t.process is not None}
        if lock.get("pid") in ended:
            return False  # nos bots, arrêtés à l'instant : leur signal de vie n'a pas encore eu le temps de vieillir
        return fleet_running(self.fleet_folder())

    def restart_fleet(self) -> bool:
        """Les bots relisent leurs réglages : arrêtés puis relancés tout de suite (positions et comptes repris)."""
        task = next((t for t in self.tasks.running() if t.action.key == "flotte"), None)
        if task is None:
            return False

        def again() -> None:
            task.stop()
            task.thread.join(60)
            if self.fleet_stopped:
                return  # arrêtés à la main entre-temps
            try:
                self.tasks.start("flotte")
            except ValueError as exc:  # le site les relancera tout seul (keep_fleet_running)
                log.warning("Relance des bots : %s", exc)

        threading.Thread(target=again, name="relance-bots", daemon=True).start()
        return True

    def swarm_data(self) -> dict:
        summary = self.fleet_file(SWARM_FILE)
        running = self.fleet_running()
        data = dict(summary or {"coins": [], "bots": [], "events": [], "totals": None})
        data.update(ready=bool(summary), running=running)
        data["step"] = swarm_step(data, running)
        settings = self.settings()
        data["action"] = {"key": "flotte", "title": ACTIONS["flotte"].title,
                          "blocked": self.blocked("flotte", settings.mode if settings else "?")}
        return data

    def coin_data(self, raw) -> dict:
        symbol = coin_symbol(raw)
        summary = self.fleet_file(SWARM_FILE) or {}
        info = next((c for c in summary.get("coins") or [] if c.get("symbol") == symbol), None)
        bots = [b for b in summary.get("bots") or [] if b.get("symbol") == symbol]
        base = symbol.split("/")[0]
        latest = self.news_poller.get()[0] or {}  # relevé toutes les 10 minutes tant qu'une page le demande
        news = [n for n in latest.get("news") or [] if base in (n.get("coins") or [])][:8]
        return {"symbol": symbol, "coin": base, "info": info, "bots": bots, "news": news, "mood": summary.get("mood"),
                "running": self.fleet_running(), "timeframes": sorted({b["timeframe"] for b in bots},
                                                                      key=timeframe_to_ms)}

    def _bot(self, raw) -> dict:
        bid = str(raw or "")
        if not re.fullmatch(r"[0-9a-f]{10}", bid):
            raise ValueError("Bot inconnu")
        bot = load_fleet_json(self.fleet_folder() / DETAIL_DIR / f"{bid}.json", tries=3)
        if not bot:
            raise ValueError("Ce bot n'existe pas (ou plus : il a peut-être été arrêté).")
        return bot

    def bot_data(self, raw) -> dict:
        bot = self._bot(raw)
        brief = next((b for b in (self.fleet_file(SWARM_FILE) or {}).get("bots") or [] if b.get("id") == bot["id"]),
                     None)
        if brief:  # le dernier tour (prix, statut, signal, probabilité) : plus frais que le fichier du bot
            bot = {**bot, **{k: brief[k] for k in ("last_price", "status", "signal", "proba") if brief.get(k) is not None}}
        try:
            detail = bot_detail(bot)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Bot illisible : {exc}") from None
        family = detail.get("family")
        card = next((e for e in KNOWLEDGE if e.get("family") == family), None)
        detail["technique_card"] = {k: card[k] for k in ("title", "measures", "reading", "research")} if card else None
        detail["live"] = brief.get("live") if brief else None  # le verdict de sa stratégie en direct
        return detail

    # --- le bot de tendance ---
    def trend_view(self) -> dict:
        """La page « Tendance » : où en est la règle, le compte fictif, l'histoire, le test de robustesse. Argent
        fictif : la page se calcule à partir des seules bougies publiques, aucun ordre n'existe nulle part."""
        with self.trend_lock:
            at, page = self.trend_page
            if page is None or time.monotonic() - at >= 10:
                page = trend.view(self.trend_feed, self.data_dir() / trend.FOLDER, cache=self.trend_cache,
                                  funding=self.trend_funding)
                self.trend_page = (time.monotonic(), page)
            return page

    def trend_chart(self, raw) -> dict:
        symbol = coin_symbol(raw)
        if symbol not in trend.SYMBOLS:
            raise ValueError("Le bot de tendance ne suit que le Bitcoin et l'Ether.")
        return trend.chart_view(symbol, self.trend_feed.get(symbol))

    def coin_chart(self, raw, timeframe: str) -> dict:
        """Le graphique d'une crypto : ses bougies, ses supports et résistances, et ce qu'y font ses bots."""
        symbol = coin_symbol(raw)
        df = self.charts.candles(symbol, timeframe, 1000)
        if len(df) < 30:
            raise ValueError("Pas assez d'historique pour ce graphique.")
        reading = read_chart(df.iloc[-400:])
        last = float(df["close"].iloc[-1])
        levels = [{**z, "kind": "support" if z["price"] < last else "resistance"}
                  for z in reading.pop("levels") if z["touches"] >= 2]
        first = int(df["ts"].iloc[0])
        summary = self.fleet_file(SWARM_FILE) or {}
        marks, trades = [], []
        for b in summary.get("bots") or []:
            if b.get("symbol") != symbol or b.get("timeframe") != timeframe:
                continue
            name = b["technique"]
            p = b.get("position")
            if p:
                marks.append({"bot": b["id"], "name": name, "side": p["side"], "price": p["price"], "stop": p["stop"],
                              "target": p.get("target"), "entry_ts": p["entry_ts"]})
            detail = load_fleet_json(self.fleet_folder() / DETAIL_DIR / f"{b['id']}.json", tries=2) or {}
            for t in (detail.get("book") or {}).get("trades") or []:
                if t["exit_ts"] >= first:
                    trades.append({"bot": b["id"], "name": name, "side": t["side"], "entry": t["entry_ts"],
                                   "exit": t["exit_ts"], "net": t["net"], "entry_price": t["price"],
                                   "exit_price": t["exit_price"]})
        return {"symbol": symbol, "timeframe": timeframe, "last": last,
                "candles": df[["ts", "open", "high", "low", "close", "volume"]].values.tolist(),
                "levels": levels, "reading": reading, "positions": marks, "trades": trades}

    def bot_chart(self, raw) -> dict:
        bot = self._bot(raw)
        spec = bot["spec"]
        df = self.charts.candles(spec["symbol"], spec["timeframe"], 1000)
        try:
            return chart_view(df, {"slot": bot["id"], "bot": bot}, shown=len(df))
        except KeyError as exc:  # une technique d'une ancienne version
            raise ValueError(f"Bot illisible : {exc}") from None

    # --- l'actualité ---
    def _btc_closes(self):
        """Les clôtures journalières du Bitcoin, pour l'étude de l'indice peur et avidité."""
        df = load_or_fetch(self.exchange_id, "BTC/USDT", "1d", 3000, self.data_dir() / "cache",
                           self.make_exchange(self.exchange_id))
        return df["close"].astype(float)

    def _known_bases(self) -> set[str]:
        """Les cryptos cotées en USDT sur la plateforme (pour reconnaître les tickers dans les titres)."""
        with self.lock:
            if self.markets is None:
                try:
                    exchange = self.make_exchange(self.exchange_id)
                    exchange.load_markets()
                    self.markets = {m["base"] for m in exchange.markets.values()
                                    if m.get("quote") == "USDT" and m.get("spot")}
                except Exception as exc:  # pas de liste : les noms connus suffisent
                    log.debug("Liste des cryptos indisponible : %s", short_error(exc))
                    return set()
            return self.markets

    def _price_now(self, bases: set[str]) -> dict[str, float]:
        """Les derniers prix des cryptos citées (une requête, gardée une minute)."""
        at, prices = self.now_prices
        missing = {b for b in bases if b not in prices}
        if time.monotonic() - at < 60 and not missing:
            return prices
        symbols = sorted(f"{b}/USDT" for b in bases if b in self._known_bases())
        if not symbols:
            return prices
        try:
            if self.charts.exchange is None:
                self.charts.exchange = self.make_exchange(self.exchange_id)
            tickers = self.charts.exchange.fetch_tickers(symbols)
            prices = {s.split("/")[0]: float(t["last"]) for s, t in tickers.items() if (t or {}).get("last")}
            self.now_prices = (time.monotonic(), prices)
        except Exception as exc:
            log.debug("Prix des cryptos citées indisponibles : %s", short_error(exc))
        return prices

    def _price_then(self, base: str, published: str | None) -> float | None:
        """Le prix d'une crypto au moment d'une nouvelle (ouverture de la bougie de 5 min), gardé une fois trouvé."""
        symbol = f"{base}/USDT"
        key = (symbol, published or "")
        if key in self.pub_prices:
            return self.pub_prices[key]
        price = None
        try:
            when = int(datetime.fromisoformat(published).timestamp() * 1000) if published else None
            if when and base in self._known_bases() and time.time() * 1000 - when < 3 * 86_400_000:
                if self.charts.exchange is None:
                    self.charts.exchange = self.make_exchange(self.exchange_id)
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

        now = self._price_now({c for n in news for c in n.get("coins") or []})
        reaction(news, then, lambda base: now.get(base))
        return {"news": news, "fng": data["fng"], "errors": data["errors"] + ([error] if error else []),
                "updated": iso(updated)}

    # --- réglages, état ---
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
        mode = settings.mode if settings else "?"
        return {
            "mode": mode, "mode_label": MODE_LABELS.get(mode, mode), "exchange": settings.exchange if settings else "?",
            "settings_error": self.settings_error,
            "tasks": [t.to_dict() for t in sorted(self.tasks.all(), key=lambda t: -t.id)],
            "actions": [{"key": a.key, "title": a.title, "group": a.group, "description": a.description,
                         "duration": a.duration, "blocked": self.blocked(a.key, mode)} for a in ACTIONS.values()],
            "groups": list(GROUPS),
        }

    def blocked(self, key: str, mode: str) -> str | None:
        if key == "flotte" and not any(t.action.key == "flotte" for t in self.tasks.running()) \
                and self.fleet_running():
            return "Les bots tournent déjà (lancés par un lanceur) : regarde l'écran Direct."
        return self.tasks.blocker(key)

    def launch(self, key: str) -> dict:
        settings = self.settings()
        if settings is None:
            raise ValueError(f"Réglages invalides, corrige-les d'abord : {self.settings_error}")
        if key not in ACTIONS:
            raise ValueError(f"Action inconnue : {key}")
        if reason := self.blocked(key, settings.mode):
            raise ValueError(reason)
        if key == "flotte":
            self.fleet_stopped = False
        return self.tasks.start(key).to_dict()

    def settings_form(self, local: bool) -> dict:
        values = parse_dotenv(self.env_path)
        settings = self.settings()
        fields = []
        for f in FIELDS:
            current = values.get(f.key, "")
            item = {"key": f.key, "title": f.title, "help": f.help, "kind": f.kind, "default": f.default}
            if f.kind == "secret":
                item["set"] = bool(current)  # jamais renvoyé : un token ne s'affiche pas sur une page
            else:  # une case oui/non : le choix que les bots appliquent, pas le texte brut (« 0 » se lit « non »)
                item["value"] = (switch_value(f, current) or f.default) if f.kind == "switch" else current
            fields.append(item)
        mode = settings.mode if settings else values.get("MODE", "paper")
        return {"fields": fields, "mode": mode, "mode_label": MODE_LABELS.get(mode, mode), "local": local,
                "error": self.settings_error}

    def save_settings(self, changes: dict) -> dict:
        cleaned = {}
        current = parse_dotenv(self.env_path)
        for key, raw in changes.items():
            field = FIELD_KEYS.get(key)
            if field is None:
                raise ValueError(f"Ce réglage ne se change pas depuis le site : {key}")
            if not str(raw).strip() and field.kind in ("secret", "money", "fee", "exchange", "number", "count", "switch"):
                continue  # vide : on garde la valeur actuelle (le token enregistré, ou la valeur par défaut)
            value = clean_value(field, raw)
            if field.kind == "switch" and value == switch_value(field, current.get(key)):
                continue  # une liste envoie toujours son choix : inchangé, on n'écrit rien (et les bots ne redémarrent pas)
            cleaned[key] = value
        if not self.env_path.exists() and (self.root / ".env.example").exists():
            atomic_write(self.env_path, (self.root / ".env.example").read_text(encoding="utf-8"))
        if cleaned:
            update_env(self.env_path, cleaned)
        if self.settings() is None:
            raise ConfigError(f"Réglages enregistrés, mais invalides : {self.settings_error}")
        restarted = any(k.startswith("FLOTTE_") or k == "EXCHANGE" for k in cleaned) and self.restart_fleet()
        return {"saved": sorted(cleaned), "restarted": restarted}


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

        def arg(name: str) -> str:
            return (query.get(name) or [""])[0]

        if url.path == "/api/ping":
            if self.headers.get("Host") in self.site.hosts:
                self.json({"site": "tradingbot", "lan": bool(self.site.lan_address)})
            else:
                self.fail(403, "Adresse inconnue")
            return
        if url.path == "/" and not self.local:  # un appareil du réseau local (option --ipad)
            if same(arg("code"), self.site.code):  # code bon : retenu un an par l'appareil
                self.send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": (
                    f"{CODE_COOKIE}={self.site.code}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict")})
                return
            if not same(self.cookie_code(), self.site.code):
                from .sitepage import code_page
                self.html(code_page(), 403)
                return
        if not self.allowed(action=False):
            return
        page_only = url.path in ("/api/crypto-graphique", "/api/bot-graphique", "/api/actualite", "/api/tendance",
                                 "/api/tendance-graphique")
        if page_only and self.headers.get(HEADER) != HEADER_VALUE:  # elles téléchargent : seulement pour la page
            self.fail(403, "Demande refusée : elle doit venir de la page du site.")
            return
        if url.path in ("/", "/index.html"):
            from .sitepage import render_page
            self.html(render_page(), extra={"Content-Security-Policy": (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'")})
        elif url.path == "/api/etat":
            self.json(self.site.state())
        elif url.path == "/api/journal":
            task = self.site.tasks.get(int(arg("tache") or 0))
            if task is None:
                self.fail(404, "Tâche introuvable")
                return
            lines, total = task.read(int(arg("depuis") or 0))
            self.json({"lines": lines, "next": total, "task": task.to_dict()})
        elif url.path == "/api/bots":
            self.json(self.site.swarm_data())
        elif url.path == "/api/crypto":
            self.json(self.site.coin_data(arg("c")))
        elif url.path == "/api/crypto-graphique":
            self.json(self.site.coin_chart(arg("c"), arg("unite") or "15m"))
        elif url.path == "/api/bot":
            self.json(self.site.bot_data(arg("id")))
        elif url.path == "/api/bot-graphique":
            self.json(self.site.bot_chart(arg("id")))
        elif url.path == "/api/ecole":
            self.json(school(self.site.data_dir()))
        elif url.path == "/api/actualite":
            self.json(self.site.news_view())
        elif url.path == "/api/tendance":
            self.json(self.site.trend_view())
        elif url.path == "/api/tendance-graphique":
            self.json(self.site.trend_chart(arg("c")))
        elif url.path == "/api/prix":
            data, error, updated = self.site.prices_poller.get()
            self.json({"board": data, "error": error, "updated": iso(updated)})
        elif url.path == "/api/reglages":
            self.json(self.site.settings_form(self.local))
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
                if task.action.key == "flotte":
                    self.site.fleet_stopped = True  # arrêtés à la main : le site ne les relance plus tout seul
                task.stop()
                self.json({"ok": True})
            elif path == "/api/reglages":
                values = body.get("values")
                if not isinstance(values, dict):
                    raise ValueError("Demande illisible")
                self.json({"ok": True, **self.site.save_settings(values)})
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
    site.start_background()  # les bots démarrent (ou repartent) tout de suite
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
