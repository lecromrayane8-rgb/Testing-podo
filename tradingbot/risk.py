"""Gestion du risque : taille de position et garde-fous (perte journalière, drawdown max, élimination)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from statistics import NormalDist

Z_95 = 1.96
CANDIDATE_MIN_TRADES = 30


# --- Une fourchette honnête quand les trades se ressemblent -------------------------------------------------------

def _beta_fraction(a: float, b: float, x: float) -> float:
    """Fraction continue de la fonction bêta incomplète (méthode de Lentz)."""
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + num * d
            c = 1.0 + num / c
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-14:
            break
    return h


def _beta_inc(a: float, b: float, x: float) -> float:
    """Fonction bêta incomplète régularisée I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def student_tail(t: float, df: float) -> float:
    """P(T > t) pour une loi de Student à `df` degrés de liberté (t >= 0)."""
    return 0.5 * _beta_inc(df / 2.0, 0.5, df / (df + t * t))


@lru_cache(maxsize=4096)
def student_t(alpha: float, df: int) -> float:
    """Le seuil t tel que P(T > t) = alpha. Avec peu de groupes (peu de jours), il est bien plus grand que le 1,96 de
    la loi normale : c'est ce qui rend la fourchette prudente tant qu'on a peu de journées."""
    if not 0.0 < alpha <= 0.5 or df < 1:
        raise ValueError("alpha doit être entre 0 et 0,5, et df >= 1")
    lo, hi = 0.0, 2.0
    while student_tail(hi, df) > alpha:
        lo, hi = hi, hi * 2.0
        if hi > 1e15:
            return math.inf
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if student_tail(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-12 * max(1.0, hi):
            break
    return (lo + hi) / 2.0


def clustered_bounds(groups, alpha: float = 0.025) -> tuple[float, float, float]:
    """La moyenne par trade et sa fourchette quand les trades d'un même groupe (une journée) se ressemblent.

    Quarante bots qui gagnent pendant la même chute du marché ne font pas quarante preuves : on compare donc les
    groupes entre eux, au lieu de compter chaque trade à part. `groups` : (nombre de trades, somme des rendements)
    de chaque groupe. Rend (moyenne, bas, haut) ; pas de fourchette avec moins de deux groupes."""
    groups = [(int(n), float(total)) for n, total in groups if n > 0]
    count = sum(n for n, _ in groups)
    if not count:
        return math.nan, math.nan, math.nan
    mean = sum(total for _, total in groups) / count
    g = len(groups)
    if g < 2:
        return mean, math.nan, math.nan
    spread = sum((total - mean * n) ** 2 for n, total in groups)
    half = student_t(alpha, g - 1) * math.sqrt(g / (g - 1) * spread) / count
    return mean, mean - half, mean + half


def paired_bounds(groups, alpha: float = 0.025) -> tuple[float, float, float]:
    """L'écart entre deux façons de trader mesurées sur les mêmes groupes (les mêmes journées, les mêmes cryptos).

    `groups` : pour chaque groupe, (trades de A, somme des rendements de A, trades de B, somme de B). Rend (écart, bas,
    haut) pour « moyenne par trade de A − moyenne par trade de B ». Les deux mesures ont vécu les mêmes marchés : une
    bonne journée l'est pour les deux. La fourchette vient donc de ce que l'écart varie d'un groupe à l'autre, pas de
    la dispersion de chaque mesure (qui exagérerait le doute). Pas de fourchette avec moins de deux groupes."""
    groups = [(int(na), float(ta), int(nb), float(tb)) for na, ta, nb, tb in groups if na > 0 or nb > 0]
    count_a, count_b = sum(g[0] for g in groups), sum(g[2] for g in groups)
    if not count_a or not count_b:
        return math.nan, math.nan, math.nan
    mean_a, mean_b = sum(g[1] for g in groups) / count_a, sum(g[3] for g in groups) / count_b
    diff = mean_a - mean_b
    g = len(groups)
    if g < 2:
        return diff, math.nan, math.nan
    spread = sum(((ta - mean_a * na) / count_a - (tb - mean_b * nb) / count_b) ** 2 for na, ta, nb, tb in groups)
    half = student_t(alpha, g - 1) * math.sqrt(g / (g - 1) * spread)
    return diff, diff - half, diff + half


@dataclass(frozen=True)
class RiskParams:
    risk_per_trade: float = 0.01  # fraction du capital perdue si le stop est touché
    max_position_pct: float = 0.95  # exposition max (spot, sans levier)
    daily_loss_limit: float = 0.03  # plus de nouvelle entrée ce jour-là au-delà
    max_drawdown: float = 0.15  # arrêt des entrées jusqu'à réarmement manuel
    eliminate_after_trades: int = 20  # élimine une stratégie qui perd nettement après N trades (0 = jamais)


@dataclass
class TradeStats:
    """Statistiques incrémentales des rendements par trade (en fraction : 0.01 = +1 %)."""

    n: int = 0
    total: float = 0.0
    total_sq: float = 0.0

    def add(self, ret: float) -> None:
        self.n += 1
        self.total += ret
        self.total_sq += ret * ret

    @property
    def mean(self) -> float:
        return self.total / self.n if self.n else math.nan

    def bounds(self, z: float = Z_95) -> tuple[float, float]:
        """Fourchette de l'espérance par trade (approximation normale)."""
        if self.n < 2:
            return math.nan, math.nan
        var = max(self.total_sq - self.n * self.mean ** 2, 0.0) / (self.n - 1)
        half = z * math.sqrt(var / self.n)
        return self.mean - half, self.mean + half

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "TradeStats":
        return cls(**(data or {}))


def elimination_reason(stats: TradeStats, min_trades: int) -> str | None:
    """Une stratégie est éliminée quand, après assez de trades, même le haut de sa fourchette est négatif."""
    if not min_trades or stats.n < min_trades:
        return None
    if stats.bounds()[1] < 0:
        pct = f"{100 * stats.mean:+.2f}".replace(".", ",")
        return f"perd nettement après {stats.n} trades ({pct} % par trade)"
    return None


def is_candidate(stats: TradeStats, n_tests: int = 1) -> bool:
    """Gagnante de façon nette sur assez de trades : candidate au testnet (jamais à l'argent réel seule).

    `n_tests` : nombre de bots (ou de stratégies) comparés. Parmi 80 bots sans aucun avantage, environ 2
    passeraient le seuil à 95 % par chance : le seuil est durci d'autant (correction de Bonferroni)."""
    if stats.n < CANDIDATE_MIN_TRADES:
        return False
    z = NormalDist().inv_cdf(1 - 0.025 / max(n_tests, 1))
    return stats.bounds(z)[0] > 0


def position_size(equity: float, entry_price: float, stop_price: float, p: RiskParams) -> float:
    """Quantité telle que toucher le stop coûte `risk_per_trade` du capital."""
    risk_per_unit = entry_price - stop_price
    if equity <= 0 or entry_price <= 0 or risk_per_unit <= 0:
        return 0.0
    qty = equity * p.risk_per_trade / risk_per_unit
    max_qty = equity * p.max_position_pct / entry_price
    return min(qty, max_qty)


class RiskGuard:
    def __init__(
        self,
        params: RiskParams,
        peak_equity: float | None = None,
        day: str | None = None,
        day_start_equity: float | None = None,
        last_equity: float | None = None,
        halted: str | None = None,
    ):
        self.params = params
        self.peak_equity = peak_equity
        self.day = day
        self.day_start_equity = day_start_equity
        self.last_equity = last_equity
        self.halted = halted

    def update(self, equity: float, day: str) -> None:
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity
        if day != self.day:
            self.day = day
            self.day_start_equity = equity
        self.last_equity = equity
        if not self.halted and equity <= self.peak_equity * (1 - self.params.max_drawdown):
            self.halted = (
                f"drawdown max atteint ({equity:.2f} <= {self.peak_equity:.2f} "
                f"- {self.params.max_drawdown:.0%})"
            )

    def blocked_reason(self) -> str | None:
        if self.halted:
            return self.halted
        if (
            self.day_start_equity
            and self.last_equity is not None
            and self.last_equity <= self.day_start_equity * (1 - self.params.daily_loss_limit)
        ):
            return f"limite de perte journalière atteinte ({self.params.daily_loss_limit:.0%})"
        return None

    def can_open(self) -> bool:
        return self.blocked_reason() is None

    def to_dict(self) -> dict:
        return {
            "peak_equity": self.peak_equity,
            "day": self.day,
            "day_start_equity": self.day_start_equity,
            "last_equity": self.last_equity,
            "halted": self.halted,
        }

    @classmethod
    def from_dict(cls, params: RiskParams, data: dict | None) -> "RiskGuard":
        return cls(params, **(data or {}))
