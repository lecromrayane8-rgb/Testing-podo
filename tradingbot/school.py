"""L'école du trading : des leçons courtes pour un débutant, affichées dans l'onglet « École » du site.

Chaque leçon : une seule idée, un exemple chiffré, au plus un schéma ou un simulateur quand l'idée a une forme (une
bougie, un graphique réel avec ses supports, le levier qu'on fait varier soi-même), puis ce qu'il faut retenir et un
mini-quiz dont chaque réponse est expliquée. Les sources sont les études de knowledge.SOURCES. La dernière leçon
montre les vrais trades des bots de l'utilisateur, avec leur diagnostic.

Rien ici n'est un conseil d'investissement : l'école explique comment les traders raisonnent et pourquoi le bot teste
tout avant de s'en servir.
"""
from __future__ import annotations

import json
from pathlib import Path

from .explain import KINDS
from .knowledge import SOURCES

FIGURES = ("candle", "chart", "risk", "leverage", "fees", "diagnoses")

LESSONS = (
    {"id": "trading", "title": "Le trading, c'est quoi ?", "minutes": 4,
     "blocks": [
         {"text": "Trader, c'est acheter quelque chose pour le revendre plus cher. Le gain vient de la différence de "
                  "prix, moins les frais payés à l'achat et à la vente."},
         {"example": "Tu achètes 100 $ de Bitcoin. Il monte de 3 % : tu revends 103 $. Les frais (environ 0,1 % à "
                     "l'achat et 0,1 % à la vente) te coûtent 0,20 $ : il te reste 2,80 $ de gain."},
         {"text": "Le piège qui attrape presque tout le monde : gagner souvent ne suffit pas. Avec 7 trades sur 10 à "
                  "+0,5 % et 3 trades à −2 %, tu gagnes 3,5 % et tu perds 6 % : au total, −2,5 %. Tu as gagné 7 fois "
                  "sur 10… et tu as perdu de l'argent."},
         {"text": "Ce qui compte, c'est la moyenne par trade, frais compris : l'« espérance ». C'est le premier "
                  "chiffre que ton labo regarde."},
         {"text": "La vérité qui fâche : chez les particuliers, deux fois plus de day traders perdent qu'ils ne "
                  "gagnent. Le trading n'est pas un salaire, c'est une compétition où chaque coup est payant."},
     ],
     "remember": ["Gain = différence de prix − frais.",
                  "Ce qui compte : la moyenne par trade après frais, pas le nombre de trades gagnants.",
                  "Personne ne gagne à tous les coups ; la plupart des day traders perdent."],
     "quiz": [
         {"q": "Une stratégie gagne 8 trades sur 10 à +1 % et perd 2 trades à −5 %. Sur ces 10 trades, elle…",
          "choices": ["gagne 8 %", "perd 2 %", "finit à zéro"], "answer": 1,
          "why": "8 × 1 % = +8 %, 2 × 5 % = −10 % : −2 % au total, malgré 80 % de trades gagnants."},
         {"q": "Qu'est-ce qui décide vraiment si une stratégie rapporte ?",
          "choices": ["Le pourcentage de trades gagnants", "La moyenne par trade, frais compris",
                      "Le nombre de trades par jour"], "answer": 1,
          "why": "Une stratégie qui gagne rarement mais beaucoup peut rapporter ; une qui gagne souvent un peu et perd "
                 "parfois beaucoup peut faire perdre."},
     ],
     "sources": ["jordan_diltz"]},
    {"id": "crypto", "title": "Une crypto, c'est quoi ?", "minutes": 4,
     "blocks": [
         {"text": "Une crypto est une monnaie numérique. Pas de banque centrale : un registre public, la "
                  "« blockchain », garde la trace de qui possède quoi, copié sur des milliers d'ordinateurs."},
         {"text": "Le Bitcoin (BTC, 2009) est la première ; il n'y en aura jamais plus de 21 millions. Ether (ETH) "
                  "sert aussi à faire tourner des programmes. Les autres (Solana, XRP…) sont appelées « altcoins ». "
                  "Les memecoins (DOGE, PEPE…) n'ont souvent qu'une blague ou une communauté derrière eux : ils "
                  "bougent énormément, dans les deux sens."},
         {"text": "USDT (Tether) et USDC sont des « stablecoins » : des jetons qui valent toujours environ 1 dollar. "
                  "BTC/USDT, c'est donc le prix d'un Bitcoin en dollars numériques."},
         {"example": "Le Bitcoin peut faire ±5 % dans une journée, un memecoin ±30 %. C'est ce qui attire les traders, "
                     "et ce qui fait perdre vite."},
         {"text": "Les cryptos s'échangent sur des plateformes (Binance, Kraken, Coinbase…), 24 h sur 24, 7 jours sur "
                  "7. En France, seules les plateformes agréées MiCA peuvent te proposer leurs services : vérifie "
                  "avant d'y mettre de l'argent réel."},
     ],
     "remember": ["Une crypto = une monnaie numérique tenue par un registre public (la blockchain).",
                  "USDT ≈ 1 dollar : BTC/USDT est le prix du Bitcoin en dollars.",
                  "Les memecoins bougent très fort dans les deux sens."],
     "quiz": [
         {"q": "Que veut dire BTC/USDT ?",
          "choices": ["Le prix d'un Bitcoin en dollars numériques", "Un échange entre deux banques",
                      "Le nombre de Bitcoin en circulation"], "answer": 0,
          "why": "La paire se lit « un BTC vaut tant d'USDT », et 1 USDT vaut environ 1 dollar."},
         {"q": "Pourquoi les memecoins sont-ils risqués ?",
          "choices": ["Ils bougent très fort dans les deux sens, souvent sans raison solide", "Ils sont interdits",
                      "Leur prix ne bouge jamais"], "answer": 0,
          "why": "Des mouvements de 30 % en un jour, à la hausse comme à la baisse : on peut gagner vite, et perdre "
                 "encore plus vite."},
     ],
     "sources": []},
    {"id": "bougies", "title": "Lire un graphique : les bougies", "minutes": 4,
     "blocks": [
         {"text": "Un graphique de trader est fait de bougies. Chaque bougie résume une période : 1 minute, 1 heure, "
                  "1 jour… c'est l'« unité de temps »."},
         {"figure": "candle"},
         {"text": "Le corps va de l'ouverture (le prix au début de la période) à la clôture (le prix à la fin). "
                  "Verte : la clôture est plus haute, le prix a monté. Rouge : il a baissé. Les mèches montent "
                  "jusqu'au plus haut et descendent jusqu'au plus bas de la période."},
         {"example": "Une longue mèche sous une bougie verte : le prix est descendu, puis les acheteurs l'ont fait "
                     "remonter. C'est exactement ce que cherche la règle « rebond sur support » de tes bots."},
         {"text": "Sous les bougies, le volume dit combien a été échangé. Un mouvement avec beaucoup de volume a plus "
                  "de monde derrière lui. Plus l'unité est courte, plus il y a de bruit : en 1 minute, la plupart des "
                  "mouvements sont du hasard."},
     ],
     "remember": ["Corps : de l'ouverture à la clôture. Mèches : jusqu'au plus haut et au plus bas.",
                  "Verte = hausse sur la période, rouge = baisse.",
                  "Plus l'unité de temps est courte, plus il y a de bruit."],
     "quiz": [
         {"q": "Une bougie verte veut dire…",
          "choices": ["que la clôture est au-dessus de l'ouverture", "que le volume a été élevé",
                      "que le prix a battu un record"], "answer": 0,
          "why": "La couleur ne dit que le sens du mouvement entre l'ouverture et la clôture de la période."},
         {"q": "Une longue mèche sous une bougie montre…",
          "choices": ["que le prix est descendu puis que les acheteurs l'ont fait remonter",
                      "que la bougie est fausse", "que le prix va forcément monter"], "answer": 0,
          "why": "C'est un indice que des acheteurs sont venus, pas une promesse : la suite peut décevoir."},
     ],
     "sources": []},
    {"id": "tendance", "title": "La tendance", "minutes": 4,
     "blocks": [
         {"text": "La tendance, c'est la direction de fond. Un prix qui fait des sommets de plus en plus hauts et des "
                  "creux de plus en plus hauts est en tendance haussière."},
         {"text": "Pour la voir sans se laisser distraire par le bruit, les traders tracent une moyenne mobile : la "
                  "moyenne des N dernières clôtures. La moyenne sur 200 bougies (MM 200) est la plus regardée : "
                  "au-dessus, on parle de tendance haussière."},
         {"figure": "chart", "symbol": "BTC/USDT", "timeframe": "1d",
          "caption": "Le Bitcoin en bougies d'un jour, avec ses moyennes sur 50 et 200 jours."},
         {"text": "En crypto, la tendance des 1 à 8 dernières semaines a tendance à continuer : c'est l'effet le mieux "
                  "établi par la recherche. Mais une tendance finit toujours par s'arrêter, et personne ne sait "
                  "quand."},
         {"example": "Quand la moyenne rapide (50) passe au-dessus de la lente (200), la tendance tourne à la hausse : "
                     "c'est le « croisement », une des règles que ton labo teste."},
     ],
     "remember": ["La tendance = la direction de fond, au-delà du bruit.",
                  "Au-dessus d'une MM 200 qui monte : tendance haussière.",
                  "En crypto, la tendance de quelques semaines a tendance à continuer… jusqu'à ce qu'elle s'arrête."],
     "quiz": [
         {"q": "Le prix est au-dessus de sa moyenne sur 200 jours, et cette moyenne monte. La tendance de fond est…",
          "choices": ["haussière", "baissière", "impossible à dire"], "answer": 0,
          "why": "C'est la définition la plus utilisée par les traders, et celle du filtre « MM200 » de ton bot."},
         {"q": "Pourquoi utiliser une moyenne mobile ?",
          "choices": ["Pour lisser le bruit et voir la direction de fond", "Pour connaître le prix de demain",
                      "Pour payer moins de frais"], "answer": 0,
          "why": "Elle résume le passé ; elle ne prévoit rien toute seule."},
     ],
     "sources": ["liu_tsyvinski", "detzel"]},
    {"id": "supports", "title": "Supports et résistances", "minutes": 5,
     "blocks": [
         {"text": "Un support est un prix où le marché s'est déjà retourné vers le haut plusieurs fois : les acheteurs "
                  "y reviennent. Une résistance, c'est l'inverse : un plafond où les vendeurs reviennent."},
         {"figure": "chart", "symbol": "BTC/USDT", "timeframe": "4h",
          "caption": "Les supports (en dessous) et les résistances (au-dessus) que ton bot trouve sur le Bitcoin, en "
                     "bougies de 4 heures, avec le nombre de fois où chaque zone a été touchée."},
         {"text": "Pourquoi ça marche parfois : beaucoup de gens placent leurs ordres aux mêmes endroits, surtout aux "
                  "chiffres ronds (70 000 $). Les études le confirment : les ordres s'accumulent à ces niveaux, et le "
                  "carnet d'ordres y est plus fourni."},
         {"text": "Deux façons de les trader. Le rebond : acheter sur le support, stop juste dessous, objectif la "
                  "résistance. La cassure : acheter quand le prix clôture nettement au-dessus d'une résistance. Une "
                  "résistance cassée devient souvent un support."},
         {"example": "Support à 100, résistance à 110. Tu achètes le rebond à 101 avec un stop à 98 : tu risques 3 % "
                     "pour viser +9 %. Le gain possible vaut 3 fois le risque : c'est ce que les traders appellent un "
                     "bon rapport gain/risque."},
         {"text": "Plus un niveau a été touché, plus il compte… jusqu'au jour où il cède. Le stop juste sous le "
                  "support limite la perte ce jour-là."},
     ],
     "remember": ["Support = plancher où les acheteurs reviennent ; résistance = plafond où les vendeurs reviennent.",
                  "Rebond : acheter au support, stop juste dessous. Cassure : acheter au-dessus de la résistance.",
                  "Une résistance cassée devient souvent un support."],
     "quiz": [
         {"q": "Tu achètes un rebond sur un support à 100. Où mets-tu ton stop ?",
          "choices": ["Juste sous le support, vers 98", "À 50, pour être tranquille", "Pas de stop"], "answer": 0,
          "why": "Si le prix casse le support, ton idée est fausse : le stop juste dessous coupe la perte tôt."},
         {"q": "Le prix clôture nettement au-dessus d'une résistance à 110. Ensuite, 110 devient souvent…",
          "choices": ["un support", "une résistance plus forte", "un prix sans importance"], "answer": 0,
          "why": "Les vendeurs qui tenaient 110 ont cédé ; ceux qui ont raté l'achat y attendent souvent un retour."},
         {"q": "Support à 50, résistance à 56. Tu achètes à 51 avec un stop à 49. Le rapport gain/risque est de…",
          "choices": ["2,5 (tu vises +5 pour risquer 2)", "0,4", "5"], "answer": 0,
          "why": "Objectif 56 − 51 = 5 ; risque 51 − 49 = 2 ; 5 ÷ 2 = 2,5."},
     ],
     "sources": ["osler_2000", "osler_2003", "kavajecz"]},
    {"id": "risque", "title": "Le stop, le stop suiveur et la taille de position", "minutes": 5,
     "blocks": [
         {"text": "Le stop-loss est un prix de sortie fixé à l'avance : si le prix y descend, tu vends. La perte est "
                  "limitée. Sans stop, une seule mauvaise journée peut effacer des mois de gains."},
         {"text": "Les pros ne choisissent pas la taille au feeling. Ils décident d'abord combien ils acceptent de "
                  "perdre si le stop est touché, souvent 1 % du compte. La taille de la position en découle : taille "
                  "= capital × risque ÷ distance du stop."},
         {"example": "Compte de 1 000 $, risque 1 % = 10 $. Stop à 2 % sous l'achat : position de 10 ÷ 0,02 = 500 $. "
                     "Si le stop est touché, tu perds 10 $, pas plus."},
         {"figure": "risk", "question": "Avant de bouger les curseurs : si tu rapproches le stop, la position "
                                        "devient-elle plus grosse ou plus petite ?"},
         {"text": "Avec 1 % par trade, il faut une longue série de pertes pour faire mal : 10 pertes d'affilée coûtent "
                  "environ 10 %. C'est la règle des traders prudents. Tes bots en argent fictif, eux, misent tout "
                  "leur capital à chaque trade (c'est ton choix, pour voir vite ce que vaut chaque stratégie) : un "
                  "stop touché leur coûte plusieurs pourcents. Le bot en argent réel, lui, reste à 1 %."},
         {"text": "Le stop peut aussi bouger, mais seulement dans le bon sens. Le stop suiveur monte avec le prix "
                  "(à la même distance du plus haut atteint) : il laisse courir un gain et en garde une partie quand "
                  "le prix se retourne. Le stop sécurisé passe au prix d'entrée dès que le trade a gagné autant qu'il "
                  "risquait : le trade ne peut presque plus perdre. En échange, ils coupent parfois un trade qui "
                  "serait reparti : tes bots testent ces façons de sortir sur chaque crypto et gardent celle qui "
                  "marche."},
     ],
     "remember": ["Un stop à chaque trade, décidé avant d'entrer.",
                  "Taille = capital × risque ÷ distance du stop.",
                  "1 % de risque par trade : une série de pertes ne te ruine pas.",
                  "Un stop ne bouge que pour protéger : il monte (à l'achat), il ne recule jamais."],
     "quiz": [
         {"q": "Achat à 100 $, stop à 98 $. Le prix monte à 106 $. Avec un stop suiveur à 2 $ du plus haut, où est "
               "le stop ?",
          "choices": ["104 $", "98 $", "106 $"], "answer": 0,
          "why": "Il suit le plus haut (106 $) à 2 $ de distance : 104 $. Si le prix redescend, le trade sort en gain."},
         {"q": "Compte de 2 000 $, risque 1 %, stop à 4 % sous l'achat. Taille de la position ?",
          "choices": ["500 $", "2 000 $", "80 $"], "answer": 0,
          "why": "1 % de 2 000 = 20 $ ; 20 ÷ 0,04 = 500 $. Si le stop est touché, la perte est de 20 $."},
         {"q": "À quoi sert le stop ?",
          "choices": ["À limiter la perte quand le scénario ne se réalise pas", "À garantir un gain",
                      "À payer moins de frais"], "answer": 0,
          "why": "Il ne garantit rien de positif : il empêche une perte de devenir une catastrophe."},
     ],
     "sources": []},
    {"id": "levier", "title": "Le levier", "minutes": 4,
     "blocks": [
         {"text": "Le levier, c'est trader avec plus d'argent que tu n'en as : avec un levier de 5, 100 $ de ta poche "
                  "contrôlent une position de 500 $. La plateforme te prête la différence."},
         {"text": "Il multiplie tout : +2 % sur le prix = +10 % sur ta mise ; −2 % = −10 %. Et vers −20 % (1 ÷ 5), ta "
                  "mise est perdue : c'est la liquidation, la plateforme ferme la position d'office."},
         {"figure": "leverage", "question": "Prédis d'abord : avec un levier de 10, à partir de quelle baisse du prix "
                                            "ta mise est-elle perdue ? Puis vérifie avec les curseurs."},
         {"text": "Le levier ne transforme pas une stratégie perdante en gagnante : il fait juste perdre, ou gagner, "
                  "plus vite. Il sert à une chose : prendre la taille voulue quand le stop est très proche (le "
                  "scalping). Tes bots en argent fictif l'utilisent en plein (×5 en scalping par défaut) : leurs "
                  "gains et leurs pertes en sont multipliés d'autant."},
         {"text": "Les contrats à terme (futures), qui permettent le levier, coûtent aussi un « financement » toutes "
                  "les 8 heures : garder une position des semaines coûte cher."},
     ],
     "remember": ["Levier × mouvement du prix = mouvement de ta mise.",
                  "Liquidation vers −100 % ÷ levier (−20 % avec x5, −10 % avec x10).",
                  "Le levier ne change pas le signe de l'espérance : il l'amplifie."],
     "quiz": [
         {"q": "Levier 10, le prix baisse de 5 %. Ta mise…",
          "choices": ["perd 50 %", "perd 5 %", "ne bouge pas"], "answer": 0,
          "why": "10 × 5 % = 50 %. Une baisse de 10 % suffirait à tout perdre."},
         {"q": "Le levier rend-il une stratégie rentable ?",
          "choices": ["Non : il grossit gains et pertes, l'espérance garde son signe", "Oui, toujours",
                      "Seulement en crypto"], "answer": 0,
          "why": "Une stratégie qui perd 0,1 % par trade perd 1 % par trade avec un levier de 10."},
     ],
     "sources": []},
    {"id": "decouvert", "title": "Vendre à découvert, l'objectif et la liquidation : comment jouent tes bots",
     "minutes": 5,
     "blocks": [
         {"text": "Vendre à découvert, c'est parier sur la baisse : le bot vend d'abord, et rachète plus tard. Si le prix "
                  "a baissé entre-temps, il gagne la différence. Avec les contrats à terme (futures), c'est aussi simple "
                  "qu'acheter : chaque technique est testée dans les deux sens sur chaque crypto, et seul un sens qui "
                  "gagne sur tout l'historique récent devient un bot."},
         {"example": "Un bot vend à découvert SOL à 150 $. Le prix tombe à 145 $ (−3,3 %) : il rachète et gagne 3,3 %, "
                     "moins les frais. Si le prix monte à 155 $, il perd 3,3 %."},
         {"text": "Le stop d'un vendeur est donc au-dessus de son prix d'entrée : il coupe la perte si le prix monte. "
                  "Attention : une baisse s'arrête à zéro, une hausse n'a pas de limite."},
         {"text": "L'objectif (le « take-profit ») est un prix fixé d'avance où le bot encaisse. Ceux de tes bots qui en "
                  "ont un le placent à 2 fois la distance de leur stop (« 2R ») : quand il est touché, le gain vaut deux "
                  "fois la perte possible. Encaisser tôt évite de rendre un gain, mais coupe aussi les grands "
                  "mouvements : chaque technique est testée avec et sans objectif, et seule une version gagnante devient "
                  "un bot."},
         {"text": "Tes bots misent tout leur capital fictif à chaque trade, avec le levier de leur horizon (×1 en long "
                  "terme, ×3 en court terme, ×5 en scalping, par défaut). Un stop touché à 2 % du prix avec un levier "
                  "de 5 coûte donc environ 10 % du capital du bot, frais compris."},
         {"text": "La liquidation : avec un levier de 5, une baisse d'environ 20 % (pour un acheteur) fait perdre toute "
                  "la mise. Tes bots réduisent leur levier quand leur stop est loin, pour que le stop passe toujours "
                  "avant la liquidation ; seul un saut de prix brutal peut encore liquider un bot. Il est alors arrêté, "
                  "et sa combinaison mise de côté une journée."},
     ],
     "remember": ["Vendeur à découvert : il gagne si le prix baisse ; son stop est au-dessus de son prix d'entrée.",
                  "L'objectif « 2R » : encaisser quand le gain vaut 2 fois la distance du stop.",
                  "Tout le capital × le levier : un stop à 2 % avec ×5 coûte environ 10 % du capital."],
     "quiz": [
         {"q": "Un bot vend à découvert à 100 $ avec un levier de 3. Le prix descend à 98 $. Son capital…",
          "choices": ["gagne environ 6 %, moins les frais", "perd environ 6 %", "gagne 2 %"], "answer": 0,
          "why": "Le prix baisse de 2 % : le vendeur gagne 2 % sur sa position, multipliés par 3 avec le levier."},
         {"q": "Où se place le stop d'un vendeur à découvert ?",
          "choices": ["Au-dessus de son prix d'entrée", "En dessous de son prix d'entrée", "Il n'en a pas besoin"],
          "answer": 0,
          "why": "Il perd quand le prix monte : son stop coupe la perte au-dessus."},
     ],
     "sources": []},
    {"id": "frais", "title": "Les frais et le scalping", "minutes": 5,
     "blocks": [
         {"text": "Le scalping, c'est viser de tout petits mouvements (0,1 à 0,5 %), des dizaines de fois par jour. Le "
                  "problème : les frais sont payés à chaque aller-retour."},
         {"text": "Au comptant, un aller-retour coûte environ 0,3 % (frais, écart entre acheteurs et vendeurs, "
                  "glissement). Si tu vises +0,3 %, tu travailles pour la plateforme."},
         {"figure": "fees", "question": "Avant de bouger le curseur : à partir de quel gain moyen par trade (avant "
                                        "frais) le scalping au comptant commence-t-il à rapporter ?"},
         {"text": "Ton labo l'a vérifié sur tes propres données : en 1 et 5 minutes, toutes les stratégies perdaient "
                  "après frais. Et les études sur les particuliers sont dures : les day traders perdent en moyenne, "
                  "parfois même avant frais. En face, des firmes réagissent en microsecondes."},
         {"example": "Pour réduire le poids des frais : des ordres limites (frais « maker », plus bas), les contrats à "
                     "terme (0,05 % par ordre au lieu de 0,1 %), ou viser des mouvements plus grands (15 minutes, 1 "
                     "heure). C'est ce que teste ton labo « scalping, frais futures »."},
     ],
     "remember": ["Chaque aller-retour paie des frais : environ 0,3 % au comptant, 0,14 % en futures au marché.",
                  "Un petit gain visé est vite mangé par les frais.",
                  "Moins de frais, ou des mouvements plus grands : sinon le scalping ne paie pas."],
     "quiz": [
         {"q": "Tu vises +0,25 % par trade et un aller-retour coûte 0,3 %. En moyenne, chaque trade…",
          "choices": ["perd environ 0,05 %", "gagne 0,25 %", "gagne 0,55 %"], "answer": 0,
          "why": "0,25 % − 0,30 % = −0,05 % : plus tu trades, plus tu perds."},
         {"q": "Quelle est la meilleure façon de réduire le poids des frais ?",
          "choices": ["Viser des mouvements plus grands ou payer moins de frais", "Trader plus souvent",
                      "Augmenter le levier"], "answer": 0,
          "why": "Trader plus souvent multiplie les frais ; le levier multiplie le résultat, frais compris."},
         {"q": "Rappel de la leçon sur le levier : levier 5, le prix monte de 1 %. Ta mise…",
          "choices": ["gagne 5 %, avant frais", "gagne 1 %", "gagne 0,2 %"], "answer": 0,
          "why": "Levier × mouvement : 5 × 1 % = 5 % ; et les frais sont payés sur la position entière."},
     ],
     "sources": ["jordan_diltz", "kuo_lin", "resta"]},
    {"id": "indicateurs", "title": "RSI, MACD, Bollinger : les indicateurs", "minutes": 4,
     "blocks": [
         {"text": "Un indicateur est un calcul sur les prix passés, affiché sur ou sous le graphique. Il ne prévoit "
                  "rien tout seul : il résume."},
         {"text": "Le RSI compare les hausses et les baisses récentes, de 0 à 100. Au-dessus de 70, les acheteurs ont "
                  "beaucoup poussé (« suracheté ») ; sous 30, les vendeurs (« survendu »)."},
         {"text": "Le MACD est l'écart entre deux moyennes : quand il croise sa ligne de signal par le haut, la hausse "
                  "accélère. Les bandes de Bollinger entourent une moyenne : la plupart des prix restent dedans, une "
                  "sortie est un mouvement inhabituel. L'ATR mesure la taille moyenne d'une bougie : ton bot s'en "
                  "sert pour placer ses stops."},
         {"text": "Ce que dit la recherche : des milliers de règles testées en crypto montrent de la prévisibilité, "
                  "surtout en bougies d'un jour, mais beaucoup de résultats publiés fondent une fois les frais et le "
                  "nombre d'essais comptés. D'où le labo."},
     ],
     "remember": ["Un indicateur résume le passé ; il ne prédit rien seul.",
                  "RSI > 70 : beaucoup d'achats récents ; RSI < 30 : beaucoup de ventes.",
                  "L'ATR (taille d'une bougie) sert à placer les stops."],
     "quiz": [
         {"q": "Un RSI à 85 veut dire…",
          "choices": ["que les acheteurs ont beaucoup poussé récemment", "que le prix va forcément baisser",
                      "que le volume est faible"], "answer": 0,
          "why": "« Suracheté » ne veut pas dire « va baisser » : en forte tendance, le RSI peut rester haut longtemps."},
         {"q": "À quoi sert l'ATR dans ton bot ?",
          "choices": ["À placer le stop selon l'agitation du marché", "À choisir la crypto", "À calculer les impôts"],
          "answer": 0,
          "why": "Un marché agité a besoin d'un stop plus loin : l'ATR adapte la distance."},
     ],
     "sources": ["hudson_urquhart", "zakamulin"]},
    {"id": "actualite", "title": "L'actualité et le sentiment", "minutes": 4,
     "blocks": [
         {"text": "Les nouvelles font bouger les prix : une plateforme piratée, une loi, un fonds autorisé à acheter du "
                  "Bitcoin… Mais le marché les digère vite : sur le Bitcoin, les grandes nouvelles sont absorbées en "
                  "moins d'une heure, et le mouvement commence parfois avant la publication."},
         {"text": "Quand tu lis la nouvelle, les plus rapides ont souvent déjà acheté ou vendu. Trader sur les titres, "
                  "c'est souvent arriver après la bataille."},
         {"text": "L'indice « peur et avidité » (Fear & Greed) résume l'humeur du marché, de 0 (peur extrême) à 100 "
                  "(avidité extrême). Les études sont partagées : certaines trouvent qu'il aide à prévoir, d'autres "
                  "que ce sont surtout les prix qui font bouger l'indice, pas l'inverse."},
         {"example": "Ton bot montre l'actualité et l'indice dans l'onglet « Actualité », avec ce que le prix de chaque "
                     "crypto citée a fait depuis. Il ne trade pas sur les titres : rien ne prouve que ce soit rentable, "
                     "et il arriverait toujours en retard."},
     ],
     "remember": ["Le marché digère les nouvelles en minutes, parfois avant leur publication.",
                  "L'indice peur et avidité résume l'humeur du marché ; son pouvoir de prévision est discuté.",
                  "Le bot lit l'actualité pour comprendre, pas pour trader."],
     "quiz": [
         {"q": "Une bonne nouvelle sort sur une crypto. Quand tu la lis…",
          "choices": ["une bonne partie du mouvement a souvent déjà eu lieu", "le prix n'a pas encore bougé",
                      "il faut acheter tout de suite"], "answer": 0,
          "why": "Les plus rapides réagissent en secondes ; le gros du mouvement est souvent fait avant toi."},
         {"q": "L'indice peur et avidité à 10 veut dire…",
          "choices": ["que le marché a très peur", "que le marché est euphorique", "que le prix va monter"],
          "answer": 0,
          "why": "10 est dans la zone « peur extrême ». Ce que le prix fera ensuite, personne ne le sait."},
     ],
     "sources": ["blasco", "gessie", "fng_predict"]},
    {"id": "tester", "title": "Pourquoi tout tester avant", "minutes": 4,
     "blocks": [
         {"text": "Si tu essaies 100 règles sur le même historique, quelques-unes auront l'air géniales… par pur "
                  "hasard. C'est le piège numéro un : la sur-optimisation."},
         {"example": "Pile ou face : 20 personnes lancent chacune une pièce 10 fois. L'une d'elles fera sans doute 8 "
                     "piles sur 10. Elle n'a aucun talent : le hasard s'est concentré sur elle."},
         {"text": "Comment tes bots s'en protègent : chaque re-test coupe l'historique en trois (étude, validation, et "
                  "une période récente qui doit aussi gagner), compte tous les frais, et ne garde que des combinaisons "
                  "gagnantes sur les trois. Ça ne suffit pas : sur des centaines d'essais, certaines passent par "
                  "chance."},
         {"text": "Ensuite vient l'argent fictif en direct : la vraie preuve, sur des données que personne n'a vues. Un "
                  "bot qui perd nettement est arrêté. Puis, après plusieurs semaines, le testnet. L'argent réel en "
                  "dernier, et seulement avec ce que tu acceptes de perdre."},
     ],
     "remember": ["Essayer beaucoup de règles finit toujours par en trouver une qui a gagné par hasard.",
                  "Le test final, jamais regardé pour choisir, dit si l'effet tient.",
                  "Labo, argent fictif, testnet, puis seulement un peu d'argent réel."],
     "quiz": [
         {"q": "Une stratégie a gagné +40 % sur le passé après 200 essais de réglages. C'est…",
          "choices": ["peut-être de la chance : il faut la tester sur des données jamais vues",
                      "la preuve qu'elle gagnera", "impossible"], "answer": 0,
          "why": "Avec 200 essais, un résultat spectaculaire est presque garanti, même sans aucun vrai avantage."},
         {"q": "Dans quel ordre passer à l'argent réel ?",
          "choices": ["Labo, argent fictif, testnet, puis un petit montant réel", "Argent réel tout de suite",
                      "Testnet, puis labo"], "answer": 0,
          "why": "Chaque étape attrape une erreur que la précédente ne voit pas."},
     ],
     "sources": ["zakamulin", "park_irwin"]},
    {"id": "trades", "title": "Lire les trades de tes bots", "minutes": 4,
     "blocks": [
         {"text": "Chaque trade d'un bot a deux histoires : pourquoi il est entré (sa règle, et les conditions du "
                  "graphique à ce moment-là) et ce qui s'est passé (le diagnostic, avec la leçon)."},
         {"figure": "diagnoses"},
         {"text": "Un trade perdant n'est pas une erreur : même une bonne stratégie perd souvent. Ce qui compte, c'est "
                  "la moyenne sur beaucoup de trades. Les agents d'analyse disent dans quelles conditions une stratégie "
                  "a gagné ou perdu, mais ne se lisent qu'avec assez de trades derrière : au moins 30."},
         {"text": "Ce que tes bots ne font jamais : changer leurs réglages tout seuls après une perte. Un bot qui perd "
                  "nettement est arrêté (le gardien), et chaque crypto est retestée toutes les 3 heures sur des "
                  "données fraîches. C'est comme ça qu'ils apprennent sans se raconter d'histoires."},
     ],
     "remember": ["Deux histoires par trade : pourquoi il est entré, ce qui s'est passé.",
                  "Un trade perdant n'est pas une erreur ; la moyenne sur beaucoup de trades décide.",
                  "Un bot qui perd nettement est arrêté ; personne ne bricole ses règles."],
     "quiz": [
         {"q": "Un trade monte de +3 %, puis redescend jusqu'au stop. Diagnostic ?",
          "choices": ["Gagnant, puis retourné", "Faux départ", "Scénario réussi"], "answer": 0,
          "why": "Il a été gagnant avant de se retourner : une prise de bénéfice partielle l'aurait protégé."},
         {"q": "Un bot a perdu ses 3 premiers trades. Que se passe-t-il ?",
          "choices": ["Rien de spécial : 3 trades ne disent rien, il attend d'en avoir assez", "Il change ses réglages",
                      "Il double la mise pour se refaire"], "answer": 0,
          "why": "Doubler la mise pour se refaire est la façon la plus sûre de tout perdre."},
     ],
     "sources": []},
)
LESSON_IDS = [lesson["id"] for lesson in LESSONS]

