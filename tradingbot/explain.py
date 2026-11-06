"""Lire un graphique et expliquer un trade en mots simples, comme un trader qui commente son écran.

- `read_chart` : ce qu'on voit à la dernière bougie (tendance de fond, support et résistance les plus proches, RSI,
  taille des bougies face aux frais, chiffres ronds) et le scénario qu'un trader y verrait. C'est une lecture pour
  comprendre, jamais un ordre : le bot n'achète que sur les règles que le labo a testées.
- `rule_sentence` : pourquoi une règle a acheté, dans les mots de sa famille.
- `diagnose` : après la vente, ce qui s'est passé (le scénario s'est déroulé, faux départ, gain rendu, frais trop
  lourds, rien ne s'est passé) et la leçon à en tirer.
- `lessons` : ce qu'une série de trades apprend, avec le nombre de trades derrière chaque phrase et la mise en garde
  quand ils sont trop peu nombreux pour conclure.
Les rendements sont des fractions (0,012 = +1,2 %).
"""
from __future__ import annotations

import math
from collections import Counter

import pandas as pd

from .indicators import rsi, sma
from .levels import candle_size, levels_now, nearest, round_levels
from .strategy import StrategyParams

MINUS = "−"
TREND_PERIOD, TREND_SLOPE_BARS, RECENT_BARS = 200, 20, 24
DEFAULT_FEES = 0.003  # aller-retour au comptant : frais au marché et glissement, achat et vente


def pct(x: float | None, digits: int = 1, signed: bool = True) -> str:
    """0,0123 -> « +1,2 % » (à la française, avec un vrai signe moins)."""
    if x is None or not math.isfinite(x):
        return "—"
    text = f"{abs(100 * x):.{digits}f}".replace(".", ",")
    if float(text.replace(",", ".")) == 0:
        return f"{text} %"
    sign = ("+" if x > 0 else MINUS) if signed else ("" if x >= 0 else MINUS)
    return f"{sign}{text} %"


def decimal(x: float, digits: int = 1) -> str:
    """2.345 -> « 2,3 »."""
    return f"{x:.{digits}f}".replace(".", ",")


def price(x: float | None) -> str:
    """68 400,5 -> « 68 400 » ; 0,0000123 -> « 0,0000123 » : assez de chiffres pour lire le prix."""
    if x is None or not math.isfinite(x):
        return "—"
    if x >= 1000:
        text = f"{x:,.0f}".replace(",", " ")
    elif x >= 1:
        text = f"{x:.2f}"
    elif x > 0:
        text = f"{x:.{max(2, 3 - int(math.floor(math.log10(x))))}f}"  # 0,1532 ; 0,00001235 : quatre chiffres utiles
        text = text.rstrip("0") if len(text.split(".")[1].rstrip("0")) >= 2 else f"{x:.2f}"
    else:
        text = "0"
    text = text.replace(".", ",")
    return text[:-3] if text.endswith(",00") else text


def _level(zone, close: float) -> dict | None:
    if zone is None:
        return None
    return {"price": zone.price, "low": zone.low, "high": zone.high, "touches": zone.touches,
            "distance": zone.price / close - 1}


