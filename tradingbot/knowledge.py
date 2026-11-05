"""Ce que le bot sait des courbes : chaque technique, ce qu'elle mesure, comment la lire, ce qu'en dit la recherche
publiée (études relues par des pairs, avec leurs liens) et ce qu'en dit le labo de l'utilisateur sur ses propres
données. Affiché dans l'onglet « Comprendre » du site.

La recherche donne des pistes, pas des certitudes : ce qui a marché sur d'autres marchés ou d'autres années peut ne
plus marcher, et beaucoup de profits publiés fondent une fois comptés les frais et le nombre de règles essayées. C'est
pourquoi une idée tirée d'une étude entre dans le bot comme une règle de plus à tester dans le labo, jamais comme un
ordre d'achat.
"""
from __future__ import annotations

import math
from pathlib import Path

from .lab import ALL_VARIANTS, LAB_FILES, load_lab
from .robustness import MIN_TRADES
from .strategy import STRATEGY_TYPES

SCISPACE = "https://scispace.com/papers/"
SOURCES = {  # clé -> (référence courte, page de l'étude)
    "park_irwin": ("Park et Irwin, 2007 · Journal of Economic Surveys",
                   SCISPACE + "what-do-we-know-about-the-profitability-of-technical-4svhpdrsbw"),
    "hsu_kuan": ("Hsu et Kuan, 2005 · Journal of Financial Econometrics",
                 SCISPACE + "reexamining-the-profitability-of-technical-analysis-with-3p9n4soxs6"),
    "hudson_urquhart": ("Hudson et Urquhart, 2021 · Annals of Operations Research",
                        SCISPACE + "technical-trading-and-cryptocurrencies-1w8eblmirh"),
    "resta": ("Resta, Pagnottoni et De Giuli, 2020 · le Bitcoin en 5 minutes et en jours",
              SCISPACE + "technical-analysis-on-the-bitcoin-market-trading-4gp1abyifg"),
    "ready": ("Ready, 1998 · glissement et frais réels",
              SCISPACE + "profits-from-technical-trading-rules-4ligcj7waw"),
    "zakamulin": ("Zakamulin, 2014 · Journal of Asset Management",
                  SCISPACE + "the-real-life-performance-of-market-timing-with-moving-vsu9awlsga"),
    "detzel": ("Detzel, Liu et Strauss, 2021 · Financial Management",
               SCISPACE + "learning-and-predictability-via-technical-analysis-evidence-2pp4nr99el"),
    "liu_tsyvinski": ("Liu et Tsyvinski, 2021 · Review of Financial Studies",
                      SCISPACE + "risks-and-returns-of-cryptocurrency-n5yjfxlljc"),
    "hong": ("Hong, 2017 · Information Technology & Management",
             SCISPACE + "bitcoin-as-an-alternative-investment-vehicle-1fl29x7uwg"),
    "liu_tsyvinski_wu": ("Liu, Tsyvinski et Wu · Common Risk Factors in Cryptocurrency (NBER, 2019)",
                         SCISPACE + "common-risk-factors-in-cryptocurrency-4zmx2us8fn"),
    "kosc": ("Kosc, Sakowski et Ślepaczuk, 2019 · Physica A",
             SCISPACE + "momentum-and-contrarian-effects-on-the-cryptocurrency-market-25qyds3z4a"),
    "caporale_overreactions": ("Caporale et Plastun, 2019 · Journal of Economic Studies",
                               SCISPACE + "price-overreactions-in-the-cryptocurrency-market-2wmsozh1bp"),
    "caporale_momentum": ("Caporale et Plastun, 2020 · Financial Markets and Portfolio Management",
                          SCISPACE + "momentum-effects-in-the-cryptocurrency-market-after-one-day-22x4jnb5a2"),
    "lo": ("Lo, Mamaysky et Wang, 2000 · Journal of Finance",
           SCISPACE + "foundations-of-technical-analysis-computational-algorithms-4h8k8gtawh"),
    "savin": ("Savin, Weller et Zvingelis, 2006 · Journal of Financial Econometrics",
              SCISPACE + "the-predictive-power-of-head-and-shoulders-price-patterns-in-27vef4itvx"),
    "caginalp": ("Caginalp et Laurent, 1998 · Applied Mathematical Finance",
                 SCISPACE + "the-predictive-power-of-price-patterns-2cp7mk7862"),
    "jiang": ("Jiang, Kelly et Xiu, 2023 · Journal of Finance",
              SCISPACE + "re-imag-in-ing-price-trends-25je0svpuj"),
}

