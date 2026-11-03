import pytest

from tradingbot.scanner import MEMECOINS, pick_markets, scan_volatile


class FakeExchange:
    """Marchés et tickers figés ; compte les requêtes de tickers."""

    def __init__(self, markets, tickers):
        self.markets = markets
        self.tickers = tickers
        self.ticker_calls = 0

    def load_markets(self):
        return self.markets

    def fetch_tickers(self):
        self.ticker_calls += 1
        return self.tickers


def market(symbol, spot=True, active=True):
    base, quote = symbol.split(":")[0].split("/")
    return {"symbol": symbol, "base": base, "quote": quote, "spot": spot, "active": active}


def ticker(amplitude, volume, last=1.0, change=3.0):
    return {"high": last * (1 + amplitude), "low": last, "last": last, "quoteVolume": volume, "percentage": change}


def exchange(**entries):
    """entries : symbole -> (marché, ticker)."""
    return FakeExchange({s: m for s, (m, _) in entries.items() if m}, {s: t for s, (_, t) in entries.items()})


def test_scanner_keeps_only_liquid_spot_cryptos_from_the_most_agitated():
    ex = exchange(**{
        "SOL/USDT": (market("SOL/USDT"), ticker(0.10, 50e6, last=180.0)),
        "PEPE/USDT": (market("PEPE/USDT"), ticker(0.25, 30e6, last=0.00001)),
        "TINY/USDT": (market("TINY/USDT"), ticker(0.80, 100e3)),  # personne en face pour revendre
        "USDC/USDT": (market("USDC/USDT"), ticker(0.001, 1e9)),  # monnaie stable
        "BTCUP/USDT": (market("BTCUP/USDT"), ticker(0.50, 10e6)),  # token à levier
        "ETH/BTC": (market("ETH/BTC"), ticker(0.05, 10e6)),  # pas coté en USDT
        "OLD/USDT": (market("OLD/USDT", active=False), ticker(0.30, 10e6)),
        "SOL/USDT:USDT": (market("SOL/USDT:USDT", spot=False), ticker(0.40, 900e6)),  # contrat à terme
        "NOPRICE/USDT": (market("NOPRICE/USDT"), {"high": None, "low": None, "last": None, "quoteVolume": 9e9}),
        "GHOST/USDT": (None, ticker(0.90, 9e9)),  # ticker sans marché connu
    })
    found = scan_volatile(ex, top=5)
    assert [r.symbol for r in found] == ["PEPE/USDT", "SOL/USDT"]
    assert found[0].amplitude == pytest.approx(0.25) and found[0].volume == 30e6
    assert found[0].change == pytest.approx(0.03)


def test_tournament_adds_liquid_memecoins_without_duplicates():
    ex = exchange(**{
        "PEPE/USDT": (market("PEPE/USDT"), ticker(0.25, 30e6)),
        "SUI/USDT": (market("SUI/USDT"), ticker(0.20, 80e6)),
        "SOL/USDT": (market("SOL/USDT"), ticker(0.10, 50e6)),
        "DOGE/USDT": (market("DOGE/USDT"), ticker(0.05, 500e6)),
        "WIF/USDT": (market("WIF/USDT"), ticker(0.02, 20e6)),
        "BONK/USDT": (market("BONK/USDT"), ticker(0.40, 1e6)),  # memecoin trop peu échangé : écarté
    })
    picked = [r.symbol for r in pick_markets(ex, top=2)]
    assert picked == ["PEPE/USDT", "SUI/USDT", "DOGE/USDT", "WIF/USDT"]
    assert ex.ticker_calls == 1  # une seule requête pour tout le marché
    assert [r.symbol for r in pick_markets(ex, top=2, memecoins=False)] == ["PEPE/USDT", "SUI/USDT"]
    assert {"DOGE/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT"} <= set(MEMECOINS)
