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
