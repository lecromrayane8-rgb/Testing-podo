"""Paramètres d'exécution des ordres : au marché, ou à cours limité « post-only » (frais maker)."""
from __future__ import annotations

from dataclasses import dataclass

ORDER_TYPES = ("market", "limit")
ENTRY_FALLBACKS = ("skip", "market")


@dataclass(frozen=True)
class ExecutionParams:
    order_type: str = "market"
    fee_rate: float = 0.001  # frais taker (ordre au marché)
    maker_fee_rate: float = 0.001  # frais maker (ordre limite exécuté sans croiser le carnet)
    slippage: float = 0.0005  # glissement estimé des ordres au marché
    limit_timeout_bars: int = 1  # durée de vie d'un ordre limite, en bougies
    limit_entry_fallback: str = "skip"  # achat limite non exécuté : "skip" (abandon) ou "market"

    def __post_init__(self):
        if self.order_type not in ORDER_TYPES:
            raise ValueError(f"ORDER_TYPE doit valoir {' ou '.join(ORDER_TYPES)} (reçu : {self.order_type!r})")
        if self.limit_entry_fallback not in ENTRY_FALLBACKS:
            raise ValueError(
                f"LIMIT_ENTRY_FALLBACK doit valoir {' ou '.join(ENTRY_FALLBACKS)} (reçu : {self.limit_entry_fallback!r})"
            )
        if self.limit_timeout_bars < 1:
            raise ValueError("LIMIT_TIMEOUT_BARS doit être >= 1")
        if self.fee_rate < 0 or self.maker_fee_rate < 0 or self.slippage < 0:
            raise ValueError("FEE_RATE, MAKER_FEE_RATE et SLIPPAGE doivent être positifs")
