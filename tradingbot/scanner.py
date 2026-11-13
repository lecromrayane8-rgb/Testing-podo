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
    "U", "RLUSD", "XUSD", "RWUSD", "USDS",  # ajoutées le 13/11/2026 : restées à 1,00 $ à 2 % près sur 15 jours
}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
# Actions et fonds en jetons de Binance (NVDAB, GOOGLB, SOXLB… : 105 paires le 13/11/2026). Ce ne sont pas des cryptos :
# presque pas d'échanges la nuit et le week-end, donc des prix affichés auxquels on ne peut pas vraiment traiter.
# Binance ne les étiquette pas. Deux indices réunis les désignent toutes sans toucher une seule crypto (vérifié sur
# les 518 paires USDT ouvertes) : le nom finit par « B », et la paire n'est pas ouverte au groupe d'échange
# « TRD_GRP_016 » (les cryptos ARB, BNB, SHIB… le sont). Sur une autre plateforme (pas de groupes) : rien n'est écarté.
STOCK_TOKEN_SUFFIX, STOCK_TOKEN_CLOSED_GROUP = "B", "TRD_GRP_016"
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


def by_volume(exchange: ccxt.Exchange, quote: str = "USDT", top: int = 30,
              min_volume: float = 5_000_000) -> list[ScanResult]:
    """Les `top` paires spot les plus échangées sur 24 h (sans monnaies stables, tokens à levier ni actions en jetons)."""
    return sorted(liquid_markets(exchange, quote, min_volume), key=lambda r: r.volume, reverse=True)[:top]


def tokenized_stock(market: dict) -> bool:
    """Une action ou un fonds en jeton de Binance (voir STOCK_TOKEN_SUFFIX) : pas une crypto."""
    groups = (market.get("info") or {}).get("permissionSets")
    if not groups or not str(market.get("base", "")).endswith(STOCK_TOKEN_SUFFIX):
        return False
    return not any(STOCK_TOKEN_CLOSED_GROUP in group for group in groups)


def tradable(market: dict | None, quote: str) -> bool:
    """Une paire spot ouverte, cotée dans `quote`, qui n'est ni une monnaie stable, ni un token à levier, ni une
    action en jeton."""
    if not market or not market.get("spot") or market.get("active") is False or market.get("quote") != quote:
        return False
    base = market.get("base", "")
    return base not in STABLE_OR_PEGGED and not base.endswith(LEVERAGED_SUFFIXES) and not tokenized_stock(market)


def liquid_markets(exchange: ccxt.Exchange, quote: str, min_volume: float) -> list[ScanResult]:
    """Toutes les paires spot assez échangées, de la plus agitée à la plus calme (une seule requête)."""
    if not exchange.markets:
        exchange.load_markets()
    results = []
    for symbol, t in exchange.fetch_tickers().items():
        if not tradable(exchange.markets.get(symbol), quote):
            continue
        high, low, last = t.get("high"), t.get("low"), t.get("last")
        volume = t.get("quoteVolume") or 0
        if not (high and low and last) or volume < min_volume:
            continue
        results.append(ScanResult(symbol, (high - low) / last, float(volume), float(t.get("percentage") or 0) / 100))
    return sorted(results, key=lambda r: r.amplitude, reverse=True)
