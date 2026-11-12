# Plan des bots

Le plan de travail donné par l'utilisateur le 11/11/2026, étape par étape. À relire au début de chaque session et à
mettre à jour à la fin de chaque étape (journal en bas de page).

**Le but : trouver un avantage réel et mesurable, pas embellir les chiffres.**

## Règles permanentes

1. Argent fictif uniquement. Jamais le mode réel, jamais les clés du fichier `.env`, aucun secret affiché.
2. Une étape à la fois : plan court → l'utilisateur approuve → code sans redemander à chaque fichier → tests → compte
   rendu.
3. Avant chaque étape, un commit git pour pouvoir revenir en arrière.
4. Une seule logique de gestion des trades, partagée par les bots en direct et par le backtest. Jamais deux versions.
5. Backtest réaliste : signaux calculés sur des bougies clôturées uniquement, exécution au prix suivant, frais maker
   et taker, glissement (slippage), coût de financement (funding) des positions à levier.
6. Tout ce qui touche à l'argent (stop, objectif, taille de position, frais, liquidation) a des tests automatiques,
   lancés avant de dire qu'une étape est finie.
7. Interface : le style actuel, en français, avec une phrase d'explication sous chaque nouveau réglage.
8. Consigne ambiguë ou bug trouvé dans l'existant : le dire avant de continuer.

L'utilisateur est podologue et apprend : le pourquoi de chaque choix s'explique en français simple, en 5 lignes au
plus. Compte rendu de fin d'étape : ce qui a changé, comment le vérifier sur le site, ce qu'il faut surveiller, l'étape
suivante.

## Ce que l'utilisateur a ajouté en envoyant le plan

- Garder tout ce qui a été demandé avant (l'essaim, le site, les stops qui bougent, le classement en direct...).
- Le **maximum de bots possible** (le plan parlait d'une soixantaine) : tester le plus de positions possible, sur tout.
- Les derniers indicateurs qui pourraient annoncer une hausse ou une baisse.
- Tous les horizons : long terme, très court terme, scalping, jusqu'à la seconde.

Où ces demandes entrent dans le plan :

- Le maximum de bots : l'étape 0 bis proposée plus bas (toutes les combinaisons tournent « à l'essai »).
- Les derniers indicateurs : le flux d'ordres (étapes 4 et 5) et le contexte de marché (étape 6). Une nouvelle
  technique sur bougies peut s'ajouter à la bibliothèque à tout moment : elle est alors testée partout, comme les autres.
- Jusqu'à la seconde : impossible avec des bougies d'une minute ; il faut le flux enregistré à l'étape 4.

Dit franchement : aucun indicateur ne prédit le prix de façon fiable, et plus l'horizon est court, plus les frais
pèsent (un aller-retour au marché coûte environ 0,14 % de la position, alors que le prix du Bitcoin bouge d'environ
0,01 % en une seconde). On peut tout tester en argent fictif ; ce sont les mesures qui trancheront.

---

## Étape 0 — Audit (faite le 12/11/2026)

Aucun code du bot n'a été modifié : seulement ce fichier, `CLAUDE.md` et les deux scripts de mesure du dossier
`audit/` (ils ne font pas partie du bot).

### Comment un bot travaille aujourd'hui, en 15 lignes

1. Toutes les 10 minutes, l'essaim prend les 60 cryptos en USDT qui ont le plus bougé sur 24 h (au moins 5 M$
   échangés par jour). Sous 3 % de mouvement, une crypto passe en veille : ses bots n'ouvrent plus de trade.
2. Le labo teste chaque crypto à son arrivée, puis toutes les 3 heures : 39 techniques × 2 sens (achat, vente à
   découvert) × 4 façons de sortir × 5 unités de temps (1 min à 4 h) = 1560 combinaisons.
3. L'historique du test : 2 jours en 1 min, 7 jours en 5 min, 20 jours en 15 min, 60 jours en 1 h, 240 jours en 4 h.
   Il est coupé en trois : étude (la première moitié), validation (30 %), test final (les derniers 20 %).
4. Une combinaison est gardée si elle gagne en moyenne, frais compris, sur chacun des trois morceaux, avec assez de
   trades (25 en 1 min, 8 en 4 h) et sans liquidation. Les 8 mieux classées de la crypto deviennent des bots.
5. Ouverture : le signal est calculé à la clôture d'une bougie ; l'ordre part à l'ouverture de la bougie suivante (en
   direct : au prix du moment, quelques secondes après la clôture).
6. Taille : tout le capital fictif du bot (1000 USDT) × le levier de son horizon (×5 scalping, ×3 court terme, ×1 long
   terme). Le levier est réduit si le stop est loin, pour que le stop passe toujours avant la liquidation.
