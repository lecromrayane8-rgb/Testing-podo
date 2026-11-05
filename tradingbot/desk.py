"""Mes essais : trader une opportunité du radar en argent fictif, avec le risque affiché avant.

Un compte fictif à part (1000 USDT au départ, `data/essais.json`). Un essai s'achète au prix réel du moment,
glissement et frais compris comme le paper trading du bot, avec une taille calculée pour que toucher le stop ne
coûte qu'environ 1 % du compte, et au plus 1/5 du compte engagé par essai (cinq essais au plus à la fois). Il se revend tout seul selon l'option choisie, avec les règles de l'étude et du
backtest : sous le plus bas des N dernières bougies de 1 minute (le mouvement s'essouffle), au stop, ou après le
temps maximum. Il peut aussi être revendu à la main. Rien ne part jamais sur une vraie plateforme.
"""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .broker import atomic_write
from .execution import ExecutionParams
from .moves import OPTIONS, option_params, trade_plan
from .radar import STRONG
from .risk import RiskParams
from .strategy import compute_signals

DESK_FILE = "essais.json"
START_BALANCE = 1000.0
MAX_OPEN = 5  # au plus 5 essais ouverts à la fois
REASONS = {"stop": "stop touché", "essoufflement": "le mouvement s'essouffle", "temps": "temps maximum",
           "main": "vendu à la main"}


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


