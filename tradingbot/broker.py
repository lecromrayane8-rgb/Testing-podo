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
from .execution import ExecutionParams

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


@dataclass(frozen=True)
class OrderStatus:
    open: bool  # encore actif dans le carnet d'ordres
    filled: float  # quantité brute exécutée
    fill: Fill | None  # None si rien n'a été exécuté


def combine_fills(a: Fill | None, b: Fill | None) -> Fill | None:
    if a is None or b is None:
        return a or b
    qty = a.qty + b.qty
    return Fill(qty, (a.qty * a.price + b.qty * b.price) / qty, a.quote + b.quote)


class CcxtBroker:
    """Ordres sur une plateforme ccxt : `venue` = "testnet", "demo" ou "real"."""

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

    # --- données de marché -----------------------------------------------------
    def fetch_candles(self, timeframe: str, limit: int) -> pd.DataFrame:
        return ohlcv_to_frame(self.ex.fetch_ohlcv(self.symbol, timeframe, limit=limit))

    def last_price(self) -> float:
        ticker = self.ex.fetch_ticker(self.symbol)
        return float(ticker["last"] or ticker["close"])

    def best_bid_ask(self) -> tuple[float, float]:
        book = self.ex.fetch_order_book(self.symbol, limit=5)
        return float(book["bids"][0][0]), float(book["asks"][0][0])

    def balances(self) -> Balances:
        free = self.ex.fetch_balance()["free"]
        return Balances(float(free.get(self.base) or 0), float(free.get(self.quote) or 0))

    def trading_fees(self) -> tuple[float, float] | None:
        """Frais (maker, taker) réels du compte, si la plateforme les fournit."""
        if not self.ex.apiKey or not self.ex.has.get("fetchTradingFee"):
            return None
        try:
            fee = self.ex.fetch_trading_fee(self.symbol)
        except ccxt.BaseError as exc:
            log.warning("Frais du compte indisponibles : %s", exc)
            return None
        return float(fee["maker"]), float(fee["taker"])

    def price_to_precision(self, price: float) -> float:
        return float(self.ex.price_to_precision(self.symbol, price))

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

    # --- ordres au marché ------------------------------------------------------
    def market_buy(self, qty: float) -> Fill:
        return self._to_fill(self._wait_filled(self.ex.create_order(self.symbol, "market", "buy", qty)))

    def market_sell(self, qty: float) -> Fill:
        return self._to_fill(self._wait_filled(self.ex.create_order(self.symbol, "market", "sell", qty)))

    # --- ordres limites post-only (toujours maker, rejetés s'ils croiseraient le carnet) -------
    def place_limit(self, side: str, qty: float, price: float) -> tuple[str, float]:
        price = self.price_to_precision(price)
        order = self.ex.create_order(self.symbol, "limit", side, qty, price, {"postOnly": True})
        return order["id"], price

    def order_status(self, order_id: str) -> OrderStatus:
        order = self.ex.fetch_order(order_id, self.symbol)
        filled = float(order.get("filled") or 0)
        return OrderStatus(order.get("status") == "open", filled, self._to_fill(order) if filled > 0 else None)

    def cancel(self, order_id: str) -> OrderStatus:
        try:
            self.ex.cancel_order(order_id, self.symbol)
        except ccxt.OrderNotFound:
            pass  # déjà exécuté ou déjà annulé
        return self.order_status(order_id)

    # --- utilitaires -------------------------------------------------------------
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

    def _to_fill(self, order: dict) -> Fill:
        filled = float(order.get("filled") or 0)
        if filled <= 0:
            raise RuntimeError(f"Ordre non exécuté : {order.get('id')} statut={order.get('status')}")
        cost = float(order.get("cost") or filled * float(order.get("average") or order.get("price")))
        fees = self._fees(order)
        if not fees:
            # Certaines plateformes (dont Binance via fetch_order) n'indiquent pas les frais : on les estime.
            rate = self.market.get("maker" if order.get("type") == "limit" else "taker") or 0.0
            fees = {self.quote: cost * float(rate)}
        if order["side"] == "buy":
            return Fill(filled - fees.get(self.base, 0.0), cost / filled, cost + fees.get(self.quote, 0.0))
        return Fill(filled, cost / filled, cost - fees.get(self.quote, 0.0))

    @staticmethod
    def _fees(order: dict) -> dict[str, float]:
        fees = order.get("fees") or ([order["fee"]] if order.get("fee") else [])
        totals: dict[str, float] = {}
        for fee in fees:
            if fee and fee.get("cost"):
                totals[fee["currency"]] = totals.get(fee["currency"], 0.0) + float(fee["cost"])
        return totals


