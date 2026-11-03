# Testing-podo : bot de trading spot

Bot de trading automatique en Python, connecté aux plateformes d'échange via [ccxt](https://github.com/ccxt/ccxt)
(Binance par défaut, plus de 100 plateformes possibles). Il trade une seule paire (ex. `BTC/USDT`), uniquement
à l'achat (spot, **sans levier**), avec une stratégie de retour à la moyenne et des garde-fous de risque.

> **À lire avant tout.** Aucun bot ne garantit un profit régulier. Un **taux de réussite élevé ne veut pas
> dire rentable** : une stratégie qui gagne 70 % du temps 0,5 % et perd 30 % du temps 2 % perd de l'argent.
> Ce qui compte, c'est l'**espérance par trade après frais**. Le backtest intégré la calcule et te dit
> franchement si les réglages perdent de l'argent. Commence par le backtest, puis le paper trading, puis le testnet.
> Passe à l'argent réel seulement avec une somme que tu acceptes de perdre entièrement.

## Les stratégies

Le bot connaît huit familles de règles, choisies avec `STRATEGY_TYPE` dans `.env`. Deux achètent un repli,
six suivent une tendance :

| Famille | `STRATEGY_TYPE` | Achète quand… | Revend quand… |
|---|---|---|---|
| Repli RSI (défaut) | `retour_moyenne` | le RSI court est survendu dans une tendance haussière | le rebond a eu lieu (clôture > moyenne courte) |
| Repli Bollinger | `bollinger` | la clôture passe sous la bande basse | elle revient sur la bande du milieu |
| Cassure (Donchian) | `cassure` | la clôture dépasse le plus haut des N bougies précédentes | elle passe sous le plus bas des M précédentes |
| Cassure Bollinger | `bollinger_cassure` | la clôture dépasse la bande haute | elle repasse sous la bande du milieu |
| Croisement de moyennes | `croisement` | la moyenne rapide croise la lente par le haut | elle la recroise par le bas |
| MACD | `macd` | la ligne MACD croise sa ligne de signal par le haut | elle la recroise par le bas |
| Momentum | `momentum` | le prix repasse au-dessus de son niveau d'il y a N bougies | il retombe dessous |
| Supertrend | `supertrend` | la tendance Supertrend devient haussière | elle redevient baissière |

Toutes ont un stop-loss à k × ATR sous le prix d'achat et un filtre de tendance optionnel (`TREND_PERIOD`,
0 = aucun). Les signaux sont identiques en backtest et en direct (`compute_signals`), et des tests le vérifient
pour chaque famille. Le détail de la famille par défaut :

« Acheter les replis dans une tendance haussière », un classique de retour à la moyenne (famille RSI(2) de Larry Connors) :

| Règle | Défaut | Variable `.env` |
|---|---|---|
| Filtre de tendance : clôture > moyenne mobile longue | MM 200 | `TREND_PERIOD` |
| Entrée : RSI court en survente | RSI(2) < 10 | `RSI_PERIOD`, `RSI_ENTRY` |
| Sortie : clôture > moyenne mobile courte (rebond) | MM 5 | `EXIT_PERIOD` |
| Stop-loss : prix d'entrée − k × ATR | 2,5 × ATR(14) | `STOP_ATR_MULT`, `ATR_PERIOD` |
| Stop temporel si le rebond ne vient pas | 24 bougies | `MAX_BARS_IN_TRADE` |

Ce type de stratégie a souvent un taux de réussite élevé, car la plupart des replis rebondissent un peu.
En contrepartie, les pertes (stops) sont plus grosses que les gains. Selon le marché et la période,
l'espérance peut être positive ou négative : **le backtest tranche**.

Les signaux sont calculés sur des bougies **clôturées** et exécutés juste après (au marché ou par ordre
limite, voir plus bas). Le backtest applique exactement les mêmes règles (exécution à l'ouverture suivante,
frais et slippage inclus). Des tests vérifient que le bot en direct prend les mêmes trades que le backtest
sur les mêmes données, dans les deux modes d'ordres.

## Ordres à cours limité (réduire les frais)

