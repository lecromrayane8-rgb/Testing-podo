"""Audit : le contexte autour du signal aide-t-il ? (étape 1 ter de PLAN-BOTS.md : la mesure seule, rien n'est changé
dans les bots.)

Pour chaque trade à l'essai (toutes les combinaisons, la variante des bots, sur de vraies bougies Binance), on note ce
qu'on savait à la clôture de la bougie du signal, donc AVANT l'entrée. Sept conditions, fixées ici d'avance, un seul
seuil chacune ; « dans le sens du trade » veut dire : à la hausse pour un achat, à la baisse pour une vente à découvert.

1. flux     : ceux qui achètent « au marché » dominent (plus de 50 % du volume des 10 dernières bougies) pour un
              achat ; ceux qui vendent au marché dominent pour une vente ;
2. activite : la bougie du signal compte plus de trades que la moyenne des 50 précédentes ;
3. dessus   : l'unité au-dessus va dans le sens du trade (sa clôture est au-dessus de sa moyenne des 50 bougies, pour
              un achat) : 15 min pour un bot en 1 min, 1 h pour 5 min, 4 h pour 15 min, 1 jour pour 1 h et 4 h ;
4. bitcoin  : le Bitcoin en bougies d'une heure va dans le sens du trade (même définition) ;
5. foule    : sur les contrats à terme, les comptes ne sont pas plus acheteurs que d'habitude (rapport acheteurs /
              vendeurs sous sa médiane des 3 derniers jours) pour un achat ; pas plus vendeurs pour une vente ;
6. argent   : l'argent engagé sur les contrats à terme (l'intérêt ouvert) a monté sur la dernière heure ;
7. ensemble : flux, dessus et bitcoin d'accord tous les trois.

Pour chaque condition, une seule question : les trades pris quand elle est vraie font-ils mieux que les autres, frais
compris ? L'écart est jugé jour par jour (risk.paired_bounds : mêmes journées, mêmes marchés), avec un seuil durci
parce qu'on pose sept questions. Deux témoins disent si la mesure sait voir quelque chose : « hasard » (pile ou face :
l'écart doit être nul) et « triche » (la bougie d'entrée finit dans le bon sens : on ne le sait qu'après coup, l'écart
doit être énorme).

Lancer (dans cet ordre ; le cache est hors du dépôt) :
  python audit/contexte.py trades  --jours 14 [--fin MS] [--coeurs 3]   les trades à l'essai, un par un (25 min)
  python audit/contexte.py donnees                                      flux des bougies et contrats à terme (10 min)
  python audit/contexte.py mesure  --sortie contexte.json               le rapport
"""
import argparse
import csv
import io
import json
import math
import sys
import threading
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vrai  # noqa: E402  (les mêmes bougies, le même univers reconstitué que la mesure à l'essai)
from tradingbot.data import timeframe_to_ms  # noqa: E402
from tradingbot.fleet import EXITS, technique, tf_label  # noqa: E402
from tradingbot.risk import clustered_bounds, paired_bounds  # noqa: E402
from tradingbot.strategy import PATTERN_FAMILIES  # noqa: E402
from tradingbot.swarm import LIBRARY, TEST_DAYS, TIMEFRAMES, SwarmSettings, retest_coin  # noqa: E402

DAY, HOUR, MIN = 86_400_000, 3_600_000, 60_000
ABOVE = {"1m": "15m", "5m": "1h", "15m": "4h", "1h": "1d", "4h": "1d"}  # l'unité au-dessus de chaque unité
FLOW_BARS, ACTIVITY_BARS, TREND_BARS = 10, 50, 50  # fixés d'avance
CROWD_ROWS, MONEY_ROWS, CROWD_DELAY = 3 * 288, 12, 5 * MIN  # 3 jours et 1 heure de points à 5 min ; un point de retard
CROWD_AGE = 20 * MIN  # un point des contrats à terme vieux de plus de 20 minutes ne compte pas (archive incomplète)
ARCHIVE = "https://data.binance.vision/data/futures/um/daily/metrics/{id}/{id}-metrics-{day}.zip"
BOOK = "https://data.binance.vision/data/futures/um/daily/bookDepth/{id}/{id}-bookDepth-{day}.zip"
BOOK_AGE = 2 * MIN  # une photo du carnet d'ordres vieille de plus de 2 minutes ne compte pas
STRONG_FLOW, VOLUME_SPIKE = 0.55, 2.0  # « flux net » : 55 % du volume d'un côté ; « pic » : 2 fois le volume moyen
MIN_CELL = 300  # trades au moins pour juger une combinaison technique × unité × sens × condition
CONDITIONS = ("flux", "flux_fort", "activite", "volume", "dessus", "bitcoin", "foule", "argent", "carnet",
              "carnet_proche", "ensemble")
WITNESSES = ("hasard", "triche")
LABELS = {"flux": "Qui pousse (acheteurs ou vendeurs au marché)", "activite": "Activité au-dessus de sa moyenne",
          "dessus": "L'unité au-dessus va dans le même sens", "bitcoin": "Le Bitcoin va dans le même sens",
          "foule": "La foule n'est pas déjà de ce côté", "argent": "L'argent engagé augmente",
          "ensemble": "Flux, unité au-dessus et Bitcoin d'accord", "hasard": "Témoin : pile ou face",
          "flux_fort": "Flux net du côté du trade (55 % du volume au moins)",
          "volume": "Pic de volume (2 fois la moyenne)",
          "carnet": "Le carnet d'ordres penche du côté du trade (à 1 % du prix)",
          "carnet_proche": "Le carnet d'ordres penche du côté du trade (à 0,2 % du prix)",
          "triche": "Témoin : la bougie d'entrée (connue après coup)"}