7. Stop : entre 1,5 et 3 fois la taille moyenne d'une bougie (ATR) du prix d'entrée, selon la technique (3 fois pour
   la plupart). Objectif, quand la sortie en a un : 2 fois la distance du stop (2R).
8. Gestion : à chaque bougie, le stop est regardé d'abord (le pire cas), puis l'objectif. En direct, le prix est aussi
   regardé toutes les 5 secondes.
9. Stop suiveur : il suit le meilleur prix à la distance du départ. Stop sécurisé : il passe au prix d'entrée, frais
   compris, après un gain de 1R. Décidés à la clôture, ils comptent dès la bougie suivante et ne reculent jamais.
10. Fermeture : stop touché, objectif touché, signal de sortie de la règle (exécuté à l'ouverture suivante), durée
    maximale pour certaines techniques (20 à 48 bougies), ou liquidation.
11. Les frais sont comptés à un seul endroit, le moteur `fleet.Book` : 0,05 % à l'entrée (`_open`), 0,05 % à la sortie
    au marché ou 0,02 % sur un objectif, qui est un ordre limite (`_close`), 0,02 % de glissement sur chaque ordre au
    marché (`_fill`), et 0,01 % de financement par tranche de 8 heures de position (`_close`). Réglages :
    `execution.FUTURES`.
12. Résultat d'un trade : `net` = le gain après tous les frais, en % de la position ; `roi` = le même en % du capital du
    bot (donc multiplié par le levier).
13. Un bot s'arrête s'il est liquidé, s'il a perdu la moitié de son capital, s'il perd nettement après 20 trades (sa
    combinaison est alors mise de côté 24 h), ou si le dernier test de sa crypto ne le choisit plus.
14. Classement en direct : chaque trade fini compte pour sa stratégie (une technique dans une unité de temps, toutes
    cryptos réunies). Après 30 trades, elle peut être « prouvée » (prioritaire) ou « recalée » (ses bots s'arrêtent).
15. Le backtest et le direct passent par le même moteur, dans le même ordre : des tests automatiques vérifient qu'un
    bot en direct prend exactement les trades de son backtest, y compris après une coupure.

### La mesure qui résume l'audit : le labo sur un marché tiré au hasard

On a fabriqué des cryptos dont le prix avance au hasard (aucune tendance, aucune mémoire : aucun avantage possible),
puis on a fait travailler le vrai code : le labo choisit ses bots, et on regarde ce qu'ils font ensuite.

| | 12 cryptos au hasard | Les 12 plus « agitées » sur 24 h parmi 80 |
|---|---|---|
| Combinaisons testées par crypto | 1560 | 1560 |
| Déclarées « gagnantes sur 3 périodes » | 56 (3,6 %) | 69 (4,4 %) |
| Bots créés par crypto | 6,5 | 7,0 |
| Leur backtest, par trade | +0,96 % | +1,09 % |
| Ensuite, en « direct » simulé | 2279 trades | 2587 trades |
| Trades gagnants | 35 % | 31 % |
| Résultat par trade, frais compris | −0,20 % (± 0,11) | −0,22 % (± 0,10) |
| Résultat par trade, en % du capital du bot | −0,65 % | −0,50 % |
| Bots qui finissent quand même positifs | 30 % | 29 % |

Ce que ça veut dire : même sur du pur hasard, le labo crée 6 à 7 bots par crypto, leur backtest est beau, et ils
perdent ensuite le prix des frais. **Un bot créé par le labo, ou un bot en gain, ne prouve donc rien pour l'instant.**
Les chiffres réels de l'utilisateur (36 % de trades gagnants, total un peu négatif) ressemblent à ceux du hasard ;
217 trades ne suffisent pas à dire s'il y a un petit avantage ou aucun (avec si peu de trades, la marge d'erreur est de
l'ordre de ± 0,3 % par trade : plus grande que l'avantage qu'on cherche).

Deuxième mesure, même méthode : on refait le test d'une crypto toutes les 3 heures pendant 48 heures, comme l'essaim.

| Sur 12 cryptos au hasard, en 48 heures | |
|---|---|
| Bots gardés d'un test au suivant | 80 % (1 sur 5 est remplacé toutes les 3 heures) |
| Bots créés par crypto, pour 8 places | 26 |
| Durée de vie d'un bot arrêté par un test | 6 heures (médiane) ; 41 % sont arrêtés dès le test suivant |
| Bots arrêtés sans avoir fait un seul trade | 69 % |
| Bots ayant atteint 30 trades | aucun |

Ce que ça veut dire : le classement d'une crypto bouge à chaque test, donc ses bots tournent sans arrêt. Presque
aucun ne vit assez longtemps pour être jugé.

Pour refaire ces mesures (quelques minutes chacune, sans connexion à une plateforme) : `python audit/hasard.py 80 12
hasard.json` et `python audit/rotation.py rotation.json 101 102 103 104 105 106 107 108 109 110 111 112`. À relancer
après chaque changement du labo : c'est le repère « aucun avantage ». Un labo réparé doit y afficher un résultat
honnête, c'est-à-dire négatif.

### Ce qui peut fausser les résultats, par gravité

**Grave : ça change la conclusion**

- **G1. Le labo prend la chance pour un avantage.** 1560 essais par crypto, et « gagner sur 3 périodes » est un
  critère que le hasard passe 3,6 % du temps (`swarm._eligible`) : voir le tableau. Rien ne tient compte du nombre
  d'essais.
- **G2. Le « test final » sert à choisir.** `fleet.judge` annonce un test final « jamais regardé pour choisir », mais
  `swarm._eligible` exige qu'il soit gagnant. Il ne reste donc aucune donnée jamais vue : le backtest affiché sur la page
  d'un bot est toujours trop beau, et « comparer sur le test final » (étapes 1 et 6) ne voudrait rien dire.
- **G3. Trop peu d'historique en très court terme.** 2 jours en 1 min, 7 jours en 5 min (`swarm.TEST_DAYS`) : une seule
  humeur de marché.
- **G4. Les bots changent trop vite pour être jugés.** Toutes les 3 heures, un bot qui n'est plus parmi les 8 mieux
  classés de sa crypto s'arrête (`Swarm.apply_test`), même s'il gagne encore sur son historique. Mesuré : un bot vit
  6 heures et 7 sur 10 s'arrêtent sans un seul trade (tableau ci-dessus). Chez l'utilisateur : 217 trades pour une
  soixantaine de bots en place. Aucun n'atteindra les 30 trades de l'étape 3.
- **G5. Des contrats à terme simulés avec les prix du comptant.** La liste des cryptos et les bougies viennent du
  marché au comptant (`scanner.tradable`, `data.make_exchange`), alors que le moteur compte un levier, des ventes à
  découvert et un financement. Certaines cryptos très agitées n'ont pas de contrat à terme : leur vente à découvert
  serait impossible en vrai. Le financement réel et la liquidité ne sont pas ceux du modèle.

**Moyen : ça embellit ou ça brouille**

- **M1. Exécution trop optimiste sur les petites cryptos.** Glissement fixe de 0,02 % pour toutes, stops compris, alors
  qu'un bot peut passer 5000 USDT d'un coup sur une crypto qui n'échange que 3500 USDT par minute. Et un stop est compté
  rempli à son prix, même quand le prix a sauté plus loin (c'est justement là que les stops glissent).
- **M2. Financement fixe.** 0,01 % par 8 heures, compté comme un coût dans les deux sens. Sur une crypto qui s'envole,
  le vrai taux peut être dix fois plus haut ; l'effet est faible en scalping, réel sur les bots en 4 h.
- **M3. L'heure du PC décide qu'une bougie est finie** (`CandleStore.closed`, `Swarm.cycle`). Si l'horloge de
  l'ordinateur avance de plus de 2 secondes, un bot peut décider sur une bougie pas terminée : le direct s'écarte alors
  du backtest (surtout en 1 min).
- **M4. Des verdicts « prouvée » et « recalée » trop faciles.** Les trades sont comptés comme indépendants, alors que
  plusieurs bots tradent la même crypto et que les cryptos montent et baissent ensemble : 40 ventes à découvert gagnantes
  pendant une seule chute du marché comptent pour 40 preuves. Et « recalée » est définitif (la stratégie ne trade plus).
- **M5. Des cryptos choisies sur leur mouvement des dernières 24 h**, alors que le backtest contient ce même mouvement.
  Mesuré : l'effet existe (4,4 % de fausses gagnantes au lieu de 3,6 %) mais il est petit.
- **M6. Un risque très inégal d'un trade à l'autre.** Tout le capital × le levier à chaque trade : dans la simulation,
  la moitié des trades perdants coûtent plus de 3 % du capital du bot, un sur dix plus de 6,6 %, le pire 14 %. Quelques
  gros trades font le résultat d'un bot (c'est l'objet de l'étape 2).

**Faible : à corriger au passage**

- **F1.** Les trades rattrapés après une coupure (PC éteint) sont rejoués sur les bougies, puis comptés dans le
  classement comme des trades vus en direct.
- **F2.** Les probabilités des « agents » sont calculées sur le backtest qui a choisi le bot : elles sont trop belles.
- **F3.** Un bot arrêté parce que sa stratégie est recalée affiche « le dernier test ne le garde plus » : texte trompeur.
- **F4.** La valeur d'une position ouverte ne compte pas encore les frais de sortie (environ 0,07 % de la position).
- **F5.** Liquidation simplifiée : même marge de maintenance (0,5 %) pour toutes les cryptos, toute la mise perdue.
  C'est prudent, mais les petites cryptos ont en vrai des règles plus dures et des leviers plus bas.
- **F6.** Le site met en avant le pourcentage de trades gagnants, qui ne dit rien seul (avec un objectif à 2R, on peut
  gagner avec 36 % de trades gagnants). Ce qui compte : le résultat moyen par trade (étape 3).
- **F7.** Le total en % est rapporté au capital de tous les bots, dont la plupart attendent : il paraît petit.

**Vérifié et correct**

- Les signaux n'utilisent que des bougies clôturées : un test automatique compare, pour les 39 techniques et dans les
  deux sens, les signaux de la fenêtre du direct à ceux de tout l'historique (un regard vers le futur le ferait échouer).
- L'ordre part à l'ouverture de la bougie suivante, jamais sur la bougie du signal.
- Frais taker et maker, glissement et financement sont tous comptés, à un seul endroit.
- Une seule logique pour le backtest et le direct (`fleet.Book`), vérifiée par des tests de parité, y compris après un
  redémarrage.
- Dans une même bougie, le stop passe avant l'objectif (hypothèse prudente) ; un objectif n'est compté que si le prix
  l'a dépassé.
- Le total affiché compte aussi les bots arrêtés : pas de « on ne montre que les survivants ».
- Supports, résistances et Ichimoku n'utilisent que le passé (testé).

### Point de référence (avant toute modification du plan)

| | Valeur |
|---|---|
| Date | 11/11/2026 (chiffres donnés avec le plan) ; code en place : `7148d95`, dernière version Windows publiée |
| Trades terminés | environ 217 |
| Trades gagnants | 36 % |
| Résultat total | −0,3 % |
| Bots | une soixantaine, sur 35 cryptos, de 1 min à 4 h |
| Repère « aucun avantage » (marché au hasard, même code) | 35 % de trades gagnants, −0,20 % par trade |

Ces chiffres sont ceux rapportés par l'utilisateur : le détail par stratégie est sur son PC (`data\bots\essaim.json` et
`essaim-etat.json`), illisible depuis une session cloud. L'étape 0 bis propose que le bot en garde une copie datée au
premier lancement de la version suivante.

---

## Proposition issue de l'audit : étape 0 bis — réparer la mesure et tout tester (à approuver)

Pourquoi avant l'étape 1 : les étapes 1 et 6 se terminent par « comparer sur le test final », et l'étape 3 par « juger
après 30 trades ». Aujourd'hui, le test final sert à choisir (G2) et presque aucun bot n'atteint 30 trades (G4).

1. **Le test final ne sert plus à choisir** : le labo choisit sur l'étude et la validation ; le test final ne fait que
   mesurer. Il redevient une vraie comparaison.
2. **Tout tester, en argent fictif (le maximum de bots)** : le labo calcule déjà les 1560 combinaisons de chaque crypto
   toutes les 3 heures, puis jette tout sauf les 8 choisies. On garde les trades de **toutes** : jusqu'à 60 × 1560 =
   93 600 « bots à l'essai », jugés par stratégie, toutes cryptos réunies. Des milliers de trades par jour au lieu de
   217 depuis le lancement, sans choix préalable : une mesure que le choix des « meilleurs » ne peut plus embellir. Les
   bots en direct d'aujourd'hui (avec leur page et leur graphique) restent, et leur nombre maximum peut monter.
3. **Un bot n'est plus arrêté parce que le classement a bougé** : seulement par ses garde-fous ou par le verdict de sa
   stratégie.
4. **Une bougie n'est « terminée » que quand la plateforme a ouvert la suivante** (plus l'horloge du PC).
5. **Le point de référence est enregistré tout seul** au premier lancement (copie datée des chiffres du moment).

