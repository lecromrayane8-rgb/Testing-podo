"""Connexion à la plateforme d'échange (via ccxt) et broker simulé pour le paper trading."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import ccxt
import pandas as pd

from .data import ohlcv_to_frame

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Balances:
    base: float  # ex. BTC disponible
    quote: float  # ex. USDT disponible


@dataclass(frozen=True)
class Fill:
    qty: float  # quantité de base reçue (achat, nette de frais) ou vendue (vente)
    price: float  # prix moyen d'exécution
    quote: float  # devise de cotation dépensée (achat, frais inclus) ou reçue (vente, nette de frais)


class CcxtBroker:
    """Ordres au marché sur une plateforme ccxt : `venue` = "testnet", "demo" ou "real"."""

    def __init__(
        self,
        exchange_id: str,
        symbol: str,
        api_key: str = "",
        secret: str = "",
        password: str = "",
        venue: str = "real",
    ):
        klass = getattr(ccxt, exchange_id, None)
        if klass is None:
            raise ValueError(f"Plateforme inconnue de ccxt : {exchange_id}")
        config: dict = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
        if api_key:
            config.update(apiKey=api_key, secret=secret)
        if password:
            config["password"] = password
        self.ex: ccxt.Exchange = klass(config)
        if venue == "testnet":
            self.ex.set_sandbox_mode(True)
        elif venue == "demo":
            if not hasattr(self.ex, "enable_demo_trading"):
                raise ValueError(f"{exchange_id} ne propose pas de mode demo dans ccxt, utilise MODE=testnet")
            self.ex.enable_demo_trading(True)
        self.ex.load_markets()
        if symbol not in self.ex.markets:
            raise ValueError(f"Paire {symbol} introuvable sur {exchange_id} ({venue})")
        self.symbol = symbol
        self.market = self.ex.market(symbol)
        self.base, self.quote = self.market["base"], self.market["quote"]

    def fetch_candles(self, timeframe: str, limit: int) -> pd.DataFrame:
        return ohlcv_to_frame(self.ex.fetch_ohlcv(self.symbol, timeframe, limit=limit))

    def last_price(self) -> float:
        ticker = self.ex.fetch_ticker(self.symbol)
        return float(ticker["last"] or ticker["close"])

    def balances(self) -> Balances:
        free = self.ex.fetch_balance()["free"]
        return Balances(float(free.get(self.base) or 0), float(free.get(self.quote) or 0))

    def normalize_qty(self, qty: float, price: float) -> float:
        """Arrondit à la précision de la plateforme ; 0 si sous les minimums (quantité / notionnel)."""
        try:
            q = float(self.ex.amount_to_precision(self.symbol, qty))
        except ccxt.BaseError:
            return 0.0
        limits = self.market.get("limits") or {}
        min_amount = (limits.get("amount") or {}).get("min") or 0
        min_cost = (limits.get("cost") or {}).get("min") or 0
        if q <= 0 or q < min_amount or q * price < min_cost:
            return 0.0
        return q

    def market_buy(self, qty: float) -> Fill:
        order = self._wait_filled(self.ex.create_order(self.symbol, "market", "buy", qty))
        filled, cost = self._filled_and_cost(order)
        fees = self._fees(order)
        return Fill(filled - fees.get(self.base, 0.0), cost / filled, cost + fees.get(self.quote, 0.0))

    def market_sell(self, qty: float) -> Fill:
        order = self._wait_filled(self.ex.create_order(self.symbol, "market", "sell", qty))
        filled, cost = self._filled_and_cost(order)
        fees = self._fees(order)
        return Fill(filled, cost / filled, cost - fees.get(self.quote, 0.0))

    def _wait_filled(self, order: dict, attempts: int = 10) -> dict:
        """Certaines plateformes renvoient l'ordre au marché avant son exécution complète."""
        for _ in range(attempts):
            if order.get("filled") and order.get("status") in ("closed", None):
                return order
            if not self.ex.has.get("fetchOrder"):
                return order
            time.sleep(1)
            order = self.ex.fetch_order(order["id"], self.symbol)
        return order

    @staticmethod
    def _filled_and_cost(order: dict) -> tuple[float, float]:
        filled = float(order.get("filled") or 0)
        if filled <= 0:
            raise RuntimeError(f"Ordre non exécuté : {order.get('id')} statut={order.get('status')}")
        cost = order.get("cost") or filled * float(order.get("average") or order.get("price"))
        return filled, float(cost)

    @staticmethod
    def _fees(order: dict) -> dict[str, float]:
        fees = order.get("fees") or ([order["fee"]] if order.get("fee") else [])
        totals: dict[str, float] = {}
        for fee in fees:
            if fee and fee.get("cost"):
                totals[fee["currency"]] = totals.get(fee["currency"], 0.0) + float(fee["cost"])
        return totals


class PaperBroker:
    """Prix réels (données publiques), ordres simulés localement. Aucune clé API nécessaire."""

    def __init__(self, data_broker: CcxtBroker, wallet_path: Path, start_balance: float, fee_rate: float, slippage: float):
        self.data = data_broker
        self.wallet_path = wallet_path
        self.fee_rate = fee_rate
        self.slippage = slippage
        if wallet_path.exists():
            self.wallet = json.loads(wallet_path.read_text())
        else:
            self.wallet = {"base": 0.0, "quote": float(start_balance)}
            self._save()

    def fetch_candles(self, timeframe: str, limit: int) -> pd.DataFrame:
        return self.data.fetch_candles(timeframe, limit)

    def last_price(self) -> float:
        return self.data.last_price()

    def normalize_qty(self, qty: float, price: float) -> float:
        return self.data.normalize_qty(qty, price)

    def balances(self) -> Balances:
        return Balances(self.wallet["base"], self.wallet["quote"])

    def market_buy(self, qty: float) -> Fill:
        price = self.last_price() * (1 + self.slippage)
        spent = qty * price * (1 + self.fee_rate)
        if spent > self.wallet["quote"] + 1e-9:
            raise ccxt.InsufficientFunds(f"paper : {spent:.2f} requis, {self.wallet['quote']:.2f} disponible")
        self.wallet["quote"] -= spent
        self.wallet["base"] += qty
        self._save()
        return Fill(qty, price, spent)

    def market_sell(self, qty: float) -> Fill:
        if qty > self.wallet["base"] + 1e-12:
            raise ccxt.InsufficientFunds(f"paper : {qty} requis, {self.wallet['base']} disponible")
        price = self.last_price() * (1 - self.slippage)
        received = qty * price * (1 - self.fee_rate)
        self.wallet["base"] -= qty
        self.wallet["quote"] += received
        self._save()
        return Fill(qty, price, received)

    def _save(self) -> None:
        atomic_write(self.wallet_path, json.dumps(self.wallet, indent=2))


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
