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
  classées de son dernier test), `bots` (chaque bot en bref, avec sa `position`), `events` et `retired`.
- `data\bots\essaim\<id>.json` : le compte complet de chaque bot : `spec` (crypto, unité, technique, sens, objectif,
  levier), `book` (argent, position, trades avec `roi`, `net`, `reason`, `diagnosis`, `analysis`), `backtest` (son
  dernier test, avec `profile` = où sa stratégie gagne et perd), `status` (`actif`, `veille`, `sortie`).
- `data\bots\essaim-etat.json` : la mémoire de l'essaim (cryptos suivies, prochains tests, combinaisons mises de côté
  24 h dans `banned`) ; `data\bots\en-cours.json` : le signal de vie (les bots tournent si son heure a moins de 45 s).
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

## Comment travaille l'essaim

1. Toutes les 10 minutes, les N cryptos USDT les plus agitées sur 24 h (au moins 5 M$ échangés par jour, sans monnaies
   stables). Sous `FLOTTE_MOUVEMENT_MIN` d'amplitude (3 % par défaut), une crypto passe en veille : ses bots n'ouvrent
   plus de trade et gèrent ceux en cours.
2. Chaque crypto est retestée dès son entrée dans la liste, puis toutes les 3 heures : 39 techniques × 2 sens × avec
   ou sans objectif × 5 unités (1 min à 4 h) = 780 combinaisons, sur l'historique récent, frais des contrats à terme
   compris. Une combinaison ne devient un bot que si elle gagne sur l'étude, la validation et la période récente, avec
   assez de trades et sans liquidation. Au plus `FLOTTE_BOTS_PAR_CRYPTO` bots par crypto (8 par défaut, 60 cryptos :
   480 bots au plus).
3. Chaque bot met tout son capital fictif à chaque trade, avec le levier de son horizon (×5 scalping, ×3 court terme,
   ×1 long terme par défaut), réduit si le stop est loin. Un bot que le dernier test ne garde plus finit son trade puis
   s'arrête ; un bot liquidé, à moitié ruiné ou nettement perdant après 20 trades est arrêté et sa combinaison mise de
   côté 24 h.
4. Les agents d'analyse mesurent, sur le backtest de chaque bot, dans quelles conditions sa stratégie gagne ou perd
   (tendance de fond, volatilité, RSI, volume, heure), une probabilité de gain dans les conditions du moment, et
   pourquoi chaque trade réel a gagné ou perdu. Ce sont des mesures : un bot n'entre que sur le signal de sa règle.

Pour expliquer un bot ou un trade à l'utilisateur, lis son fichier `data\bots\essaim\<id>.json` : `diagnosis` et
`analysis` de chaque trade, `backtest.profile`. Choisir parmi des centaines de combinaisons fait toujours sortir des
gagnants par chance : dis-le, c'est le direct qui tranche. Le levier et la vente à découvert n'existent qu'en argent
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