# Une fiche par idée. `family` : la famille du bot qu'elle décrit (ses résultats de labo s'affichent à côté) ;
# `uses` : un filtre d'achat (même chose pour les variantes qui l'utilisent) ; ni l'un ni l'autre : pas encore testable.
ENTRIES = (
    {"key": "recherche", "title": "Ce que dit la recherche, en bref", "group": "L'essentiel",
     "measures": "Des dizaines d'études ont testé l'analyse technique sur les actions, les devises, les matières "
                 "premières et les cryptos, avec des contrôles pour ne pas se laisser tromper par la chance.",
     "reading": "Trois leçons reviennent partout : ça marchait mieux autrefois et sur des marchés jeunes ; les frais et "
                "le glissement mangent une grande partie des gains publiés ; essayer beaucoup de règles finit "
                "toujours par en trouver une qui a gagné par hasard.",
     "research": "Profits fréquents jusqu'au début des années 1990, plus rares ensuite (Park et Irwin). Les marchés "
                 "jeunes restent plus prévisibles (Hsu et Kuan). En crypto, sur des bougies d'un jour, des milliers de "
                 "règles montrent une vraie prévisibilité, mais plus pour le Bitcoin sur la période récente (Hudson "
                 "et Urquhart). En 5 minutes, le Bitcoin se trade moins bien qu'en jours, et l'achat-conservation y bat "
                 "les stratégies testées (Resta et al.) : c'est ce que ton labo court terme a trouvé. Les gains publiés "
                 "fondent souvent une fois le glissement compté (Ready) ou les essais trop nombreux corrigés "
                 "(Zakamulin) : d'où le test final et le seuil durci de ton labo.",
     "sources": ("park_irwin", "hsu_kuan", "hudson_urquhart", "resta", "ready", "zakamulin")},
    {"key": "momentum", "family": "momentum", "title": "Momentum : la tendance continue", "group": "Suivre une tendance",
     "measures": "Le prix d'aujourd'hui comparé à celui d'il y a N bougies.",
     "reading": "Au-dessus : la tendance est à la hausse, le bot achète ; s'il repasse dessous, il revend.",
     "research": "C'est l'effet le mieux établi en crypto : un fort momentum, sur des horizons de 1 à 8 semaines, qui "
                 "s'inverse en partie ensuite (Liu et Tsyvinski ; Hong). Ton labo long terme teste donc aussi le "
                 "momentum sur 7 et 28 bougies d'un jour, soit 1 et 4 semaines, choisis d'après ces études et pas "
                 "d'après tes données.",
     "sources": ("liu_tsyvinski", "hong")},
    {"key": "croisement", "family": "croisement", "title": "Moyennes mobiles et croisements", "group": "Suivre une tendance",
     "measures": "La moyenne des N dernières clôtures : elle lisse le bruit des bougies.",
     "reading": "Quand la moyenne rapide passe au-dessus de la lente, la tendance devient haussière ; le filtre « MM200 » "
                "n'achète que si le prix est au-dessus de sa moyenne sur 200 bougies.",
     "research": "L'écart entre le prix et ses moyennes mobiles prévoit les rendements journaliers du Bitcoin, y compris "
                 "sur des années que le modèle n'avait pas vues (Detzel, Liu et Strauss). Sur le Bitcoin, les moyennes "
                 "mobiles font le mieux en données journalières, pas en intraday (Resta et al.). Méfiance envers les "
                 "résultats trop beaux : beaucoup viennent de réglages essayés jusqu'à ce que ça marche (Zakamulin).",
     "sources": ("detzel", "resta", "zakamulin")},
    {"key": "macd", "family": "macd", "title": "MACD", "group": "Suivre une tendance",
     "measures": "L'écart entre deux moyennes exponentielles (12 et 26 bougies) et sa propre moyenne (9).",
     "reading": "Quand la ligne MACD passe au-dessus de sa ligne de signal, la tendance s'accélère à la hausse.",
     "research": "C'est un croisement de moyennes plus réactif : mêmes conclusions que pour les moyennes mobiles.",
     "sources": ("detzel", "zakamulin")},
    {"key": "cassure", "family": "cassure", "title": "Cassures (canal de Donchian)", "group": "Suivre une tendance",
     "measures": "Le plus haut et le plus bas des N dernières bougies.",
     "reading": "Une clôture au-dessus du plus haut annonce peut-être une nouvelle tendance ; le bot revend sous le "
                "plus bas des M dernières bougies.",
     "research": "Les cassures de canal font partie des cinq grandes familles de règles qui montrent une prévisibilité "
                 "en crypto sur des bougies d'un jour, même après les contrôles contre le hasard (Hudson et Urquhart). "
                 "Triangles et drapeaux en sont des cas particuliers.",
     "sources": ("hudson_urquhart",)},
    {"key": "bollinger_cassure", "family": "bollinger_cassure", "title": "Bandes de Bollinger : sortie par le haut",
     "group": "Suivre une tendance",
     "measures": "Une moyenne sur 20 bougies et deux bandes à deux écarts-types : la plupart des prix restent dedans.",
     "reading": "Une clôture au-dessus de la bande haute est un mouvement inhabituel, que le bot suit jusqu'au retour "
                "sous la moyenne.",
     "research": "Une cassure dont le seuil suit la volatilité : mêmes conclusions que pour les cassures de canal.",
     "sources": ("hudson_urquhart",)},
    {"key": "supertrend", "family": "supertrend", "title": "Supertrend", "group": "Suivre une tendance",
     "measures": "Une ligne placée à k fois l'ATR (la taille moyenne des bougies) sous ou au-dessus du prix.",
     "reading": "Le prix passe au-dessus : tendance haussière, jusqu'à ce qu'il repasse dessous.",
     "research": "Pas d'étude solide qui lui soit consacrée : c'est une cousine des cassures de canal, avec une marge qui "
                 "suit la volatilité. Seul ton labo peut la juger.",
     "sources": ("hudson_urquhart",)},
    {"key": "retour_moyenne", "family": "retour_moyenne", "title": "RSI : acheter une chute brutale",
     "group": "Acheter un repli",
     "measures": "Le RSI compare les hausses et les baisses récentes, de 0 à 100 ; sous 10 (sur 2 bougies), le prix "
                 "vient de chuter fort et vite.",
     "reading": "Le bot achète la chute en pariant sur un rebond, seulement si la tendance de fond monte (MM200), et "
                "revend au rebond.",
     "research": "En crypto, après un jour excessif, le jour suivant bouge plus fort que d'habitude, mais parier sur le "
                 "retournement n'a pas rapporté une fois testé par un robot de trading (Caporale et Plastun 2019).",
     "sources": ("caporale_overreactions",)},
    {"key": "bollinger", "family": "bollinger", "title": "Bandes de Bollinger : rebond", "group": "Acheter un repli",
     "measures": "Les mêmes bandes à deux écarts-types autour d'une moyenne sur 20 bougies.",
     "reading": "Sous la bande basse, le prix est loin de sa moyenne : le bot parie sur un retour vers le milieu.",
     "research": "Même pari que le RSI : acheter un excès. Mêmes réserves.",
     "sources": ("caporale_overreactions",)},
    {"key": "impulsion", "family": "impulsion", "title": "Impulsions : sauter sur un mouvement",
     "group": "Court terme",
     "measures": "La hausse sur les N dernières bougies, par exemple +1 % en 5 minutes : ce que le radar marque en jaune.",
     "reading": "Le bot achète à la bougie où le mouvement apparaît, et revend quand il s'essouffle.",
     "research": "Un jour de rendement anormal tend à continuer dans le même sens jusqu'à la fin de ce jour (Caporale et "
                 "Plastun 2020). Mais en intraday, frais et glissement mangent l'avantage : sur le Bitcoin, trader en 5 "
                 "minutes fait moins bien qu'en jours (Resta et al.). Le journal des mouvements jaunes du radar le "
                 "mesure en direct.",
     "sources": ("caporale_momentum", "resta")},
    {"key": "volume", "uses": "volume_mult", "title": "Volume et attention", "group": "Filtres d'achat",
     "measures": "Le volume échangé pendant la bougie, comparé à sa moyenne.",
     "reading": "Un mouvement suivi par deux ou trois fois plus d'échanges que d'habitude a des acheteurs derrière lui.",
     "research": "En crypto, l'attention des investisseurs (recherches en ligne, échanges) aide à prévoir les rendements "
                 "(Liu et Tsyvinski). Les variantes « + volume » du labo testent ce filtre.",
     "sources": ("liu_tsyvinski",)},
    {"key": "figures", "title": "Figures chartistes : épaule-tête-épaule, double sommet, chandeliers",
     "group": "Ce que le bot ne fait pas (encore)",
     "measures": "Des formes dessinées par le prix sur le graphique, reconnues à l'œil par les chartistes.",
     "reading": "Elles annoncent, dit-on, un retournement ou une continuation de la tendance.",
     "research": "Reconnues automatiquement sur des actions, certaines figures apportent un peu d'information (Lo, "
                 "Mamaysky et Wang ; plus récemment Jiang, Kelly et Xiu avec de l'apprentissage automatique sur les "
                 "graphiques), mais trader l'épaule-tête-épaule seule ne rapporte presque rien (Savin, Weller et "
                 "Zvingelis). Les chandeliers sur 3 jours ont montré un effet sur des actions des années 1990 (Caginalp "
                 "et Laurent). Leur défaut : on les voit souvent après coup. Le bot en garde la forme objective et "
                 "testable : les cassures.",
     "sources": ("lo", "savin", "caginalp", "jiang")},
    {"key": "momentum-croise", "title": "Momentum croisé : garder les cryptos qui ont le plus monté",
     "group": "Ce que le bot ne fait pas (encore)",
     "measures": "Chaque semaine, classer les cryptos selon leur hausse récente.",
     "reading": "Garder les plus fortes, revendre les plus faibles, et recommencer la semaine suivante.",
     "research": "Avec la taille et le marché, le momentum est l'un des trois facteurs qui expliquent les rendements des "
                 "cryptos (Liu, Tsyvinski et Wu) ; une étude sur 100 cryptos compare momentum et contre-tendance selon "
                 "la période et les frais (Kosc et al.). Il faut un labo qui compare les cryptos entre elles : c'est la "
                 "prochaine piste à construire.",
     "sources": ("liu_tsyvinski_wu", "kosc")},
)


