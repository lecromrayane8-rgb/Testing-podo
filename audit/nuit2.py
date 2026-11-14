"""La suite de la nuit de recherche (14/11/2026) : sept mesures de plus, avec la méthode de `audit/nuit.py`.

Ce que la première partie n'avait pas mesuré : le portage du financement avec ses vrais comptes (la marge du contrat,
les remises à l'équilibre, la liquidation), l'idée de l'utilisateur à l'heure près (« rentrer dès qu'il y a un gros
mouvement »), le bot de grille, l'indice peur et avidité, les écarts de prix entre plateformes, les ordres passifs
(gagner l'écart entre acheteurs et vendeurs au lieu de le payer) et la prime de volatilité des options.

Comme dans `nuit.py` : hors des bots (rien n'est changé dans les bots ni sur le site, rien n'est écrit dans `data/`),
des règles fixées d'avance avec des seuils ronds, le protocole de chaque étude écrit dans sa fonction et enregistré
dans git AVANT son premier calcul, deux périodes quand l'historique le permet (on cherche avant le 01/01/2024, on
confirme après) et le même verdict : « TIENT » = fourchette à 95 % toute positive sur les deux périodes, « piste » =
positif en moyenne sur les deux, « rien » sinon. Trois études (écarts entre plateformes, ordres passifs, prime de
volatilité) n'ont que quelques jours ou quelques dizaines de mois de données : elles décrivent, et le disent.

    python audit/nuit2.py donnees      # bougies d'une heure de toutes les paires depuis 2020, 5 minutes de six cryptos
    python audit/nuit2.py portage | heure | grille | peur | ecarts | passif | volatilite
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nuit  # noqa: E402
import vrai  # noqa: E402
from nuit import ARCHIVE, CUT, DAY, HARD, PERP, SPOT, START, judge, ms, session, show  # noqa: E402
from tradingbot.data import make_exchange  # noqa: E402
from tradingbot.execution import FUTURES  # noqa: E402
from tradingbot.fleet import MAINTENANCE  # noqa: E402
from tradingbot.risk import clustered_bounds  # noqa: E402
from tradingbot.scanner import by_volume  # noqa: E402

HOUR, MINUTE = 3_600_000, 60_000
GRID_COINS = ("BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT")


# --- les données ---------------------------------------------------------------------------------------------------

def pairs(cache: Path) -> list[str]:
    """Les paires des études d'un jour (celles dont les bougies d'un jour sont dans le cache)."""
    return sorted(p.name[:-len("-1d.pkl")].replace("-", "/") for p in cache.glob("*-USDT-1d.pkl"))


def _candles_job(args) -> tuple[str, int | str]:
    symbol, tf, start, end, cache = args
    if not hasattr(nuit.LOCAL, "ex"):
        nuit.LOCAL.ex = vrai.exchange()
        nuit.LOCAL.ex.load_markets()
    try:
        return symbol, len(vrai.candles(nuit.LOCAL.ex, symbol, tf, start, end, cache))
    except Exception as exc:  # une paire qui ne répond pas : dite, et ignorée
        return symbol, f"{type(exc).__name__} {str(exc)[:60]}"


def donnees(args) -> None:
    """Les bougies d'une heure de toutes les paires USDT depuis 2020 (étude « heure ») et les bougies de 5 minutes de
    six grandes cryptos (étude « grille »), par le miroir public de Binance, gardées dans le cache."""
    cache = Path(args.cache)
    end = vrai.exchange().fetch_time() // HOUR * HOUR
    jobs = ([(s, "5m", ms(START), end, cache) for s in GRID_COINS]
            + [(s, "1h", ms(START), end, cache) for s in pairs(cache)])
    done = failed = rows = 0
    with ThreadPoolExecutor(args.fils) as pool:
        for k, (symbol, result) in enumerate(pool.map(_candles_job, jobs), 1):
            if isinstance(result, str):
                failed += 1
                print(f"  {symbol} : {result}", flush=True)
            else:
                done, rows = done + 1, rows + result
            if k % 50 == 0:
                print(f"  {k}/{len(jobs)} séries · {rows / 1e6:.1f} millions de bougies", flush=True)
    print(f"bougies : {done} séries gardées ({rows / 1e6:.1f} millions de bougies), {failed} sans réponse", flush=True)


def brief(title: str, result: dict, unit: str = "par trade") -> str:
    """Une étude en une ligne (quand il y en a des dizaines)."""
    def part(m: dict) -> str:
        if not m["n"]:
            return "rien à mesurer"
        span = f" ({100 * m['low']:+.3f} à {100 * m['high']:+.3f})" if m["low"] == m["low"] else ""
        return f"{100 * m['mean']:+.3f} %{span} n={m['n']}"
    return (f"  [{result['verdict']:>5}] {title} · recherche {part(result['recherche'])} · "
            f"confirmation {part(result['confirmation'])} {unit}")


# --- étude 3 bis : le portage du financement avec ses vrais comptes ----------------------------------------------------

MARGIN, BAND_LOW, BAND_HIGH = 0.5, 0.25, 0.75


def carry_account(frame: pd.DataFrame, rates: pd.Series, cost_spot: float, cost_perp: float,
                  rebalance: bool = True) -> dict:
    """Le compte d'un portage sur une crypto, jour par jour, pour 1 de capital au départ (voir `portage`)."""
    ts = frame["ts"].to_numpy(dtype="int64")
    opens, highs, closes = (frame[c].to_numpy(dtype=float) for c in ("open", "high", "close"))
    fund = rates.reindex(ts).fillna(0.0).to_numpy()
    coins = 1.0 / (1 + MARGIN) / opens[0]  # pièces achetées au comptant, et autant vendues en contrat
    equity = 1.0 - coins * opens[0] * (cost_spot + cost_perp)
    short, entry, wallet = coins, opens[0], equity - coins * opens[0]  # wallet : la marge du contrat, gains encaissés compris
    values, turns, liquidations, traded = [], [], [], 0.0
    for i in range(len(ts)):
        if short > 0:
            wallet += fund[i] * short * opens[i]
            limit = (wallet + short * entry) / (short * (1 + MAINTENANCE))  # le prix où la marge ne couvre plus la vente
            if highs[i] >= limit:
                liquidations.append(int(ts[i]))
                short, wallet = 0.0, 0.0  # la marge est perdue ; il reste les pièces achetées
                if not rebalance:
                    values.append(coins * closes[i])
                    break
        held = wallet + short * (entry - closes[i])  # ce que vaut le côté contrat ce soir
        ratio = held / (short * closes[i]) if short > 0 else 0.0
        if rebalance and (short == 0 or ratio < BAND_LOW or ratio > BAND_HIGH):
            equity = coins * closes[i] + held
            target = equity / (1 + MARGIN) / closes[i]
            moved = abs(target - coins) * closes[i] * cost_spot + abs(target - short) * closes[i] * cost_perp
            traded += abs(target - coins) * closes[i] + abs(target - short) * closes[i]
            equity -= moved
            coins = short = equity / (1 + MARGIN) / closes[i]
            entry, wallet = closes[i], equity - coins * closes[i]
            turns.append(int(ts[i]))
            held = wallet
        values.append(coins * closes[i] + held)
    values = np.asarray(values)
    return {"ts": ts[:len(values)], "days": values / np.concatenate(([1.0], values[:-1])) - 1,
            "rebalances": len(turns), "liquidations": liquidations, "traded": traded}


