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

- `main.py` : ligne de commande (`backtest`, `robustesse`, `check`, `run`, `tableau`, `reset-guard`).
- `BOTS=PAIRE@UNITE,...` : plusieurs bots dans une boucle (`live.run_bots`). En paper, un compte fictif par bot ;
  sur un vrai compte, `MAX_CAPITAL` est le montant de chaque bot (validé dans `config.py`).
- `tradingbot/strategy.py` : trois familles (`STRATEGY_TYPE`) : retour_moyenne (RSI(2), défaut), cassure (Donchian),
  croisement (moyennes). `compute_signals` produit `entry`/`exit` pour le backtest ET le live (tests de parité).
- `tradingbot/lab.py` : commande `labo`, 7 variantes × marchés × unités de temps, étude 60 % / validation 40 %,
  Bonferroni sur le nombre d'essais, comparaison au buy & hold. Études sans garde-fous live (`research_risk`).
- `tradingbot/backtest.py` : simulation bougie par bougie, mêmes règles que le live ; ordres au marché ou limites.
- `tradingbot/live.py` : boucle live, état JSON dans `data/` repris au redémarrage, ordres limites suivis d'un tour à l'autre.
- `tradingbot/broker.py` : plateforme via ccxt (testnet, demo, réel) et `PaperBroker` simulé.
- `tradingbot/robustness.py` : intervalle de confiance bootstrap, sous-périodes, correction de Bonferroni.
- `tradingbot/obsidian.py` : notes Markdown dans le coffre `OBSIDIAN_VAULT` (trades, backtests, journal, tableau de bord).
- `tradingbot/dashboard.py` : page HTML autonome `data/tableau-de-bord.html`, réécrite à chaque tour de `run`.
  Palette et règles de lisibilité issues du skill dataviz ; les textes venant des données passent par `esc()`.
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
- En attente : le laboratoire sur de vraies données (« 6 - Laboratoire de strategies.bat »).
- L'utilisateur veut du levier et du court terme : on n'en parle qu'après une structure « prometteuse »
  confirmée en paper puis testnet. Le levier ne change pas le signe de l'espérance, il l'amplifie.