def read_chart(df: pd.DataFrame, fees: float = DEFAULT_FEES, window: int = 5, lookback: int = 150) -> dict:
    """La lecture du graphique à la dernière bougie de `df` (bougies clôturées seulement)."""
    close = df["close"]
    last = float(close.iloc[-1])
    out: dict = {"price": last, "sentences": []}
    say = out["sentences"].append
    ma200 = sma(close, TREND_PERIOD)
    if len(df) >= TREND_PERIOD + TREND_SLOPE_BARS and math.isfinite(ma200.iloc[-1]):
        level, before = float(ma200.iloc[-1]), float(ma200.iloc[-1 - TREND_SLOPE_BARS])
        if last > level and level > before:
            out["trend"] = "hausse"
            say("Tendance de fond : hausse. Le prix est au-dessus de sa moyenne des 200 dernières bougies, qui monte.")
        elif last < level and level < before:
            out["trend"] = "baisse"
            say("Tendance de fond : baisse. Le prix est sous sa moyenne des 200 dernières bougies, qui descend.")
        else:
            out["trend"] = "indécise"
            say("Tendance de fond : indécise. Le prix et sa moyenne des 200 dernières bougies ne vont pas dans le même "
                "sens.")
        out["ma200"] = level
    else:
        out["trend"] = None
        say("Pas encore assez d'historique pour juger la tendance de fond (il faut plus de 200 bougies).")

    zones = levels_now(df, window, lookback)
    size = float(candle_size(df).iloc[-1]) if len(df) > 14 else math.nan
    support, resistance = nearest(zones, last)
    out["support"], out["resistance"] = _level(support, last), _level(resistance, last)
    out["levels"] = [{"price": z.price, "low": z.low, "high": z.high, "touches": z.touches} for z in zones]
    inside = next((z for z in zones if z.touches >= 2 and math.isfinite(size) and abs(z.price - last) <= 0.5 * size),
                  None)
    if inside:
        say(f"Le prix est en plein dans une zone touchée {inside.touches} fois, vers {price(inside.price)} : c'est là "
            "que tout se joue (rebond ou cassure).")
    if support:
        say(f"Support le plus proche : {price(support.price)} ({pct(support.price / last - 1)}), touché "
            f"{support.touches} fois.")
    else:
        say(f"Aucun support solide en dessous sur les {lookback} dernières bougies.")
    if resistance:
        say(f"Résistance la plus proche : {price(resistance.price)} ({pct(resistance.price / last - 1)}), touchée "
            f"{resistance.touches} fois.")
    else:
        say("Aucune résistance au-dessus : le prix est au plus haut de ses dernières bougies, en terrain libre.")

    r = rsi(close, 14)
    if len(df) > 15 and math.isfinite(r.iloc[-1]):
        value = float(r.iloc[-1])
        out["rsi"] = value
        value = round(value)  # les seuils jugent le nombre affiché : « 70 » est bien au seuil de 70
        if value >= 70:
            say(f"RSI à {value:.0f} : les acheteurs ont beaucoup poussé (au-dessus de 70, on dit « suracheté » ; un "
                "repli devient plus probable, sans certitude).")
        elif value <= 30:
            say(f"RSI à {value:.0f} : les vendeurs ont beaucoup poussé (sous 30, on dit « survendu »).")
        else:
            say(f"RSI à {value:.0f} : ni excès d'achat, ni excès de vente.")
    if math.isfinite(size) and last > 0:
        move = size / last
        out["candle_pct"] = move
        if move < fees:
            say(f"Une bougie bouge en moyenne de {pct(move, 2, False)} : moins que les frais d'un aller-retour "
                f"({pct(fees, 2, False)}). Pour gagner, il faut un mouvement de plusieurs bougies.")
        else:
            say(f"Une bougie bouge en moyenne de {pct(move, 2, False)} ; les frais d'un aller-retour "
                f"({pct(fees, 2, False)}) en valent {100 * fees / move:.0f} %.")
    if len(df) > RECENT_BARS:
        change = last / float(close.iloc[-1 - RECENT_BARS]) - 1
        out["change"] = change
        say(f"Sur les {RECENT_BARS} dernières bougies : {pct(change)}.")
    if "volume" in df and len(df) > 21:
        avg = float(df["volume"].iloc[-21:-1].mean())
        if avg > 0:
            ratio = float(df["volume"].iloc[-1]) / avg
            out["volume_ratio"] = ratio
            if ratio >= 2:
                say(f"Volume {decimal(ratio)} fois plus élevé que d'habitude sur la dernière bougie : beaucoup de monde "
                    "sur ce mouvement.")
    below, above = round_levels(last)
    out["round_below"], out["round_above"] = below, above
    if math.isfinite(above):
        say(f"Chiffres ronds autour du prix : {price(below)} et {price(above)}. Les ordres s'y accumulent souvent.")
    out["plan"] = scenario(last, support, resistance, size)
    if out["plan"]:
        say(out["plan"]["text"])
    return out


def scenario(last: float, support, resistance, size: float) -> dict | None:
    """Ce qu'un trader verrait : un rebond sur le support visant la résistance, avec le gain possible face au risque."""
    if support is None or resistance is None or not math.isfinite(size):
        return None
    stop = support.low - 0.5 * size
    target = resistance.low
    near = last - support.price <= 1.5 * size
    entry = last if near else support.high
    risk, reward = 1 - stop / entry, target / entry - 1
    if not (risk > 0 and reward > 0):
        return None
    ratio = reward / risk
    if near:
        text = (f"Scénario d'un trader : le prix est près du support. Acheter ici, stop juste dessous à {price(stop)} "
                f"({pct(-risk)}), objectif la résistance à {price(target)} ({pct(reward)}) : le gain possible vaut "
                f"{decimal(ratio)} fois le risque.")
    else:
        text = (f"Scénario d'un trader : attendre un retour sur le support ({price(support.price)}) pour acheter, ou une "
                f"clôture au-dessus de la résistance ({price(resistance.price)}) pour suivre la cassure.")
    if near and ratio < 1.5:
        text += " Moins de 1,5 fois : la plupart des traders passeraient leur tour."
    return {"entry": entry, "stop": stop, "target": target, "risk": risk, "reward": reward, "ratio": ratio,
            "near": near, "text": text}


