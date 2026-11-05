"""Radar des mouvements : toutes les cryptos d'une plateforme, et celles qui bougent le plus en ce moment.

Une seule requête donne le dernier prix de toutes les paires. Le radar garde ces relevés un peu plus d'un quart
d'heure et calcule, pour chaque crypto assez échangée, sa variation sur 1, 5 et 15 minutes. Un mouvement vu ici
a déjà eu lieu : c'est une information, pas un ordre d'achat. Les stratégies « impulsion » du labo testent
justement s'il est rentable de sauter dessus, frais compris.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .scanner import tradable

WINDOWS = (60, 300, 900)  # 1, 5 et 15 minutes, en secondes
STRONG = {60: 0.01, 300: 0.02, 900: 0.04}  # au-delà : « gros mouvement » (affichage seulement, jamais un ordre)
MIN_VOLUME = 5_000_000  # comme le scanner : assez échangée pour être tradée pour de vrai


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


class Radar:
    def __init__(self, quote: str = "USDT", min_volume: float = MIN_VOLUME, keep_seconds: float = max(WINDOWS) + 120):
        self.quote, self.min_volume, self.keep_seconds = quote, min_volume, keep_seconds
        self.history: deque[tuple[float, dict[str, float]]] = deque()  # (heure, prix de chaque paire)
        self.info: dict[str, tuple[float, float | None]] = {}  # paire -> (volume 24 h, variation 24 h)

    def update(self, markets: dict, tickers: dict, now: float) -> int:
        """Ajoute un relevé (les tickers de toutes les paires) ; renvoie le nombre de cryptos suivies."""
        prices, info = {}, {}
        for symbol, t in tickers.items():
            if not tradable(markets.get(symbol), self.quote):
                continue
            last, volume = t.get("last") or t.get("close"), t.get("quoteVolume") or 0
            if not last or volume < self.min_volume:
                continue
            prices[symbol] = float(last)
            change = t.get("percentage")
            info[symbol] = (float(volume), float(change) / 100 if change is not None else None)
        self.history.append((now, prices))
        self.info = info
        while self.history and now - self.history[0][0] > self.keep_seconds:
            self.history.popleft()
        return len(prices)

    @property
    def span(self) -> float:
        """Secondes couvertes par les relevés gardés : le radar est « rempli » à 15 minutes."""
        return self.history[-1][0] - self.history[0][0] if len(self.history) > 1 else 0.0

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

    def moves(self, window: int = 300, top: int = 20, rising_only: bool = False) -> list[Move]:
        """Les cryptos qui bougent le plus sur `window` secondes (hausses et baisses, ou hausses seulement).
        Tant que la fenêtre n'est pas remplie, le classement se fait sur la variation sur 24 h."""
        if not self.history:
            return []
        latest = self.history[-1][1]
        refs = {w: self.reference(w) for w in WINDOWS}
        result = []
        for symbol, last in latest.items():
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
        return ranked[:top]
