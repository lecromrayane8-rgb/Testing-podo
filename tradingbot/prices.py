"""Prix en direct : les vrais prix de plusieurs plateformes côte à côte (données publiques, sans compte).

Chaque plateforme cote ses cryptos dans sa propre monnaie stable : on prend la paire en USDT, sinon en USDC,
sinon en dollars (les trois valent presque exactement un dollar). L'écart entre plateformes montre qu'un même
actif n'a jamais tout à fait le même prix partout ; il est en général bien plus petit que les frais.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import ccxt

from .broker import atomic_write
from .live import px
from .scanner import ScanResult

QUOTES = ("USDT", "USDC", "USD")
DEFAULT_PLATFORMS = ("binance", "okx", "kraken", "coinbaseexchange", "bybit")
NAMES = {"binance": "Binance", "okx": "OKX", "kraken": "Kraken", "coinbaseexchange": "Coinbase", "bybit": "Bybit",
         "bitstamp": "Bitstamp", "cryptocom": "Crypto.com", "bitget": "Bitget", "onetrading": "One Trading"}


def label(platform: str) -> str:
    return NAMES.get(platform, platform)


def resolve(markets: dict, base: str) -> str | None:
    """La paire spot de `base` cotée en USDT, sinon USDC, sinon USD ; None si la plateforme ne l'a pas."""
    for quote in QUOTES:
        market = markets.get(f"{base}/{quote}")
        if market and market.get("spot", True) and market.get("active") is not False:
            return f"{base}/{quote}"
    return None


@dataclass
class Board:
    bases: list[str]
    platforms: list[str]
    prices: dict[tuple[str, str], tuple[float, str]] = field(default_factory=dict)  # (crypto, plateforme)
    changes: dict[str, float] = field(default_factory=dict)  # variation sur 24 h (fraction)
    errors: dict[str, str] = field(default_factory=dict)  # plateforme -> problème rencontré

    def spread(self, base: str) -> float | None:
        """Écart entre la plateforme la plus chère et la moins chère (fraction)."""
        quotes = [price for (b, _), (price, _) in self.prices.items() if b == base and price > 0]
        return max(quotes) / min(quotes) - 1 if len(quotes) >= 2 else None


def connect(platforms: list[str], make) -> tuple[dict[str, ccxt.Exchange], dict[str, str]]:
    """Charge la liste des paires de chaque plateforme ; une plateforme injoignable n'arrête pas les autres."""
    exchanges, errors = {}, {}
    for platform in platforms:
        try:
            ex = make(platform)
            ex.load_markets()
            exchanges[platform] = ex
        except (ccxt.BaseError, ValueError, OSError) as exc:
            errors[platform] = short_error(exc)
    return exchanges, errors


def short_error(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__} : {text[:80]}" if text else type(exc).__name__


def snapshot(exchanges: dict[str, ccxt.Exchange], bases: list[str], errors: dict[str, str] | None = None) -> Board:
    board = Board(bases, list(exchanges) + [p for p in (errors or {}) if p not in exchanges], errors=dict(errors or {}))
    for platform, ex in exchanges.items():
        symbols = {base: s for base in bases if (s := resolve(ex.markets, base))}
        if not symbols:
            continue
        try:
            try:  # une seule requête pour toutes les paires, quand la plateforme le permet
                tickers = ex.fetch_tickers(list(symbols.values()))
            except (ccxt.NotSupported, ccxt.BadRequest, ccxt.ArgumentsRequired):
                tickers = {s: ex.fetch_ticker(s) for s in symbols.values()}
        except ccxt.BaseError as exc:
            board.errors[platform] = short_error(exc)
            continue
        for base, symbol in symbols.items():
            ticker = tickers.get(symbol) or {}
            price = ticker.get("last") or ticker.get("close")
            if price:
                board.prices[(base, platform)] = (float(price), symbol)
                change = ticker.get("percentage")
                if base not in board.changes and change is not None:
                    board.changes[base] = float(change) / 100
    return board


def new_listings(exchange: ccxt.Exchange, path: Path, quote: str = "USDT") -> list[str] | None:
    """Les paires spot apparues depuis la dernière visite (None à la toute première : rien à comparer)."""
    current = sorted(s for s, m in exchange.markets.items()
                     if m.get("spot", True) and m.get("active") is not False and m.get("quote") == quote)
    try:
        known = set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        known = None
    atomic_write(path, json.dumps(current))
    return None if known is None else [s for s in current if s not in known]


def format_board(board: Board, now: datetime, hot: list[ScanResult] | None = None, every: float | None = None,
                 listings: list[str] | None = None) -> str:
    cell = 14
    header = f"{'Crypto':<8}" + "".join(f"{label(p):>{cell}}" for p in board.platforms) + f"{'Écart':>9}{'24 h':>9}"
    lines = [f"PRIX EN DIRECT · {now.strftime('%d/%m/%Y %H:%M:%S')}"
             + (f" · mis à jour toutes les {every:.0f} s (Ctrl+C pour arrêter)" if every else ""), "", header,
             "-" * len(header)]
    for base in board.bases:
        cells = []
        for platform in board.platforms:
            price = board.prices.get((base, platform))
            cells.append(f"{px(price[0]) + ('$' if price[1].endswith('/USD') else ''):>{cell}}" if price else f"{'—':>{cell}}")
        spread, change = board.spread(base), board.changes.get(base)
        lines.append(f"{base:<8}" + "".join(cells) + f"{(f'{100 * spread:.2f} %' if spread is not None else '—'):>9}"
                     + f"{(f'{100 * change:+.1f} %' if change is not None else '—'):>9}")
    lines += ["", "Écart : différence entre la plateforme la plus chère et la moins chère. Prix en USDT, sinon en USDC ;",
              "« $ » = coté en dollars. Un écart de 0,1 % ne couvre même pas les frais d'un aller-retour (environ 0,3 %)."]
    for platform, problem in board.errors.items():
        lines.append(f"{label(platform)} indisponible : {problem}")
    if listings is not None:
        first = label(board.platforms[0])
        lines += ["", f"NOUVELLES COTATIONS sur {first} depuis ta dernière visite : "
                  + (", ".join(listings[:12]) + (" ..." if len(listings) > 12 else "") if listings else "aucune")]
        if listings:
            lines.append("  Une crypto qui vient d'arriver bouge beaucoup, mais sans historique aucune stratégie ne peut "
                         "la juger : à regarder, pas à acheter sur un coup de tête.")
    if hot:
        lines += ["", f"LES PLUS AGITÉES EN CE MOMENT sur {label(board.platforms[0])} (amplitude sur 24 h, volume > 5 M$) :"]
        for r in hot:
            volume = f"{r.volume / 1e6:,.0f} M$".replace(",", " ")
            change = f"{100 * r.change:+.1f} %" if not math.isnan(r.change) else "—"
            lines.append(f"  {r.symbol:<16}amplitude {100 * r.amplitude:5.1f} %   variation {change:>8}   volume {volume}")
    return "\n".join(lines)
