"""Alertes sur le téléphone par Telegram (optionnel) : achats, ventes, éliminations, résumés du tournoi.

Mise en place (5 minutes, gratuit) : dans Telegram, écrire à @BotFather, envoyer /newbot et suivre les étapes ;
il donne un « token » à mettre dans TELEGRAM_TOKEN. Écrire ensuite un message au nouveau bot, puis lancer
`python main.py telegram` : la commande trouve l'identifiant de la discussion (TELEGRAM_CHAT_ID) et envoie un test.

Les messages partent d'un fil à part, un par seconde au plus : une panne de Telegram ne ralentit jamais le bot.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"
ALERT = {"alert": True}  # `extra=` d'un log à envoyer sur le téléphone, même dans un tournoi
MAX_PENDING = 200

log = logging.getLogger(__name__)


def call(token: str, method: str, params: dict | None = None, opener=urllib.request.urlopen, timeout: float = 10.0):
    """Appelle l'API de Telegram et renvoie son champ `result` (lève une erreur si Telegram refuse)."""
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(API.format(token=token, method=method), data=data, method="POST")
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or "réponse refusée par Telegram")
    return payload.get("result")


def latest_chat_id(token: str, opener=urllib.request.urlopen) -> str | None:
    """L'identifiant de la dernière discussion qui a écrit au bot (pour remplir TELEGRAM_CHAT_ID)."""
    for update in reversed(call(token, "getUpdates", opener=opener) or []):
        chat = (update.get("message") or update.get("channel_post") or {}).get("chat") or {}
        if chat.get("id") is not None:
            return str(chat["id"])
    return None


class TelegramHandler(logging.Handler):
    """Envoie sur Telegram les erreurs et les logs marqués `extra=ALERT` (et `extra=JOURNAL` si `journal`).

    `journal=False` dans un tournoi : des dizaines de bots y tradent, seuls les résumés et les éliminations partent.
    """

    def __init__(self, token: str, chat_id: str, journal: bool = True, opener=urllib.request.urlopen,
                 min_interval: float = 1.0, start: bool = True):
        super().__init__(logging.INFO)
        self.token, self.chat_id, self.journal = token, chat_id, journal
        self.opener, self.min_interval = opener, min_interval
        self.pending: queue.Queue[str] = queue.Queue(MAX_PENDING)
        self.warned = False
        if start:
            threading.Thread(target=self._run, name="telegram", daemon=True).start()

    def wanted(self, record: logging.LogRecord) -> bool:
        if record.name == log.name:  # jamais ses propres messages (une panne de Telegram ne boucle pas)
            return False
        if record.levelno >= logging.ERROR or getattr(record, "alert", False):
            return True
        return self.journal and getattr(record, "journal", False)

    def emit(self, record: logging.LogRecord) -> None:
        if not self.wanted(record):
            return
        try:
            self.pending.put_nowait(record.getMessage())
        except queue.Full:  # Telegram en panne depuis longtemps : on garde le bot léger
            pass

    def send(self, text: str) -> None:
        call(self.token, "sendMessage", {"chat_id": self.chat_id, "text": text[:4000],
                                         "disable_web_page_preview": "true"}, opener=self.opener)

    def _run(self) -> None:
        while True:
            text = self.pending.get()
            try:
                self.send(text)
                self.warned = False
            except Exception as exc:
                if not self.warned:  # une seule alerte tant que la panne dure
                    log.warning("Alerte Telegram non envoyée : %s", exc)
                    self.warned = True
            time.sleep(self.min_interval)


def attach(settings, journal: bool = True) -> TelegramHandler | None:
    """Branche les alertes Telegram sur le journal du bot si TELEGRAM_TOKEN et TELEGRAM_CHAT_ID sont remplis."""
    if not (settings.telegram_token and settings.telegram_chat_id):
        return None
    handler = TelegramHandler(settings.telegram_token, settings.telegram_chat_id, journal=journal)
    logging.getLogger("tradingbot").addHandler(handler)
    return handler