READING = np.array([technique(name).strategy_type in PATTERN_FAMILIES for name in LIBRARY])


def safe(symbol: str) -> str:
    return symbol.replace("/", "-")


# --- 1. les trades à l'essai, un par un ---------------------------------------------------------------------------

def _rows_job(args):
    symbol, frames, settings, trial, out = args
    started = time.time()
    rows = retest_coin(symbol, frames, settings, trial=trial)["trial"]["rows"]
    exits = {(float(target), mode): k for k, (target, mode) in enumerate(EXITS)}
    np.savez_compressed(
        out, tf=np.array([TIMEFRAMES.index(r[0]) for r in rows], dtype=np.int8),
        tech=np.array([LIBRARY.index(r[1]) for r in rows], dtype=np.int16),
        short=np.array([r[2] == "short" for r in rows], dtype=bool),
        exit=np.array([exits[(float(r[3]), r[4])] for r in rows], dtype=np.int8),
        entry=np.array([r[5] for r in rows], dtype=np.int64), out=np.array([r[6] for r in rows], dtype=np.int64),
        net=np.array([r[7] for r in rows], dtype=np.float64))
    return symbol, len(rows), time.time() - started


def history(ex, symbol: str, units: list[str], start: int, end: int, cache: Path) -> dict[str, pd.DataFrame]:
    """Les bougies d'une crypto pour quelques unités seulement (une longue période en 1 h et 4 h, par exemple)."""
    frames = {}
    for tf in units:
        try:
            frames[tf] = vrai.candles(ex, symbol, tf, start - TEST_DAYS[tf] * DAY, end, cache)
        except Exception as exc:
            print(f"  {symbol} {tf} : historique indisponible ({exc})", flush=True)
    return frames


def trades(args) -> None:
    cache, folder = Path(args.cache), Path(args.cache) / args.dossier
    folder.mkdir(parents=True, exist_ok=True)
    units = [tf for tf in TIMEFRAMES if tf in args.unites.split(",")] or list(TIMEFRAMES)
    ex = vrai.exchange()
    ex.load_markets()
    end = (args.fin or ex.fetch_time()) // HOUR * HOUR
    start = end - args.jours * DAY
    settings = SwarmSettings(coins=args.cryptos)
    print(f"Univers reconstitué du {pd.to_datetime(start, unit='ms')} au {pd.to_datetime(end, unit='ms')} (UTC), "
          "actions en jetons écartées", flush=True)
    stretches = vrai.universe(ex, start, end, cache, settings.coins, settings.min_move)
    active = sorted(stretches, key=lambda s: -sum(b - a for a, b in stretches[s]))
    # écrit tout de suite : `donnees` peut télécharger pendant que les trades se calculent
    (folder / "meta.json").write_text(json.dumps({"start": start, "end": end, "days": args.jours, "symbols": active,
                                                  "settings": asdict(settings)}), encoding="utf-8")
    jobs = []
    for k, symbol in enumerate(active, 1):
        frames = {tf: frame for tf, frame in vrai.frames_for(ex, symbol, start, end, cache).items()} \
            if len(units) == len(TIMEFRAMES) else history(ex, symbol, units, start, end, cache)
        trial = {"done": {}, "active": stretches[symbol], "final": True, "rows": True}
        jobs.append((symbol, frames, asdict(settings), trial, folder / f"rows-{safe(symbol)}.npz"))
        if k % 20 == 0:
            print(f"  bougies : {k}/{len(active)} cryptos", flush=True)
    history(ex, "BTC/USDT", ["1h"], start, end, cache)  # la tendance du Bitcoin, même s'il n'a pas « bougé »
    began, total = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.coeurs) as pool:
        for k, (symbol, n, seconds) in enumerate(pool.map(_rows_job, jobs), 1):
            total += n
            if k % 10 == 0 or k == len(jobs):
                print(f"  {k}/{len(jobs)} cryptos · {total} trades · {time.time() - began:5.0f} s écoulées", flush=True)
    print(f"{total} trades à l'essai notés pour {len(active)} cryptos, dans {folder}")


# --- 2. ce qu'on savait : le flux des bougies, les contrats à terme -------------------------------------------------

LOCAL = threading.local()


def _exchange():
    if not hasattr(LOCAL, "ex"):
        LOCAL.ex = vrai.exchange()
        LOCAL.ex.load_markets()
    return LOCAL.ex


