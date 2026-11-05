"""Radar des mouvements : toutes les cryptos d'une plateforme, et celles qui bougent le plus en ce moment.

Une requête complète (toutes les paires, volume compris) toutes les 5 minutes donne la liste des cryptos assez
échangées ; entre deux, une requête légère (le dernier prix seulement) toutes les 10 secondes suffit. Le radar garde
ces relevés un peu plus d'un quart d'heure et calcule, pour chaque crypto, sa variation sur 1, 5 et 15 minutes.

Un mouvement vu ici a déjà eu lieu : c'est une information, pas un ordre d'achat. Le journal des mouvements note
chaque gros mouvement à la hausse, puis ce que le prix a fait 5 minutes, 15 minutes et 1 heure après : jour après
jour, il dit honnêtement, frais compris, ce qu'aurait rapporté le fait de sauter dessus.
"""
from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .scanner import tradable

WINDOWS = (60, 300, 900)  # 1, 5 et 15 minutes, en secondes
STRONG = {60: 0.01, 300: 0.02, 900: 0.04}  # au-delà : « gros mouvement » (affichage seulement, jamais un ordre)
MIN_VOLUME = 5_000_000  # comme le scanner : assez échangée pour être tradée pour de vrai
HORIZONS = (300, 900, 3600)  # ce que le journal mesure après un gros mouvement : 5 min, 15 min, 1 h
QUIET = 900  # une même crypto n'est notée qu'une fois par quart d'heure (une envolée = un seul mouvement)
JOURNAL_FILE = "mouvements.jsonl"


@dataclass(frozen=True)
class Move:
    symbol: str
    last: float
    changes: dict[int, float | None]  # fenêtre (s) -> variation (fraction) ; None tant que le radar se remplit
    change_24h: float | None
    volume_24h: float

    @property
    def strong(self) -> bool:
        return any(c is not None and abs(c) >= STRONG[w] for w, c in self.changes.items())

    @property
    def strong_rise(self) -> int | None:
        """La plus courte fenêtre où la crypto a fait un gros mouvement à la hausse (None : aucune)."""
        return next((w for w in WINDOWS if (c := self.changes.get(w)) is not None and c >= STRONG[w]), None)


class Radar:
    def __init__(self, quote: str = "USDT", min_volume: float = MIN_VOLUME, keep_seconds: float = max(WINDOWS) + 120):
        self.quote, self.min_volume, self.keep_seconds = quote, min_volume, keep_seconds
        self.history: deque[tuple[float, dict[str, float]]] = deque()  # (heure, prix de chaque paire)
        self.info: dict[str, tuple[float, float | None]] = {}  # paire suivie -> (volume 24 h, variation 24 h)

    def update_info(self, markets: dict, tickers: dict) -> None:
        """Requête complète : quelles paires suivre (assez échangées) et leur volume et variation sur 24 h."""
        info = {}
        for symbol, t in tickers.items():
            if not tradable(markets.get(symbol), self.quote):
                continue
            volume = t.get("quoteVolume") or 0
            if volume < self.min_volume or not (t.get("last") or t.get("close")):
                continue
            change = t.get("percentage")
            info[symbol] = (float(volume), float(change) / 100 if change is not None else None)
        self.info = info

    def add_prices(self, prices: dict[str, float | None], now: float) -> int:
        """Ajoute un relevé des derniers prix (seulement les paires suivies) ; renvoie le nombre de cryptos."""
        snapshot = {s: float(p) for s, p in prices.items() if s in self.info and p}
        self.history.append((now, snapshot))
        while self.history and now - self.history[0][0] > self.keep_seconds:
            self.history.popleft()
        return len(snapshot)

    def update(self, markets: dict, tickers: dict, now: float) -> int:
        """Requête complète et relevé d'un coup (les tickers de toutes les paires)."""
        self.update_info(markets, tickers)
        return self.add_prices({s: t.get("last") or t.get("close") for s, t in tickers.items()}, now)

    @property
    def span(self) -> float:
        """Secondes couvertes par les relevés gardés : le radar est « rempli » à 15 minutes."""
        return self.history[-1][0] - self.history[0][0] if len(self.history) > 1 else 0.0

    @property
    def latest(self) -> dict[str, float]:
        return self.history[-1][1] if self.history else {}

    def reference(self, seconds: float) -> dict[str, float] | None:
        """Le relevé le plus récent datant d'au moins `seconds` avant le dernier ; None s'il manque, ou si une
        coupure du réseau l'a laissé bien plus vieux que la fenêtre (la variation ne voudrait plus rien dire)."""
        if not self.history:
            return None
        now = self.history[-1][0]
        for ts, prices in reversed(self.history):
            age = now - ts
            if age >= seconds:
                return prices if age <= 1.5 * seconds + 30 else None
        return None

    def moves(self, window: int = 300, top: int | None = 20, rising_only: bool = False) -> list[Move]:
        """Les cryptos qui bougent le plus sur `window` secondes (hausses et baisses, ou hausses seulement) ;
        `top=None` : toutes. Tant que la fenêtre n'est pas remplie, le classement se fait sur 24 h."""
        if not self.history:
            return []
        refs = {w: self.reference(w) for w in WINDOWS}
        result = []
        for symbol, last in self.latest.items():
            changes = {}
            for w, ref in refs.items():
                before = ref.get(symbol) if ref else None
                changes[w] = last / before - 1 if before else None
            volume, change_24h = self.info.get(symbol, (0.0, None))
            result.append(Move(symbol, last, changes, change_24h, volume))

        def value(m: Move) -> float | None:
            return m.changes.get(window) if refs.get(window) else m.change_24h

        ranked = [m for m in result if value(m) is not None]
        if rising_only:
            ranked = sorted((m for m in ranked if value(m) > 0), key=value, reverse=True)
        else:
            ranked.sort(key=lambda m: abs(value(m)), reverse=True)
        return ranked if top is None else ranked[:top]