Ce que cette étape ne fait pas : elle ne rend aucun bot gagnant. Elle donne une mesure à laquelle on peut se fier,
avant de toucher aux stops (étape 1) et au risque (étape 2).

---

## Étape 1 — Sécurisation des gains

- Break-even : quand le prix a avancé de 1R (R = distance entre l'entrée et le stop initial), le stop passe au prix
  d'entrée plus les frais aller-retour.
- Objectif partiel : au même moment, fermer 50 % de la position. Le reste suit la règle de sortie du bot.
- Seuil et pourcentage réglables dans Réglages, et désactivables.
- Graphique : zone du stop, zone de l'objectif, seuil de sécurisation en pointillés, puis le nouveau stop. Journal :
  chaque sécurisation.

Terminé quand : le labo compare avec et sans sécurisation sur le test final, et montre le résultat.

Existant : le stop sécurisé (`stop_mode = "securise"`) fait déjà la première moitié, comme l'une des quatre sorties
testées. Il reste la fermeture partielle (nouveau dans le moteur), les réglages, le graphique et le journal.

## Étape 2 — Gestion du risque

- Taille de position calculée pour risquer un % fixe du capital du bot par trade (1 % par défaut), dans la limite des
  leviers actuels.
- Perte maximale par jour pour l'ensemble des bots : au-delà, aucune nouvelle position jusqu'au lendemain.
- Nombre maximal de positions ouvertes en même temps.

Terminé quand : ces trois limites sont réglables, testées et visibles sur la page Direct.

Existant : `risk.position_size` et `risk.RiskGuard` font déjà ces calculs pour le bot au comptant ; à réutiliser dans
le moteur des bots plutôt qu'à réécrire.

## Étape 3 — Classement fiable

- Aucun bot jugé avant 30 trades terminés.
- Pour chaque bot : espérance par trade en R, taux de gain, gain moyen et perte moyenne, profit factor, drawdown
  maximal.
- Classement par un score prudent : l'espérance moins sa marge d'erreur.
- Des bots témoins qui entrent au hasard avec les mêmes stops et objectifs, pour mesurer la part de chance.

Terminé quand : la page Direct trie par score prudent et affiche l'écart avec les témoins.

À prévoir d'après l'audit (M4) : compter les jours et les cryptos différents, pas seulement les trades, pour qu'une
seule chute du marché ne « prouve » pas une stratégie.

## Étape 4 — Enregistrement du flux d'ordres

- Via les WebSocket de la plateforme, pour les 10 cryptos les plus liquides : chaque transaction avec son côté
  (acheteur ou vendeur agressif), le carnet d'ordres (20 niveaux, une photo par seconde), les liquidations, le taux de
  financement, l'open interest.
- Stockage local compact, limité à 5 Go avec rotation. Un voyant sur le site indique si l'enregistrement tourne.
- Si ces données ne sont pas accessibles sur Binance depuis la France, proposer une autre plateforme déjà gérée par le
  site.

Terminé quand : 24 h de données sont enregistrées sans coupure.

À prévoir d'après l'audit (G5) : c'est le moment de passer aux vrais contrats à terme (liste des cryptos, prix,
financement réel) au lieu du comptant.