def rule_sentence(p: StrategyParams) -> str:
    """Pourquoi la règle a acheté, dans les mots de sa famille."""
    t = p.strategy_type
    trend = f" dans une tendance de fond haussière (au-dessus de la moyenne des {p.trend_period} bougies)" \
        if p.trend_period else ""
    texts = {
        "retour_moyenne": f"Le RSI sur {p.rsi_period} bougies est tombé sous {p.rsi_entry:g} : une chute brutale, et "
                          f"un rebond est attendu{trend}.",
        "bollinger": f"Le prix a clôturé sous la bande basse de Bollinger : loin sous sa moyenne, un retour vers le milieu "
                     f"est attendu{trend}.",
        "bollinger_cassure": f"Le prix a clôturé au-dessus de la bande haute de Bollinger : un mouvement inhabituellement "
                             f"fort, que le bot suit{trend}.",
        "cassure": f"Le prix a clôturé au-dessus du plus haut des {p.breakout_period} bougies précédentes : un nouveau "
                   f"sommet{trend}.",
        "croisement": (f"Le prix vient de passer au-dessus de sa moyenne des {p.slow_period} dernières clôtures{trend}."
                       if p.fast_period == 1 else
                       f"La moyenne des {p.fast_period} dernières clôtures vient de passer au-dessus de celle des "
                       f"{p.slow_period} : la tendance tourne à la hausse{trend}."),
        "macd": f"La ligne MACD vient de croiser sa ligne de signal par le haut : la hausse accélère{trend}.",
        "momentum": f"Le prix est repassé au-dessus de son niveau d'il y a {p.momentum_period} bougies : la tendance "
                    f"redevient haussière{trend}.",
        "supertrend": f"Le Supertrend vient de passer à la hausse{trend}.",
        "impulsion": f"Le prix a pris plus de {pct(p.impulse_pct, 1, False)} en {p.impulse_bars} bougies : un mouvement "
                     f"soudain, sur lequel le bot saute{trend}.",
        "support": f"Le prix est descendu sur un support solide puis a clôturé au-dessus, en hausse : un rebond{trend}.",
        "resistance": f"Le prix a clôturé nettement au-dessus d'une résistance solide : une cassure{trend}.",
        "ema_croisement": f"La moyenne exponentielle des {p.ema_fast} dernières clôtures vient de passer au-dessus de celle "
                          f"des {p.ema_slow} : la tendance tourne à la hausse{trend}.",
        "vwap": f"Le prix est repassé au-dessus de son prix moyen pondéré par le volume (VWAP sur {p.vwap_period} bougies), "
                f"avec la moyenne exponentielle {p.ema_fast} au-dessus de la {p.ema_slow}{trend}.",
        "stochastique": f"Le stochastique est sorti de la zone de survente (sous {p.stoch_low:g}) en croisant sa moyenne par "
                        f"le haut : un rebond s'amorce{trend}.",
        "keltner": f"Le prix a clôturé au-dessus du canal de Keltner (moyenne + {decimal(p.keltner_mult)} fois la taille "
                   f"moyenne d'une bougie) : un mouvement fort, que le bot suit{trend}.",
        "adx": f"Le DI+ est passé devant le DI− avec une tendance forte (ADX au-dessus de {p.adx_min:g}){trend}.",
        "psar": f"Le Parabolic SAR est passé sous le prix : la tendance devient haussière{trend}.",
        "ichimoku": f"Le prix est passé au-dessus du nuage d'Ichimoku, avec la Tenkan au-dessus de la Kijun{trend}.",
        "zscore": f"Le prix est tombé à plus de {decimal(p.zscore_entry)} écarts-types sous sa moyenne des "
                  f"{p.zscore_period} bougies : un retour vers la moyenne est attendu{trend}.",
        "heikin": f"Les bougies Heikin-Ashi (lissées) sont vertes {p.heikin_bars} fois de suite après une rouge : la "
                  f"hausse s'installe{trend}.",
    }
    filters = []
    if p.volume_mult:
        filters.append(f"le volume valait au moins {p.volume_mult:g} fois sa moyenne")
    if p.min_atr_pct:
        filters.append(f"les bougies bougeaient d'au moins {pct(p.min_atr_pct, 1, False)}")
    if p.active_hours:
        filters.append(f"pendant les heures actives ({p.active_hours} h UTC)")
    if p.squeeze_quantile:
        filters.append("après un marché calme (bandes de Bollinger resserrées)")
    text = texts[t]
    return text + (f" En plus : {', '.join(filters)}." if filters else "")