def portage(args) -> dict:
    """LE PORTAGE DU FINANCEMENT AVEC SES VRAIS COMPTES (suite de l'étude 3, la seule qui « tient »).
    L'étude 3 supposait que le montant tenu reste égal à 1 pour 1,5 de capital, tous les jours, sans rien payer. En
    vrai, quand le prix monte, la vente du contrat perd ce que l'achat au comptant gagne : il faut faire passer de
    l'argent d'un côté à l'autre, sinon la vente est liquidée. Protocole, fixé avant le calcul :
    - Bitcoin et Ether, moitié chacun, tenus en permanence du 01/01/2020 au dernier jour de financement connu ;
    - pour 1,5 de capital : 1 de pièces achetées au comptant, la même quantité vendue en contrat perpétuel (au prix du
      comptant), 0,5 de marge dans le compte du contrat ;
    - chaque jour : le financement du jour est versé (ou pris) sur le montant de la vente au prix d'ouverture ; si, au
      plus haut du jour, la marge ne couvre plus 0,5 % de la vente, la vente est liquidée (marge perdue) et la position
      est refaite le soir même ; le soir, si la marge vaut moins de 25 % ou plus de 75 % de la vente, les deux côtés
      sont remis à l'équilibre (marge de 50 %), en payant les frais sur ce qui est acheté et vendu ;
    - frais : 0,15 % au comptant et 0,07 % sur le contrat (ceux des bots), puis 0,30 % des deux côtés (« durs ») ;
    - on donne aussi le compte SANS remise à l'équilibre, pour voir quand la vente aurait été liquidée ;
    - ce qui n'est toujours PAS compté : l'écart de prix entre le contrat et le comptant (le contrat est pris au prix
      du comptant), le risque que la plateforme fasse défaut, les impôts."""
    cache = Path(args.cache)
    frames, rates = {}, {}
    for symbol, contract in (("BTC/USDT", "BTCUSDT"), ("ETH/USDT", "ETHUSDT")):
        rates[symbol] = nuit.daily_funding(contract, cache)
        frame = nuit.major(symbol, cache)
        frames[symbol] = frame[(frame["ts"] >= ms(START)) & (frame["ts"] <= rates[symbol].index.max())].reset_index(drop=True)
    index = frames["BTC/USDT"]["ts"].to_numpy(dtype="int64")
    simple = np.mean([rates[s].reindex(index).fillna(0.0).to_numpy() for s in frames], axis=0) / (1 + MARGIN)
    years = pd.to_datetime(index, unit="ms", utc=True).year.to_numpy()
    print(f"ÉTUDE 3 bis — LE PORTAGE AVEC SES VRAIS COMPTES · {len(index)} jours, du {nuit.longterm_day(index[0])} au "
          f"{nuit.longterm_day(index[-1])}")
    out = {"simple": judge(simple, index)}
    print(show("le calcul simple de l'étude 3 (montant tenu constant, sans frais d'entretien)", out["simple"]))
    for (spot, perp), name in (((SPOT, PERP), "frais des bots"), ((HARD, HARD), "frais durs")):
        runs = {s: carry_account(frames[s], rates[s], spot, perp) for s in frames}
        days = np.mean([runs[s]["days"] for s in frames], axis=0)
        result = judge(days, index)
        out[name] = {**result, "yearly": {}, "rebalances": {s: runs[s]["rebalances"] for s in frames},
                     "liquidations": {s: len(runs[s]["liquidations"]) for s in frames}}
        print(show(f"avec ses vrais comptes, {name} · remises à l'équilibre : "
                   + ", ".join(f"{s.split('/')[0]} {runs[s]['rebalances']}" for s in frames) + " · liquidations : "
                   + ", ".join(f"{s.split('/')[0]} {len(runs[s]['liquidations'])}" for s in frames), result))
        line = []
        for year in sorted(set(years)):
            gain = float(np.prod(1 + days[years == year]) - 1)
            out[name]["yearly"][int(year)] = gain
            line.append(f"{year} : {100 * gain:+.1f} %")
        print("      par année, sur le capital : " + " · ".join(line))
    for symbol in frames:
        alone = carry_account(frames[symbol], rates[symbol], SPOT, PERP, rebalance=False)
        when = nuit.longterm_day(alone["liquidations"][0]) if alone["liquidations"] else "jamais"
        out[f"sans remise | {symbol}"] = when
        print(f"  sans remise à l'équilibre, la vente de {symbol.split('/')[0]} est liquidée : {when}")
    return out


# --- étude 9 : les gros mouvements à l'heure près ------------------------------------------------------------------------

MOVES, HOURS, HTRAILS, MAX_HOURS, QUIET, USUAL = (0.05, 0.10, 0.20), (1, 4, 24), (0.05, 0.10), 72, 24, 168
EXITS = [f"{h} h" for h in HOURS] + [f"stop suiveur {100 * t:.0f} %" for t in HTRAILS]


def after_move(o: list, h: list, low: list, c: list, at: int, side: int) -> list[float]:
    """Ce que rapporte une entrée à l'OUVERTURE de l'heure qui suit l'heure `at` (avant frais, sans levier) : à la
    clôture 1, 4 et 24 heures après le mouvement, puis avec un stop suiveur à 5 % et à 10 % du meilleur prix de clôture
    (72 heures au plus). `side` : +1 acheter, −1 vendre à découvert (liquidée, −100 %, si le prix double)."""
    entry, last, out = o[at + 1], len(c) - 1, []
    for hours in HOURS:
        end = min(at + hours, last)
        result = side * (c[end] / entry - 1)
        if side < 0 and max(h[at + 1:end + 1]) >= 2 * entry:
            result = -1.0
        out.append(result)
    for trail in HTRAILS:
        best, result, final = entry, None, min(at + MAX_HOURS, last)
        for k in range(at + 1, final + 1):
            if side > 0:
                stop = best * (1 - trail)
                if low[k] <= stop:
                    result = min(stop, o[k]) / entry - 1  # une ouverture sous le stop : vendu à l'ouverture
                    break
                best = max(best, c[k])
            else:
                stop = best * (1 + trail)
                if h[k] >= stop:
                    result = max(-1.0, -(max(stop, o[k]) / entry - 1))
                    break
                best = min(best, c[k])
        out.append(side * (c[final] / entry - 1) if result is None else result)
    return out


