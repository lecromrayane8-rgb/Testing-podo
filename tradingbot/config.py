"""Configuration lue depuis l'environnement (et un fichier .env optionnel)."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace
from pathlib import Path

from .data import timeframe_to_ms
from .execution import ExecutionParams
from .risk import RiskParams
from .strategy import StrategyParams

MODES = ("paper", "testnet", "demo", "live")
LIVE_CONFIRMATION = "OUI"


class ConfigError(ValueError):
    pass


def load_dotenv(path: Path = Path(".env")) -> None:
    """Charge un fichier KEY=VALUE sans écraser les variables déjà définies."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _params_from_env(cls):
    """Chaque champ du dataclass peut être surchargé par la variable d'env du même nom en majuscules."""
    defaults = cls()
    overrides = {}
    for f in fields(cls):
        raw = os.environ.get(f.name.upper(), "").strip()
        if raw:
            default = getattr(defaults, f.name)
            # « 2,5 » à la française est accepté comme 2.5
            overrides[f.name] = raw.lower() if isinstance(default, str) else type(default)(raw.replace(",", "."))
    return cls(**overrides)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def parse_bots(raw: str) -> tuple[tuple[str, str], ...]:
    """`BTC/USDT@15m,ETH/USDT@4h` -> ((BTC/USDT, 15m), (ETH/USDT, 4h))."""
    bots = []
    for item in (x.strip() for x in raw.split(",")):
        if not item:
            continue
        symbol, sep, timeframe = item.partition("@")
        if not sep or not symbol.strip() or not timeframe.strip():
            raise ConfigError(f"BOTS : « {item} » doit s'écrire PAIRE@UNITE, par exemple BTC/USDT@1h")
        bots.append((symbol.strip().upper(), timeframe.strip()))
    return tuple(bots)


@dataclass(frozen=True)
class Settings:
    mode: str
    exchange: str
    symbol: str
    timeframe: str
    api_key: str
    api_secret: str
    api_password: str
    poll_seconds: int
    max_capital: float
    paper_start_balance: float
    data_dir: Path
    obsidian_vault: Path | None
    live_confirmed: bool
    strategy: StrategyParams
    risk: RiskParams
    execution: ExecutionParams
    bots: tuple[tuple[str, str], ...] = ()
    bot_label: str = ""  # nom de la stratégie d'un bot du tournoi (fichiers et affichage)
    telegram_token: str = ""  # alertes sur le téléphone (optionnel, voir tradingbot/notify.py)
    telegram_chat_id: str = ""

    @property
    def markets(self) -> tuple[tuple[str, str], ...]:
        """Les bots à faire tourner : BOTS, ou à défaut SYMBOL@TIMEFRAME."""
        return self.bots or ((self.symbol, self.timeframe),)

    def per_bot(self) -> list["Settings"]:
        """Un jeu de réglages par bot (BOTS), chacun avec sa paire et son unité de temps."""
        return [replace(self, symbol=symbol, timeframe=timeframe) for symbol, timeframe in self.markets]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=_env("MODE", "paper").lower(),
            exchange=_env("EXCHANGE", "binance").lower(),
            symbol=_env("SYMBOL", "BTC/USDT"),
            timeframe=_env("TIMEFRAME", "1h"),
            api_key=_env("API_KEY"),
            api_secret=_env("API_SECRET"),
            api_password=_env("API_PASSWORD"),
            poll_seconds=int(_env("POLL_SECONDS", "30")),
            max_capital=float(_env("MAX_CAPITAL", "0")),
            paper_start_balance=float(_env("PAPER_START_BALANCE", "10000")),
            data_dir=Path(_env("DATA_DIR", "data")),
            obsidian_vault=Path(_env("OBSIDIAN_VAULT")).expanduser() if _env("OBSIDIAN_VAULT") else None,
            live_confirmed=_env("CONFIRM_LIVE_TRADING") == LIVE_CONFIRMATION,
            strategy=_params_from_env(StrategyParams),
            risk=_params_from_env(RiskParams),
            execution=_params_from_env(ExecutionParams),
            bots=parse_bots(_env("BOTS")),
            telegram_token=_env("TELEGRAM_TOKEN"),
            telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        )

    def validate_for_trading(self) -> None:
        if self.mode not in MODES:
            raise ConfigError(f"MODE doit valoir {', '.join(MODES)} (reçu : {self.mode!r})")
        if self.mode != "paper" and not (self.api_key and self.api_secret):
            raise ConfigError(f"MODE={self.mode} nécessite API_KEY et API_SECRET dans le fichier .env")
        if self.mode == "live":
            if not self.live_confirmed:
                raise ConfigError(
                    "MODE=live passe de VRAIS ordres avec de l'argent réel. "
                    f"Pour l'autoriser, ajoute CONFIRM_LIVE_TRADING={LIVE_CONFIRMATION} dans .env."
                )
            if self.max_capital <= 0:
                raise ConfigError("MODE=live exige MAX_CAPITAL > 0 (montant max confié au bot, ex. 200).")
        markets = self.markets
        if len(set(markets)) != len(markets):
            raise ConfigError("BOTS contient deux fois le même bot (même paire et même unité de temps)")
        for symbol, timeframe in markets:
            try:
                timeframe_to_ms(timeframe)
            except Exception:
                raise ConfigError(
                    f"Unité de temps invalide pour {symbol} : « {timeframe} » (ex. 15m, 1h, 4h, 1d)"
                ) from None
        if self.mode != "paper" and len(markets) > 1 and self.max_capital <= 0:
            raise ConfigError(
                "Avec plusieurs bots sur un vrai compte, MAX_CAPITAL (montant confié à CHAQUE bot) est obligatoire, "
                "sinon chacun croirait disposer de tout le solde."
            )
        r = self.risk
        if not 0 < r.risk_per_trade <= 0.05:
            raise ConfigError("RISK_PER_TRADE doit être entre 0 et 0.05 (5 % max par trade)")
        if not 0 < r.max_position_pct <= 1:
            raise ConfigError("MAX_POSITION_PCT doit être entre 0 et 1 (pas de levier)")
