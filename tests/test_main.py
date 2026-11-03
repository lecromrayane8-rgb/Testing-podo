import json

import numpy as np

import main
from tests.conftest import frame_from_closes


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
