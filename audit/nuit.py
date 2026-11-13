"""La nuit de recherche du 13 au 14/11/2026 : « toutes les stratégies possibles », mesurées franchement.

Demande de l'utilisateur : ne plus attendre qu'il nomme chaque idée, pousser l'effort au maximum. Ce fichier mesure,
hors des bots (rien n'est changé dans les bots ni sur le site, rien n'est écrit dans `data/`), les familles de
stratégies qui n'avaient pas encore été mesurées. Chaque étude a son protocole écrit ICI, dans sa fonction, et
enregistré dans git AVANT son premier calcul.

LA MÉTHODE, LA MÊME POUR TOUTES LES ÉTUDES :
- De vrais prix (Binance : bougies d'un jour de toutes les paires USDT depuis 2020, retirées de la cote comprises ;
  archives des contrats à terme pour le financement). Des règles fixées d'avance, avec des seuils ronds.
- Deux périodes : on cherche avant le 01/01/2024, on confirme après. Rien n'est retenu sur une seule période.
- Le verdict, le même partout : « TIENT » = positif avec une fourchette à 95 % toute positive sur la période de
  recherche ET sur celle de confirmation (la fourchette compare les mois entre eux : `risk.clustered_bounds`) ;
  « piste » = positif en moyenne sur les deux périodes, sans cette netteté ; « rien » sinon. Exiger la netteté deux
  fois laisse passer moins d'un essai au hasard sur mille : on peut donc essayer beaucoup de règles.
- Des frais réalistes, à deux niveaux : ceux des bots (0,07 % par ordre sur les contrats à terme, 0,15 % au
  comptant) et des frais « durs » pour les petites cryptos (0,30 % par ordre : sur une crypto qui s'envole, on
  n'obtient pas le prix affiché).
- Le résultat en argent composé (ce que devient 1), avec la pire baisse en route : une moyenne peut cacher une ruine.

    python audit/nuit.py donnees                 # télécharge le financement de tous les contrats (une fois)
    python audit/nuit.py tendance | mouvements | croise | cotations | paire | financement | heures
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import long as longterm  # noqa: E402
import vrai  # noqa: E402
from tradingbot import trend  # noqa: E402
from tradingbot.execution import FUTURES  # noqa: E402
from tradingbot.risk import clustered_bounds  # noqa: E402

DAY = trend.DAY_MS
START, CUT = "2020-01-01", "2024-01-01"  # avant la coupure : on cherche ; après : on confirme
PERP = FUTURES.fee_rate + FUTURES.slippage  # un ordre sur un contrat à terme, frais des bots : 0,07 %
SPOT = trend.SPOT.fee_rate + trend.SPOT.slippage  # un ordre au comptant : 0,15 %
HARD = 0.003  # un ordre « dur » sur une petite crypto agitée : 0,30 %
LISTING = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
ARCHIVE = "https://data.binance.vision/"
FUNDING = "data/futures/um/monthly/fundingRate/"
LOCAL = threading.local()


def ms(day: str) -> int:
    return int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)


# --- les données ---------------------------------------------------------------------------------------------------

def session():
    """Une connexion par fil (celle de la bibliothèque installée avec ccxt : proxy et certificat de l'environnement)."""
    if not hasattr(LOCAL, "session"):
        import requests
        LOCAL.session = requests.Session()
    return LOCAL.session


def listing(prefix: str) -> tuple[list[str], list[str]]:
    """Les dossiers et les fichiers rangés sous un préfixe des archives de Binance (toutes les pages)."""
    folders, files, marker = [], [], ""
    while True:
        text = session().get(LISTING, params={"delimiter": "/", "prefix": prefix, "marker": marker}, timeout=60).text
        folders += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>", text)
        files += re.findall(r"<Key>([^<]+)</Key>", text)
        if "<IsTruncated>true" not in text:
            return folders, files
        marker = (re.findall(r"<NextMarker>([^<]+)</NextMarker>", text) or [(folders + files)[-1]])[0]


def _funding_job(args) -> tuple[str, int | str]:
    contract, folder = args
    path = folder / f"{contract}.pkl"
    if path.exists():
        return contract, len(pd.read_pickle(path))
    try:
        _, files = listing(f"{FUNDING}{contract}/")
        parts = []
        for key in sorted(k for k in files if k.endswith(".zip")):
            raw = session().get(ARCHIVE + key, timeout=60).content
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                parts.append(pd.read_csv(io.BytesIO(archive.read(archive.namelist()[0]))))
        if not parts:
            return contract, "aucun fichier"
        table = pd.concat(parts)
        rates = pd.Series(table["last_funding_rate"].to_numpy(dtype=float),
                          index=table["calc_time"].to_numpy(dtype="int64")).sort_index()
        rates[~rates.index.duplicated()].to_pickle(path)
        return contract, len(rates)
    except Exception as exc:  # un contrat qui ne répond pas : dit, et ignoré
        return contract, f"{type(exc).__name__} {str(exc)[:60]}"


def donnees(args) -> None:
    """Le financement de tous les contrats perpétuels en USDT (archives mensuelles), gardé un fichier par contrat."""
    folder = Path(args.cache) / "financement"
    folder.mkdir(parents=True, exist_ok=True)
    folders, _ = listing(FUNDING)
    contracts = sorted(f.rstrip("/").split("/")[-1] for f in folders)
    contracts = [c for c in contracts if c.endswith("USDT")]  # ni USDC, ni contrats à échéance (BTCUSDT_240329)
    print(f"{len(contracts)} contrats perpétuels en USDT dans les archives", flush=True)
    done = failed = 0
    with ThreadPoolExecutor(args.fils) as pool:
        for k, (contract, result) in enumerate(pool.map(_funding_job, [(c, folder) for c in contracts]), 1):
            done, failed = done + isinstance(result, int), failed + isinstance(result, str)
            if isinstance(result, str):
                print(f"  {contract} : {result}", flush=True)
            if k % 50 == 0:
                print(f"  {k}/{len(contracts)} contrats", flush=True)
    print(f"financement : {done} contrats gardés, {failed} sans réponse", flush=True)


def funding(contract: str, cache: Path) -> pd.Series | None:
    """Le financement d'un contrat : un taux par échéance (ms), positif = les acheteurs paient les vendeurs."""
    path = cache / "financement" / f"{contract}.pkl"
    return pd.read_pickle(path) if path.exists() else None


def daily_funding(contract: str, cache: Path) -> pd.Series | None:
    """La somme des taux de chaque jour (jour en ms, à 00:00 UTC) : ce qu'un vendeur encaisse en tenant la journée."""
    rates = funding(contract, cache)
    if rates is None or not len(rates):
        return None
    return rates.groupby(rates.index // DAY * DAY).sum()


def daily_frames(cache: Path) -> dict[str, pd.DataFrame]:
    """Les bougies d'un jour de toutes les paires USDT au comptant depuis 2020, retirées de la cote comprises."""
    ex = vrai.exchange()
    ex.load_markets()
    return longterm.load(ex, ms(START), ex.fetch_time() // DAY * DAY, cache)


def major(symbol: str, cache: Path) -> pd.DataFrame:
    """Le Bitcoin ou l'Ether depuis leur première cotation (2017), comme le bot de tendance."""
    ex = vrai.exchange()
    ex.load_markets()
    return vrai.candles(ex, symbol, "1d", trend.EARLY_MS, ex.fetch_time() // DAY * DAY, cache).reset_index(drop=True)


def contract_of(symbol: str, cache: Path) -> str | None:
    """Le contrat perpétuel d'une crypto (les très petits prix sont cotés par mille : 1000PEPEUSDT)."""
    base = symbol.split("/")[0]
    for name in (f"{base}USDT", f"1000{base}USDT", f"1000000{base}USDT"):
        if (cache / "financement" / f"{name}.pkl").exists():
            return name
    return None


# --- juger : la même façon pour toutes les études ---------------------------------------------------------------

def month_of(index) -> np.ndarray:
    stamps = pd.to_datetime(np.asarray(index, dtype="int64"), unit="ms", utc=True)
    return (stamps.year * 12 + stamps.month).to_numpy()


def bounds(values, index) -> dict:
    """La moyenne et sa fourchette à 95 %, en comparant les mois entre eux (un mois = un groupe)."""
    values, groups = np.asarray(values, dtype=float), month_of(index)
    table = pd.DataFrame({"g": groups, "v": values}).groupby("g")["v"].agg(["count", "sum"])
    mean, low, high = clustered_bounds(list(zip(table["count"], table["sum"])))
    return {"n": int(len(values)), "mean": mean, "low": low, "high": high,
            "wins": float((values > 0).mean()) if len(values) else math.nan}


def compound(values) -> dict:
    """Ce que devient 1 quand ces résultats s'enchaînent, et la pire baisse en route (−100 % = ruiné)."""
    path = np.cumprod(np.maximum(1 + np.asarray(values, dtype=float), 0.0))
    if not len(path):
        return {"total": 1.0, "worst": 0.0}
    return {"total": float(path[-1]), "worst": float((path / np.maximum.accumulate(np.maximum(path, 1e-300)) - 1).min())}


def judge(values, index, cut: int = ms(CUT), chain: bool = True) -> dict:
    """Une série de résultats (par jour, ou par trade) coupée en deux périodes, et son verdict."""
    values, index = np.asarray(values, dtype=float), np.asarray(index, dtype="int64")
    keep = np.isfinite(values)
    values, index = values[keep], index[keep]
    out = {}
    for name, mask in (("recherche", index < cut), ("confirmation", index >= cut)):
        out[name] = {**bounds(values[mask], index[mask]), **(compound(values[mask]) if chain else {})}
    a, b = out["recherche"], out["confirmation"]
    clear = lambda m: m["n"] > 0 and m["low"] == m["low"] and m["low"] > 0  # noqa: E731
    positive = lambda m: m["n"] > 0 and m["mean"] > 0  # noqa: E731
    out["verdict"] = "TIENT" if clear(a) and clear(b) else "piste" if positive(a) and positive(b) else "rien"
    return out


def show(title: str, result: dict, unit: str = "par jour") -> str:
    def part(m: dict) -> str:
        if not m["n"]:
            return "rien à mesurer"
        span = f"(de {100 * m['low']:+.3f} à {100 * m['high']:+.3f})" if m["low"] == m["low"] else ""
        chain = f" · ×{m['total']:.2f} (pire baisse {100 * m['worst']:+.0f} %)" if "total" in m else ""
        return f"{100 * m['mean']:+.3f} % {unit} {span} · {m['n']} · {100 * m['wins']:.0f} % gagnants{chain}"
    return (f"  {title}\n      recherche    : {part(result['recherche'])}\n      confirmation : "
            f"{part(result['confirmation'])}\n      → {result['verdict']}")


# --- étude 1 : la règle de tendance dans les deux sens --------------------------------------------------------------

KINDS = {"hausse seule (le bot)": lambda level: level / 3, "baisse seule": lambda level: -(3 - level) / 3,
         "hausse et baisse": lambda level: (2 * level - 3) / 3}


def trend_days(close: np.ndarray, fund_next: np.ndarray, kind: str, cost: float = SPOT) -> np.ndarray:
    """Le résultat de chaque jour d'une variante de la règle de tendance sur une crypto. Décidé à la clôture du jour
    t, tenu du soir t au soir t+1 ; la part change au prix de la clôture (marché ouvert jour et nuit), frais sur ce qui
    change ; une vente à découvert encaisse le financement du jour (ou le paie s'il est négatif). NaN avant que les
    trois moyennes existent, et le dernier jour (pas de lendemain)."""
    level = trend.levels(close).astype(float)
    share = np.where(level >= 0, KINDS[kind](np.maximum(level, 0)), 0.0)
    move = np.append(close[1:] / close[:-1] - 1, np.nan)
    turn = np.abs(np.diff(np.concatenate(([0.0], share))))
    out = share * move - cost * turn + np.maximum(-share, 0) * fund_next
    out[level < 0] = np.nan
    return out


def next_funding(index: np.ndarray, contract: str | None, cache: Path) -> np.ndarray:
    """Pour chaque jour t, le financement encaissé par un vendeur pendant le jour t+1 (0 quand il est inconnu)."""
    rates = daily_funding(contract, cache) if contract else None
    if rates is None:
        return np.zeros(len(index))
    return rates.reindex(np.asarray(index, dtype="int64") + DAY).fillna(0.0).to_numpy()


def tendance(args) -> dict:
    """LA RÈGLE DE TENDANCE DANS LES DEUX SENS (demande : « ce serait plus jouable »).
    Protocole, fixé avant le calcul :
    - la règle du bot, inchangée : à chaque clôture, N = le nombre de moyennes (50, 100, 200 jours) sous le prix ;
    - trois variantes : « hausse seule » tient N/3 (le bot) ; « baisse seule » vend à découvert (3 − N)/3 ; « hausse
      et baisse » tient (2N − 3)/3, de −1 (tout vendu à découvert) à +1 (tout acheté) ;
    - frais : 0,15 % sur chaque changement de part (ceux du bot : plus que le vrai prix d'un contrat à terme) ; la
      vente à découvert encaisse le vrai financement du contrat (archives ; 0 avant qu'elles existent) ;
    - marchés : le Bitcoin et l'Ether depuis 2018 ; puis un panier : chaque jour, les 20 cryptos les plus échangées
      (connues la veille), un vingtième du compte chacune, chacune avec sa propre règle ;
    - en plus, pour le Bitcoin et l'Ether, le test du mélange (1 000 fois les mêmes journées dans le désordre) : la
      variante finit-elle plus haut sur le vrai marché que sur ses mélanges ?"""
    cache, out = Path(args.cache), {"majors": {}, "basket": {}}
    print("ÉTUDE 1 — LA RÈGLE DE TENDANCE DANS LES DEUX SENS (frais 0,15 % par changement, financement réel pour les ventes)")
    for symbol in trend.SYMBOLS:
        frame = major(symbol, cache)
        ts, close = frame["ts"].to_numpy(dtype="int64"), frame["close"].to_numpy(dtype=float)
        fund = next_funding(ts, contract_of(symbol, cache), cache)
        hold = np.append(close[1:] / close[:-1] - 1, np.nan)
        hold[:max(trend.AVERAGES) - 1] = np.nan
        print(f"\n{symbol} · depuis le {longterm_day(ts[max(trend.AVERAGES)])}")
        print(show("acheter et garder", judge(hold, ts)))
        rng, steps = np.random.default_rng(7), np.diff(np.log(close))
        for kind in KINDS:
            days = trend_days(close, fund, kind)
            result = judge(days, ts)
            bare = trend_days(close, np.zeros(len(close)), kind)  # sans financement, comme les mélanges
            real = compound(bare[np.isfinite(bare)])["total"]
            mixed = []
            for _ in range(1000):  # les mêmes journées dans le désordre : plus aucune tendance, même prix d'arrivée
                path = close[0] * np.exp(np.concatenate(([0.0], np.cumsum(rng.permutation(steps)))))
                d = trend_days(path, np.zeros(len(path)), kind)
                mixed.append(compound(d[np.isfinite(d)])["total"])
            result["shuffle"] = {"real": real, "median": float(np.median(mixed)), "beats": float((real > np.array(mixed)).mean())}
            whole = compound(days[np.isfinite(days)])
            print(show(kind, result))
            print(f"      tout : ×{whole['total']:.2f} (pire baisse {100 * whole['worst']:+.0f} %) · mieux que "
                  f"{100 * result['shuffle']['beats']:.1f} % des mélanges (médiane des mélanges ×{result['shuffle']['median']:.2f})")
            out["majors"][f"{symbol} {kind}"] = {**result, "whole": whole}
    frames = daily_frames(cache)
    member, _ = longterm.universe(frames, 20)
    index = member.index.to_numpy(dtype="int64")
    print(f"\nLe panier : chaque jour les 20 cryptos les plus échangées, un vingtième chacune ({len(frames)} paires lues)")
    totals = {kind: np.zeros(len(index)) for kind in KINDS}
    hold_total, counted = np.zeros(len(index)), np.zeros(len(index))
    for symbol, frame in frames.items():
        if symbol not in member.columns or not member[symbol].any() or len(frame) <= max(trend.AVERAGES):
            continue
        ts, close = frame["ts"].to_numpy(dtype="int64"), frame["close"].to_numpy(dtype=float)
        inside = member[symbol].reindex(ts).fillna(False).to_numpy(dtype=bool)
        fund = next_funding(ts, contract_of(symbol, cache), cache)
        where = np.searchsorted(index, ts)
        move = np.append(close[1:] / close[:-1] - 1, np.nan)
        ready = inside & np.isfinite(move) & (trend.levels(close) >= 0)
        hold_total[where[ready]] += move[ready] / 20
        counted[where[ready]] += 1
        for kind in KINDS:
            days = trend_days(close, fund, kind)
            # la crypto n'est tenue que les jours où elle fait partie des 20 ; en sortir ou y entrer coûte un ordre
            share = np.where(trend.levels(close) >= 0, KINDS[kind](np.maximum(trend.levels(close).astype(float), 0)), 0.0)
            edge = np.abs(np.diff(np.concatenate(([False], inside)).astype(float))) * np.abs(share) * SPOT
            totals[kind][where[ready]] += (days[ready] - edge[ready]) / 20
    live = counted > 0
    print(show("le panier simplement gardé (les 20, à parts égales)", judge(hold_total[live], index[live])))
    for kind in KINDS:
        result = judge(totals[kind][live], index[live])
        whole = compound(totals[kind][live])
        print(show(kind, result))
        print(f"      tout : ×{whole['total']:.2f} (pire baisse {100 * whole['worst']:+.0f} %)")
        out["basket"][kind] = {**result, "whole": whole}
    return out


def longterm_day(stamp: int) -> str:
    return pd.Timestamp(int(stamp), unit="ms", tz="UTC").strftime("%d/%m/%Y")


# --- étude 2 : les gros mouvements des petites cryptos ----------------------------------------------------------------

JUMPS, SURGE, MIN_MONEY, HORIZONS, TRAILS, MAX_DAYS = (0.20, 0.30, 0.50), 3.0, 1e6, (1, 3, 7), (0.15, 0.30), 30


def after_jump(frame: pd.DataFrame, at: int, side: int) -> dict:
    """Ce que rapporte une entrée à la clôture du jour `at` (avant frais, sans levier) : à 1, 3 et 7 jours, puis avec un
    stop suiveur à 15 % et à 30 % du meilleur prix de clôture (30 jours au plus). `side` : +1 acheter (suivre le
    mouvement), −1 vendre à découvert (parier sur la retombée). Une vente à découvert dont le prix double est
    liquidée (−100 %). Une crypto retirée de la cote sort à son dernier prix."""
    opens, highs, lows, closes = (frame[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    entry, last, out = closes[at], len(closes) - 1, {}
    for days in HORIZONS:
        end = min(at + days, last)
        result = side * (closes[end] / entry - 1)
        if side < 0 and highs[at + 1:end + 1].size and highs[at + 1:end + 1].max() >= 2 * entry:
            result = -1.0
        out[f"{days} j"] = result
    for trail in TRAILS:
        best, result = entry, None
        for day in range(at + 1, min(at + MAX_DAYS, last) + 1):
            if side > 0:
                stop = best * (1 - trail)
                if lows[day] <= stop:
                    result = min(stop, opens[day]) / entry - 1  # une ouverture sous le stop : vendu à l'ouverture
                    break
                best = max(best, closes[day])
            else:
                stop = best * (1 + trail)
                if highs[day] >= stop:
                    result = max(-1.0, -(max(stop, opens[day]) / entry - 1))
                    break
                best = min(best, closes[day])
        if result is None:
            result = side * (closes[min(at + MAX_DAYS, last)] / entry - 1)
        out[f"stop suiveur {100 * trail:.0f} %"] = result
    return out


def mouvements(args) -> dict:
    """LES GROS MOUVEMENTS (idée de l'utilisateur : « rentrer dès qu'il y a un gros mouvement », stop suiveur, levier).
    Protocole, fixé avant le calcul :
    - un « gros mouvement » : une crypto qui prend au moins 20 %, 30 % ou 50 % dans la journée, avec un volume d'au
      moins 3 fois sa moyenne des 30 jours d'avant, et au moins 1 million de dollars échangés par jour en moyenne sur
      ces 30 jours (tout est connu à la clôture) ; toutes les paires USDT, retirées de la cote comprises ;
    - l'entrée : à la clôture de cette journée. Deux sens : suivre (acheter) ou parier sur la retombée (vendre à
      découvert) ;
    - la sortie : après 1, 3 ou 7 jours ; ou par un stop suiveur à 15 % ou 30 % du meilleur prix (30 jours au plus) ;
    - les frais : deux ordres à 0,07 % (ceux des bots), puis à 0,30 % (« durs ») ; le financement n'est pas compté
      (inconnu sur ces cryptos ce jour-là : en général, il coûte au vendeur après une envolée) ;
    - le levier : pour les sorties avec stop, celui qui garde la liquidation derrière le stop (×5,8 à 15 %, ×3 à 30 %).
    30 façons de faire (3 seuils × 2 sens × 5 sorties) : seules comptent celles qui tiennent sur les deux périodes."""
    cache = Path(args.cache)
    frames = daily_frames(cache)
    rows = []
    for symbol, frame in frames.items():
        closes = frame["close"].to_numpy(dtype=float)
        money = (frame["close"] * frame["volume"]).to_numpy(dtype=float)
        ts = frame["ts"].to_numpy(dtype="int64")
        if len(closes) < 40:
            continue
        usual = pd.Series(money).rolling(30).mean().shift(1).to_numpy()
        jump = np.concatenate(([0.0], closes[1:] / closes[:-1] - 1))
        for at in np.flatnonzero((jump >= JUMPS[0]) & (money >= SURGE * usual) & (usual >= MIN_MONEY)):
            if at >= len(closes) - 1:
                continue
            for side in (1, -1):
                rows.append({"symbol": symbol, "ts": int(ts[at]), "jump": float(jump[at]), "side": side,
                             **after_jump(frame, int(at), side)})
    table = pd.DataFrame(rows)
    events = table[table["side"] == 1]
    print(f"ÉTUDE 2 — LES GROS MOUVEMENTS : {len(events)} journées à +20 % ou plus avec un volume triplé, sur "
          f"{events['symbol'].nunique()} cryptos ({(events['ts'] < ms(CUT)).sum()} avant 2024, {(events['ts'] >= ms(CUT)).sum()} depuis)")
    out, exits = {}, [f"{d} j" for d in HORIZONS] + [f"stop suiveur {100 * t:.0f} %" for t in TRAILS]
    for cost, cost_name in ((PERP, "frais des bots (0,07 % par ordre)"), (HARD, "frais durs (0,30 % par ordre)")):
        print(f"\n--- {cost_name} ---")
        for jump in JUMPS:
            for side, side_name in ((1, "SUIVRE (acheter)"), (-1, "PARIER SUR LA RETOMBÉE (vendre à découvert)")):
                part = table[(table["jump"] >= jump) & (table["side"] == side)]
                print(f"\n{side_name} après +{100 * jump:.0f} % ou plus · {len(part)} entrées")
                for name in exits:
                    net = part[name].to_numpy(dtype=float) - 2 * cost
                    result = judge(np.maximum(net, -1.0), part["ts"].to_numpy(), chain=False)
                    line = show(name, result, "par trade")
                    if name.startswith("stop"):
                        trail = float(name.split()[-2]) / 100
                        lever = 0.9 / (trail + 0.005)
                        geared = np.maximum(lever * net, -1.0)
                        line += f" · avec levier ×{lever:.1f} : {100 * geared.mean():+.2f} % par trade, {100 * (geared <= -1).mean():.0f} % de mises perdues en entier"
                    print(line)
                    out[f"{cost_name} | {side_name} | +{100 * jump:.0f} % | {name}"] = result
    return out


# --- étude 4 : acheter les perdantes, vendre les gagnantes (et l'inverse) ------------------------------------------------

def croise(args) -> dict:
    """ACHETER LES PERDANTES ET VENDRE LES GAGNANTES DE LA VEILLE (et l'inverse), sans dépendre du sens du marché.
    Protocole, fixé avant le calcul :
    - chaque jour, parmi les 50 cryptos les plus échangées (connues la veille), on classe selon la variation des 1, 3,
      7 ou 28 derniers jours ; « retour » : acheter les 10 qui ont le plus baissé et vendre à découvert les 10 qui ont
      le plus monté ; « élan » : l'inverse ; un dixième du compte par crypto de chaque côté (autant acheté que vendu) ;
    - tenu un jour, refait chaque soir à la clôture ; frais sur tout ce qui change : 0,07 % (bots), puis 0,30 % (durs) ;
      le financement n'est pas compté.
    8 façons de faire (4 durées × 2 sens), à deux niveaux de frais."""
    cache = Path(args.cache)
    frames = daily_frames(cache)
    member, _ = longterm.universe(frames, 50)
    close = pd.DataFrame({s: f.set_index("ts")["close"] for s, f in frames.items()}).sort_index().reindex(member.index)
    move = close.pct_change(fill_method=None).shift(-1)  # du soir t au soir t+1
    index = close.index.to_numpy(dtype="int64")
    print("ÉTUDE 4 — ACHETER LES PERDANTES, VENDRE LES GAGNANTES (les 50 cryptos les plus échangées de chaque jour)")
    out = {}
    for look in (1, 3, 7, 28):
        past = (close / close.shift(look) - 1).where(member)
        rank = past.rank(axis=1, ascending=True).to_numpy()
        count = past.notna().sum(axis=1).to_numpy()[:, None]
        enough = count >= 30
        low, high = (rank <= 10) & enough, (rank > count - 10) & enough
        weight = (low.astype(float) - high.astype(float)) / 10  # « retour » : +1/10 sur les perdantes, −1/10 sur les gagnantes
        gross = (weight * move.fillna(0.0).to_numpy()).sum(axis=1)
        turn = np.abs(np.diff(weight, axis=0, prepend=np.zeros((1, weight.shape[1])))).sum(axis=1)
        live = enough[:, 0] & np.isfinite(move.mean(axis=1).to_numpy())
        for sign, name in ((1, "retour (acheter les perdantes)"), (-1, "élan (acheter les gagnantes)")):
            for cost, cost_name in ((PERP, "frais des bots"), (HARD, "frais durs")):
                days = sign * gross - cost * turn
                result = judge(days[live], index[live])
                print(show(f"{name} sur {look} jour(s), {cost_name} · {turn[live].mean():.2f} fois le compte échangé par jour", result))
                out[f"{name} | {look} j | {cost_name}"] = result
    return out


# --- étude 5 : les nouvelles cotations ---------------------------------------------------------------------------------

def cotations(args) -> dict:
    """LES NOUVELLES COTATIONS : que fait une crypto après son arrivée sur la plateforme ?
    Protocole, fixé avant le calcul :
    - une « nouvelle cotation » : une paire USDT dont la première bougie vient au moins 60 jours après le début de nos
      données (donc arrivée depuis mars 2020), retirées de la cote comprises ;
    - on mesure sa variation de la clôture du 1er jour, ou du 7e, jusqu'à 30 et 90 jours plus tard, brute puis comparée
      au Bitcoin sur les mêmes jours ;
    - la stratégie jugée : vendre à découvert à cette clôture et racheter 30 ou 90 jours plus tard, deux ordres à
      0,30 % (frais durs), sans financement (souvent pas de contrat les premiers jours : théorique). Une vente dont
      le prix double est liquidée (−100 %).
    4 façons de faire (2 entrées × 2 durées)."""
    cache = Path(args.cache)
    frames = daily_frames(cache)
    bitcoin = frames["BTC/USDT"].set_index("ts")["close"]
    first_day = int(bitcoin.index[0])
    rows = []
    for symbol, frame in frames.items():
        ts = frame["ts"].to_numpy(dtype="int64")
        if ts[0] < first_day + 60 * DAY:
            continue
        closes, highs = frame["close"].to_numpy(dtype=float), frame["high"].to_numpy(dtype=float)
        for start in (0, 6):
            for days in (30, 90):
                end = start + days
                if end >= len(closes):
                    continue  # pas encore assez de jours, ou retirée de la cote avant : écartée (rare)
                raw = closes[end] / closes[start] - 1
                market = bitcoin.reindex([ts[start], ts[end]])
                versus = raw - (market.iloc[1] / market.iloc[0] - 1) if market.notna().all() else math.nan
                short = -1.0 if highs[start + 1:end + 1].max() >= 2 * closes[start] else -raw - 2 * HARD
                rows.append({"symbol": symbol, "ts": int(ts[start]), "start": start + 1, "days": days, "raw": raw,
                             "versus": versus, "short": short})
    table = pd.DataFrame(rows)
    print(f"ÉTUDE 5 — LES NOUVELLES COTATIONS : {table['symbol'].nunique()} cryptos arrivées depuis mars 2020")
    out = {}
    for (start, days), part in table.groupby(["start", "days"]):
        name = f"de la clôture du jour {start} à {days} jours plus tard"
        raw, versus = part["raw"].to_numpy(), part["versus"].to_numpy()
        print(f"\n{name} · {len(part)} cotations · variation médiane {100 * np.median(raw):+.0f} %, moyenne {100 * raw.mean():+.0f} % ; "
              f"contre le Bitcoin : médiane {100 * np.nanmedian(versus):+.0f} %, {100 * (versus < 0).mean():.0f} % font moins bien que lui")
        result = judge(part["short"].to_numpy(), part["ts"].to_numpy(), chain=False)
        print(show("vendre à découvert et racheter (frais durs, sans financement)", result, "par trade"))
        out[name] = result
    return out


# --- étude 8 : l'écart entre le Bitcoin et l'Ether ----------------------------------------------------------------------

def paire(args) -> dict:
    """L'ÉCART ENTRE L'ETHER ET LE BITCOIN : quand l'un s'écarte trop de l'autre, parier sur le retour.
    Protocole, fixé avant le calcul :
    - le rapport = prix de l'Ether / prix du Bitcoin, à la clôture de chaque jour ; son écart = (rapport − sa moyenne
      des 30 derniers jours) / sa dispersion sur ces 30 jours ;
    - écart au-dessus de +2 : vendre l'Ether à découvert et acheter autant de Bitcoin ; en dessous de −2 : l'inverse ;
      on sort quand l'écart revient à 0 ;
    - résultat par jour pour 1 placé de chaque côté ; frais : 0,07 % sur chacune des deux jambes à chaque changement.
    Une seule façon de faire (les réglages classiques des manuels : 30 jours, 2 écarts-types)."""
    cache = Path(args.cache)
    btc, eth = major("BTC/USDT", cache).set_index("ts")["close"], major("ETH/USDT", cache).set_index("ts")["close"]
    both = pd.concat([btc, eth], axis=1, keys=["btc", "eth"]).dropna()
    ratio = both["eth"] / both["btc"]
    gap = ((ratio - ratio.rolling(30).mean()) / ratio.rolling(30).std()).to_numpy()
    held, state = np.zeros(len(gap)), 0
    for i, z in enumerate(gap):  # +1 : Ether acheté et Bitcoin vendu ; −1 : l'inverse
        if not math.isfinite(z):
            state = 0
        elif state == 0:
            state = -1 if z > 2 else 1 if z < -2 else 0
        elif (state == -1 and z <= 0) or (state == 1 and z >= 0):
            state = 0
        held[i] = state
    spread = (both["eth"].pct_change() - both["btc"].pct_change()).shift(-1).to_numpy()
    days = held * spread - 2 * PERP * np.abs(np.diff(np.concatenate(([0.0], held))))
    index = both.index.to_numpy(dtype="int64")
    live = np.isfinite(gap) & np.isfinite(spread)
    result = judge(days[live], index[live])
    print("ÉTUDE 8 — L'ÉCART ENTRE L'ETHER ET LE BITCOIN (30 jours, 2 écarts-types, retour à 0)")
    print(show(f"parier sur le retour de l'écart · en position {100 * (held[live] != 0).mean():.0f} % du temps · "
               f"{int(np.abs(np.diff(held)).sum() / 2)} allers-retours", result))
    return {"paire": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("etude", choices=sorted(STUDIES))
    parser.add_argument("--cache", default=vrai.CACHE)
    parser.add_argument("--fils", type=int, default=16)
    parser.add_argument("--sortie", default="")
    args = parser.parse_args()
    began = time.time()
    report = STUDIES[args.etude](args)
    if args.sortie and report is not None:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n({args.etude} : {time.time() - began:.0f} s)", flush=True)


STUDIES = {"donnees": donnees, "tendance": tendance, "mouvements": mouvements, "croise": croise,
           "cotations": cotations, "paire": paire}

if __name__ == "__main__":
    main()
