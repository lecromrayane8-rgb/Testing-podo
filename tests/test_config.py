import pytest

from tests.test_live import settings
from tradingbot.config import ConfigError, parse_bots


def test_parse_bots():
    assert parse_bots("BTC/USDT@15m, eth/usdt@4h,") == (("BTC/USDT", "15m"), ("ETH/USDT", "4h"))
    assert parse_bots("") == ()


@pytest.mark.parametrize("raw", ["BTC/USDT", "@1h", "BTC/USDT@"])
def test_parse_bots_rejects_malformed_items(raw):
    with pytest.raises(ConfigError, match="PAIRE@UNITE"):
        parse_bots(raw)


def test_markets_default_to_symbol_and_timeframe(tmp_path):
    assert settings(tmp_path).markets == (("BTC/USDT", "1h"),)
    several = settings(tmp_path, bots=(("BTC/USDT", "15m"), ("BTC/USDT", "1d")))
    assert several.markets == (("BTC/USDT", "15m"), ("BTC/USDT", "1d"))


def test_several_paper_bots_are_valid(tmp_path):
    settings(tmp_path, bots=(("BTC/USDT", "15m"), ("BTC/USDT", "1h"), ("BTC/USDT", "1d"))).validate_for_trading()


def test_duplicate_bots_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="deux fois"):
        settings(tmp_path, bots=(("BTC/USDT", "1h"), ("BTC/USDT", "1h"))).validate_for_trading()


def test_invalid_timeframe_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Unité de temps invalide"):
        settings(tmp_path, bots=(("BTC/USDT", "1x"),)).validate_for_trading()


def test_several_bots_on_a_real_account_need_a_capital_each(tmp_path):
    two = (("BTC/USDT", "1h"), ("ETH/USDT", "1h"))
    with pytest.raises(ConfigError, match="MAX_CAPITAL"):
        settings(tmp_path, mode="testnet", api_key="k", api_secret="s", bots=two).validate_for_trading()
    settings(tmp_path, mode="testnet", api_key="k", api_secret="s", bots=two, max_capital=100.0).validate_for_trading()