Avec `ORDER_TYPE=limit`, le bot n'achète plus au marché : il place un ordre d'achat **au meilleur prix
acheteur** du carnet (et un ordre de vente au meilleur prix vendeur pour sortir). Ces ordres sont
**post-only** : la plateforme les refuse s'ils devaient s'exécuter immédiatement au prix du marché. Ils paient
donc toujours le tarif « maker », et jamais d'écart acheteur/vendeur ni de glissement.

| Variable | Défaut | Rôle |
|---|---|---|
| `ORDER_TYPE` | `market` | `market` ou `limit` |
| `FEE_RATE` | `0.001` | frais d'un ordre au marché (taker) |
| `MAKER_FEE_RATE` | `0.001` | frais d'un ordre limite exécuté (maker) |
| `LIMIT_TIMEOUT_BARS` | `1` | durée de vie de l'ordre limite, en bougies |
| `LIMIT_ENTRY_FALLBACK` | `skip` | achat non exécuté à temps : `skip` (trade abandonné) ou `market` (achat au marché) |

Ce qui se passe quand l'ordre n'est pas exécuté avant la fin de sa durée de vie :
- **à l'achat** : le trade est abandonné (`skip`) ou acheté au marché (`market`) ;
- **à la vente** : toujours vendu au marché, le bot ne reste jamais coincé dans une position ;
- **stop-loss** : toujours au marché, immédiatement. Si le stop est touché pendant qu'un ordre de vente limite
  attend, cet ordre est annulé et la position vendue au marché.

**Est-ce que ça réduit vraiment tes frais ?** Ça dépend de ta plateforme et de ton niveau de compte.
Chez Binance au tarif de base, maker et taker coûtent tous les deux 0,1 % : l'ordre limite ne fait alors
économiser que l'écart et le glissement, soit peu sur une paire très liquide comme BTC/USDT. D'autres
plateformes (ou des niveaux de compte plus élevés) facturent moins cher les ordres maker. Pour le savoir :
1. `python main.py check` (en mode testnet, demo ou live) affiche les frais **réels de ton compte** ;
2. reporte-les dans `FEE_RATE` et `MAKER_FEE_RATE` ;
3. `python main.py backtest` compare automatiquement les deux modes sur l'historique.

Contrepartie : un ordre limite peut ne pas être exécuté. Si le prix rebondit tout de suite, tu rates le trade
(`skip`) ou tu achètes plus cher (`market`). Le backtest compte une exécution seulement si le prix passe
**strictement** au-delà de ta limite : être au même prix ne garantit pas d'être servi.

## Gestion du risque

- **Taille de position** : chaque trade risque `RISK_PER_TRADE` du capital (1 % par défaut) si le stop est touché.
- **Exposition max** : `MAX_POSITION_PCT` (95 %), jamais de levier.
- **Perte journalière** : au-delà de `DAILY_LOSS_LIMIT` (3 %), plus de nouvelle entrée jusqu'au lendemain (UTC).
- **Drawdown max** : au-delà de `MAX_DRAWDOWN` (15 %) depuis le plus haut, le bot n'ouvre plus rien jusqu'à
  `python main.py reset-guard`.
- **Capital confié** : `MAX_CAPITAL` limite l'argent que le bot utilise (obligatoire en réel). Le bot ne touche pas
  aux autres avoirs du compte : il ne vend que ce qu'il a lui-même acheté.
- **Élimination d'une stratégie perdante** (le « gardien ») : après `ELIMINATE_AFTER_TRADES` trades (20 par défaut,
  0 = jamais), si même le haut de la fourchette de confiance à 95 % du gain moyen par trade est négatif, la
  stratégie perd nettement : le bot n'ouvre plus de position et le tableau de bord affiche « Éliminée » avec la
  raison. La règle est la même en backtest et en direct (test de parité). Elle coupe ce qui perd, elle ne
  modifie jamais un réglage. `python main.py reset-guard` (bots arrêtés) redonne sa chance à une stratégie.

## Windows sans Python (le plus simple)

