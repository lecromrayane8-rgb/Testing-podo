# CLAUDE.md

Mémoire du projet, lue au début de chaque session. À tenir à jour quand l'état du projet change.

## Le projet

Bot de trading crypto spot en Python (ccxt) pour un utilisateur francophone débutant, sur Windows et iPad.
Réponds en français, en tutoyant, avec des étapes concrètes et des explications simples.
L'utilisateur veut déléguer au maximum et seulement vérifier : fais le travail plutôt que de lui donner des commandes.

## Principes non négociables

- Aucun bot ne garantit un profit : ne promets jamais de gains, ni de « zéro perte ».
- Pas d'argent réel sans un verdict « robuste » de `python main.py robustesse` sur de vraies données,
  suivi de plusieurs semaines en testnet sur ce marché.
- Ne sur-optimise pas les réglages pour embellir un backtest : toute modification se valide avec `robustesse`.
- Les décisions de trading restent des règles testées. Pas d'IA qui change les réglages ou trade à l'instinct.
- Le mode live exige `CONFIRM_LIVE_TRADING=OUI` et `MAX_CAPITAL > 0` : n'affaiblis jamais ces garde-fous.

## Architecture

- `main.py` : ligne de commande (`backtest`, `robustesse`, `labo`, `tournoi`, `check`, `run`, `tableau`, `reset-guard`).
- `BOTS=PAIRE@UNITE,...` : plusieurs bots dans une boucle (`live.run_bots`). En paper, un compte fictif par bot ;
  sur un vrai compte, `MAX_CAPITAL` est le montant de chaque bot (validé dans `config.py`).
- `tradingbot/strategy.py` : huit familles (`STRATEGY_TYPE`) : retour_moyenne (RSI, défaut), bollinger, cassure
  (Donchian), bollinger_cassure, croisement, macd, momentum, supertrend. `compute_signals` produit `entry`/`exit`
  pour le backtest ET le live (tests de parité par famille). Le backtest respecte le même temps de chauffe que le live.
- `tradingbot/lab.py` : commande `labo`, 24 variantes × 7 marchés × 4 unités = 96 combinaisons, étude 60 % /
  validation 40 %, Bonferroni (approximation normale) sur le nombre d'essais, comparaison au buy & hold.
  Études sans garde-fous live ni élimination (`research_risk`). Pas de levier dans le labo (choix de l'utilisateur,
  à revoir). `--scanner N` / `--memecoins` ajoutent des cryptos ; sous 15 min, historique plafonné (60 j en 1m).
- `tradingbot/scanner.py` : cryptos spot USDT les plus agitées sur 24 h, volume ≥ 5 M$, sans stables ni tokens à
  levier ; `MEMECOINS` (DOGE, SHIB, PEPE, FLOKI, BONK, WIF) gardés seulement s'ils sont assez échangés.
- Commande `tournoi` (`main.py`) : stratégies « à surveiller »/« prometteur » d'un labo (`--labo`, défaut
  `laboratoire.json` ; le labo court terme écrit `laboratoire-court-terme.json` via `labo --resultats`) × cryptos du
  scanner (+ `--avec-marches-du-labo`), toujours en paper, un compte fictif par bot (`bot_label` = variante), données
  partagées par crypto (`CcxtBroker` avec cache), un dossier par labo (`data/tournoi/`, `data/tournoi-court-terme/`).
- Élimination (`risk.TradeStats`, `elimination_reason`, `is_candidate`) : après `ELIMINATE_AFTER_TRADES` trades,
  borne haute à 95 % < 0 → plus d'entrée ; mêmes règles en backtest et en live (test de parité). Jamais de
  modification automatique des réglages. « Candidate au testnet » : ≥ 30 trades et borne basse > 0, seuil durci
  par Bonferroni selon le nombre de bots (ou de stratégies, trades réunis) comparés.