class PaperBroker:
    """Prix réels (données publiques), ordres simulés localement. Aucune clé API nécessaire.

    Un ordre limite simulé n'est exécuté que si le prix passe strictement au-delà de sa limite
    (hypothèse prudente : être au même prix ne garantit pas d'être servi dans la file d'attente).
    """

    def __init__(self, data_broker: CcxtBroker, wallet_path: Path, start_balance: float, execution: ExecutionParams):
        self.data = data_broker
        self.wallet_path = wallet_path
        self.execution = execution
        if wallet_path.exists():
            self.wallet = json.loads(wallet_path.read_text())
        else:
            self.wallet = {"base": 0.0, "quote": float(start_balance)}
        self.wallet.setdefault("orders", {})
        self.wallet.setdefault("next_id", 1)
        self._save()

    def fetch_candles(self, timeframe: str, limit: int) -> pd.DataFrame:
        return self.data.fetch_candles(timeframe, limit)

    def last_price(self) -> float:
        return self.data.last_price()

    def best_bid_ask(self) -> tuple[float, float]:
        return self.data.best_bid_ask()

    def normalize_qty(self, qty: float, price: float) -> float:
        return self.data.normalize_qty(qty, price)

    def balances(self) -> Balances:
        return Balances(self.wallet["base"], self.wallet["quote"])

    def trading_fees(self) -> tuple[float, float]:
        return self.execution.maker_fee_rate, self.execution.fee_rate

    def market_buy(self, qty: float) -> Fill:
        price = self.last_price() * (1 + self.execution.slippage)
        spent = qty * price * (1 + self.execution.fee_rate)
        if spent > self.wallet["quote"] + 1e-9:
            raise ccxt.InsufficientFunds(f"paper : {spent:.2f} requis, {self.wallet['quote']:.2f} disponible")
        self.wallet["quote"] -= spent
        self.wallet["base"] += qty
        self._save()
        return Fill(qty, price, spent)

    def market_sell(self, qty: float) -> Fill:
        if qty > self.wallet["base"] + 1e-12:
            raise ccxt.InsufficientFunds(f"paper : {qty} requis, {self.wallet['base']} disponible")
        price = self.last_price() * (1 - self.execution.slippage)
        received = qty * price * (1 - self.execution.fee_rate)
        self.wallet["base"] -= qty
        self.wallet["quote"] += received
        self._save()
        return Fill(qty, price, received)

    def place_limit(self, side: str, qty: float, price: float) -> tuple[str, float]:
        price = self.data.price_to_precision(price)
        bid, ask = self.best_bid_ask()
        if (side == "buy" and price >= ask) or (side == "sell" and price <= bid):
            raise ccxt.OrderImmediatelyFillable(f"paper : un ordre {side} à {price} serait exécuté au marché")
        if side == "buy":
            locked = qty * price * (1 + self.execution.maker_fee_rate)
            if locked > self.wallet["quote"] + 1e-9:
                raise ccxt.InsufficientFunds(f"paper : {locked:.2f} requis, {self.wallet['quote']:.2f} disponible")
            self.wallet["quote"] -= locked
        else:
            if qty > self.wallet["base"] + 1e-12:
                raise ccxt.InsufficientFunds(f"paper : {qty} requis, {self.wallet['base']} disponible")
            self.wallet["base"] -= qty
        order_id = f"paper-{self.wallet['next_id']}"
        self.wallet["next_id"] += 1
        self.wallet["orders"][order_id] = {"side": side, "qty": qty, "price": price, "status": "open"}
        self._save()
        return order_id, price

    def order_status(self, order_id: str) -> OrderStatus:
        order = self.wallet["orders"][order_id]
        if order["status"] == "open":
            last = self.last_price()
            if (order["side"] == "buy" and last < order["price"]) or (order["side"] == "sell" and last > order["price"]):
                self._fill_limit(order)
        return self._status(order)

    def cancel(self, order_id: str) -> OrderStatus:
        status = self.order_status(order_id)
        order = self.wallet["orders"][order_id]
        if order["status"] == "open":
            if order["side"] == "buy":
                self.wallet["quote"] += order["qty"] * order["price"] * (1 + self.execution.maker_fee_rate)
            else:
                self.wallet["base"] += order["qty"]
            order["status"] = "canceled"
            self._save()
            status = self._status(order)
        return status

    def _fill_limit(self, order: dict) -> None:
        if order["side"] == "buy":
            self.wallet["base"] += order["qty"]
        else:
            self.wallet["quote"] += order["qty"] * order["price"] * (1 - self.execution.maker_fee_rate)
        order["status"] = "closed"
        self._save()

    def _status(self, order: dict) -> OrderStatus:
        if order["status"] != "closed":
            return OrderStatus(order["status"] == "open", 0.0, None)
        notional = order["qty"] * order["price"]
        maker = self.execution.maker_fee_rate
        quote = notional * (1 + maker) if order["side"] == "buy" else notional * (1 - maker)
        return OrderStatus(False, order["qty"], Fill(order["qty"], order["price"], quote))

    def _save(self) -> None:
        atomic_write(self.wallet_path, json.dumps(self.wallet, indent=2))


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