FAILURES = {
    "support": "Le support n'a pas tenu.",
    "resistance": "La cassure était fausse : le prix est retombé sous l'ancienne résistance.",
    "impulsion": "Le mouvement s'est retourné aussitôt.",
    "retour_moyenne": "Le rebond attendu n'est pas venu : la chute a continué.",
    "bollinger": "Le rebond attendu n'est pas venu : la chute a continué.",
}
SUCCESSES = {
    "support": "Le support a tenu et le prix est remonté vers la résistance.",
    "resistance": "La cassure était la bonne : le prix a continué au-dessus de l'ancienne résistance.",
    "impulsion": "Le mouvement a continué après l'achat.",
    "retour_moyenne": "Le rebond attendu est venu.",
    "bollinger": "Le prix est revenu vers sa moyenne, comme prévu.",
}
KINDS = {  # étiquette courte de chaque diagnostic
    "gagne": "Scénario réussi", "gain_partiel": "Gagné, une partie rendue", "frais": "Bon sens, mais trop petit",
    "faux_depart": "Faux départ", "gain_rendu": "Gagnant, puis retourné", "stop": "Stop touché",
    "temps": "Rien ne s'est passé", "sortie_regle": "La règle a coupé", "liquidation": "Liquidé par le levier",
    "ouvert": "Encore ouvert",
}


def diagnose(t: dict) -> dict:
    """Ce que dit un trade fini. Clés attendues : reason, net, gross, family ; facultatives : mfe, mae, risk, fees,
    bars (plus haut et plus bas atteints pendant le trade, distance du stop, frais, durée en bougies)."""
    reason, net, gross = t["reason"], float(t["net"]), float(t.get("gross", t["net"]))
    family = t.get("family", "")
    mfe, risk, fees = t.get("mfe"), t.get("risk"), t.get("fees") or 0.0
    bars = t.get("bars")
    fail = FAILURES.get(family, "La tendance attendue n'a pas démarré.")
    if reason == "liquidation":
        kind = "liquidation"
        text = f"Le prix a atteint le seuil de liquidation : avec le levier, la marge de ce trade est perdue ({pct(net)})."
        lesson = "Le levier grossit les pertes autant que les gains : un stop placé avant la liquidation l'évite."
    elif reason == "fin du test":
        kind, text, lesson = "ouvert", f"Le trade était encore ouvert à la fin de l'historique ({pct(net)}).", ""
    elif net > 0:
        if mfe is not None and mfe > 0 and net < 0.4 * mfe and mfe >= 2 * max(fees, 1e-9):
            kind = "gain_partiel"
            text = f"Le trade est monté jusqu'à {pct(mfe)} avant de sortir à {pct(net)} après frais."
            lesson = "Une partie du gain s'est évaporée avant la sortie : attendre la confirmation de la sortie a un prix."
        else:
            kind = "gagne"
            text = f"{SUCCESSES.get(family, 'La tendance a joué en faveur du trade.')} Résultat : {pct(net)} après frais " \
                   f"({pct(gross)} avant frais)."
            lesson = "Le scénario prévu s'est déroulé : c'est le cas que la règle cherche."
    elif gross > 0:
        kind = "frais"
        text = f"Le prix est allé dans le bon sens ({pct(gross)}), mais les frais ({pct(fees, 2, False)}) ont tout mangé : " \
               f"{pct(net)} au final."
        lesson = "Les petits mouvements ne paient pas les frais : il faut viser plus loin, ou payer moins de frais."
    elif reason == "stop":
        if mfe is not None and risk and mfe >= risk:
            kind = "gain_rendu"
            text = f"Le trade a été gagnant (jusqu'à {pct(mfe)}), puis le prix s'est retourné jusqu'au stop : {pct(net)}."
            lesson = "Prendre une partie du bénéfice plus tôt, ou remonter le stop, aurait protégé ce gain."
        elif mfe is not None and risk and mfe < 0.25 * risk:
            kind = "faux_depart"
            text = f"Le prix est reparti contre le trade presque tout de suite, jusqu'au stop : {pct(net)}. {fail}"
            lesson = "Un signal faux fait partie du jeu : le stop a limité la perte comme prévu."
        else:
            kind = "stop"
            text = f"Le prix a hésité, puis touché le stop : {pct(net)}. {fail}"
            lesson = "Le scénario n'a pas tenu ; le stop a fait son travail en coupant la perte."
    elif reason == "temps":
        kind = "temps"
        text = f"Après {bars} bougies sans le mouvement attendu, le bot a coupé : {pct(net)}." if bars else \
            f"Le mouvement attendu n'est pas venu à temps : {pct(net)}."
        lesson = "Quand le mouvement ne vient pas, mieux vaut libérer l'argent pour un autre trade."
    else:
        kind = "sortie_regle"
        text = f"La règle de sortie ({reason}) a parlé avant que le trade ne devienne gagnant : {pct(net)}. {fail}"
        lesson = "La règle de sortie a limité la casse en voyant le scénario se retourner."
    return {"kind": kind, "title": KINDS[kind], "text": text, "lesson": lesson}