def _flow_job(args):
    """Les bougies Binance complètes d'une crypto : ouverture, clôture, volume, nombre de trades, volume acheté au
    marché (les champs que fetch_ohlcv ne rend pas)."""
    symbol, tf, start, end, out = args
    if out.exists():
        return 0
    ex, step, rows, since = _exchange(), timeframe_to_ms(tf), [], start
    market = ex.market(symbol)["id"]
    while since < end:
        batch = ex.publicGetKlines({"symbol": market, "interval": tf, "startTime": since, "limit": 1000})
        if not batch:
            break
        rows += batch
        since = int(batch[-1][0]) + step
        if len(batch) < 1000:
            break
    rows = [r for r in rows if int(r[0]) + step <= end]  # seulement des bougies terminées
    np.savez_compressed(out, ts=np.array([int(r[0]) for r in rows], dtype=np.int64),
                        open=np.array([float(r[1]) for r in rows]), close=np.array([float(r[4]) for r in rows]),
                        volume=np.array([float(r[5]) for r in rows]), trades=np.array([float(r[8]) for r in rows]),
                        taker=np.array([float(r[9]) for r in rows]))
    return len(rows)


def _book_job(args):
    """Le carnet d'ordres des contrats à terme d'une crypto, une photo toutes les 30 secondes (archives publiques de
    Binance) : la valeur des ordres d'achat et de vente en attente à 1 % et à 0,2 % du prix."""
    symbol, days, out = args
    if out.exists():
        return 0
    import requests  # la session de la bibliothèque déjà installée avec ccxt : proxy et certificat de l'environnement
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
    base, parts = symbol.split("/")[0], []
    for name in (f"{base}USDT", f"1000{base}USDT"):
        for day in days:
            try:
                reply = LOCAL.session.get(BOOK.format(id=name, day=day), timeout=60)
            except Exception:
                continue
            if reply.status_code != 200:
                continue
            with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
                frame = pd.read_csv(archive.open(archive.namelist()[0]))
            frame = frame[frame["percentage"].isin((-1.0, 1.0, -0.2, 0.2))]
            parts.append(frame.pivot_table(index="timestamp", columns="percentage", values="notional", aggfunc="last"))
        if parts:
            break
    if not parts:
        np.savez_compressed(out, ts=np.array([], dtype=np.int64), b1=np.array([]), a1=np.array([]), b02=np.array([]),
                            a02=np.array([]))
        return 0
    wide = pd.concat(parts).sort_index()
    wide = wide[~wide.index.duplicated(keep="last")]
    stamps = pd.to_datetime(wide.index, utc=True)
    ts = np.asarray((stamps - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1), dtype=np.int64)
    column = lambda level: wide[level].to_numpy(float) if level in wide.columns else np.full(len(wide), np.nan)  # noqa: E731
    np.savez_compressed(out, ts=ts, b1=column(-1.0), a1=column(1.0), b02=column(-0.2), a02=column(0.2))
    return len(parts)


def _crowd_job(args):
    """Les contrats à terme d'une crypto, toutes les 5 minutes : intérêt ouvert et nombre de comptes acheteurs pour un
    compte vendeur (archives publiques de Binance ; « 1000PEPE » pour les cryptos au prix minuscule)."""
    symbol, days, out = args
    if out.exists():
        return 0
    session, base = _exchange().session, symbol.split("/")[0]
    rows = []
    for name in (f"{base}USDT", f"1000{base}USDT"):
        for day in days:
            try:
                reply = session.get(ARCHIVE.format(id=name, day=day), timeout=30)
            except Exception:
                continue
            if reply.status_code != 200:
                continue  # jour pas encore publié, ou pas de contrat sous ce nom
            with zipfile.ZipFile(io.BytesIO(reply.content)) as archive:
                text = io.TextIOWrapper(archive.open(archive.namelist()[0]), encoding="utf-8")
                for line in csv.DictReader(text):
                    try:
                        rows.append((int(pd.Timestamp(line["create_time"], tz="UTC").timestamp() * 1000),
                                     float(line["sum_open_interest"]), float(line["count_long_short_ratio"])))
                    except (KeyError, ValueError):
                        continue  # une ligne incomplète : ignorée
        if rows:
            break
    rows.sort()
    np.savez_compressed(out, ts=np.array([r[0] for r in rows], dtype=np.int64), oi=np.array([r[1] for r in rows]),
                        ls=np.array([r[2] for r in rows]))
    return len(rows)


def donnees(args) -> None:
    folder = Path(args.cache) / args.dossier
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    start, end = meta["start"], meta["end"]
    units = [tf for tf in TIMEFRAMES if tf in args.unites.split(",")]
    flow = [(s, tf, start - (ACTIVITY_BARS + 10) * timeframe_to_ms(tf), end, folder / f"flux-{safe(s)}-{tf}.npz")
            for s in meta["symbols"] for tf in units]
    days = [str(pd.Timestamp(t, unit="ms").date()) for t in range(start - 4 * DAY, end + 1, DAY)]
    crowd = [(s, days, folder / f"foule-{safe(s)}.npz") for s in meta["symbols"]]
    began = time.time()
    with ThreadPoolExecutor(4) as pool:
        for k, n in enumerate(pool.map(_flow_job, flow), 1):
            if k % 100 == 0 or k == len(flow):
                print(f"  flux : {k}/{len(flow)} séries · {time.time() - began:4.0f} s", flush=True)
    with ThreadPoolExecutor(8) as pool:
        got = [n for n in pool.map(_crowd_job, crowd)]
    with_contract = sum(1 for _, _, out in crowd if len(np.load(out)["ts"]))
    print(f"contrats à terme : {with_contract}/{len(crowd)} cryptos en ont un ({sum(got)} points lus) · "
          f"{time.time() - began:4.0f} s", flush=True)
    if args.sans_carnet:  # sur une longue période, le carnet pèse trop lourd (0,5 Mo par crypto et par jour)
        return
    book_days = [str(pd.Timestamp(t, unit="ms").date()) for t in range(start - DAY, end + 1, DAY)]
    books = [(s, book_days, folder / f"carnet-{safe(s)}.npz") for s in meta["symbols"]]
    with ThreadPoolExecutor(8) as pool:
        files = sum(pool.map(_book_job, books))
    with_book = sum(1 for _, _, out in books if len(np.load(out)["ts"]))
    print(f"carnet d'ordres : {with_book}/{len(books)} cryptos ({files} journées lues) · {time.time() - began:4.0f} s")