def finite(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def lab_rows(data_dir: Path) -> list[dict]:
    """Toutes les lignes des labos de l'utilisateur, chacune avec le titre de son labo."""
    rows = []
    for name, title in LAB_FILES:
        for row in (load_lab(data_dir / name) or {}).get("rows") or []:
            if row.get("variant") in ALL_VARIANTS:
                rows.append({**row, "lab": title})
    return rows


def evidence(entry: dict, rows: list[dict]) -> dict | None:
    """Ce que les labos de l'utilisateur disent de cette idée : combien d'essais, et la meilleure version après frais."""
    family, uses = entry.get("family"), entry.get("uses")
    if not family and not uses:
        return None
    mine = [r for r in rows if (family and ALL_VARIANTS[r["variant"]].strategy_type == family)
            or (uses and getattr(ALL_VARIANTS[r["variant"]], uses))]
    judged = [r for r in mine if (r.get("trades") or 0) >= MIN_TRADES and finite(r.get("expectancy_pct")) is not None]
    best = max(judged, key=lambda r: finite(r["expectancy_pct"])) if judged else None
    return {
        "tested": len(mine), "judged": len(judged),
        "retained": sum(r.get("verdict") in ("prometteur", "à surveiller") for r in mine),
        "best": {"variant": best["variant"], "timeframe": best.get("timeframe"), "lab": best["lab"],
                 "net": finite(best["expectancy_pct"]), "gross": finite(best.get("gross_expectancy_pct")),
                 "verdict": best.get("verdict")} if best else None,
    }


def knowledge(data_dir: Path) -> dict:
    rows = lab_rows(data_dir)
    return {
        "entries": [{**{k: v for k, v in e.items() if k != "sources"},
                     "sources": [{"title": SOURCES[s][0], "url": SOURCES[s][1]} for s in e["sources"]],
                     "lab": evidence(e, rows)} for e in ENTRIES],
        "families_covered": sorted({e["family"] for e in ENTRIES if e.get("family")}),
        "all_families": list(STRATEGY_TYPES),
    }