1. Télécharge [tradingbot-windows.zip](https://github.com/lecromrayane8-rgb/Testing-podo/releases/download/windows-dev/tradingbot-windows.zip)
   (reconstruit automatiquement à chaque modification du code).
2. Clic droit sur le ZIP → Propriétés → coche « Débloquer » → OK, puis clic droit → « Extraire tout ».
3. Dans le dossier extrait, double-clique sur `1 - Tester la robustesse.bat`, puis suis `LISEZ-MOI.txt`.
   `4 - Lancer le bot.bat` lance 3 bots en argent fictif (15 min, 1 h, 1 jour) et `5 - Tableau de bord.bat`
   ouvre la page de suivi. `7 - Labo court terme.bat` puis `8 - Tournoi en 1 minute.bat` testent le très court
   terme sur les cryptos agitées et les memecoins (voir « Le tournoi » plus bas).

Windows peut afficher « Windows a protégé votre ordinateur » : clique sur « Informations complémentaires »
puis « Exécuter quand même ». C'est normal pour un programme qui n'est pas signé.

## Installation avec Python

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Étape 1 : backtest sur l'historique réel

```bash
python main.py backtest --days 730
```

Le bot télécharge deux ans de bougies publiques (sans clé), simule la stratégie et affiche le taux de réussite,
le profit factor, l'espérance par trade, le drawdown max et la comparaison avec le simple achat-conservation.
Le détail des trades est écrit dans `data/backtest_trades.csv`.

### Le test qui compte : la robustesse

```bash
python main.py robustesse
```

Cette commande teste les mêmes réglages sur 5 paires (BTC, ETH, SOL, BNB, XRP) et 4 unités de temps (15 min,
1 h, 4 h et 1 jour pour le long terme), sur deux ans, et environ 7 ans pour les bougies d'un jour, qui donnent moins
de trades. Elle répond à la seule question qui compte : **l'avantage est-il réel, ou dû à la chance ?**

- **Fourchette de confiance à 95 %** sur le gain moyen par trade : si elle contient 0, le gain peut venir du hasard.
- **Régularité** : l'historique est coupé en 4 périodes, la stratégie doit gagner dans au moins 3 d'entre elles.
- **Seuil durci selon le nombre de marchés testés** : en tester 20 et garder le meilleur fait toujours
  « trouver » un gagnant par hasard.

Seuls les marchés marqués **« robuste »** méritent un essai en testnet. Pour les petits mouvements :
`python main.py robustesse --timeframes 5m,15m`.

**Méfie-toi de la sur-optimisation** : des réglages ajustés jusqu'à ce que le backtest soit beau échouent presque
toujours en réel. Si tu modifies un réglage, relance `robustesse` : un vrai progrès doit tenir sur la plupart des marchés.

Les études (`robustesse`, `labo`) tournent **sans les garde-fous du direct** (perte journalière, drawdown max) :
sinon une stratégie perdante cesserait de trader en cours de route et ne serait jugée que sur un bout d'historique.

### Le laboratoire : comparer les techniques

```bash
python main.py labo                       # ou « 6 - Laboratoire de strategies.bat »
python main.py labo --csv-dir actions     # + des actions : CSV quotidiens Date,Open,High,Low,Close
```

Le laboratoire essaie 24 variantes des huit familles, sur 7 marchés (BTC, ETH, SOL, BNB, XRP, l'or via PAXG,
l'euro via EUR/USDT, plus tes CSV d'actions) et 4 unités de temps (15 min, 1 h, 4 h, 1 jour), soit 96
combinaisons. Compter 10 à 20 minutes. Pour ne pas se laisser tromper par la chance :

1. **Étude puis validation** : chaque historique est coupé dans le temps. Les 60 % les plus anciens servent
   d'étude, les 40 % les plus récents de validation, et seule la validation décide.
2. **Tous les marchés à la fois** : une structure qui marche doit marcher un peu partout, pas sur un seul
   marché choisi après coup.
3. **Seuil durci par le nombre d'essais** : 96 combinaisons testées, donc un seuil 96 fois plus exigeant
   (correction de Bonferroni). Plus on ajoute de variantes, plus il est dur d'être retenu : c'est voulu.
   Sur des prix purement aléatoires, aucune des 96 ne sort « prometteur ».
4. **Comparaison au buy & hold** : la stratégie doit faire mieux, ou risquer bien moins, que garder l'actif.

Verdicts : **prometteur** (tout est réuni), **à surveiller** (positif, mais le hasard peut l'expliquer),
**instable** (gagne sur la validation mais perdait sur l'étude), **perd de l'argent**, **trop peu de trades**.
Pour une variante prometteuse, le labo affiche les lignes exactes à copier dans `.env` pour l'essayer en
argent fictif. Le labo peut **tester** des actions ; le bot ne peut pas encore en **acheter**.

**Le très court terme** (`7 - Labo court terme.bat`) :

```bash
python main.py labo --symbols BTC/USDT,ETH/USDT,SOL/USDT --timeframes 1m,5m --scanner 8 --memecoins
```

`--scanner 8` ajoute les 8 cryptos les plus agitées des dernières 24 h, `--memecoins` les memecoins cotés sur
Binance (DOGE, SHIB, PEPE, FLOKI, BONK, WIF). Le scanner ne garde que les paires spot en USDT échangées pour au
moins 5 millions de dollars par jour, sans monnaies stables ni tokens à levier : sur une crypto peu échangée, le
prix affiché n'est pas celui auquel on peut revendre. En 1 et 5 minutes, l'historique est limité à 60 et 300
jours (environ 86 000 bougies) pour que le labo reste rapide. Les frais pèsent lourd sur de si petits mouvements
(environ 0,3 % par aller-retour avec l'écart et le glissement) : c'est ce que ce labo vérifie.

## Étape 2 : paper trading (prix réels, ordres simulés, sans clé)

```bash
# .env : MODE=paper
python main.py check   # vérifie l'accès aux prix
python main.py run     # Ctrl+C pour arrêter, la position est reprise au redémarrage
```

### Plusieurs bots en même temps (15 min, 1 h, long terme)

`BOTS` lance plusieurs bots dans la même fenêtre, au format `PAIRE@UNITE` :

```
BOTS=BTC/USDT@15m,BTC/USDT@1h,BTC/USDT@1d
```

- En mode paper, chaque bot a son propre compte fictif de `PAPER_START_BALANCE` : leurs résultats se comparent
  sans se mélanger.
- Sur un vrai compte (testnet, demo, live), `MAX_CAPITAL` est obligatoire : c'est le montant confié à **chaque** bot.
- Une erreur réseau sur un bot n'arrête pas les autres. Un bot qui plante 5 fois de suite est mis à l'écart avec
  une alerte dans le journal.

### Le tableau de bord

```bash
python main.py tableau   # ou double-clic sur « 5 - Tableau de bord.bat »
```

Une page s'ouvre dans ton navigateur, sombre par défaut (bouton « Clair / sombre ») : résultat net après frais,
portefeuille, trades, positions, puis « l'équipe » (scanner, stratèges, exécution, gardien), les positions ouvertes
avec leur stop, le classement des bots, la courbe du rendement cumulé, le journal des achats et ventes, le dernier
labo et le dernier test de robustesse. Pendant `run`, le bot la réécrit à chaque tour et elle se recharge toute
seule chaque minute. Un bot qui ne donne plus de nouvelles depuis 10 minutes y apparaît en rouge : ses stops ne
sont plus surveillés. La page fonctionne hors ligne (`data/tableau-de-bord.html`), aussi sur tablette et téléphone.

### Le tournoi : les stratégies du labo en argent fictif, sur les cryptos agitées

```bash
python main.py tournoi --unite 1m      # ou « 8 - Tournoi en 1 minute.bat »
```

Le tournoi reprend les stratégies **« à surveiller » ou « prometteur » du dernier labo** (jamais celles qui
perdent), 6 au plus, et les fait tourner chacune sur les cryptos choisies par le scanner et sur les memecoins
assez échangés : un bot par stratégie et par crypto, chacun avec 1 000 USDT fictifs (`--capital`). Tout reste
**en argent fictif**, quel que soit le `MODE` du `.env`. Les achats se font au prix vendeur et les ventes au prix
acheteur, frais et glissement compris : sur les petites cryptos, l'écart coûte cher et le cacher rendrait le test
trop beau.

- `--unite 1m` force une unité de temps pour toutes les stratégies ; sans elle, chacune garde celle du labo.
- `--symbols PEPE/USDT,WIF/USDT` remplace le scanner, `--top 8` règle sa taille, `--sans-memecoins` les retire.
- Le gardien élimine les stratégies qui perdent nettement ; une stratégie est marquée **« candidate au testnet »**
  après au moins 30 trades dont la fourchette de confiance reste au-dessus de zéro. Ce n'est pas un feu vert pour
  l'argent réel : c'est le signal pour la tester plusieurs semaines en testnet.
- Le tournoi a son propre dossier et son propre tableau de bord (`data/tournoi/`). Relancé, il reprend ses bots ;
  pour repartir de zéro, supprime ce dossier.
- La console affiche les achats, les ventes, les éliminations et un résumé toutes les 5 minutes ; le détail de
  chaque bougie est dans le tableau de bord. Le tournoi n'écrit pas dans Obsidian : des dizaines de bots en
  1 minute y créeraient des milliers de notes par jour.

Le scanner choisit les cryptos agitées **du moment** : il ne les lance pas au moment de leur création (les gains
affichés au lancement d'un memecoin sont rarement exécutables, faute d'acheteurs et à cause des frais).

## Étape 3 : connexion à un espace de trading de test (faux argent, vraie plateforme)

Ici, les ordres passent vraiment sur la plateforme, mais sur un compte de test.

**Binance Spot Testnet** (`MODE=testnet`)
1. Va sur https://testnet.binance.vision et connecte-toi avec GitHub.
2. Clique sur « Generate HMAC_SHA256 Key » et copie la clé et le secret.
3. Dans `.env` : `MODE=testnet`, `API_KEY=...`, `API_SECRET=...`

**Binance Demo Trading** (`MODE=demo`), avec des prix plus proches du marché réel
1. Sur https://demo.binance.com, ouvre la gestion des API et crée une clé.
2. Dans `.env` : `MODE=demo`, `API_KEY=...`, `API_SECRET=...`

Ensuite :

```bash
python main.py check   # doit afficher « Connexion OK » et tes soldes de test
python main.py run
```

Laisse tourner **plusieurs semaines** et compare `data/trades_*.csv` avec le backtest.

## Étape 4 : argent réel (à tes risques)

Ne le fais que si le backtest **et** le testnet montrent une espérance positive. Ensuite :

1. Crée une clé API sur ta plateforme avec **uniquement** le droit de trading spot. **Désactive les retraits**
   et restreins la clé à l'adresse IP de ta machine.
2. Dans `.env` :
   ```
   MODE=live
   API_KEY=...
   API_SECRET=...
   MAX_CAPITAL=100          # petit montant pour commencer
   CONFIRM_LIVE_TRADING=OUI # sans ça, le bot refuse de démarrer en réel
   ```
3. `python main.py check` puis `python main.py run`.

Vérifie que la plateforme est autorisée dans ton pays (en France : registre de l'AMF / agrément MiCA) et
renseigne-toi sur la fiscalité de tes plus-values.

## Journal Obsidian (la mémoire du bot)

[Obsidian](https://obsidian.md) est une application de notes gratuite. Un coffre Obsidian n'est qu'un dossier
de fichiers texte : le bot y écrit tout seul, sans connecteur.

1. Installe Obsidian et crée un coffre (ou utilise le tien).
2. Dans `.env` : `OBSIDIAN_VAULT=` suivi du chemin du coffre, par exemple
   `OBSIDIAN_VAULT=C:\Users\toi\Documents\MonCoffre` ou `OBSIDIAN_VAULT=~/Documents/MonCoffre`.
3. Pour les tableaux du tableau de bord, installe l'extension communautaire **Dataview**
   (Réglages → Extensions communautaires → Parcourir → « Dataview »).

Le bot crée un dossier `Trading bot` dans le coffre :

| Note | Écrite quand | Contenu |
|---|---|---|
| `Tableau de bord` | une seule fois | résumé des trades, backtests et tests de robustesse |
| `Journal/AAAA-MM-JJ` | pendant `run` | achats, ventes, ordres et alertes de la journée |
| `Trades/…` | à chaque trade clôturé | prix, PnL, raison de sortie, et une section « Ce que je retiens » |
| `Backtests/…` | à chaque `backtest` | résultat complet, réglages utilisés, et « Mes observations » |
| `Robustesse/…` | à chaque `robustesse` | tableau, verdict, réglages |

**Ce que ce « cerveau » fait, et ne fait pas.** Il garde la mémoire de tout ce qui a été testé et tradé. Tu ne
refais pas deux fois le même test, tu vois si le réel colle au backtest, et tu peux demander à Claude d'analyser
le dossier. En revanche, il ne prend **aucune décision** à la place des règles du bot. Un bot qui modifie ses
réglages tout seul d'après ses derniers résultats finit par suivre le bruit du marché, et perd de l'argent.

## Faire tourner le bot 24h/24

Le stop-loss est surveillé par le bot (vérification toutes les `POLL_SECONDS` secondes) : **si le bot est arrêté,
aucun stop ne protège la position**. Fais-le tourner sur une machine allumée en permanence (un petit VPS par exemple) :

```bash
nohup python main.py run > /dev/null 2>&1 &
tail -f data/bot.log
```

## Commandes

| Commande | Rôle |
|---|---|
| `python main.py backtest [--days N] [--capital X] [--csv fichier]` | tester la stratégie sur l'historique |
| `python main.py robustesse [--symbols A,B] [--timeframes 15m,1h,1d] [--days N]` | tester plusieurs marchés et périodes, avec verdict statistique |
| `python main.py labo [--symbols A,B] [--timeframes 1h,1d] [--csv-dir dossier] [--scanner N] [--memecoins]` | comparer les stratégies, validées hors échantillon |
| `python main.py tournoi [--unite 1m] [--top N] [--symbols A,B] [--sans-memecoins] [--capital X]` | faire s'affronter en argent fictif les stratégies retenues par le labo |
| `python main.py check` | vérifier la connexion, le prix et les soldes de chaque bot |
| `python main.py run` | lancer les bots selon `MODE` et `BOTS` |
| `python main.py tableau [--no-open]` | générer et ouvrir le tableau de bord |
| `python main.py reset-guard` | réarmer les bots après un arrêt pour drawdown (à lancer bots arrêtés) |

Fichiers produits dans `data/` : `bot.log` (journal), `state_*.json` (position en cours, reprise au redémarrage),
`trades_*.csv` (historique des trades), `paper_wallet_*.json` (portefeuilles simulés), `robustesse.json`
(dernier test), `laboratoire.json` (dernier labo) et `tableau-de-bord.html`. Le tournoi range les siens dans
`data/tournoi/`, avec `tournoi.json` (cryptos et stratégies en compétition).

## Limites connues

- Achat seulement, une position à la fois par bot.
- En mode limite, le backtest ne voit que les bougies : il ne sait pas si l'ordre aurait été servi dans la file
  d'attente à ton prix. Le testnet donne une idée plus réaliste du taux d'exécution.
- Le stop n'existe que tant que le bot tourne : il n'y a pas d'ordre stop posé sur la plateforme.
- Les prix du testnet Binance peuvent s'écarter fortement du marché réel ; le mode `demo` est plus réaliste.
- Les frais payés en BNB ne sont pas déduits du PnL calculé par le bot.
- Si la réponse d'un ordre se perd sur le réseau, le bot peut ignorer une position ouverte : surveille le journal.
- En argent fictif, un ordre au marché est servi en entier au meilleur prix du carnet : sur une petite crypto, un
  gros ordre réel ferait bouger le prix. Garde des montants modestes par rapport au volume échangé.
- Le tournoi suit les cryptos choisies au lancement : relance-le de temps en temps pour que le scanner les renouvelle.

## Tests

```bash
python -m pytest -q
```