# --- 3. la mesure ---------------------------------------------------------------------------------------------------

def trend_up(frame: pd.DataFrame, step: int) -> tuple[np.ndarray, np.ndarray]:
    """Pour chaque bougie terminée : l'instant où elle se termine, et « sa clôture est au-dessus de sa moyenne des
    TREND_BARS dernières clôtures » (NaN tant que la moyenne n'existe pas)."""
    close = frame["close"].astype(float)
    mean = close.rolling(TREND_BARS, min_periods=TREND_BARS).mean()
    up = np.where(mean.notna(), (close > mean).astype(float), np.nan)
    return frame["ts"].to_numpy(np.int64) + step, up


def daily(frame_4h: pd.DataFrame) -> pd.DataFrame:
    """Des bougies d'un jour (UTC) tirées des bougies de 4 h : seulement les jours complets."""
    day = frame_4h["ts"] // DAY * DAY
    full = frame_4h.groupby(day)["close"].agg(["last", "size"])
    full = full[full["size"] == 6]
    return pd.DataFrame({"ts": full.index.to_numpy(np.int64), "close": full["last"].to_numpy(float)})


def known(times: np.ndarray, values: np.ndarray, at: np.ndarray, max_age: int | None = None) -> np.ndarray:
    """La dernière valeur connue à l'instant `at` (les `times` sont les instants où chaque valeur devient connue) ;
    inconnue si elle a plus de `max_age` millisecondes."""
    if not len(times):
        return np.full(len(at), np.nan)
    idx = np.searchsorted(times, at, side="right") - 1
    pos = np.clip(idx, 0, None)
    fresh = (idx >= 0) if max_age is None else (idx >= 0) & (at - times[pos] <= max_age)
    return np.where(fresh, values[pos], np.nan)


