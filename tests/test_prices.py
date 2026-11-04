from datetime import datetime

import ccxt

import main
from tradingbot.prices import Board, connect, format_board, resolve, snapshot
from tradingbot.scanner import ScanResult


def market(symbol, spot=True, active=True):
    return {"symbol": symbol, "spot": spot, "active": active}


class Platform:
    """Plateforme simulée : prix publics seulement."""

    def __init__(self, prices, change=2.5, batch=True, broken=False):
        self.markets = {s: market(s) for s in prices}
        self.prices, self.change, self.batch, self.broken, self.calls = prices, change, batch, broken, 0

    def load_markets(self):
        return self.markets

    def _ticker(self, symbol):
        return {"last": self.prices[symbol], "percentage": self.change}

    def fetch_tickers(self, symbols):
        self.calls += 1
        if self.broken:
            raise ccxt.NetworkError("délai dépassé")
        if not self.batch:
            raise ccxt.NotSupported("une paire à la fois")
        return {s: self._ticker(s) for s in symbols}

    def fetch_ticker(self, symbol):
        self.calls += 1
        return self._ticker(symbol)


def test_each_platform_is_read_in_its_own_stable_coin():
    markets = {"PEPE/USD": market("PEPE/USD"), "BTC/USDC": market("BTC/USDC"), "BTC/USD": market("BTC/USD"),
               "ETH/USDT": market("ETH/USDT", active=False), "ETH/USDC": market("ETH/USDC")}
    assert resolve(markets, "BTC") == "BTC/USDC" and resolve(markets, "PEPE") == "PEPE/USD"
    assert resolve(markets, "ETH") == "ETH/USDC"  # la paire en USDT est fermée
    assert resolve(markets, "SOL") is None


def test_prices_are_compared_across_platforms():
    exchanges = {
        "binance": Platform({"BTC/USDT": 68_000.0, "PEPE/USDT": 0.0000123}, change=3.0),
        "kraken": Platform({"BTC/USDT": 68_068.0, "PEPE/USD": 0.0000124}, batch=False),
        "okx": Platform({"BTC/USDT": 67_990.0}, broken=True),
    }
    board = snapshot(exchanges, ["BTC", "PEPE"])
    assert board.prices[("BTC", "kraken")] == (68_068.0, "BTC/USDT")
    assert board.spread("BTC") == 68_068.0 / 68_000.0 - 1  # OKX n'a pas répondu
    assert board.changes["BTC"] == 0.03 and "okx" in board.errors and "délai dépassé" in board.errors["okx"]
    text = format_board(board, datetime(2026, 11, 4, 14, 30), hot=[ScanResult("WIF/USDT", 0.21, 3.2e7, 0.07)],
                        every=10)
    assert "Binance" in text and "Kraken" in text and "68000.00" in text and "0.000012300" in text
    assert "0.000012400$" in text  # PEPE coté en dollars sur Kraken
    assert "OKX indisponible" in text and "WIF/USDT" in text and "toutes les 10 s" in text


def test_an_unreachable_platform_does_not_stop_the_others():
    def make(platform):
        if platform == "kraken":
            raise ccxt.ExchangeNotAvailable("maintenance")
        return Platform({"BTC/USDT": 68_000.0})

    exchanges, errors = connect(["binance", "kraken"], make)
    assert list(exchanges) == ["binance"] and "maintenance" in errors["kraken"]
    board = snapshot(exchanges, ["BTC"], errors)
    assert board.platforms == ["binance", "kraken"] and board.prices[("BTC", "binance")][0] == 68_000.0
    assert Board(["BTC"], ["binance"]).spread("BTC") is None


def test_prices_command_shows_one_board(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    platforms = {"binance": Platform({"BTC/USDT": 68_000.0, "ETH/USDT": 3_500.0}),
                 "okx": Platform({"BTC/USDT": 68_010.0, "ETH/USDT": 3_499.0})}
    monkeypatch.setattr(main, "make_exchange", lambda platform: platforms[platform])
    monkeypatch.setattr(main, "scan_volatile", lambda exchange, top: [ScanResult("PEPE/USDT", 0.18, 4e7, -0.05)])
    assert main.main(["prix", "--cryptos", "btc,ETH/USDT", "--plateformes", "binance,okx", "--une-fois"]) == 0
    out = capsys.readouterr().out
    assert "PRIX EN DIRECT" in out and "BTC" in out and "ETH" in out and "PEPE/USDT" in out and "OKX" in out


def test_new_listings_are_the_pairs_that_appeared_since_the_last_visit(tmp_path):
    from tradingbot.prices import new_listings
    ex = Platform({"BTC/USDT": 68_000.0})
    ex.markets = {"BTC/USDT": {"quote": "USDT", "spot": True}, "ETH/BTC": {"quote": "BTC", "spot": True}}
    memory = tmp_path / "marches-connus-binance.json"
    assert new_listings(ex, memory) is None  # toute première visite : rien à comparer
    ex.markets["NEWMEME/USDT"] = {"quote": "USDT", "spot": True}
    ex.markets["OLD/USDT"] = {"quote": "USDT", "spot": True, "active": False}
    assert new_listings(ex, memory) == ["NEWMEME/USDT"]
    assert new_listings(ex, memory) == []  # déjà vue à la visite précédente
    board = snapshot({"binance": ex}, ["BTC"])
    text = format_board(board, datetime(2026, 11, 4, 15, 0), listings=["NEWMEME/USDT"])
    assert "NOUVELLES COTATIONS sur Binance depuis ta dernière visite : NEWMEME/USDT" in text
    assert "aucune" in format_board(board, datetime(2026, 11, 4, 15, 0), listings=[])
