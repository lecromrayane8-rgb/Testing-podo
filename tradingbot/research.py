"""La base de recherche des bots : les effets documentés par des études de finance, traduits en règles que le labo
teste et que les bots utilisent si elles passent.

Le chemin d'une idée est toujours le même :
1. une étude relue par des pairs documente un effet (par exemple : en crypto, la tendance des 1 à 8 dernières semaines
   continue) ;
2. l'effet devient une règle chiffrée, avec des réglages fixés ici d'après l'étude, jamais ajustés sur nos données ;
3. le labo la teste sur les vraies données de l'utilisateur (étude, validation, test final jamais regardé, seuil durci
   selon le nombre d'essais) ;
4. si elle tient, le tournoi (ou le portefeuille) la fait tourner en argent fictif ; plusieurs semaines plus tard,
   éventuellement, le testnet.
Les bots n'agissent donc jamais « parce qu'une étude le dit » : ils appliquent les règles qui ont passé le labo.
Les sources (clés de `knowledge.SOURCES`) renvoient aux pages des études.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .strategy import StrategyParams

TREND = {"stop_atr_mult": 3.0, "max_bars_in_trade": 0}  # suivre une tendance : stop large, pas de stop temporel
# Supports et résistances : un sommet ou un creux net sur 5 bougies de chaque côté, parmi les 150 dernières, touché au
# moins 2 fois ; une zone large d'une demi-bougie moyenne. Des réglages ronds et courants, fixés d'avance.
LEVELS = {"level_window": 5, "level_lookback": 150, "level_touches": 2, "level_tol": 0.5}


@dataclass(frozen=True)
class Idea:
    key: str
    title: str
    finding: str  # ce que les études ont trouvé, en une phrase
    sources: tuple[str, ...]
    rules: dict[str, StrategyParams] = field(default_factory=dict)  # règles par crypto, ajoutées au labo
    portfolio: tuple[str, ...] = ()  # variantes du labo portefeuille (tradingbot/portfolio.py)
    caution: str = ""  # pourquoi l'idée ne devient pas une règle de plus
    unfavorable: bool = True  # sans règle : la recherche est défavorable (sinon, information seulement)


IDEAS = (
    Idea("momentum-serie", "La tendance des dernières semaines continue",
         "En crypto, un fort momentum sur 1 à 8 semaines, qui s'inverse en partie ensuite.",
         ("liu_tsyvinski", "hong"),
         rules={"Momentum 7": StrategyParams(strategy_type="momentum", momentum_period=7, trend_period=0, **TREND),
                "Momentum 28": StrategyParams(strategy_type="momentum", momentum_period=28, trend_period=0, **TREND)}),
    Idea("prix-moyenne", "Le prix au-dessus de sa moyenne mobile",
         "Le rapport entre le prix et ses moyennes mobiles prévoit les rendements journaliers du Bitcoin, y compris "
         "sur des années que le modèle n'avait pas vues.",
         ("detzel",),
         rules={"Prix au-dessus de la MM 20": StrategyParams(strategy_type="croisement", fast_period=1, slow_period=20,
                                                            trend_period=0, **TREND),
                "Prix au-dessus de la MM 50": StrategyParams(strategy_type="croisement", fast_period=1, slow_period=50,
                                                            trend_period=0, **TREND)}),
    Idea("supports", "Les supports et les résistances",
         "Les supports et résistances annoncent bien des arrêts de tendance, et les tendances accélèrent une fois un "
         "niveau franchi : les ordres s'y accumulent, surtout aux chiffres ronds.",
         ("osler_2000", "osler_2003", "kavajecz", "brock"),
         rules={"Rebond sur support": StrategyParams(strategy_type="support", trend_period=0, stop_atr_mult=1.5,
                                                     max_bars_in_trade=48, **LEVELS),
                "Rebond sur support + MM200": StrategyParams(strategy_type="support", trend_period=200,
                                                             stop_atr_mult=1.5, max_bars_in_trade=48, **LEVELS),
                "Cassure de résistance": StrategyParams(strategy_type="resistance", trend_period=0, stop_atr_mult=2.5,
                                                        max_bars_in_trade=0, **LEVELS),
                "Cassure de résistance + volume x2": StrategyParams(strategy_type="resistance", trend_period=0,
                                                                    stop_atr_mult=2.5, max_bars_in_trade=0,
                                                                    volume_mult=2.0, **LEVELS)}),
    Idea("chiffres-ronds", "Les chiffres ronds",
         "Les prix du Bitcoin s'accumulent aux chiffres ronds (plus de 10 % finissent par 00), mais rien de "
         "particulier ne se passe ensuite.",
         ("urquhart_clustering", "osler_2003"),
         caution="Le bot les montre sur les graphiques et dans ses explications, sans en faire une règle à part : "
                 "l'étude ne trouve pas de rendement particulier après un chiffre rond.", unfavorable=False),
    Idea("momentum-croise", "Garder les cryptos qui ont le plus monté",
         "Avec la taille et le marché, le momentum entre cryptos est l'un des trois facteurs qui expliquent leurs "
         "rendements.",
         ("liu_tsyvinski_wu", "kosc"),
         portfolio=("Momentum croisé 7 j, 3 cryptos", "Momentum croisé 7 j, 5 cryptos", "Momentum croisé 14 j, 3 cryptos",
                    "Momentum croisé 14 j, 5 cryptos", "Momentum croisé 28 j, 3 cryptos",
                    "Momentum croisé 28 j, 5 cryptos")),
    Idea("surreaction", "Parier contre un excès",
         "Après un jour excessif, le suivant bouge plus fort que d'habitude, mais parier sur le retournement n'a pas "
         "rapporté une fois testé par un robot de trading.",
         ("caporale_overreactions",),
         caution="La recherche est défavorable : le bot garde ces règles (RSI, Bollinger) parce qu'elles sont simples à "
                 "comprendre, mais ne leur fait confiance qu'après le labo."),
    Idea("intraday", "Trader en minutes plutôt qu'en jours",
         "Sur le Bitcoin, trader en 5 minutes fait moins bien qu'en jours, et l'achat-conservation y bat les "
         "stratégies testées. Chez les particuliers, deux fois plus de day traders perdent qu'ils ne gagnent.",
         ("resta", "jordan_diltz", "kuo_lin"),
         caution="La recherche est défavorable, et le labo court terme de l'utilisateur l'a confirmé : les frais "
                 "mangent les petits mouvements."),
)
IDEAS_BY_KEY = {idea.key: idea for idea in IDEAS}

# Les règles par crypto issues de la recherche : le labo (long et court terme) les teste avec les autres variantes.
RESEARCH_VARIANTS: dict[str, StrategyParams] = {name: params for idea in IDEAS for name, params in idea.rules.items()}