def conditions(symbol: str, rows, cache: Path, folder: Path, ex, btc: tuple, seed: int, start: int,
               end: int) -> dict[str, np.ndarray]:
    """Pour chaque trade de `rows` : chaque condition vraie (1), fausse (0) ou inconnue (NaN). `start` et `end` : la
    période mesurée (les bougies déjà en cache)."""
    n = len(rows["net"])
    short, entry = rows["short"], rows["entry"]
    out = {name: np.full(n, np.nan) for name in CONDITIONS + WITNESSES}
    frames = {}
    for k, tf in enumerate(TIMEFRAMES):
        mine = rows["tf"] == k
        if not mine.any():
            continue
        step, at, side = timeframe_to_ms(tf), entry[mine], short[mine]  # `at` : l'ouverture de la bougie d'entrée,
        source = folder / f"flux-{safe(symbol)}-{tf}.npz"               # donc la clôture de la bougie du signal
        if source.exists():  # sans les bougies complètes (flux pas téléchargé) : seulement les tendances
            flow = np.load(source)
            ts = flow["ts"]
            volume, taker, count = (pd.Series(flow[key]) for key in ("volume", "taker", "trades"))
            total = volume.rolling(FLOW_BARS, min_periods=FLOW_BARS).sum()
            share = (taker.rolling(FLOW_BARS, min_periods=FLOW_BARS).sum() / total.where(total > 0)).to_numpy()
            usual = count.rolling(ACTIVITY_BARS, min_periods=ACTIVITY_BARS).mean().shift(1)
            busy = np.where(usual.notna() & (usual > 0), (count > usual).astype(float), np.nan)
            at_signal = np.searchsorted(ts, at - step)  # la bougie du signal : celle qui se termine à `at`
            found = (at_signal < len(ts)) & (ts[np.clip(at_signal, 0, len(ts) - 1)] == at - step) if len(ts) else np.zeros(len(at), bool)
            pos = np.clip(at_signal, 0, max(len(ts) - 1, 0))
            buyers = np.where(found, share[pos], np.nan) if len(ts) else np.full(len(at), np.nan)
            with np.errstate(invalid="ignore"):
                out["flux"][mine] = np.where(np.isnan(buyers), np.nan, np.where(side, buyers < 0.5, buyers > 0.5))
                out["activite"][mine] = np.where(found, busy[pos], np.nan) if len(ts) else np.nan
                out["flux_fort"][mine] = np.where(np.isnan(buyers), np.nan, np.where(
                    side, buyers <= 1 - STRONG_FLOW, buyers >= STRONG_FLOW))
            calm = volume.rolling(ACTIVITY_BARS, min_periods=ACTIVITY_BARS).mean().shift(1)
            spike = np.where(calm.notna() & (calm > 0), (volume > VOLUME_SPIKE * calm).astype(float), np.nan)
            out["volume"][mine] = np.where(found, spike[pos], np.nan) if len(ts) else np.nan
            # le témoin « triche » : le sens de la bougie d'entrée elle-même, connu seulement à sa clôture
            at_entry = np.searchsorted(ts, at)
            seen = (at_entry < len(ts)) & (ts[np.clip(at_entry, 0, len(ts) - 1)] == at) if len(ts) else np.zeros(len(at), bool)
            move = (flow["close"] - flow["open"])[np.clip(at_entry, 0, max(len(ts) - 1, 0))] if len(ts) else np.zeros(len(at))
            out["triche"][mine] = np.where(seen, np.where(side, move < 0, move > 0), np.nan)
        # l'unité au-dessus
        above = ABOVE[tf]
        wide = "4h" if above == "1d" else above
        if wide not in frames:
            frames[wide] = vrai.candles(ex, symbol, wide, start - TEST_DAYS[wide] * DAY, end, cache)
        frame = daily(frames[wide]) if above == "1d" else frames[wide]
        up = known(*trend_up(frame, DAY if above == "1d" else timeframe_to_ms(above)), at)
        out["dessus"][mine] = np.where(np.isnan(up), np.nan, np.where(side, up == 0, up == 1))
    up = known(*btc, entry)
    out["bitcoin"] = np.where(np.isnan(up), np.nan, np.where(short, up == 0, up == 1))
    source = folder / f"foule-{safe(symbol)}.npz"
    crowd = np.load(source) if source.exists() else {"ts": np.array([], dtype=np.int64)}
    if len(crowd["ts"]) > CROWD_ROWS // 3:
        ratio, money = pd.Series(crowd["ls"]), pd.Series(crowd["oi"])
        usual = ratio.rolling(CROWD_ROWS, min_periods=CROWD_ROWS // 3).median().shift(1)
        more_buyers = np.where(usual.notna(), np.sign(ratio - usual), np.nan)  # +1 : plus acheteuse que d'habitude
        rising = np.where(money.shift(MONEY_ROWS).notna(), (money > money.shift(MONEY_ROWS)).astype(float), np.nan)
        lean = known(crowd["ts"], more_buyers, entry - CROWD_DELAY, CROWD_AGE)
        out["foule"] = np.where(np.isnan(lean), np.nan, np.where(short, lean >= 0, lean <= 0))
        out["argent"] = known(crowd["ts"], rising, entry - CROWD_DELAY, CROWD_AGE)
    source = folder / f"carnet-{safe(symbol)}.npz"
    book = np.load(source) if source.exists() else {"ts": np.array([], dtype=np.int64)}
    if len(book["ts"]):  # la dernière photo du carnet avant la clôture du signal : part des ordres d'achat en attente
        for name, bids, asks in (("carnet", "b1", "a1"), ("carnet_proche", "b02", "a02")):
            waiting = book[bids] + book[asks]
            with np.errstate(invalid="ignore", divide="ignore"):
                lean = np.where(waiting > 0, book[bids] / waiting, np.nan)
            seen = known(book["ts"], lean, entry, BOOK_AGE)
            out[name] = np.where(np.isnan(seen), np.nan, np.where(short, seen < 0.5, seen > 0.5))
    agree = np.stack([out["flux"], out["dessus"], out["bitcoin"]])
    out["ensemble"] = np.where(np.isnan(agree).any(axis=0), np.nan, (agree == 1).all(axis=0))
    out["hasard"] = np.random.default_rng(seed).integers(0, 2, n).astype(float)
    return out


def mesure(args) -> None:
    cache, folder = Path(args.cache), Path(args.cache) / args.dossier
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    ex = vrai.exchange()
    ex.load_markets()
    btc = trend_up(vrai.candles(ex, "BTC/USDT", "1h", meta["start"] - TEST_DAYS["1h"] * DAY, meta["end"], cache), HOUR)
    day0, days = meta["start"] // DAY - 1, meta["days"] + 4
    groups = ["toutes", "lectures", "indicateurs", "achat", "vente"] + [f"unite:{tf}" for tf in TIMEFRAMES]
    # table[condition][groupe] : par jour, trades et somme quand la condition est vraie, puis quand elle est fausse
    table = {c: {g: np.zeros((days, 6)) for g in groups} for c in CONDITIONS + WITNESSES}
    overall = np.zeros((days, 3))
    total = 0
    missing = [s for s in meta["symbols"] if not (folder / f"rows-{safe(s)}.npz").exists()]
    if missing:
        print(f"ATTENTION : {len(missing)} cryptos sans trades notés (calcul pas fini ?) : mesure partielle", flush=True)
    for seed, symbol in enumerate(meta["symbols"]):
        if symbol in missing:
            continue
        rows = np.load(folder / f"rows-{safe(symbol)}.npz")
        if not len(rows["net"]):
            continue
        cond = conditions(symbol, rows, cache, folder, ex, btc, seed, meta["start"], meta["end"])
        net, day = rows["net"], np.clip(rows["out"] // DAY - day0, 0, days - 1)
        total += len(net)
        np.add.at(overall, day, np.c_[np.ones(len(net)), net, net > 0])
        member = {"toutes": np.ones(len(net), bool), "lectures": READING[rows["tech"]], "achat": ~rows["short"],
                  "vente": rows["short"], **{f"unite:{tf}": rows["tf"] == k for k, tf in enumerate(TIMEFRAMES)}}
        member["indicateurs"] = ~member["lectures"]
        for name, value in cond.items():
            for g in groups:
                for column, flag in ((0, 1.0), (3, 0.0)):
                    pick = member[g] & (value == flag)
                    np.add.at(table[name][g][:, column:column + 3], day[pick],
                              np.c_[np.ones(pick.sum()), net[pick], net[pick] > 0])
    alpha = 0.025 / len(CONDITIONS)  # sept questions : seuil durci (Bonferroni)
    report = {"start": meta["start"], "end": meta["end"], "coins": len(meta["symbols"]), "trades": total,
              "all": line([(r[0], r[1]) for r in overall], overall[:, 2].sum()), "conditions": {}}
    print(f"\nLE CONTEXTE AUTOUR DU SIGNAL : {total} trades à l'essai sur {len(meta['symbols'])} cryptos, "
          f"{meta['days']} jours de vraies bougies (actions en jetons écartées)")
    print(f"Tous les trades : {show(report['all'])}   (repère « aucun avantage » : environ −0,14 %)")
    print("Pour chaque condition : les trades pris quand elle est vraie, ceux pris quand elle est fausse, et l'écart "
          "(fourchette durcie pour sept questions).")
    for name in CONDITIONS + WITNESSES:
        result = {g: compare(table[name][g], alpha if name in CONDITIONS else 0.025) for g in groups}
        report["conditions"][name] = result
        r = result["toutes"]
        print(f"\n{LABELS[name]}  ({r['share']:.0%} des trades où elle est connue ; connue pour {r['known'] / total:.0%})")
        print(f"   vraie  : {show(r['yes'])}\n   fausse : {show(r['no'])}")
        print(f"   écart  : {vrai.pct(r['diff'])} [{vrai.pct(r['lo'])} ; {vrai.pct(r['hi'])}] → {verdict(r)}")
        print("   par unité : " + " · ".join(f"{tf_label(tf)} {vrai.pct(result[f'unite:{tf}']['diff'])}" for tf in TIMEFRAMES))
        print("   " + " · ".join(f"{g} {vrai.pct(result[g]['diff'])} (vraie {vrai.pct(result[g]['yes']['mean'])})"
                                 for g in ("lectures", "indicateurs", "achat", "vente")))
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


def cells(args, name: str) -> dict:
    """Pour une période : par combinaison (unité × technique × sens) et par condition vraie ou fausse, les trades et
    leur somme, jour par jour. « seule » : la technique sans condition."""
    cache, folder = Path(args.cache), Path(args.cache) / name
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    ex = vrai.exchange()
    ex.load_markets()
    btc = trend_up(vrai.candles(ex, "BTC/USDT", "1h", meta["start"] - TEST_DAYS["1h"] * DAY, meta["end"], cache), HOUR)
    day0, days = meta["start"] // DAY - 1, meta["days"] + 4
    size = len(TIMEFRAMES) * len(LIBRARY) * 2
    keys = [("seule", 1)] + [(c, state) for c in CONDITIONS for state in (1, 0)]
    count, total = ({k: np.zeros((size, days)) for k in keys} for _ in range(2))
    for seed, symbol in enumerate(meta["symbols"]):
        path = folder / f"rows-{safe(symbol)}.npz"
        if not path.exists():
            continue
        rows = np.load(path)
        if not len(rows["net"]):
            continue
        cond = conditions(symbol, rows, cache, folder, ex, btc, seed, meta["start"], meta["end"])
        cell = (rows["tf"].astype(np.int64) * len(LIBRARY) + rows["tech"]) * 2 + rows["short"]
        day, net = np.clip(rows["out"] // DAY - day0, 0, days - 1), rows["net"]
        for key in keys:
            pick = np.ones(len(net), bool) if key[0] == "seule" else cond[key[0]] == key[1]
            np.add.at(count[key], (cell[pick], day[pick]), 1)
            np.add.at(total[key], (cell[pick], day[pick]), net[pick])
    return {"count": count, "total": total, "keys": keys, "size": size, "meta": meta}


def cell_name(cell: int, key: tuple) -> str:
    short, rest = cell % 2, cell // 2
    tech, tf = rest % len(LIBRARY), rest // len(LIBRARY)
    extra = "" if key[0] == "seule" else f" + {LABELS[key[0]].lower()} : {'oui' if key[1] else 'non'}"
    return f"{LIBRARY[tech]} · {tf_label(TIMEFRAMES[tf])} · {'vente' if short else 'achat'}{extra}"


def cell_stat(data: dict, key: tuple, cell: int, alpha: float = 0.025) -> dict:
    groups = [(n, t) for n, t in zip(data["count"][key][cell], data["total"][key][cell]) if n > 0]
    n = int(sum(g[0] for g in groups))
    mean, lo, hi = clustered_bounds(groups, alpha) if groups else (math.nan, math.nan, math.nan)
    return {"n": n, "mean": mean, "lo": lo, "hi": hi}


def matrice(args) -> None:
    """Chercher large sur une période, ne croire que ce qui se confirme sur l'autre. Une combinaison est « candidate »
    si, sur la période de recherche, elle a au moins MIN_CELL trades et une fourchette à 95 % entièrement positive
    (frais compris). Elle est « confirmée » si, sur l'autre période, sa fourchette durcie par le nombre de candidates
    est encore entièrement positive."""
    first, second = cells(args, args.decouverte), cells(args, args.confirmation)
    report = {}
    for label, search, check in (("aller", first, second), ("retour", second, first)):
        measured, positive, candidates = 0, 0, []
        for key in search["keys"]:
            for cell in range(search["size"]):
                a = cell_stat(search, key, cell)
                if a["n"] < MIN_CELL:
                    continue
                measured += 1
                positive += a["mean"] > 0
                if math.isfinite(a["lo"]) and a["lo"] > 0:
                    candidates.append((key, cell, a))
        alpha = 0.025 / max(len(candidates), 1)
        rows = []
        for key, cell, a in candidates:
            b, plain = cell_stat(check, key, cell, alpha), cell_stat(check, key, cell)
            rows.append({"name": cell_name(cell, key), "a": a, "b": b, "b95": plain,
                         "confirmed": bool(b["n"] >= MIN_CELL // 3 and math.isfinite(b["lo"]) and b["lo"] > 0)})
        judged = [r for r in rows if r["b"]["n"] >= MIN_CELL // 3]
        period = lambda d: (f"{pd.to_datetime(d['meta']['start'], unit='ms'):%d/%m} → "  # noqa: E731
                            f"{pd.to_datetime(d['meta']['end'], unit='ms'):%d/%m}")
        print(f"\n=== Recherche sur {period(search)}, confirmation sur {period(check)} ===")
        print(f"combinaisons avec au moins {MIN_CELL} trades : {measured} · moyenne positive après frais : {positive} · "
              f"candidates (fourchette à 95 % toute positive) : {len(candidates)}")
        print(f"sur l'autre période : {len(judged)} jugées · encore positives en moyenne : "
              f"{sum(r['b']['mean'] > 0 for r in judged)} · CONFIRMÉES (fourchette durcie toute positive) : "
              f"{sum(r['confirmed'] for r in rows)}")
        best = sorted(judged, key=lambda r: -(r["b"]["mean"]))[:12]
        for r in sorted(rows, key=lambda r: (-r["confirmed"], -r["a"]["mean"]))[:8] + [x for x in best if x["confirmed"]]:
            a, b = r["a"], r["b95"]
            print(f"  {'CONFIRMÉE ' if r['confirmed'] else ''}{r['name']}\n      recherche : {a['n']} trades {vrai.pct(a['mean'])} "
                  f"[{vrai.pct(a['lo'])} ; {vrai.pct(a['hi'])}] · autre période : {b['n']} trades {vrai.pct(b['mean'])} "
                  f"[{vrai.pct(b['lo'])} ; {vrai.pct(b['hi'])}]")
        report[label] = {"measured": measured, "positive": int(positive), "candidates": len(candidates),
                         "judged": len(judged), "still_positive": int(sum(r["b"]["mean"] > 0 for r in judged)),
                         "confirmed": [r for r in rows if r["confirmed"]], "rows": rows}
    # Les deux périodes réunies : ce qui ressort le plus, à titre indicatif (seuil durci par le nombre de combinaisons)
    days_a = first["count"][("seule", 1)].shape[1]
    pooled = []
    for key in first["keys"]:
        both_n = np.concatenate([first["count"][key], second["count"][key]], axis=1)
        both_t = np.concatenate([first["total"][key], second["total"][key]], axis=1)
        for cell in np.flatnonzero(both_n.sum(axis=1) >= 2 * MIN_CELL):
            groups = [(n, t) for n, t in zip(both_n[cell], both_t[cell]) if n > 0]
            mean, lo, hi = clustered_bounds(groups)
            pooled.append((mean, lo, hi, int(both_n[cell].sum()), key, int(cell), groups))
    hard = 0.025 / max(len(pooled), 1)
    pooled.sort(key=lambda r: -r[0])
    proven = [r for r in pooled if clustered_bounds(r[6], hard)[1] > 0]
    print(f"\n=== Les deux périodes réunies ({days_a - 4} + {second['count'][('seule', 1)].shape[1] - 4} jours) ===")
    print(f"combinaisons avec au moins {2 * MIN_CELL} trades : {len(pooled)} · moyenne positive après frais : "
          f"{sum(r[0] > 0 for r in pooled)} · fourchette à 95 % toute positive : {sum(r[1] > 0 for r in pooled)} "
          f"(attendu par chance : environ {0.025 * len(pooled):.0f}) · prouvées au seuil durci : {len(proven)}")
    print("Les 15 qui ressortent le plus (indicatif) :")
    for mean, lo, hi, n, key, cell, _ in pooled[:15]:
        print(f"  {cell_name(cell, key)}\n      {n} trades {vrai.pct(mean)} [{vrai.pct(lo)} ; {vrai.pct(hi)}]")
    report["pooled"] = {"measured": len(pooled), "positive": int(sum(r[0] > 0 for r in pooled)),
                        "ci_positive": int(sum(r[1] > 0 for r in pooled)), "proven": len(proven),
                        "top": [{"name": cell_name(c, k), "n": n, "mean": m, "lo": lo, "hi": hi}
                                for m, lo, hi, n, k, c, _ in pooled[:40]], "units": {}}
    print("\nPar unité de temps (les deux périodes réunies) : combinaisons jugées · gagnantes en moyenne · fourchette à 95 % "
          "toute positive (attendu par chance) · prouvées · puis les trois meilleures")
    for k, tf in enumerate(TIMEFRAMES):
        mine = [r for r in pooled if r[5] // 2 // len(LIBRARY) == k]
        if not mine:
            continue
        sure = [r for r in mine if r[1] > 0]
        print(f"  {tf_label(tf)} : {len(mine)} · {sum(r[0] > 0 for r in mine)} · {len(sure)} ({0.025 * len(mine):.0f}) · "
              f"{sum(1 for r in mine if r in proven)}")
        for mean, lo, hi, n, key, cell, _ in mine[:3]:
            print(f"      {cell_name(cell, key)} : {n} trades {vrai.pct(mean)} [{vrai.pct(lo)} ; {vrai.pct(hi)}]")
        report["pooled"]["units"][tf] = {"measured": len(mine), "positive": int(sum(r[0] > 0 for r in mine)),
                                         "ci_positive": len(sure), "proven": sum(1 for r in mine if r in proven),
                                         "top": [{"name": cell_name(c, key), "n": n, "mean": m, "lo": lo, "hi": hi}
                                                 for m, lo, hi, n, key, c, _ in mine[:5]]}
    if args.sortie:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
        print(f"\nDétail écrit dans {args.sortie}")


def line(groups, wins) -> dict:
    n = sum(g[0] for g in groups)
    mean, lo, hi = clustered_bounds(groups)
    clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
    return {"n": int(n), "mean": clean(mean), "lo": clean(lo), "hi": clean(hi), "win": wins / n if n else None}


def compare(rows: np.ndarray, alpha: float) -> dict:
    """`rows` : par jour, [trades, somme, gagnants] quand la condition est vraie, puis quand elle est fausse."""
    yes, no = line([(r[0], r[1]) for r in rows], rows[:, 2].sum()), line([(r[3], r[4]) for r in rows], rows[:, 5].sum())
    pairs = [(r[0], r[1], r[3], r[4]) for r in rows]
    diff, lo, hi = paired_bounds(pairs, alpha)
    _, lo95, hi95 = paired_bounds(pairs)  # la fourchette simple à 95 % : pour UNE question posée d'avance
    clean = lambda x: x if math.isfinite(x) else None  # noqa: E731
    known_n = yes["n"] + no["n"]
    return {"yes": yes, "no": no, "diff": clean(diff), "lo": clean(lo), "hi": clean(hi), "lo95": clean(lo95),
            "hi95": clean(hi95), "known": known_n, "share": yes["n"] / known_n if known_n else 0.0}


def show(m: dict) -> str:
    span = f"[{vrai.pct(m['lo'])} ; {vrai.pct(m['hi'])}]" if m["lo"] is not None else ""
    wins = "" if m["win"] is None else f"{100 * m['win']:.0f} % gagnants"
    return f"{m['n']:>8} trades  {vrai.pct(m['mean'])} {span}  {wins}"


def verdict(r: dict) -> str:
    if r["diff"] is None or r["lo"] is None:
        return "pas assez de données"
    if r["lo"] > 0:
        return ("les trades pris avec elle font mieux, ET ils gagnent après frais" if (r["yes"]["lo"] or -1) > 0 else
                "les trades pris avec elle font nettement mieux, mais perdent encore après frais")
    if r["hi"] < 0:
        return "les trades pris avec elle font nettement moins bien"
    return "pas de différence nette"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("trades", "donnees", "mesure", "matrice"):
        p = sub.add_parser(name)
        p.add_argument("--cache", default=vrai.CACHE, help="dossier des bougies déjà téléchargées (hors du dépôt)")
        p.add_argument("--dossier", default="contexte", help="sous-dossier de cette mesure (une période = un dossier)")
        if name == "trades":
            p.add_argument("--jours", type=int, default=14)
            p.add_argument("--fin", type=int, default=0, help="fin de la période, en millisecondes (défaut : maintenant)")
            p.add_argument("--cryptos", type=int, default=60)
            p.add_argument("--coeurs", type=int, default=3)
            p.add_argument("--unites", default=",".join(TIMEFRAMES), help="unités mesurées, par exemple 1h,4h")
        if name == "donnees":
            p.add_argument("--unites", default=",".join(TIMEFRAMES), help="unités dont on télécharge le flux")
            p.add_argument("--sans-carnet", dest="sans_carnet", action="store_true")
        if name in ("mesure", "matrice"):
            p.add_argument("--sortie", default="")
        if name == "matrice":
            p.add_argument("--decouverte", default="contexte", help="dossier de la période où l'on cherche")
            p.add_argument("--confirmation", default="contexte-b", help="dossier de la période où l'on confirme")
    args = parser.parse_args()
    {"trades": trades, "donnees": donnees, "mesure": mesure, "matrice": matrice}[args.command](args)


if __name__ == "__main__":
    main()