def hour_events(symbol: str, frame: pd.DataFrame) -> list[tuple]:
    """Les gros mouvements d'une paire, heure par heure, et ce que chaque façon d'y entrer a rapporté."""
    rows, ts = [], frame["ts"].to_numpy(dtype="int64")
    edges = [0, *(np.flatnonzero(np.diff(ts) != HOUR) + 1).tolist(), len(ts)]
    for a, b in zip(edges[:-1], edges[1:]):  # morceaux continus : une cotation interrompue n'est pas un mouvement
        if b - a < USUAL + 2:
            continue
        part = frame.iloc[a:b]
        closes = part["close"].to_numpy(dtype=float)
        money = closes * part["volume"].to_numpy(dtype=float)
        usual = pd.Series(money).rolling(USUAL).mean().shift(1).to_numpy()
        jump = np.concatenate(([0.0], closes[1:] / closes[:-1] - 1))
        with np.errstate(invalid="ignore"):
            base = (money >= nuit.SURGE * usual) & (usual >= nuit.MIN_MONEY / 24)
        base[-1] = False  # pas d'heure suivante pour entrer
        o, h, low, c = (part[name].tolist() for name in ("open", "high", "low", "close"))
        stamps = ts[a:b]
        for direction, sign in (("hausse", 1), ("chute", -1)):
            for move in MOVES:
                taken = -QUIET - 1
                for at in np.flatnonzero(base & (sign * jump >= move)).tolist():
                    if at - taken < QUIET:
                        continue
                    taken = at
                    for side in (1, -1):
                        rows.append((symbol, int(stamps[at + 1]), direction, move, side, *after_move(o, h, low, c, at, side)))
    return rows


def heure(args) -> dict:
    """LES GROS MOUVEMENTS À L'HEURE PRÈS (l'idée de l'utilisateur : « rentrer dans le game dès qu'il y a un gros
    mouvement », avec un stop suiveur et du levier). L'étude 2 regardait les journées ; celle-ci entre dans l'heure.
    Protocole, fixé avant le calcul :
    - toutes les paires USDT au comptant de Binance depuis 2020, retirées de la cote comprises, en bougies d'une heure ;
    - un « gros mouvement » : une heure qui clôture à +5 %, +10 % ou +20 % (ou à −5 %, −10 %, −20 % : une chute) de la
      clôture précédente, avec un volume d'au moins 3 fois sa moyenne des 7 jours d'avant, sur une crypto qui a échangé
      au moins 1 million de dollars par jour en moyenne ces 7 jours ; tout est connu à la clôture de l'heure ;
    - une seule entrée par crypto et par 24 heures (la première heure qui passe le seuil) ;
    - l'entrée : à l'ouverture de l'heure suivante, au marché. Deux sens à chaque fois : après une hausse, suivre
      (acheter) ou parier sur la retombée (vendre à découvert) ; après une chute, suivre (vendre) ou acheter le creux ;
    - la sortie : à la clôture 1, 4 ou 24 heures après le mouvement ; ou par un stop suiveur à 5 % ou 10 % du meilleur
      prix de clôture (72 heures au plus) ;
    - les frais : deux ordres à 0,07 % (ceux des bots), puis à 0,30 % (« durs ») ; le financement d'une vente à
      découvert n'est pas compté (3 jours au plus) : une « piste » à la vente serait à refaire avec lui ;
    - le levier : pour les sorties avec stop, celui qui garde la liquidation derrière le stop (×16 à 5 %, ×8,6 à 10 %).
    60 façons de faire (2 mouvements × 3 seuils × 2 sens × 5 sorties) à deux niveaux de frais : seules comptent celles
    qui tiennent sur les deux périodes ; sur 120 essais sans aucun avantage, on en attend 0,1 par hasard."""
    cache = Path(args.cache)
    rows, read = [], 0
    for symbol in pairs(cache):
        path = cache / f"{symbol.replace('/', '-')}-1h.pkl"
        if not path.exists():
            continue
        frame = pd.read_pickle(path)
        frame = frame[frame["ts"] >= ms(START)].reset_index(drop=True)
        if len(frame) > USUAL + 2:
            read += 1
            rows += hour_events(symbol, frame)
    table = pd.DataFrame(rows, columns=["symbol", "ts", "direction", "move", "side", *EXITS])
    first = table[(table["side"] == 1) & (table["move"] == MOVES[0])]
    print(f"ÉTUDE 9 — LES GROS MOUVEMENTS À L'HEURE : {read} paires lues · {(first['direction'] == 'hausse').sum()} "
          f"hausses et {(first['direction'] == 'chute').sum()} chutes d'au moins 5 % en une heure avec un volume triplé "
          f"({(first['ts'] < ms(CUT)).sum()} avant 2024, {(first['ts'] >= ms(CUT)).sum()} depuis)")
    names = {("hausse", 1): "suivre la hausse (acheter)", ("hausse", -1): "parier sur la retombée (vendre)",
             ("chute", -1): "suivre la chute (vendre)", ("chute", 1): "acheter le creux"}
    out = {}
    for cost, cost_name in ((PERP, "frais des bots (0,07 % par ordre)"), (HARD, "frais durs (0,30 % par ordre)")):
        print(f"\n--- {cost_name} ---")
        kept = 0
        for (direction, side), name in names.items():
            for move in MOVES:
                part = table[(table["direction"] == direction) & (table["move"] == move) & (table["side"] == side)]
                for exit_name in EXITS:
                    net = part[exit_name].to_numpy(dtype=float) - 2 * cost
                    result = judge(np.maximum(net, -1.0), part["ts"].to_numpy(), chain=False)
                    out[f"{cost_name} | {name} | {100 * move:.0f} % | {exit_name}"] = result
                    line = brief(f"{name} après {100 * move:.0f} % · {exit_name}", result)
                    if exit_name.startswith("stop"):
                        trail = float(exit_name.split()[-2]) / 100
                        lever = 0.9 / (trail + MAINTENANCE)
                        geared = np.maximum(lever * net, -1.0)
                        line += (f" · levier ×{lever:.1f} : {100 * geared.mean():+.2f} %, "
                                 f"{100 * (geared <= -1).mean():.1f} % de mises perdues en entier")
                    if cost == PERP or result["verdict"] != "rien":
                        print(line)
                        kept += 1
        if cost != PERP:
            print(f"  ({kept} façon(s) sur 60 ne sont pas « rien » avec ces frais)")
    return out