class Desk:
    def __init__(self, path: Path, execution: ExecutionParams, risk: RiskParams, start: float = START_BALANCE):
        self.path, self.start = path, start
        self.execution = replace(execution, order_type="market")  # un essai s'achète et se revend au marché
        # Chaque essai engage au plus 1/5 du compte : cinq essais peuvent tourner en même temps.
        self.risk = replace(risk, max_position_pct=min(risk.max_position_pct, 1 / MAX_OPEN))
        self.lock = threading.RLock()
        self.state = self._load()

    def _fresh(self, now: float | None = None) -> dict:
        return {"start": self.start, "cash": self.start, "next_id": 1, "positions": [], "trades": [],
                "since": iso(now if now is not None else datetime.now(timezone.utc).timestamp())}

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(state, dict) and {"cash", "positions", "trades", "next_id"} <= set(state):
                return state
        except (OSError, ValueError):
            pass
        return self._fresh()

    def _save(self) -> None:
        atomic_write(self.path, json.dumps(self.state, ensure_ascii=False, indent=1))

    def equity(self, prices: dict[str, float]) -> float:
        with self.lock:
            return self.state["cash"] + sum(p["qty"] * prices.get(p["symbol"], p["mark"])
                                            for p in self.state["positions"])

    def plan(self, symbol: str, window: int, option: str, price: float, candles: pd.DataFrame) -> dict | None:
        """L'essai tel qu'il serait passé maintenant (ATR des dernières bougies de 1 minute)."""
        atr = float(compute_signals(candles, option_params(window, option))["atr"].iloc[-1]) if len(candles) else 0.0
        return trade_plan(price, atr, window, option, self.equity({symbol: price}), self.risk, self.execution)

    def open(self, symbol: str, window: int, option: str, price: float, candles: pd.DataFrame, now: float) -> dict:
        if window not in STRONG or option not in OPTIONS:
            raise ValueError("Option inconnue")
        with self.lock:
            positions = self.state["positions"]
            if len(positions) >= MAX_OPEN:
                raise ValueError(f"Déjà {MAX_OPEN} essais ouverts : attends qu'un se termine, ou vends-en un.")
            if any(p["symbol"] == symbol for p in positions):
                raise ValueError(f"Un essai est déjà ouvert sur {symbol}.")
            plan = self.plan(symbol, window, option, price, candles)
            if plan is None:
                raise ValueError("Impossible de placer le stop : pas assez de bougies récentes pour cette crypto.")
            fee = self.execution.fee_rate
            qty = min(plan["qty"], self.state["cash"] / (plan["entry"] * (1 + fee)))
            if qty * plan["entry"] < 10:
                raise ValueError("Plus assez d'argent fictif libre pour un essai (minimum 10 USDT).")
            cost = qty * plan["entry"] * (1 + fee)
            position = {"id": self.state["next_id"], "symbol": symbol, "window": window, "option": option,
                        "opened": iso(now), "opened_ts": now, "mark": price, "entry": plan["entry"], "qty": qty,
                        "stop": plan["stop"], "cost": cost, "candle_ts": int(candles["ts"].iloc[-1]),
                        "risk": cost - qty * plan["stop"] * (1 - self.execution.slippage) * (1 - fee)}
            self.state["next_id"] += 1
            self.state["cash"] -= cost
            positions.append(position)
            self._save()
            return position

    def exit_reason(self, position: dict, price: float, candles: pd.DataFrame | None) -> str | None:
        """La règle de sortie de l'option : stop au prix du moment, puis, sur les bougies de 1 minute clôturées
        depuis l'achat, le temps maximum et l'essoufflement (comme le backtest)."""
        if price <= position["stop"]:
            return "stop"
        if candles is None or not len(candles):
            return None
        params = option_params(position["window"], position["option"])
        since = candles[candles["ts"] > position["candle_ts"]]
        if not len(since):
            return None
        if params.max_bars_in_trade and len(since) >= params.max_bars_in_trade:
            return "temps"
        return "essoufflement" if bool(compute_signals(candles, params)["exit"].iloc[-1]) else None

    def check(self, prices: dict[str, float], candles: dict[str, pd.DataFrame], now: float) -> list[dict]:
        """Revend les essais dont la règle de sortie est atteinte ; renvoie les trades clôturés."""
        closed = []
        with self.lock:
            for position in list(self.state["positions"]):
                price = prices.get(position["symbol"])
                if price is None:
                    continue
                reason = self.exit_reason(position, price, candles.get(position["symbol"]))
                if reason:
                    closed.append(self._close(position, price, reason, now))
            if closed:
                self._save()
        return closed

    def _close(self, position: dict, price: float, reason: str, now: float) -> dict:
        exit_price = price * (1 - self.execution.slippage)
        proceeds = position["qty"] * exit_price * (1 - self.execution.fee_rate)
        self.state["cash"] += proceeds
        self.state["positions"] = [p for p in self.state["positions"] if p["id"] != position["id"]]
        trade = {**{k: position[k] for k in ("id", "symbol", "window", "option", "opened", "entry", "qty", "cost")},
                 "closed": iso(now), "exit": exit_price, "proceeds": proceeds, "pnl": proceeds - position["cost"],
                 "return": proceeds / position["cost"] - 1, "reason": reason,
                 "minutes": round((now - position["opened_ts"]) / 60, 1)}
        self.state["trades"].append(trade)
        return trade

    def sell(self, pid: int, price: float, now: float) -> dict:
        """Revendre un essai à la main, au prix du moment."""
        with self.lock:
            position = next((p for p in self.state["positions"] if p["id"] == pid), None)
            if position is None:
                raise ValueError("Cet essai n'est plus ouvert.")
            trade = self._close(position, price, "main", now)
            self._save()
            return trade

    def reset(self, now: float) -> None:
        with self.lock:
            self.state = self._fresh(now)
            self._save()

    def symbols(self) -> list[str]:
        with self.lock:
            return sorted({p["symbol"] for p in self.state["positions"]})

    def summary(self, prices: dict[str, float]) -> dict:
        with self.lock:
            state = json.loads(json.dumps(self.state))  # copie : le fil des vérifications peut écrire en même temps
        positions = []
        for p in state["positions"]:
            price = prices.get(p["symbol"])
            value = p["qty"] * price * (1 - self.execution.slippage) * (1 - self.execution.fee_rate) if price else None
            positions.append({**p, "price": price, "option_title": OPTIONS[p["option"]][0],
                              "pnl": value - p["cost"] if value is not None else None,
                              "return": value / p["cost"] - 1 if value is not None else None})
        trades = state["trades"]
        returns = [t["return"] for t in trades]
        equity, curve = state["start"], []
        for t in trades:
            equity += t["pnl"]
            curve.append({"t": t["closed"], "equity": equity})
        open_value = sum(p["qty"] * (p["price"] or p["mark"]) for p in positions)
        total = state["cash"] + open_value
        return {
            "since": state.get("since"), "start": state["start"], "cash": state["cash"], "equity": total,
            "result": total - state["start"], "result_pct": total / state["start"] - 1,
            "positions": positions, "max_open": MAX_OPEN,
            "trades": [{**t, "option_title": OPTIONS[t["option"]][0], "reason_text": REASONS.get(t["reason"], t["reason"])}
                       for t in reversed(trades)],
            "stats": {"n": len(trades), "winners": sum(r > 0 for r in returns),
                      "mean": sum(returns) / len(returns) if returns else None,
                      "realized": sum(t["pnl"] for t in trades)},
            "curve": curve,
        }