MIN_GROUP = 8  # trades par groupe en dessous desquels on ne compare pas


def lessons(trades: list[dict]) -> list[dict]:
    """Ce qu'une série de trades apprend, stratégie par stratégie. Chaque trade : strategy, symbol, net, kind et,
    s'il est connu, trend (la tendance de fond à l'achat). Les phrases donnent toujours le nombre de trades."""
    out = []
    by_strategy: dict[str, list[dict]] = {}
    for t in trades:
        if t.get("kind") != "ouvert":
            by_strategy.setdefault(t["strategy"], []).append(t)
    for name, ts in sorted(by_strategy.items(), key=lambda kv: -len(kv[1])):
        n = len(ts)
        wins = sum(t["net"] > 0 for t in ts)
        avg = sum(t["net"] for t in ts) / n
        losses = [t for t in ts if t["net"] <= 0]
        text = f"« {name} » : {n} trade{'s' if n > 1 else ''}, {round(100 * wins / n)} % gagnants, {pct(avg, 2)} par " \
               "trade en moyenne après frais."
        if losses:
            kind, count = Counter(t["kind"] for t in losses).most_common(1)[0]
            text += f" Perte la plus fréquente : « {KINDS.get(kind, kind)} » ({count} sur {len(losses)})."
        if n < 30:
            text += " Trop peu de trades pour conclure : le hasard pèse encore beaucoup."
        out.append({"strategy": name, "n": n, "text": text})
        up = [t for t in ts if t.get("trend") == "hausse"]
        down = [t for t in ts if t.get("trend") == "baisse"]
        if len(up) >= MIN_GROUP and len(down) >= MIN_GROUP:
            a = sum(t["net"] > 0 for t in up) / len(up)
            b = sum(t["net"] > 0 for t in down) / len(down)
            if abs(a - b) >= 0.2:
                out.append({"strategy": name, "n": len(up) + len(down), "text":
                            f"« {name} » gagne {round(100 * a)} % du temps quand la tendance de fond monte, contre "
                            f"{round(100 * b)} % quand elle baisse ({len(up)} et {len(down)} trades). À confirmer : sur "
                            "si peu de trades, le hasard peut créer un tel écart. Le labo teste justement des versions "
                            "avec filtre de tendance."})
        coins: dict[str, list[float]] = {}
        for t in ts:
            coins.setdefault(t.get("symbol", "?"), []).append(t["net"])
        rated = sorted(((sum(v) / len(v), c, len(v)) for c, v in coins.items() if len(v) >= 5), reverse=True)
        if len(rated) >= 2:
            (best, bc, bn), (worst, wc, wn) = rated[0], rated[-1]
            out.append({"strategy": name, "n": bn + wn, "text":
                        f"Pour « {name} », meilleure crypto : {bc.split('/')[0]} ({pct(best, 2)} par trade sur {bn}) ; "
                        f"la moins bonne : {wc.split('/')[0]} ({pct(worst, 2)} sur {wn})."})
    return out
