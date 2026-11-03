"""Scanner : repère les cryptos les plus agitées parmi celles assez échangées pour être tradées pour de vrai.

Une forte amplitude seule ne suffit pas : sur une crypto peu échangée, le prix affiché n'est pas celui
auquel on peut revendre (personne en face). Le volume minimum garde des résultats réalistes.
"""
from __future__ import annotations

from dataclasses import dataclass

import ccxt

# Monnaies stables ou adossées à un actif peu volatil : pas d'intérêt pour un scanner de volatilité.
STABLE_OR_PEGGED = {
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "BUSD", "USDP", "USDD", "USDE", "USD1", "PYUSD", "EUR", "EURI",
    "AEUR", "GBP", "TRY", "BRL", "PAXG", "XAUT", "WBTC", "WBETH", "BFUSD",
}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
# Memecoins cotés sur Binance spot : gardés seulement s'ils sont assez échangés (pas de memecoins de lancement).
MEMECOINS = ("DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "FLOKI/USDT", "BONK/USDT", "WIF/USDT")


@dataclass(frozen=True)
class ScanResult:
    symbol: str
    amplitude: float  # (plus haut - plus bas) / dernier prix, sur 24 h
    volume: float  # volume échangé sur 24 h, en devise de cotation
    change: float  # variation sur 24 h (fraction)


def scan_volatile(
    exchange: ccxt.Exchange, quote: str = "USDT", top: int = 8, min_volume: float = 5_000_000
) -> list[ScanResult]:
    """Les `top` paires spot les plus agitées sur 24 h, avec au moins `min_volume` échangés."""
    return liquid_markets(exchange, quote, min_volume)[:top]


def pick_markets(
    exchange: ccxt.Exchange, top: int = 8, memecoins: bool = True, min_volume: float = 5_000_000
) -> list[ScanResult]:
    """Cryptos du tournoi : les `top` plus agitées du moment, plus les memecoins assez échangés."""
    liquid = liquid_markets(exchange, "USDT", min_volume)
    chosen = liquid[:top]
    if memecoins:
        chosen += [r for r in liquid if r.symbol in MEMECOINS and r not in chosen]
    return chosen


def liquid_markets(exchange: ccxt.Exchange, quote: str, min_volume: float) -> list[ScanResult]:
    """Toutes les paires spot assez échangées, de la plus agitée à la plus calme (une seule requête)."""
    if not exchange.markets:
        exchange.load_markets()
    results = []
    for symbol, t in exchange.fetch_tickers().items():
        market = exchange.markets.get(symbol)
        if not market or not market.get("spot") or market.get("active") is False or market.get("quote") != quote:
            continue
        base = market.get("base", "")
        if base in STABLE_OR_PEGGED or base.endswith(LEVERAGED_SUFFIXES):
            continue
        high, low, last = t.get("high"), t.get("low"), t.get("last")
        volume = t.get("quoteVolume") or 0
        if not (high and low and last) or volume < min_volume:
            continue
        results.append(ScanResult(symbol, (high - low) / last, float(volume), float(t.get("percentage") or 0) / 100))
    return sorted(results, key=lambda r: r.amplitude, reverse=True)