## Étape 5 — Signaux de flux d'ordres

- Delta cumulé, déséquilibre du carnet, murs d'ordres, pics de liquidations, financement extrême, ajoutés comme
  techniques dans le labo.
- À lancer après 2 à 3 semaines d'enregistrement.

Terminé quand : le labo les teste sur 3 périodes comme les autres techniques.

C'est ici que se jouent les bots « à la seconde » : ils ont besoin du flux enregistré à l'étape 4.

## Étape 6 — Filtres de contexte

- Régime de marché (tendance ou range), tendance du BTC, horaires de liquidité, volatilité minimale et maximale, pause
  autour des grosses annonces économiques.

Terminé quand : chaque filtre est testé, et seuls restent ceux qui améliorent le test final sur la majorité des
cryptos.

## Étape 7 — Combinaisons

- Stratégies combinant une seule technique par famille : tendance, excès, volatilité (ATR pour le stop et l'objectif),
  volume ou flux d'ordres. 2 à 4 paramètres maximum.

Terminé quand : les meilleures combinaisons tournent en fictif avec leur score prudent.

## Étape 8 — Critères avant tout passage au testnet

Afficher pour chaque bot s'il remplit ces conditions : 100 trades fictifs au moins, score prudent positif après frais,
drawdown maximal sous 15 %, résultats stables sur 4 semaines. Rien ne change de mode automatiquement.

---

## Journal des étapes

| Date | Étape | État | Commit de départ |
|---|---|---|---|
| 12/11/2026 | 0 — Audit | Faite : résumé, problèmes par gravité, point de référence | `7148d95` |
| | 0 bis — Réparer la mesure et tout tester | Proposée, en attente d'accord | |
| | 1 — Sécurisation des gains | En attente | |
