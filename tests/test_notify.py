import io
import json
import logging
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

import main
from tradingbot import notify
from tradingbot.notify import ALERT, TelegramHandler, attach, call, latest_chat_id
from tradingbot.obsidian import JOURNAL


class FakeTelegram:
    """Remplace l'API de Telegram : garde chaque requête et répond comme elle."""

    def __init__(self, result=True, ok=True):
        self.requests, self.result, self.ok = [], result, ok
        self.received = threading.Event()

    def __call__(self, request, timeout):
        self.requests.append((request.full_url, parse_qs(request.data.decode())))
        self.received.set()
        return io.BytesIO(json.dumps({"ok": self.ok, "result": self.result, "description": "Unauthorized"}).encode())


def record(level=logging.INFO, name="tradingbot.live", **extra):
    rec = logging.LogRecord(name, level, __file__, 1, "[BTC/USDT 1h] ACHAT %s", ("0.1",), None)
    rec.__dict__.update(extra)
    return rec


def test_only_trades_alerts_and_errors_reach_the_phone():
    bot = TelegramHandler("t", "42", journal=True, start=False)
    tournament = TelegramHandler("t", "42", journal=False, start=False)
    trade, alert, error, chatter = record(**JOURNAL), record(**ALERT), record(logging.ERROR), record()
    assert bot.wanted(trade) and bot.wanted(alert) and bot.wanted(error) and not bot.wanted(chatter)
    assert not tournament.wanted(trade) and tournament.wanted(alert) and tournament.wanted(error)
    assert not bot.wanted(record(logging.ERROR, name=notify.log.name))  # jamais ses propres pannes


def test_messages_are_sent_from_a_separate_thread():
    api = FakeTelegram()
    handler = TelegramHandler("SECRET", "42", opener=api, min_interval=0)
    handler.emit(record(**JOURNAL))
    assert api.received.wait(5)
    url, data = api.requests[0]
    assert url == "https://api.telegram.org/botSECRET/sendMessage"
    assert data["chat_id"] == ["42"] and data["text"] == ["[BTC/USDT 1h] ACHAT 0.1"]


def test_chat_id_is_found_from_the_last_message_sent_to_the_bot():
    api = FakeTelegram(result=[{"message": {"chat": {"id": 7}}}, {"message": {"chat": {"id": 123456789}}}])
    assert latest_chat_id("t", opener=api) == "123456789"
    assert latest_chat_id("t", opener=FakeTelegram(result=[])) is None
    with pytest.raises(RuntimeError, match="Unauthorized"):
        call("t", "getMe", opener=FakeTelegram(ok=False))


def test_alerts_are_attached_only_when_configured():
    assert attach(SimpleNamespace(telegram_token="", telegram_chat_id="")) is None
    handler = attach(SimpleNamespace(telegram_token="t", telegram_chat_id="42"), journal=False)
    try:
        assert handler in logging.getLogger("tradingbot").handlers and handler.journal is False
    finally:
        logging.getLogger("tradingbot").removeHandler(handler)


def test_telegram_command_finds_the_chat_and_sends_a_test(tmp_path, monkeypatch, capsys, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    assert main.main(["telegram"]) == 2  # pas encore de token : explication, pas de plantage
    assert "@BotFather" in caplog.text
    sent = []
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setattr(main, "latest_chat_id", lambda token: "123456789")
    monkeypatch.setattr(main, "telegram_call", lambda token, method, params: sent.append(params))
    assert main.main(["telegram"]) == 0
    out = capsys.readouterr().out
    assert "TELEGRAM_CHAT_ID=123456789" in out and sent[0]["chat_id"] == "123456789"
