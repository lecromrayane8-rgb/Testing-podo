# CLAUDE.md : le bot de trading, version Windows

Ce dossier est la version Windows du bot de trading de l'utilisateur. Le code source est sur GitHub :
https://github.com/lecromrayane8-rgb/Testing-podo (branche `claude/trading-bot`, avec son propre CLAUDE.md détaillé).

Réponds en français, en tutoyant, avec des mots simples : l'utilisateur débute et veut que tu fasses le travail à sa
place, puis lui dises en quelques lignes ce qui en ressort.

## Ce qu'il y a ici

- `tradingbot\tradingbot.exe` : le programme (aucun Python nécessaire). Sans argument, il ouvre le site du bot
  (http://127.0.0.1:8765), qui lance tout seul l'essaim de bots en argent fictif ; avec une commande, il l'exécute
  dans la console.
- `.env` : les réglages (copie de `.env.example` au premier lancement). `MODE=paper` = argent fictif.
- `data\bots\essaim.json` : le résumé que lit le site, réécrit à chaque tour (toutes les 5 secondes) : `totals`
  (valeur, résultat, trades, bots arrêtés compris), `coins` (une ligne par crypto suivie : `amplitude` sur 24 h,
  `moving` = assez de mouvement, `status`, `tested`, `n_tested`, `n_eligible`, `best` = les combinaisons les mieux
  classées de son dernier test), `bots` (chaque bot en bref, avec sa `position`), `events` et `retired` ; `trial` (la
  mesure à l'essai : `bots` = combinaisons mesurées, `n` trades comptés sur 30 jours, `mean` par trade, `lo` et `hi` sa
  fourchette, `days`, `ranking` par stratégie avec `verdict`, `variant` = la variante que les bots utilisent),
  `holdout` (le test final des choix du labo), `secure` (la sécurisation des gains : réglage `on`, `r`, `part`, et la
  comparaison `sans` / `avec` : `trial` à l'essai par jour, `final` sur le test final par crypto ; `diff`, `lo`, `hi` =
  l'écart avec − sans et sa fourchette) et `reference` (le point de référence).
- `data\bots\essaim\<id>.json` : le compte complet de chaque bot : `spec` (crypto, unité, technique, sens, objectif,
  levier, `secure_r` et `secure_part` = sa sécurisation des gains), `book` (argent, position, trades avec `roi`,
  `net`, `reason`, `diagnosis`, `analysis`, `secured` = la part encaissée en route), `backtest` (son dernier test,
  avec `profile` = où sa stratégie gagne et perd), `status` (`actif`, `veille`, `endormi` = sa crypto a quitté la
  liste, il garde son compte et reprendra à son retour, `sortie`).
- `data\bots\essaim-etat.json` : la mémoire de l'essaim (cryptos suivies, prochains tests, combinaisons mises de côté
  24 h dans `banned`, classement des bots en direct dans `live`, `verdicts`) ; `data\bots\en-cours.json` : le signal de
  vie (les bots tournent si son heure a moins de 45 s).
- `data\bots\essaim-essais.json` : la mesure à l'essai (`stats` : une ligne par stratégie `strategie:technique|unité`,
  par `sortie:`, `sens:`, `unite:`, `technique:` et par combinaison complète `detail:` ; `n`, `total`, `wins`, `gain`,
  `r`, et `days` = trades, somme et gagnants de chaque jour ; les mêmes lignes avec le préfixe `avec:` = la variante
  avec sécurisation des gains). `data\bots\reference.json` : les chiffres du site au
  premier lancement de cette version (`totals`, `ranking`), jamais réécrits : le point de comparaison.
