# CLAUDE.md : le bot de trading, version Windows

Ce dossier est la version Windows du bot de trading de l'utilisateur. Le code source est sur GitHub :
https://github.com/lecromrayane8-rgb/Testing-podo (branche `claude/trading-bot`, avec son propre CLAUDE.md détaillé).

Réponds en français, en tutoyant, avec des mots simples : l'utilisateur débute et veut que tu fasses le travail à sa
place, puis lui dises en quelques lignes ce qui en ressort.

## Ce qu'il y a ici

- `tradingbot\tradingbot.exe` : le programme (aucun Python nécessaire). Sans argument, il ouvre le site du bot
  (http://127.0.0.1:8765) ; avec une commande, il l'exécute dans la console.
- `.env` : les réglages (copie de `.env.example` au premier lancement). `MODE=paper` = argent fictif.
- `data\` : résultats des labos (`laboratoire.json`, `laboratoire-court-terme.json`,
  `laboratoire-court-terme-limites.json`), tournois (`data\tournoi\`, `data\tournoi-court-terme\`, chacun avec son
  `tableau-de-bord.html`), tableau de bord des bots (`data\tableau-de-bord.html`), journal (`data\bot.log`).
- `data\laboratoire-portefeuille.json` : le labo portefeuille (momentum croisé) ; `data\portefeuille\` : un fichier
  par portefeuille fictif (`value`, `holdings`, `rotations`, `next` = prochaine rotation).
- `data\essais.json` : « Mes essais », le compte fictif des essais lancés depuis le radar du site (positions,
  trades clôturés avec `return` après frais et `reason` : stop, essoufflement, temps, main).
- `data\mouvements.jsonl` : le journal des gros mouvements à la hausse vus par le radar, une ligne par mouvement,
  avec `after` = variation 300, 900 et 3600 s après (avant frais ; un aller-retour coûte environ 0,3 %).
- `autres lanceurs\` : un fichier .bat par commande ; `LISEZ-MOI.txt` : le mode d'emploi de l'utilisateur.

## Les commandes (lancées depuis ce dossier)

| Pour… | Commande | Durée |
|---|---|---|
| labo court terme | `tradingbot\tradingbot.exe labo --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --timeframes "1m,5m,15m" --scanner 8 --memecoins --combinaisons --resultats laboratoire-court-terme.json` | ~1 h |
| le même en ordres limites | la même ligne avec `--ordres-limites --resultats laboratoire-court-terme-limites.json` | ~1 h |
| labo long terme | `tradingbot\tradingbot.exe labo` (ajoute `--csv-dir actions` s'il y a des CSV dans `actions\`) | 10 à 20 min |
| labo portefeuille | `tradingbot\tradingbot.exe labo-portefeuille` | 2 à 5 min |
| tournoi court terme (argent fictif) | `tradingbot\tradingbot.exe tournoi --labo laboratoire-court-terme.json,laboratoire-court-terme-limites.json --top 20 --sans-navigateur` | jusqu'à l'arrêt |
| tournoi long terme (argent fictif) | `tradingbot\tradingbot.exe tournoi --avec-marches-du-labo --top 20 --sans-navigateur` | jusqu'à l'arrêt |
| portefeuille momentum (argent fictif) | `tradingbot\tradingbot.exe portefeuille` | jusqu'à l'arrêt |
| prix en direct, une fois | `tradingbot\tradingbot.exe prix --une-fois` | quelques secondes |
| vérifier la connexion | `tradingbot\tradingbot.exe check` | quelques secondes |
| régénérer le tableau de bord | `tradingbot\tradingbot.exe tableau --no-open` | quelques secondes |

Le plus simple pour l'utilisateur reste le site (« Ouvrir le bot.bat ») et son bouton « Pilote automatique » : les
quatre labos (portefeuille d'abord), puis les deux tournois et le portefeuille. Un seul labo à la fois : ils se
partagent le processeur.

## Lire les résultats d'un labo

Dans chaque fichier `data\laboratoire*.json` : `verdict` (le texte du verdict) et `rows`, une ligne par stratégie et
unité de temps : `variant`, `timeframe`, `trades`, `win_rate`, `gross_expectancy_pct` (gain par trade avant frais, en
%), `expectancy_pct` (après frais), `test_expectancy_pct` (sur le test final, jamais regardé pour choisir),
`verdict`. Seules les stratégies « prometteur » ou « à surveiller » vont en tournoi. Si l'avant-frais est positif mais
l'après-frais négatif, ce sont les frais qui font perdre ; si même l'avant-frais est négatif, rien ne gagne.

Dans `data\laboratoire-portefeuille.json` : `rows`, une ligne par variante : `mean_pct` (rendement moyen par semaine
après frais, en %), `basket_pct` (le panier de toutes les cryptos à parts égales), `excess_pct` (l'écart : ce qui
compte), `test_mean_pct` et `test_excess_pct` (test final), `verdict`. Une variante n'est retenue que si elle bat le
panier ; « ne bat pas le panier » veut dire que garder toutes les cryptos aurait rapporté autant sans rien choisir.

## Règles non négociables

- Ne promets jamais de gains, ni « zéro perte ».
- Pas d'argent réel sans un verdict « prometteur » sur de vraies données, puis plusieurs semaines de testnet.
- Ne touche jamais à `MODE`, aux clés API, à `CONFIRM_LIVE_TRADING` ni à `MAX_CAPITAL` sans une demande explicite de
  l'utilisateur, et jamais pour passer en argent réel sans ces preuves.
- Ne règle pas une stratégie à la main pour embellir un résultat : les décisions de trading restent des règles
  testées par le labo. Pas de trading « à l'instinct ».
- Pour changer le code, travaille dans le dépôt GitHub (branche `claude/trading-bot`) : la version Windows se
  reconstruit toute seule à chaque modification.
