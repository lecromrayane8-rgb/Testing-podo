"""Gestion du risque : taille de position et garde-fous (perte journalière, drawdown max, élimination)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

Z_95 = 1.96
CANDIDATE_MIN_TRADES = 30


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


def is_candidate(stats: TradeStats) -> bool:
    """Gagnante de façon nette sur assez de trades : candidate au testnet (jamais à l'argent réel seule)."""
    return stats.n >= CANDIDATE_MIN_TRADES and stats.bounds()[0] > 0


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
