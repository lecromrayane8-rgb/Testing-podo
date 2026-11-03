"""Récupération et mise en cache des bougies OHLCV."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import ccxt
import pandas as pd

log = logging.getLogger(__name__)

COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


def make_exchange(exchange_id: str, **config) -> ccxt.Exchange:
    klass = getattr(ccxt, exchange_id, None)
    if klass is None:
        raise ValueError(f"Plateforme inconnue de ccxt : {exchange_id}")
    options: dict = {"defaultType": "spot"}
    if exchange_id == "binance":
        # Le bot ne trade que du spot : inutile de charger les marchés à terme (autres domaines réseau).
        options["fetchMarkets"] = {"types": ["spot"]}
    return klass({"enableRateLimit": True, "options": options, **config})


def timeframe_to_ms(timeframe: str) -> int:
    return int(ccxt.Exchange.parse_timeframe(timeframe) * 1000)


def ohlcv_to_frame(rows: list[list[float]]) -> pd.DataFrame:
    """Convertit la sortie ccxt en DataFrame indexé par date UTC (colonne `ts` en ms conservée)."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["ts"] = df["ts"].astype("int64")
    df[COLUMNS[1:]] = df[COLUMNS[1:]].astype(float)
    df = df.drop_duplicates("ts").sort_values("ts")
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.index.name = "date"
    return df


def fetch_history(
    exchange: ccxt.Exchange, symbol: str, timeframe: str, since_ms: int, until_ms: int | None = None
) -> pd.DataFrame:
    tf_ms = timeframe_to_ms(timeframe)
    until_ms = until_ms or exchange.milliseconds()
    rows: list[list[float]] = []
    cursor = since_ms
    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=cursor, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        next_cursor = batch[-1][0] + tf_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        log.info("%s %s : %d bougies récupérées", symbol, timeframe, len(rows))
        time.sleep(exchange.rateLimit / 1000)
    df = ohlcv_to_frame(rows)
    # La dernière bougie est encore en cours : on ne garde que les bougies clôturées.
    return df[df["ts"] + tf_ms <= until_ms]


def load_or_fetch(
    exchange_id: str, symbol: str, timeframe: str, days: int, cache_dir: Path, exchange: ccxt.Exchange | None = None
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{exchange_id}_{symbol.replace('/', '-')}_{timeframe}_{days}j.csv"
    if cache.exists() and time.time() - cache.stat().st_mtime < 6 * 3600:
        log.info("Données lues depuis le cache %s", cache)
        return load_csv(cache)
    exchange = exchange or make_exchange(exchange_id)
    since = exchange.milliseconds() - days * 24 * 3600 * 1000
    df = fetch_history(exchange, symbol, timeframe, since)
    df[COLUMNS].to_csv(cache, index=False)
    return df


def load_csv(path: Path) -> pd.DataFrame:
    """CSV du bot (ts en ms, open...) ou export classique « Date,Open,High,Low,Close[,Volume] » (actions, ETF...)."""
    raw = pd.read_csv(path)
    names = {str(c).strip().lower(): c for c in raw.columns}
    if "ts" in names:
        ts = pd.to_numeric(raw[names["ts"]], errors="coerce")
    else:
        date_col = next((names[k] for k in ("date", "datetime", "time", "timestamp") if k in names), None)
        if date_col is None:
            raise ValueError(f"{path} : colonne de date introuvable (attendu ts ou Date)")
        dates = pd.to_datetime(raw[date_col], utc=True, errors="coerce")
        ts = (dates - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)
    missing = [c for c in COLUMNS[1:5] if c not in names]
    if missing:
        raise ValueError(f"{path} : colonnes manquantes {missing} (attendu Open, High, Low, Close)")
    frame = pd.DataFrame({"ts": ts})
    for col in COLUMNS[1:]:
        frame[col] = pd.to_numeric(raw[names[col]], errors="coerce") if col in names else 0.0
    frame = frame.dropna()
    return ohlcv_to_frame(frame[COLUMNS].values.tolist())