@dataclass
class Sighting:
    """Un gros mouvement à la hausse vu par le radar, et ce que le prix a fait ensuite (avant frais)."""
    symbol: str
    t: float  # heure du relevé (secondes depuis 1970)
    window: int
    change: float
    price: float
    after: dict[int, float | None] = field(default_factory=dict)  # horizon (s) -> variation depuis le relevé


class MoveJournal:
    """Le carnet des gros mouvements à la hausse : un test en direct, sans regard vers le futur, de l'idée
    « sauter sur ce qui monte ». Chaque mouvement est jugé 5 min, 15 min et 1 h après, au prix réel."""

    def __init__(self, path: Path | None = None, horizons: tuple[int, ...] = HORIZONS, quiet: float = QUIET):
        self.path, self.horizons, self.quiet = path, horizons, quiet
        self.pending: list[Sighting] = []
        self.last_seen: dict[str, float] = {}

    def observe(self, moves: list[Move], prices: dict[str, float], now: float) -> list[Sighting]:
        """Mesure les mouvements en attente, note les nouveaux ; renvoie (et enregistre) ceux qui sont complets."""
        for s in self.pending:
            for h in self.horizons:
                if h in s.after or now < s.t + h:
                    continue
                price = prices.get(s.symbol)
                # Relevé manqué de beaucoup (réseau coupé, site fermé) : cette mesure ne compte pas.
                late = now - (s.t + h) > max(30.0, 0.1 * h)
                s.after[h] = None if late or not price else price / s.price - 1
        done = [s for s in self.pending if len(s.after) == len(self.horizons)]
        self.pending = [s for s in self.pending if len(s.after) < len(self.horizons)]
        for m in moves:
            window = m.strong_rise
            if window is None or now - self.last_seen.get(m.symbol, -math.inf) < self.quiet:
                continue
            self.last_seen[m.symbol] = now
            self.pending.append(Sighting(m.symbol, now, window, float(m.changes[window]), m.last))
        if done and self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                for s in done:
                    f.write(json.dumps(record(s), ensure_ascii=False) + "\n")
        return done

    def records(self) -> list[dict]:
        if not self.path or not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:  # ligne coupée par un arrêt brutal : ignorée
                continue
        return out


def record(s: Sighting) -> dict:
    data = asdict(s)
    data["t"] = datetime.fromtimestamp(s.t, timezone.utc).isoformat(timespec="seconds")
    data["after"] = {str(h): v for h, v in s.after.items()}
    return data


def journal_stats(records: list[dict], cost: float, horizons: tuple[int, ...] = HORIZONS) -> list[dict]:
    """Par fenêtre de mouvement : combien, et ce qu'acheter juste après aurait donné à chaque horizon, frais
    compris (`cost` = un aller-retour, environ 0,003)."""
    rows = []
    for window in WINDOWS:
        group = [r for r in records if r.get("window") == window]
        cells = {}
        for h in horizons:
            values = np.array([v for r in group if (v := (r.get("after") or {}).get(str(h))) is not None]) - cost
            cells[str(h)] = None if not len(values) else {
                "n": int(len(values)), "mean": float(values.mean()), "median": float(np.median(values)),
                "winners": float((values > 0).mean()), "worst": float(np.percentile(values, 10)),
            }
        rows.append({"window": window, "threshold": STRONG[window], "count": len(group), "after": cells})
    return rows