- `tradingbot/backtest.py` : simulation bougie par bougie, mêmes règles que le live ; ordres au marché ou limites.
- `tradingbot/live.py` : boucle live, état JSON dans `data/` repris au redémarrage, ordres limites suivis d'un tour à l'autre.
- `tradingbot/broker.py` : plateforme via ccxt (testnet, demo, réel) et `PaperBroker` simulé (ordres au marché
  servis au prix vendeur/acheteur du carnet, frais et glissement compris).
- `tradingbot/robustness.py` : intervalle de confiance bootstrap, sous-périodes, correction de Bonferroni.
- `tradingbot/obsidian.py` : notes Markdown dans le coffre `OBSIDIAN_VAULT` (trades, backtests, journal, tableau de bord).
- `tradingbot/dashboard.py` : page HTML autonome `data/tableau-de-bord.html`, réécrite à chaque tour de `run`.
  Palette et règles de lisibilité issues du skill dataviz ; les textes venant des données passent par `esc()`.
  Sombre par défaut (bouton clair/sombre), chiffres clés, « équipe » (scanner, stratèges, exécution, gardien),
  positions, classement, par stratégie, courbe (par bot, ou par stratégie dans le tournoi : la couleur suit
  l'entité), journal. Vérifiée à 1280, 820 et 390 px (pas de défilement horizontal de la page).
- Le guide du trading pour l'utilisateur est un document Claude Docs : https://claude.ai/artifact/3CF8W3xks9c3oxa3mNqbA5
- `packaging/` et `.github/workflows/windows-package.yml` : version Windows sans Python, publiée en pré-version
  `windows-dev` (https://github.com/lecromrayane8-rgb/Testing-podo/releases/tag/windows-dev).

## Vérifications

- Tests : `python -m pytest -q`. Les tests de parité live/backtest doivent rester verts.
- Lint : `python -m pyflakes main.py tradingbot tests packaging`.
- Lis et écris les fichiers en UTF-8 explicite : les tests tournent aussi sur Windows (workflow).

## Environnement

- Les sessions cloud n'accèdent pas aux plateformes d'échange (réseau bloqué). Les vraies données s'obtiennent
  sur l'ordinateur de l'utilisateur : version Windows, ou Remote Control vers un dossier de son PC.
- Branche de travail : `claude/trading-bot`.

## État actuel

- Fait : stratégie, backtest, modes paper/testnet/demo/live, ordres limites, test de robustesse (15m, 1h, 4h, 1d),
  journal Obsidian, version Windows sans Python, plusieurs bots en parallèle, tableau de bord, guide du trading.
- Premier test de robustesse réel (03/11/2026, avec l'ancien biais du garde-fou) : le retour à la moyenne perd
  sur 15m, 1h et 4h pour les 5 cryptos (souvent significativement) ; en 1d, 4 cryptos sur 5 sont positives
  (+0,15 % à +0,84 % par trade, ~60 trades) mais non prouvées (fourchette contenant 0).
- Fait (03/11/2026) : scanner + memecoins, labo court terme (1m/5m), tournoi paper en 1 minute, élimination
  automatique, nouvelle interface sombre « équipe de trading ». Lanceurs 7 (labo court terme) et 8 (tournoi 1m).
- Résultat réel rapporté par l'utilisateur : le labo court terme (1m/5m) perd partout après frais ; le labo long
  terme a des stratégies « à surveiller ». Recommandation : abandonner le 1 minute, tournoi long terme (lanceur 9,
  `tournoi --avec-marches-du-labo`) sur beaucoup de cryptos pour accumuler des trades plus vite.
- En attente : photos des tableaux des deux labos (calculer l'avantage brut = espérance + ~0,3 % de coûts, pour
  savoir si des frais plus bas changeraient quelque chose), puis plusieurs semaines de tournoi long terme.
- L'utilisateur veut du levier et du court terme : on n'en parle qu'après une structure « prometteuse »
  confirmée en paper puis testnet. Le levier ne change pas le signe de l'espérance, il l'amplifie.