# Sources de l'école qui ne servent pas ailleurs (les autres viennent de knowledge.SOURCES).
EXTRA_SOURCES = {
    "blasco": ("Blasco, Corredor et Satrústegui, 2025 · nouvelles mondiales et volatilité du Bitcoin",
               "https://scispace.com/papers/the-impact-of-global-news-items-on-bitcoin-volatility-gpdijy9lyxos"),
    "gessie": ("Gessie, 2026 · le Bitcoin fait-il bouger le sentiment ?",
               "https://scispace.com/papers/do-bitcoin-returns-move-sentiment-evidence-from-the-crypto-ajnfdjp0wwr0"),
    "fng_predict": ("Finance Research Letters, 2023 · prévoir les rendements des cryptos avec l'indice peur et avidité",
                    "https://scispace.com/papers/predicting-cryptocurrency-returns-for-real-world-investments-5259b83bef"),
}


def source(key: str) -> dict:
    title, url = SOURCES.get(key) or EXTRA_SOURCES[key]
    return {"title": title, "url": url}


def examples(data_dir: Path, limit: int = 6, files: int = 400) -> list[dict]:
    """Des trades récents des bots (data/bots/essaim/), un par diagnostic si possible, pour la dernière leçon."""
    trades = []
    for path in sorted((data_dir / "bots" / "essaim").glob("*.json"))[:files]:
        try:
            bot = json.loads(path.read_text(encoding="utf-8"))
            spec = bot["spec"]
            play = f"{spec['technique']} ({spec['timeframe']}, {'achat' if spec['side'] == 'long' else 'vente'})"
            for t in (bot.get("book") or {}).get("trades") or []:
                if t.get("diagnosis"):
                    trades.append({"symbol": spec["symbol"], "play": play, "net": t["net"], "exit_ts": t["exit_ts"],
                                   "diagnosis": t["diagnosis"]})
        except (OSError, ValueError, KeyError, TypeError):
            continue  # un fichier en train d'être réécrit, ou d'une ancienne version
    picked, seen = [], set()
    for t in sorted(trades, key=lambda t: -t["exit_ts"]):
        kind = t["diagnosis"].get("kind")
        if kind not in seen:
            seen.add(kind)
            picked.append({**t, "replay": False})
        if len(picked) >= limit:
            break
    return picked


def school(data_dir: Path) -> dict:
    lessons = []
    for i, lesson in enumerate(LESSONS):
        lessons.append({**lesson, "number": i + 1, "sources": [source(k) for k in lesson["sources"]],
                        "next": LESSONS[i + 1]["id"] if i + 1 < len(LESSONS) else None})
    return {"lessons": lessons, "kinds": KINDS, "examples": examples(data_dir)}