# --- étude 10 : le bot de grille -----------------------------------------------------------------------------------------

GRID_STEPS = (0.005, 0.01, 0.02, 0.05)
GRID_FEES = ((0.001, "ordre limite au comptant : 0,10 %"), (FUTURES.maker_fee_rate, "au moins cher : 0,02 %"))


def grid_account(frame: pd.DataFrame, step: float, fees: tuple[float, ...]) -> dict:
    """Une grille sans bornes sur une crypto (voir `grille`) : la valeur du compte à la fin de chaque jour, pour
    chaque niveau de frais, et le nombre d'ordres servis. Dans une bougie, le prix va de l'ouverture au plus bas puis
    au plus haut quand elle clôture en hausse, au plus haut puis au plus bas sinon."""
    ts, o, h, low, c = (frame[name].tolist() for name in ("ts", "open", "high", "low", "close"))
    accounts = [[0.5 * (1 - fee) / o[0], 0.5, fee] for fee in fees]  # pièces, argent, frais
    anchor, fills = o[0], 0
    up, down = anchor * (1 + step), anchor / (1 + step)
    days, values, prices, day = [], [[] for _ in fees], [], ts[0] // DAY
    for i in range(len(ts)):
        if ts[i] // DAY != day:
            days.append(day * DAY)
            prices.append(c[i - 1])
            for k, (coins, cash, _) in enumerate(accounts):
                values[k].append(coins * c[i - 1] + cash)
            day = ts[i] // DAY
        if h[i] < up and low[i] > down:
            continue
        for target in ((low[i], h[i], c[i]) if c[i] >= o[i] else (h[i], low[i], c[i])):
            while True:
                if target >= up:  # l'ordre de vente est servi : retour à moitié-moitié à ce prix
                    for account in accounts:
                        sold = (account[0] * up - account[1]) / (2 - account[2])
                        account[0] -= sold / up
                        account[1] += sold * (1 - account[2])
                    anchor = up
                elif target <= down:  # l'ordre d'achat est servi
                    for account in accounts:
                        spent = (account[1] - account[0] * down) / (2 - account[2])
                        account[1] -= spent
                        account[0] += spent * (1 - account[2]) / down
                    anchor = down
                else:
                    break
                fills += 1
                up, down = anchor * (1 + step), anchor / (1 + step)
    days.append(day * DAY)
    prices.append(c[-1])
    for k, (coins, cash, _) in enumerate(accounts):
        values[k].append(coins * c[-1] + cash)
    return {"days": np.asarray(days, dtype="int64"), "values": [np.asarray(v) for v in values],
            "prices": np.asarray(prices), "first": o[0], "fills": fills}


def grille(args) -> dict:
    """LE BOT DE GRILLE (le robot le plus vendu aux particuliers : acheter chaque fois que ça baisse d'un cran, revendre
    chaque fois que ça remonte d'un cran).
    Protocole, fixé avant le calcul :
    - six grandes cryptos (Bitcoin, Ether, BNB, Solana, XRP, Dogecoin), bougies de 5 minutes depuis 2020 ;
    - une grille SANS bornes, pour ne pas choisir une fourchette après coup : le compte part moitié en crypto, moitié
      en argent ; un ordre de vente attend un cran au-dessus du dernier prix traité, un ordre d'achat un cran en
      dessous ; chaque ordre servi ramène le compte à moitié-moitié, puis les deux ordres sont reposés autour de ce
      prix ; crans de 0,5 %, 1 %, 2 % et 5 % ;
    - ordres limites, servis au prix du cran ; frais : 0,10 % par ordre (ordre limite au comptant sur Binance), puis
      0,02 % (le moins cher qui existe pour un particulier : ordre limite sur un contrat à terme) ;
    - ce qu'on juge : le résultat de chaque jour de la grille MOINS la moitié de la variation de la crypto ce jour-là
      (ce que gagne un compte tenu à moitié-moitié sans rien faire d'autre). Sur un marché sans mémoire, cette
      différence vaut zéro moins les frais : la grille ne gagne quelque chose par elle-même que si les prix reviennent
      vraiment sur leurs pas ;
    - on montre aussi l'argent composé : la grille, « moitié gardée, moitié en argent, sans y toucher », et tout gardé.
    Ajouté APRÈS avoir vu les résultats par crypto (donc hors protocole, pour décrire) : la même différence pour les
    six cryptos réunies, chaque jour la moyenne des six. Une grille qui gagne sur une crypto et pas sur les cinq
    autres ressemble plus à un hasard qu'à une règle."""
    cache = Path(args.cache)
    ex = vrai.exchange()
    ex.load_markets()
    end = ex.fetch_time() // DAY * DAY
    out, together = {}, {}
    print("ÉTUDE 10 — LE BOT DE GRILLE (bougies de 5 minutes depuis 2020)")
    for symbol in GRID_COINS:
        frame = vrai.candles(ex, symbol, "5m", ms(START), end, cache).reset_index(drop=True)
        coin = symbol.split("/")[0]
        for step in GRID_STEPS:
            run = grid_account(frame, step, tuple(fee for fee, _ in GRID_FEES))
            move = run["prices"] / np.concatenate(([run["first"]], run["prices"][:-1])) - 1
            hold = nuit.compound(move)
            idle = nuit.compound((0.5 + 0.5 * run["prices"] / run["first"])
                                 / np.concatenate(([1.0], (0.5 + 0.5 * run["prices"] / run["first"])[:-1])) - 1)
            for k, (fee, fee_name) in enumerate(GRID_FEES):
                daily = run["values"][k] / np.concatenate(([1.0], run["values"][k][:-1])) - 1
                result = judge(daily - 0.5 * move, run["days"])
                together.setdefault((step, fee_name), []).append(pd.Series(daily - 0.5 * move, index=run["days"]))
                whole = nuit.compound(daily)
                out[f"{coin} | cran {100 * step:.1f} % | {fee_name}"] = {
                    **result, "fills": run["fills"], "grid": whole, "idle": idle, "hold": hold}
                print(brief(f"{coin} · cran de {100 * step:.1f} % · {fee_name} · {run['fills'] / len(run['days']):.1f} ordres "
                            f"par jour", result, "par jour")
                      + f" · grille ×{whole['total']:.2f} ({100 * whole['worst']:+.0f} %), moitié gardée ×{idle['total']:.2f} "
                        f"({100 * idle['worst']:+.0f} %), tout gardé ×{hold['total']:.2f} ({100 * hold['worst']:+.0f} %)")
    print("  les six cryptos réunies (hors protocole, ajouté après coup) :")
    for (step, fee_name), series in together.items():
        mean = pd.concat(series, axis=1).mean(axis=1)
        result = judge(mean.to_numpy(), mean.index.to_numpy(), chain=False)
        out[f"réunies | cran {100 * step:.1f} % | {fee_name}"] = result
        print(brief(f"réunies · cran de {100 * step:.1f} % · {fee_name}", result, "par jour"))
    return out