- `data\bot.log` : le journal. Les anciens labos, tournois et le trader fictif écrivent toujours dans `data\` quand
  on les lance depuis `autres lanceurs\`.
- `autres lanceurs\` : un fichier .bat par commande ; `LISEZ-MOI.txt` : le mode d'emploi de l'utilisateur.

## Les commandes (lancées depuis ce dossier)

| Pour… | Commande | Durée |
|---|---|---|
| les bots en direct (argent fictif) | `tradingbot\tradingbot.exe flotte` | jusqu'à l'arrêt |
| vérifier la connexion | `tradingbot\tradingbot.exe check` | quelques secondes |
| prix en direct | `tradingbot\tradingbot.exe prix` | jusqu'à l'arrêt |
| tester les alertes Telegram | `tradingbot\tradingbot.exe telegram` | quelques secondes |
| test de robustesse (avant tout argent réel) | `tradingbot\tradingbot.exe robustesse` | quelques minutes |
| labo court terme (ancien outil) | `tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json` | ~1 h |
| labo long terme (ancien outil) | `tradingbot\tradingbot.exe labo` | 10 à 20 min |

Le plus simple pour l'utilisateur reste le site (« Ouvrir le bot.bat ») : l'écran « Direct » liste tous les bots
(filtres par horizon et par état, tri par résultat), l'onglet « Cryptos » les cryptos suivies ; un clic sur une crypto
montre ses bots, son graphique zoomable et ce que le labo en direct y a testé ; un clic sur un bot montre sa position
(prix d'entrée, stop, objectif, liquidation), son graphique, ses agents d'analyse et chaque trade expliqué. Le site
relance les bots tout seul toutes les 20 secondes s'ils s'arrêtent, sauf si l'utilisateur les a arrêtés à la main.

L'onglet « Tendance » est un bot à part, en argent fictif lui aussi : Bitcoin et Ether tenus seulement au-dessus de
leur moyenne des 50, 100 et 200 derniers jours (un tiers du compte par moyenne dépassée), décision une fois par jour à
la clôture, ordre à l'ouverture suivante, jamais de levier. Ses fichiers sont dans `data\tendance\` : `compte.json`
(la date de création du compte fictif, jamais changée), les bougies d'un jour gardées (`*_1d.csv`) et
`robustesse.json` (le dernier test). Son compte est recalculé à partir des bougies : rien d'autre n'est à lire. Le
test de robustesse ne le déclare pas « robuste » : ne propose jamais de le passer en argent réel. Sans le site, deux
commandes (pas de lanceur, quelques secondes chacune) : `tradingbot\tradingbot.exe tendance` affiche la même page en
texte, et `tradingbot\tradingbot.exe robustesse --tendance` refait son test de robustesse.

## Comment travaille l'essaim

1. Toutes les 10 minutes, les N cryptos USDT les plus agitées sur 24 h (au moins 5 M$ échangés par jour, sans monnaies
   stables). Sous `FLOTTE_MOUVEMENT_MIN` d'amplitude (3 % par défaut), une crypto passe en veille : ses bots n'ouvrent
   plus de trade et gèrent ceux en cours.
2. Chaque crypto est retestée dès son entrée dans la liste, puis toutes les 3 heures : 51 techniques (39 à base
   d'indicateurs, 12 de lecture du graphique : zones à combler, order blocks, prises de liquidité, structure, bougies
   de retournement, divergence, Fibonacci, double creux) × 2 sens × 3
   façons de sortir (par la règle, objectif 2R, stop suiveur) × 5 unités (1 min à 4 h) = 1530 combinaisons, chacune
   simulée sans et avec la sécurisation des gains (`FLOTTE_SECURISATION`, `_SEUIL` en R, `_PART` en % : au seuil, une
   part de la position est encaissée et le stop du reste passe au prix d'entrée, frais compris), sur l'historique
   récent, frais des contrats à terme compris. Une combinaison peut devenir un bot
   si elle gagne sur l'étude et la validation (les premiers 80 % de l'historique), avec assez de trades et sans
   liquidation. Le test final (les derniers 20 %) n'est jamais regardé pour choisir : il mesure ce que vaut le choix
   (`holdout`). Au plus `FLOTTE_BOTS_PAR_CRYPTO` bots par crypto (8 par défaut, 60 cryptos : 480 bots au plus).
3. Chaque bot met tout son capital fictif à chaque trade, avec le levier de son horizon (×5 scalping, ×3 court terme,
   ×1 long terme par défaut), réduit si le stop est loin. Un bot garde sa place d'un test à l'autre ; il n'est arrêté
   que s'il est liquidé, à moitié ruiné ou nettement perdant après 20 trades (sa combinaison est alors mise de côté
   24 h), ou si sa stratégie est recalée. Quand sa crypto quitte la liste depuis 6 heures, il s'endort (`endormi` :
   compte et historique gardés, plus de bougies ni de prix demandés) et se réveille à son retour ; il n'est arrêté
   pour de bon qu'après 30 jours sans retour.
4. Les agents d'analyse mesurent, sur le backtest de chaque bot, dans quelles conditions sa stratégie gagne ou perd
   (tendance de fond, volatilité, RSI, volume, heure), une probabilité de gain dans les conditions du moment, et
   pourquoi chaque trade réel a gagné ou perdu. Ce sont des mesures : un bot n'entre que sur le signal de sa règle.
5. La mesure à l'essai (`essaim-essais.json`) : à chaque test d'une crypto, les trades de toutes les combinaisons sont
   comptés (pas seulement ceux des bots choisis), une seule fois, et seulement s'ils ont été ouverts pendant que la
   crypto bougeait. Aucun choix préalable : c'est la mesure à laquelle se fier. Elle juge les stratégies (technique ×
   unité, toutes cryptos réunies) sur 30 jours, avec une fourchette qui compare les journées entre elles : après 7
   jours, une stratégie nettement gagnante est « prouvee » et passe en priorité aux tests ; nettement perdante,
   « recalee » : plus prise, ses bots s'arrêtent après leur trade. Dans `essaim.json`, `trial.ranking` donne ce
   classement, et `ranking` celui des seuls bots en direct (`essaim-etat.json` : `live`).

Pour expliquer un bot ou un trade à l'utilisateur, lis son fichier `data\bots\essaim\<id>.json` : `diagnosis` et
`analysis` de chaque trade, `backtest.profile`. Choisir parmi des centaines de combinaisons fait toujours sortir des
gagnants par chance : dis-le, ce sont la mesure à l'essai et le direct qui tranchent. Un bot en gain ne prouve rien
tant que sa stratégie n'est pas « prouvee » à l'essai. Le levier et la vente à découvert n'existent qu'en argent
fictif.

## Règles non négociables

- Ne promets jamais de gains, ni « zéro perte ».
- Pas d'argent réel sans un verdict « robuste » de `tradingbot\tradingbot.exe robustesse` sur de vraies données, puis
  plusieurs semaines de testnet.
- Ne touche jamais à `MODE`, aux clés API, à `CONFIRM_LIVE_TRADING` ni à `MAX_CAPITAL` sans une demande explicite de
  l'utilisateur, et jamais pour passer en argent réel sans ces preuves.
- Ne règle pas une stratégie à la main pour embellir un résultat : les décisions de trading restent des règles
  testées. Pas de trading « à l'instinct ».
- Pour changer le code, travaille dans le dépôt GitHub (branche `claude/trading-bot`) : la version Windows se
  reconstruit toute seule à chaque modification.
