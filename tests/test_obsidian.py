import logging
from datetime import datetime, timezone

import numpy as np
import pytest

from tests.test_live import dip_scenario, make_bot
from tradingbot.obsidian import JOURNAL, ObsidianHandler, ObsidianJournal, frontmatter, safe_name, yaml_value

NOW = datetime(2026, 11, 3, 14, 5, tzinfo=timezone.utc)


@pytest.fixture
def journal(tmp_path):
    return ObsidianJournal(tmp_path / "vault", clock=lambda: NOW)


def test_yaml_values():
    assert yaml_value(float("nan")) == "null"
    assert yaml_value(float("inf")) == ".inf"
    assert yaml_value(np.float64(0.1234567891)) == "0.12345679"
    assert yaml_value(np.int64(7)) == "7"
    assert yaml_value('il a dit "ok"') == '"il a dit \\"ok\\""'
    assert yaml_value(["BTC/USDT 1h"]) == '["BTC/USDT 1h"]'
    assert frontmatter({"a": 1}) == "---\na: 1\n---\n"


def test_note_names_are_valid():
    assert safe_name("2026-11-03 14h05 BTC/USDT 1h") == "2026-11-03 14h05 BTC-USDT 1h"
    assert safe_name("a:b#c|d[e]") == "a-b-c-d-e-"


def test_dashboard_is_created_once_and_never_overwritten(tmp_path):
    dashboard = tmp_path / "vault" / "Trading bot" / "Tableau de bord.md"
    ObsidianJournal(tmp_path / "vault")
    assert "```dataview" in dashboard.read_text(encoding="utf-8")
    dashboard.write_text("mes modifs")
    ObsidianJournal(tmp_path / "vault")
    assert dashboard.read_text(encoding="utf-8") == "mes modifs"


def test_events_are_appended_to_the_daily_note(journal):
    journal.event("ACHAT 0.1 BTC")
    journal.event("Erreur réseau", alert=True)
    note = journal.root / "Journal" / "2026-11-03.md"
    lines = note.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Journal du 03/11/2026"
    assert lines[-2].endswith("ACHAT 0.1 BTC")
    assert lines[-1].endswith("**ALERTE** Erreur réseau")


def test_handler_copies_only_marked_logs_and_alerts(journal):
    logger = logging.getLogger("tradingbot.test_obsidian")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(ObsidianHandler(journal))
    logger.info("bougie ordinaire")
    logger.info("VENTE (rebond)", extra=JOURNAL)
    logger.warning("Signal d'achat ignoré")
    text = (journal.root / "Journal" / "2026-11-03.md").read_text(encoding="utf-8")
    assert "bougie ordinaire" not in text
    assert "VENTE (rebond)" in text and "**ALERTE** Signal d'achat ignoré" in text


def test_same_minute_notes_do_not_overwrite_each_other(journal):
    record = {"entree": "2026-11-03T12:00:00+00:00", "sortie": "2026-11-03T14:05:00+00:00", "pnl": 5.0, "raison": "rebond"}
    first = journal.trade("testnet", "BTC/USDT", record, cost=100.0)
    second = journal.trade("testnet", "BTC/USDT", record, cost=100.0)
    assert first != second and first.exists() and second.exists()
    assert "rendement_pct: 5.0" in first.read_text(encoding="utf-8")


def test_bot_writes_a_note_for_each_closed_trade(tmp_path):
    journal = ObsidianJournal(tmp_path / "vault")
    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    bot, broker = make_bot(tmp_path, df, notes=journal)
    for i in range(95, 106):
        bot.step(broker.at_open(i))
    notes = list((journal.root / "Trades").glob("*.md"))
    assert len(notes) == 1
    text = notes[0].read_text(encoding="utf-8")
    assert 'mode: "paper"' in text and 'raison: "rebond"' in text and "Trade **gagnant**" in text


def test_journal_failure_never_stops_the_bot(tmp_path):
    class BrokenJournal:
        def trade(self, *args):
            raise OSError("coffre introuvable")

    df = dip_scenario([156.0, 159.0, 161.0, 162.0])
    bot, broker = make_bot(tmp_path, df, notes=BrokenJournal())
    for i in range(95, 106):
        bot.step(broker.at_open(i))
    assert [o[0] for o in broker.orders] == ["buy", "sell"]
    assert bot.state["position"] is None