# --- étude 11 : l'indice peur et avidité -----------------------------------------------------------------------------------

FEAR_URL = "https://api.alternative.me/fng/?limit=0&format=json"
FEAR_RULES = {
    "acheter la peur extrême": lambda mood: (mood == "Extreme Fear").astype(float),
    "acheter la peur (extrême ou non)": lambda mood: np.isin(mood, ("Extreme Fear", "Fear")).astype(float),
    "tout garder, sauf en avidité extrême": lambda mood: (mood != "Extreme Greed").astype(float),
    "suivre l'avidité (extrême ou non)": lambda mood: np.isin(mood, ("Greed", "Extreme Greed")).astype(float),
    "contre la foule dans les deux sens": lambda mood: (mood == "Extreme Fear").astype(float) - (mood == "Extreme Greed"),
}


def fear_greed(cache: Path) -> pd.Series:
    """L'indice peur et avidité d'alternative.me : pour chaque jour (ms), la catégorie donnée par la source."""
    path = cache / "peur-et-avidite.json"
    if not path.exists():
        path.write_text(session().get(FEAR_URL, timeout=60).text, encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    series = pd.Series({int(row["timestamp"]) * 1000 // DAY * DAY: row["value_classification"] for row in data})
    return series.sort_index()


def peur(args) -> dict:
    """L'INDICE PEUR ET AVIDITÉ (« acheter quand tout le monde a peur, vendre quand tout le monde est avide »).
    Protocole, fixé avant le calcul :
    - Bitcoin, bougies d'un jour ; l'indice d'alternative.me depuis février 2018, publié une fois par jour à minuit
      UTC ; les seuils sont les catégories de la source elle-même (peur extrême, peur, neutre, avidité, avidité
      extrême) : aucun seuil choisi par moi ;
    - cinq règles : acheter la peur extrême ; acheter la peur ; tout garder sauf en avidité extrême ; suivre
      l'avidité ; contre la foule dans les deux sens (acheter en peur extrême, vendre à découvert en avidité extrême) ;
    - deux moments : « le jour même » (l'indice publié à minuit décide de la journée qui commence) et « le lendemain »
      (un jour de retard, pour être sûr de ne rien savoir d'avance) ;
    - frais : 0,15 % sur ce qui change (comptant) ; une vente à découvert paie 0,07 % et touche le vrai financement ;
    - ce qu'on juge : « le choix du moment », c'est-à-dire le résultat de la règle MOINS ce qu'aurait donné la même
      part du temps passée dans le marché sans choisir ses jours. Une règle qui achète peut gagner seulement parce que
      le Bitcoin a monté : ce calcul l'enlève. On montre aussi l'argent composé face à « tout garder »."""
    cache = Path(args.cache)
    mood = fear_greed(cache)
    frame = nuit.major("BTC/USDT", cache)
    close = pd.Series(frame["close"].to_numpy(dtype=float), index=frame["ts"].to_numpy(dtype="int64"))
    days = close.index[(close.index >= mood.index[0]) & (close.index <= mood.index[-1])].to_numpy()
    move = close.pct_change().reindex(days).to_numpy()  # la variation du jour, de minuit à minuit
    label = mood.reindex(days).fillna("").to_numpy(dtype=object)  # "" : un jour sans indice
    funding = nuit.daily_funding("BTCUSDT", cache).reindex(days).fillna(0.0).to_numpy()
    print(f"ÉTUDE 11 — L'INDICE PEUR ET AVIDITÉ · {len(days)} jours, du {nuit.longterm_day(days[0])} au "
          f"{nuit.longterm_day(days[-1])} · " + ", ".join(f"{name} {100 * (label == name).mean():.0f} %" for name in
                                                          ("Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed")))
    known = (label != "") & np.isfinite(move)
    hold = nuit.compound(move[known])
    out = {}
    for delay, delay_name in ((0, "le jour même"), (1, "le lendemain")):
        for name, rule in FEAR_RULES.items():
            share = np.asarray(rule(label), dtype=float)
            share = np.concatenate((np.zeros(delay), share[:len(share) - delay]))
            turn = np.abs(np.diff(np.concatenate(([0.0], share))))
            cost = np.where((share < 0) | (np.concatenate(([0.0], share[:-1])) < 0), PERP, SPOT) * turn
            result = share * move - cost + np.maximum(-share, 0) * funding
            ok = known & np.concatenate((np.zeros(delay, dtype=bool), known[:len(known) - delay]))
            timing = np.full(len(days), np.nan)
            for mask in (days < ms(CUT), days >= ms(CUT)):
                part = ok & mask
                timing[part] = result[part] - share[part].mean() * move[part]
            verdict = judge(timing[ok], days[ok], chain=False)
            whole = nuit.compound(result[ok])
            out[f"{name} | {delay_name}"] = {**verdict, "rule": whole, "hold": hold, "inside": float(np.abs(share[ok]).mean())}
            print(brief(f"{name}, {delay_name} · en position {100 * np.abs(share[ok]).mean():.0f} % du temps", verdict,
                        "par jour (le choix du moment)")
                  + f" · la règle ×{whole['total']:.2f} ({100 * whole['worst']:+.0f} %), tout garder ×{hold['total']:.2f} "
                    f"({100 * hold['worst']:+.0f} %)")
    return out


# --- étude 12 : les écarts de prix entre plateformes -------------------------------------------------------------------

VENUES = {"okx": 100, "kucoin": 1500, "gate": 1000}  # bougies d'une minute rendues par appel
GAP_DAYS, GAP_COSTS = 7, ((0.003, "réaliste : 0,30 % (deux ordres au marché, frais et glissement)"),
                          (0.002, "au mieux : 0,20 % (frais seuls)"))


def selection(cache: Path) -> dict:
    """Les douze cryptos des études 12 et 13, choisies par une règle : les 5 plus échangées de Binance, puis les 7
    premières à partir du 41e rang qui sont aussi cotées chez OKX et KuCoin. Le choix est gardé pour être refait."""
    path = cache / "selection-nuit2.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    ranked = [r.symbol for r in by_volume(vrai.exchange(), "USDT", 300, 0)]
    listed = None
    for venue in ("okx", "kucoin"):
        other = make_exchange(venue)
        other.session.trust_env = True
        other.load_markets()
        names = {s for s, m in other.markets.items() if m.get("spot") and m.get("active") is not False}
        listed = names if listed is None else listed & names
    chosen = {"big": ranked[:5], "small": [s for s in ranked[40:] if s in listed][:7]}
    path.write_text(json.dumps(chosen), encoding="utf-8")
    return chosen


def _minutes_job(args) -> tuple[str, str, pd.DataFrame | str]:
    venue, symbol, start, end = args
    key = f"venue-{venue}"
    try:
        if not hasattr(nuit.LOCAL, key):
            other = make_exchange(venue)
            other.session.trust_env = True
            other.load_markets()
            setattr(nuit.LOCAL, key, other)
        other, rows, cursor, failures, error = getattr(nuit.LOCAL, key), {}, start, 0, "aucune bougie"
        while cursor < end and failures <= 20:
            try:
                batch = other.fetch_ohlcv(symbol, "1m", since=cursor, limit=VENUES[venue])
            except Exception as exc:  # une page refusée (trop ancienne…) : on passe à la suivante, 20 fois au plus
                failures, error = failures + 1, f"{type(exc).__name__} {str(exc)[:70]}"
                cursor += VENUES[venue] * MINUTE
                continue
            fresh = [row for row in batch if cursor <= row[0] < end]
            rows.update({int(row[0]): (float(row[4]), float(row[5] or 0.0)) for row in fresh})
            cursor = int(max(row[0] for row in fresh)) + MINUTE if fresh else cursor + VENUES[venue] * MINUTE
        if not rows:
            return venue, symbol, error
        table = pd.DataFrame.from_dict(rows, orient="index", columns=["close", "volume"]).sort_index()
        return venue, symbol, table
    except Exception as exc:  # une plateforme qui ne répond pas pour cette crypto : dite, et ignorée
        return venue, symbol, f"{type(exc).__name__} {str(exc)[:70]}"


def ecarts(args) -> dict:
    """LES ÉCARTS DE PRIX ENTRE PLATEFORMES (acheter là où c'est moins cher, vendre là où c'est plus cher).
    Protocole, fixé avant le calcul :
    - douze cryptos choisies par une règle (`selection`) : les 5 plus échangées et 7 petites ; Binance comparée à OKX,
      KuCoin et Gate (toutes cotées en USDT), minute par minute, sur les 7 derniers jours entiers ;
    - l'écart d'une minute : le dernier prix de l'autre plateforme divisé par celui de Binance, moins 1, quand les deux
      ont eu des échanges dans la minute ;
    - le coût d'un aller : deux ordres au marché (un achat ici, une vente là-bas, avec de l'argent et des pièces déjà
      en place des deux côtés) : 0,30 % en comptant frais et glissement, 0,20 % avec les frais seuls ;
    - ce qu'on juge : quand l'écart d'une minute dépasse le coût, on traite à la minute SUIVANTE (on ne peut pas traiter
      à un prix déjà passé) ; le gain est l'écart de cette minute suivante, dans le même sens, moins le coût ;
    - seulement 7 jours : cette étude décrit, elle ne prouve rien dans la durée. Elle ne voit pas non plus la quantité
      disponible à ces prix (le carnet d'ordres) : un écart affiché sur un dernier prix n'est pas toujours traitable."""
    cache = Path(args.cache)
    chosen = selection(cache)
    ex = vrai.exchange()
    ex.load_markets()
    end = ex.fetch_time() // DAY * DAY
    start = end - GAP_DAYS * DAY
    coins = chosen["big"] + chosen["small"]
    print(f"ÉTUDE 12 — LES ÉCARTS ENTRE PLATEFORMES · du {nuit.longterm_day(start)} au {nuit.longterm_day(end - DAY)} · "
          f"grandes : {', '.join(s.split('/')[0] for s in chosen['big'])} · petites : "
          f"{', '.join(s.split('/')[0] for s in chosen['small'])}")
    home = {}
    for symbol in coins:
        frame = vrai.candles(ex, symbol, "1m", start, end, cache)
        home[symbol] = pd.DataFrame({"close": frame["close"].to_numpy(dtype=float),
                                     "volume": frame["volume"].to_numpy(dtype=float)}, index=frame["ts"].to_numpy(dtype="int64"))
    jobs = [(venue, symbol, start, end) for venue in VENUES for symbol in coins]
    with ThreadPoolExecutor(len(VENUES)) as pool:
        answers = list(pool.map(_minutes_job, jobs))
    out, pooled = {}, {}
    for venue, symbol, table in answers:
        if isinstance(table, str) or len(table) < 1000:
            print(f"  {venue} {symbol} : pas de données ({table if isinstance(table, str) else len(table)})")
            continue
        both = home[symbol].join(table, how="inner", lsuffix="_a", rsuffix="_b")
        both = both[(both["volume_a"] > 0) & (both["volume_b"] > 0)]
        gap = both["close_b"] / both["close_a"] - 1
        if abs(gap.median()) > 0.02:
            print(f"  {venue} {symbol} : écart médian de {100 * gap.median():+.1f} % : pas la même crypto, écartée")
            continue
        after = gap.reindex(gap.index + MINUTE).to_numpy()
        group = "grandes" if symbol in chosen["big"] else "petites"
        pooled.setdefault((group, venue), []).append((gap.index.to_numpy(), gap.to_numpy(), after))
    for (group, venue), parts in sorted(pooled.items()):
        stamps, gaps, nexts = (np.concatenate([p[k] for p in parts]) for k in range(3))
        line = (f"  {group} · Binance et {venue} · {len(gaps)} minutes · écart médian {100 * np.median(np.abs(gaps)):.3f} %")
        entry = {"minutes": int(len(gaps)), "median": float(np.median(np.abs(gaps)))}
        for cost, cost_name in GAP_COSTS:
            seen = (np.abs(gaps) > cost) & np.isfinite(nexts)
            gain = np.sign(gaps[seen]) * nexts[seen] - cost
            hours = pd.DataFrame({"g": stamps[seen] // HOUR, "v": gain}).groupby("g")["v"].agg(["count", "sum"])
            mean, low, high = clustered_bounds(list(zip(hours["count"], hours["sum"]))) if len(hours) > 1 else (math.nan,) * 3
            entry[cost_name] = {"share": float((np.abs(gaps) > cost).mean()), "signals": int(seen.sum()),
                                "mean": float(mean), "low": float(low), "high": float(high),
                                "per_day_1000": float(gain.sum() * 1000 / GAP_DAYS) if seen.any() else 0.0}
            line += (f"\n      {cost_name} : dépassé {100 * (np.abs(gaps) > cost).mean():.3f} % des minutes · "
                     f"{seen.sum() / GAP_DAYS:.1f} occasions par jour"
                     + (f" · gain à la minute suivante {100 * mean:+.3f} % (de {100 * low:+.3f} à {100 * high:+.3f}) · "
                        f"{gain.sum() * 1000 / GAP_DAYS:+.2f} $ par jour avec 1 000 $ par ordre" if len(hours) > 1 else
                        f" · {gain.sum() * 1000 / GAP_DAYS:+.2f} $ par jour avec 1 000 $ par ordre (trop peu pour une fourchette)"
                        if seen.any() else ""))
        out[f"{group} | {venue}"] = entry
        print(line)
    return out


# --- étude 13 : les ordres passifs -----------------------------------------------------------------------------------------

PASSIVE_DAYS, PASSIVE_AFTER = ("2026-09-09", "2026-10-07", "2026-11-04"), (5, 60, 300)
AGG_TRADES = "data/futures/um/daily/aggTrades/{c}/{c}-aggTrades-{day}.zip"


def _passive_job(args) -> tuple[str, str, pd.DataFrame | str]:
    """Une journée de transactions d'un contrat, résumée heure par heure : ce que gagne celui dont l'ordre attendait."""
    contract, day, folder = args
    path = folder / f"{contract}-{day}.pkl"
    if path.exists():
        return contract, day, pd.read_pickle(path)
    try:
        answer = session().get(ARCHIVE + AGG_TRADES.format(c=contract, day=day), timeout=900)
        if answer.status_code != 200:
            return contract, day, f"HTTP {answer.status_code}"
        with zipfile.ZipFile(io.BytesIO(answer.content)) as archive:
            raw = archive.read(archive.namelist()[0])
        table = pd.read_csv(io.BytesIO(raw), header=None, skiprows=0 if raw[:1].isdigit() else 1, usecols=[1, 5, 6],
                            names=["price", "time", "maker"])
        del raw, answer
        table = table.sort_values("time", kind="stable")
        stamp = table["time"].to_numpy(dtype="int64")
        stamp = np.where(stamp > 1e14, stamp // 1000, stamp).astype(np.int64)  # microsecondes : ramenées en ms
        price = table["price"].to_numpy(dtype=float)
        waiting_buy = table["maker"].astype(str).str.lower().eq("true").to_numpy()  # le vendeur est venu chercher l'achat
        place = np.arange(len(price))
        bid = np.maximum.accumulate(np.where(waiting_buy, place, -1))
        ask = np.maximum.accumulate(np.where(~waiting_buy, place, -1))
        middle = np.where((bid >= 0) & (ask >= 0), (price[np.maximum(bid, 0)] + price[np.maximum(ask, 0)]) / 2, np.nan)
        sign = np.where(waiting_buy, 1.0, -1.0)
        columns = {"hour": stamp // HOUR, "sur le moment": sign * (np.concatenate(([np.nan], middle[:-1])) - price) / price}
        for seconds in PASSIVE_AFTER:
            later = np.searchsorted(stamp, stamp + 1000 * seconds, side="right") - 1
            gain = sign * (middle[later] - price) / price
            gain[stamp + 1000 * seconds > stamp[-1]] = np.nan
            columns[f"{seconds} s"] = gain
        frame = pd.DataFrame(columns)
        summary = frame.groupby("hour").agg(["count", "sum"])
        summary.to_pickle(path)
        return contract, day, summary
    except Exception as exc:  # un fichier qui ne répond pas : dit, et ignoré
        return contract, day, f"{type(exc).__name__} {str(exc)[:70]}"


def passif(args) -> dict:
    """LES ORDRES PASSIFS (au lieu de payer l'écart entre acheteurs et vendeurs, le gagner : poser un ordre et attendre
    qu'on vienne le chercher. C'est le métier des « teneurs de marché », et la seule façon de ne pas payer les frais
    d'un ordre au marché).
    Protocole, fixé avant le calcul :
    - les douze cryptos de l'étude 12, sur leurs contrats perpétuels, chaque transaction de trois journées fixées
      d'avance (09/09, 07/10 et 04/11/2026), archives de Binance ;
    - chaque transaction a un côté qui attendait (l'ordre passif) et un côté qui est venu le chercher ; le « prix du
      milieu » d'un instant est la moyenne du dernier prix traité à l'achat et du dernier traité à la vente ;
    - ce qu'on mesure pour l'ordre qui attendait : son avance sur le prix du milieu au moment où il est servi (le
      demi-écart), puis ce qu'il en reste 5 secondes, 1 minute et 5 minutes plus tard (le prix a souvent bougé contre
      lui : on est servi quand le marché vient vers soi) ;
    - à comparer aux frais d'un ordre limite : 0,02 % par ordre pour un particulier ;
    - verdict : « possible » seulement si ce qui reste après 1 minute dépasse nettement ces 0,02 % (fourchette à 95 %
      qui compare les heures entre elles) ;
    - ce calcul est FAVORABLE à l'ordre passif : il compte toutes les transactions, alors que l'ordre d'un particulier
      est le dernier de la file à ce prix et n'est servi que quand tout le niveau est emporté ;
    - trois journées : cette étude décrit un ordre de grandeur, pas une preuve dans la durée."""
    cache = Path(args.cache)
    folder = cache / "passif"
    folder.mkdir(parents=True, exist_ok=True)
    chosen = selection(cache)
    contracts = {s: nuit.contract_of(s, cache) for s in chosen["big"] + chosen["small"]}
    jobs = [(c, day, folder) for c in contracts.values() if c for day in PASSIVE_DAYS]
    print(f"ÉTUDE 13 — LES ORDRES PASSIFS · {len([c for c in contracts.values() if c])} contrats · journées : "
          f"{', '.join(PASSIVE_DAYS)} · frais d'un ordre limite : {100 * FUTURES.maker_fee_rate:.2f} %")
    tables = {}
    with ThreadPoolExecutor(min(args.fils, 3)) as pool:
        for contract, day, summary in pool.map(_passive_job, jobs):
            if isinstance(summary, str):
                print(f"  {contract} {day} : {summary}", flush=True)
            else:
                tables.setdefault(contract, []).append(summary)
    out, names = {}, ["sur le moment"] + [f"{s} s" for s in PASSIVE_AFTER]
    for symbol, contract in contracts.items():
        if contract not in tables:
            continue
        whole = pd.concat(tables[contract])
        entry, line = {"fills": int(whole[("sur le moment", "count")].sum())}, []
        for name in names:
            mean, low, high = clustered_bounds(list(zip(whole[(name, "count")], whole[(name, "sum")])))
            entry[name] = {"mean": float(mean), "low": float(low), "high": float(high)}
            line.append(f"{name} {100 * mean:+.4f} %")
        left = entry["60 s"]
        net_low = left["low"] - FUTURES.maker_fee_rate
        entry["verdict"] = "possible" if net_low > 0 else "impossible aux frais d'un particulier"
        out[symbol] = entry
        print(f"  {symbol.split('/')[0]:>8} ({'grande' if symbol in chosen['big'] else 'petite'}) · "
              f"{entry['fills'] / 1e6:.2f} millions d'ordres servis · " + " · ".join(line)
              + f" · après frais, à 1 minute : {100 * (left['mean'] - FUTURES.maker_fee_rate):+.4f} % "
                f"(de {100 * net_low:+.4f} à {100 * (left['high'] - FUTURES.maker_fee_rate):+.4f}) → {entry['verdict']}")
    return out


# --- étude 14 : la prime de volatilité des options ---------------------------------------------------------------------

DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
OPTION_DAYS, OPTION_COST, STRADDLE = 30, 0.003, 0.8


def dvol(currency: str, cache: Path) -> pd.Series:
    """L'indice de volatilité attendue de Deribit (DVOL, en % par an sur 30 jours) : sa clôture de chaque jour."""
    path = cache / f"dvol-{currency}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    points, end = {}, int(time.time() * 1000)
    while True:
        result = session().get(DVOL_URL, params={"currency": currency, "start_timestamp": ms("2021-01-01"),
                                                 "end_timestamp": end, "resolution": "1D"}, timeout=60).json()["result"]
        points.update({int(row[0]): float(row[4]) for row in result["data"]})
        if not result.get("continuation") or not result["data"]:
            break
        end = int(result["continuation"])
    series = pd.Series(points).sort_index()
    series.to_pickle(path)
    return series


def volatilite(args) -> dict:
    """LA PRIME DE VOLATILITÉ (vendre des options : encaisser une prime en pariant que le prix bougera moins que ce que
    le marché craint. C'est, avec le financement, l'autre revenu « de structure » connu des marchés).
    Protocole, fixé avant le calcul :
    - Bitcoin et Ether ; la volatilité attendue par le marché des options : l'indice DVOL de Deribit (30 jours), à sa
      clôture du jour, depuis son lancement en 2021 ;
    - des périodes de 30 jours qui ne se chevauchent pas, à partir du premier jour de l'indice ; pour chacune : la
      volatilité attendue au départ, et celle que le prix a vraiment eue ensuite (variations d'un jour) ;
    - le résultat d'un vendeur, pour 1 de crypto couvert : il vend une option d'achat et une option de vente au prix du
      jour, à 30 jours (prime estimée : 0,8 × volatilité attendue × racine de 30/365), il paie à l'échéance la
      variation du prix en valeur absolue, et 0,30 % de frais et d'écart ; le calcul est refait avec une prime
      réduite de 10 % (l'indice est un peu plus haut que la volatilité des options au prix du jour) ;
    - c'est une estimation à partir de l'indice, pas les vrais prix des options ; une soixantaine de périodes
      seulement : cette étude décrit. Un vendeur d'options peut perdre bien plus que la prime encaissée."""
    cache = Path(args.cache)
    out = {}
    print("ÉTUDE 14 — LA PRIME DE VOLATILITÉ DES OPTIONS (périodes de 30 jours)")
    for currency, symbol in (("BTC", "BTC/USDT"), ("ETH", "ETH/USDT")):
        expected = dvol(currency, cache)
        frame = nuit.major(symbol, cache)
        close = pd.Series(frame["close"].to_numpy(dtype=float), index=frame["ts"].to_numpy(dtype="int64"))
        change = np.log(close).diff()
        rows, day = [], int(expected.index[0]) // DAY * DAY
        while day + OPTION_DAYS * DAY in close.index:
            if day in close.index and day in expected.index:
                path = change[(change.index > day) & (change.index <= day + OPTION_DAYS * DAY)]
                rows.append((day, expected[day] / 100, math.sqrt(365 / OPTION_DAYS * float((path ** 2).sum())),
                             abs(close[day + OPTION_DAYS * DAY] / close[day] - 1)))
            day += OPTION_DAYS * DAY
        table = pd.DataFrame(rows, columns=["ts", "expected", "real", "move"])
        print(f"  {currency} · {len(table)} périodes, du {nuit.longterm_day(table['ts'].iloc[0])} au "
              f"{nuit.longterm_day(table['ts'].iloc[-1])} · volatilité attendue {100 * table['expected'].mean():.0f} % par an, "
              f"réelle {100 * table['real'].mean():.0f} % · attendue au-dessus de la réelle {100 * (table['expected'] > table['real']).mean():.0f} % du temps")
        for cut, cut_name in ((1.0, "prime de l'indice"), (0.9, "prime réduite de 10 %")):
            gain = STRADDLE * cut * table["expected"] * math.sqrt(OPTION_DAYS / 365) - table["move"] - OPTION_COST
            result = judge(gain.to_numpy(), table["ts"].to_numpy(), chain=False)
            out[f"{currency} | {cut_name}"] = {**result, "worst": float(gain.min()), "best": float(gain.max())}
            print(brief(f"{currency} · vendre la volatilité, {cut_name}", result, "par période de 30 jours")
                  + f" · pire période {100 * gain.min():+.1f} %, meilleure {100 * gain.max():+.1f} %")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("etude", choices=sorted(STUDIES))
    parser.add_argument("--cache", default=vrai.CACHE)
    parser.add_argument("--fils", type=int, default=8)
    parser.add_argument("--sortie", default="")
    args = parser.parse_args()
    began = time.time()
    report = STUDIES[args.etude](args)
    if args.sortie and report is not None:
        Path(args.sortie).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(f"\n({args.etude} : {time.time() - began:.0f} s)", flush=True)


STUDIES = {"donnees": donnees, "portage": portage, "heure": heure, "grille": grille, "peur": peur, "ecarts": ecarts,
           "passif": passif, "volatilite": volatilite}

if __name__ == "__main__":
    main()
