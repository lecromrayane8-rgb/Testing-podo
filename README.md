# Testing-podo : bot de trading spot

Bot de trading automatique en Python, connecté aux plateformes d'échange via [ccxt](https://github.com/ccxt/ccxt)
(Binance par défaut, plus de 100 plateformes possibles). Il trade uniquement à l'achat, au comptant (spot) et
**sans levier en argent réel**, avec onze familles de stratégies testées hors échantillon (dont les supports et
résistances), des garde-fous de risque, un laboratoire qui cherche ce qui tient après frais, un **trader fictif** qui
joue les stratégies retenues sur beaucoup de cryptos et explique chaque trade (levier possible en argent fictif), des
tournois, un radar des mouvements, l'actualité, une école du trading pour débutant, et un site qui réunit tout.

**Démarrage rapide (Windows, sans Python)** : télécharge le
[ZIP](https://github.com/lecromrayane8-rgb/Testing-podo/releases/download/windows-dev/tradingbot-windows.zip),
extrais-le et double-clique sur `Ouvrir le bot.bat` : le site du bot s'ouvre dans ton navigateur. Le soir, clique
sur « Pilote automatique » : les cinq labos tournent à la suite (dont le scalping avec les frais des futures et le
labo portefeuille), puis ton trader, son rejeu, les tournois et le portefeuille démarrent tout seuls en argent fictif
avec ce qui a été retenu ; l'accueil du site montre le lendemain ce que fait ton trader, trade par trade, et pourquoi.

> **À lire avant tout.** Aucun bot ne garantit un profit régulier. Un **taux de réussite élevé ne veut pas
> dire rentable** : une stratégie qui gagne 70 % du temps 0,5 % et perd 30 % du temps 2 % perd de l'argent.
> Ce qui compte, c'est l'**espérance par trade après frais**. Le backtest intégré la calcule et te dit
> franchement si les réglages perdent de l'argent. Commence par le backtest, puis le paper trading, puis le testnet.
> Passe à l'argent réel seulement avec une somme que tu acceptes de perdre entièrement.

## Les stratégies

Le bot connaît onze familles de règles, choisies avec `STRATEGY_TYPE` dans `.env`. Deux achètent un repli,
six suivent une tendance, une saute sur un mouvement soudain, deux tradent les supports et résistances :

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
| Impulsion | `impulsion` | le prix vient de prendre au moins `IMPULSE_PCT` en `IMPULSE_BARS` bougies (seulement la bougie où le mouvement apparaît) | il passe sous le plus bas des M bougies précédentes (le mouvement s'essouffle) |
| Rebond sur support | `support` | venue d'au-dessus, la bougie touche un support solide (touché au moins 2 fois) puis clôture au-dessus, en hausse | le prix touche la résistance suivante, ou le support cède |
| Cassure de résistance | `resistance` | la clôture franchit nettement une résistance solide | le prix retombe sous l'ancien niveau, devenu support |

Les supports et résistances (`tradingbot/levels.py`) sont trouvés comme un trader les trace : les sommets et creux
nets (le plus haut ou le plus bas de 5 bougies de chaque côté, connus seulement 5 bougies plus tard), regroupés en
zones larges d'une demi-bougie moyenne, parmi les 150 dernières bougies (`LEVEL_WINDOW`, `LEVEL_LOOKBACK`,
`LEVEL_TOUCHES`, `LEVEL_TOL`). Ils ne dépendent que de cette fenêtre : le bot en direct trouve exactement les mêmes
niveaux que le backtest (tests de parité).

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
3. Dans le dossier extrait, double-clique sur `Ouvrir le bot.bat` : le site du bot s'ouvre dans ton navigateur
   (voir ci-dessous). Garde la fenêtre noire ouverte : la fermer arrête le site et tout ce qu'il a lancé.
   `Ouvrir le bot sur iPad ou telephone.bat` ouvre le même site aux appareils du Wi-Fi de la maison, avec un code.
   Les anciens lanceurs (menu, labos, tournois, prix...) sont rangés dans `autres lanceurs` ; `LISEZ-MOI.txt`
   explique tout.

Windows peut afficher « Windows a protégé votre ordinateur » : clique sur « Informations complémentaires »
puis « Exécuter quand même ». C'est normal pour un programme qui n'est pas signé.

## Le site du bot (tout à portée de main)

```bash
python main.py site          # ou « Ouvrir le bot.bat » ; sans argument, le programme Windows fait de même
```

Le bot sert lui-même une page sur l'ordinateur (http://127.0.0.1:8765) :

Quatre onglets simples (Accueil, Graphiques, École, Actualité) ; le reste est sous « Plus ».

- **Accueil** : la prochaine étape en une phrase, puis **ton trader fictif** : valeur du compte, résultat depuis le
  départ, courbe, positions ouvertes avec leur stop, derniers trades expliqués (pourquoi il est entré, ce qui s'est
  passé, la leçon), ce qu'il a appris, ses stratégies et celles que le gardien a coupées ; en direct, ou rejoué sur
  l'historique. Puis ce qui tourne, avec son journal et un bouton Arrêter.
- **Pilote automatique** : les cinq labos à la suite (portefeuille, court terme, court terme en ordres limites,
  scalping avec les frais des futures, long terme), puis le trader, son rejeu, les deux tournois et le portefeuille
  momentum en argent fictif avec ce qui a été retenu. Ils tournent ensuite tant que le site est ouvert. Si un labo ne
  retient rien, la suite correspondante attend : c'est voulu.
- **Graphiques** : chaque crypto en bougies (15 min, 1 h, 4 h, 1 jour) comme un trader la lit : supports et
  résistances avec le nombre de touches, moyennes sur 50 et 200 bougies, l'achat et le stop du trader, ses derniers
  achats et ventes, la lecture du graphique en mots simples (tendance, RSI, taille des bougies face aux frais,
  chiffres ronds, scénario d'un trader) et le signal de chaque règle du trader.
- **École** : douze leçons courtes pour débutant (`tradingbot/school.py`) : le trading, une crypto, les bougies, la
  tendance, les supports, le stop et la taille de position, le levier, les frais et le scalping, les indicateurs,
  l'actualité, tester avant de trader, lire les trades de son trader. Un schéma ou un simulateur quand l'idée a une
  forme (levier, taille de position, frais), un mini-quiz dont chaque réponse est expliquée, les sources.
- **Actualité** (`tradingbot/news.py`) : les derniers titres de CoinDesk, Cointelegraph et Decrypt, les cryptos citées
  et ce que leur prix a fait depuis la publication ; l'indice peur et avidité, son année, et ce qui a suivi ses
  extrêmes (une observation, pas une règle). Le bot ne trade jamais sur les titres.
- **Plus › Labos et actions** : les résultats des labos, des tournois et du portefeuille, et un bouton par action.
- **Radar des mouvements** : toutes les cryptos de la plateforme cotées en USDT et échangées à plus de 5 M$ par
  jour, classées par variation sur 1, 5 ou 15 minutes (barre jaune au-delà de 1 %, 2 % ou 4 %). Il tourne dès
  l'ouverture du site : la liste complète des paires toutes les 5 minutes, puis le dernier prix seulement toutes
  les 10 secondes (requête légère). Le radar ne passe aucun ordre : un mouvement affiché a déjà eu lieu.
  - **L'étude d'une opportunité** (le nom d'une crypto) : 30 jours de bougies de 1 minute, les mêmes hausses dans
    le passé, la courbe médiane du prix dans l'heure qui suit l'achat (avec la moitié centrale des cas et la ligne
    des frais), trois sorties testées par le backtest du bot (rapide, normale, laisser courir : seuils fixés
    d'avance), un verdict franc (mauvais, rien de net, piste à confirmer, trop peu de cas) et la perte si le stop
    est touché (`tradingbot/moves.py`).
  - **Le journal des mouvements jaunes** (`data/mouvements.jsonl`) : chaque gros mouvement à la hausse, puis ce que
    le prix a fait 5 min, 15 min et 1 h après, frais compris. Un test en direct, sans regard vers le futur.
- **Mes essais** : un compte fictif de 1000 USDT (`data/essais.json`, `tradingbot/desk.py`) pour essayer une
  opportunité. Achat au prix réel, frais et glissement compris ; taille calculée pour risquer environ 1 % du compte
  au stop, 1/5 du compte au plus par essai, 5 essais au plus ; revente automatique par les règles de l'option
  (stop, essoufflement, temps maximum) ou à la main ; résultats, courbe et historique.
- **Comprendre** (`tradingbot/knowledge.py`) : d'abord **la base des bots**, les idées tirées d'études publiées
  (`tradingbot/research.py`), chacune avec ses règles et où elle en est (à tester, retenue par le labo et utilisée par
  les bots, recalée, ou défavorable selon la recherche) ; puis chaque technique du bot, ce qu'elle mesure et comment la
  lire, ce qu'en dit la recherche publiée (études relues par des pairs, liens SciSpace) et ce qu'en dit le labo de
  l'utilisateur (meilleure version après frais, versions retenues).
- **Prix** (plusieurs plateformes côte à côte), **Tableau de bord** (mes bots et les labos, chaque tournoi),
  **Journal** (la sortie des commandes, en direct) et **Réglages** (bots, capital fictif, frais, Telegram,
  Obsidian).

Chaque bouton lance la même commande que le lanceur `.bat` correspondant (un test le vérifie), dans un processus à
part ; un seul calcul lourd à la fois. Sous Windows, chaque tâche est rangée dans un « job » : fermer la fenêtre du
site arrête aussi les labos et les tournois qu'il a lancés, rien ne continue en cachette.

Ce que le site ne fait jamais : passer en argent réel. Les tournois restent en argent fictif, « Mes bots » refuse
`MODE=live`, et le formulaire ne touche ni à `MODE`, ni aux clés API, ni à `CONFIRM_LIVE_TRADING`, ni à
`MAX_CAPITAL` (ils se changent dans `.env`). Le site n'écoute que l'ordinateur lui-même ; toute action exige un
en-tête que seule sa page envoie, et l'adresse demandée doit être la sienne : un autre site ouvert dans le
navigateur ne peut pas lui donner d'ordres. Avec `--ipad`, il s'ouvre au Wi-Fi de la maison, et chaque appareil
doit d'abord entrer le code affiché dans la fenêtre du bot.

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

Le laboratoire calcule sur tous les cœurs du processeur sauf un (`--coeurs N` pour choisir).
Il essaie 32 variantes de dix familles, sur 7 marchés (BTC, ETH, SOL, BNB, XRP, l'or via PAXG,
l'euro via EUR/USDT, plus tes CSV d'actions) et 4 unités de temps (15 min, 1 h, 4 h, 1 jour), soit 128
combinaisons (chaque variante dans chaque unité, tous marchés réunis). Huit de ces variantes viennent de la
recherche (voir plus bas), dont les quatre sur les supports et résistances. Compter 10 à 20 minutes. Pour ne pas se laisser tromper par la chance :

1. **Étude, validation, puis test final** : chaque historique est coupé dans le temps. La première moitié sert
   d'étude, la tranche de 50 à 80 % de validation (c'est elle qui classe les variantes), et les 20 % les plus
   récents de test final, jamais regardés pour choisir. Une variante n'est « prometteur » que si elle gagne aussi
   sur le test final ; si elle y perd, elle est « instable ». Sans cette dernière tranche, essayer idée après idée
   sur les mêmes données finirait toujours par en trouver une qui a gagné par hasard.
2. **Tous les marchés à la fois** : une structure qui marche doit marcher un peu partout, pas sur un seul
   marché choisi après coup.
3. **Seuil durci par le nombre d'essais** : 128 combinaisons testées, donc un seuil 128 fois plus exigeant
   (correction de Bonferroni). Plus on ajoute de variantes, plus il est dur d'être retenu : c'est voulu.
   Sur des prix purement aléatoires, aucune ne sort « prometteur ».
4. **Comparaison au buy & hold** : la stratégie doit faire mieux, ou risquer bien moins, que garder l'actif.

Verdicts : **prometteur** (tout est réuni), **à surveiller** (positif, mais le hasard peut l'expliquer),
**instable** (gagne sur la validation mais perdait sur l'étude, ou perd sur le test final), **perd de l'argent**, **trop peu de trades**.
Pour une variante prometteuse, le labo affiche les lignes exactes à copier dans `.env` pour l'essayer en
argent fictif. Le labo peut **tester** des actions ; le bot ne peut pas encore en **acheter**.

**Le très court terme** (« Labo court terme » sur le site, ou `7 - Labo court terme.bat`) :

```bash
python main.py labo --symbols BTC/USDT,ETH/USDT,SOL/USDT --timeframes 1m,5m,15m --scanner 8 --memecoins \
    --combinaisons --resultats laboratoire-court-terme.json          # ajouter --ordres-limites : lanceur 10
```

`--scanner 8` ajoute les 8 cryptos les plus agitées des dernières 24 h, `--memecoins` les memecoins cotés sur
Binance (DOGE, SHIB, PEPE, FLOKI, BONK, WIF). Le scanner ne garde que les paires spot en USDT échangées pour au
moins 5 millions de dollars par jour, sans monnaies stables ni tokens à levier : sur une crypto peu échangée, le
prix affiché n'est pas celui auquel on peut revendre. En 1 et 5 minutes, l'historique est limité à 60 et 300
jours (environ 86 000 bougies) pour que le labo reste rapide. Les frais pèsent lourd sur de si petits mouvements
(environ 0,3 % par aller-retour avec l'écart et le glissement) : c'est ce que ce labo vérifie. `--resultats` range
ses résultats à part (`data/laboratoire-court-terme.json`) pour ne pas effacer ceux du labo long terme.

Premier essai sur de vraies données (novembre 2026, 24 variantes, 13 cryptos) : en 1 et 5 minutes, toutes les
stratégies perdent après frais, de −0,18 % à −0,32 % par trade, alors qu'un aller-retour coûte 0,30 % avec les
réglages par défaut. Avant frais, elles ne captaient donc presque rien : environ 0 à +0,04 % par trade en
1 minute, jusqu'à +0,12 % en 5 minutes pour les meilleures. Plus la bougie est longue, plus chaque trade capte de
mouvement, alors que les frais restent les mêmes : c'est pourquoi le labo court terme teste aussi le 15 minutes.

`--ordres-limites` simule des ordres limites (le bot attend son prix : frais maker, ni écart ni glissement à
l'entrée), pour savoir si une exécution moins chère suffirait ; le lanceur 10 range ces résultats dans
`data/laboratoire-court-terme-limites.json`, et le tournoi court terme lit les deux labos.
`13 - Recherche de nuit.bat` enchaîne le labo portefeuille, les deux labos court terme puis le labo long terme, et ouvre le tableau de
bord, qui montre une section (avec son graphique) par labo. Pendant un labo, un bot ou un tournoi, l'ordinateur ne
se met pas en veille (appel Windows prévu pour cela, sans changer les réglages ; l'écran peut s'éteindre). Le labo enregistre ses ordres et ses frais avec
ses résultats, et le tournoi qui reprend ses stratégies les applique à l'identique.

`--combinaisons` ajoute 17 combinaisons pensées pour ce problème : les mêmes techniques, mais qui n'achètent que
quand les bougies bougent assez (filtre de volatilité : ATR d'au moins 0,3 % du prix, le coût d'un aller-retour),
quand le volume double (le mouvement a des acheteurs derrière lui), pendant les heures actives (de 13 h à 21 h
UTC, quand l'Europe et les États-Unis échangent ensemble), ou après une compression (les bandes de Bollinger de la
bougie précédente parmi les 20 % les plus serrées des 120 dernières : un marché calme qui se réveille). Ces seuils
sont fixés d'avance, pas ajustés sur les données. S'y ajoutent 4 **impulsions**, qui sautent sur un mouvement
soudain comme ceux du radar : +1 % en 5 bougies (avec ou sans volume triplé), +0,5 % en une seule bougie avec
volume triplé, +3 % en 15 bougies avec volume triplé ; revente sous le plus bas des 5 bougies précédentes, stop à
2 ATR, 20 bougies au plus. Les 53 variantes passent par la même validation, le même seuil durci et le même test
final. Les filtres existent aussi dans `.env` (`MIN_ATR_PCT`, `VOLUME_MULT`,
`VOLUME_PERIOD`, `ACTIVE_HOURS`, `SQUEEZE_QUANTILE`, `SQUEEZE_PERIOD`) et le bot en direct les applique exactement
comme le backtest (tests de parité).

Le tableau du labo affiche deux gains par trade : **avant frais** (ce que la stratégie capte sur le prix du
graphique) et **après frais** (l'espérance). L'écart est le coût d'un aller-retour. Le verdict en tire la leçon :
si même avant frais rien ne gagne, aucune plateforme moins chère n'y changera rien ; si c'est positif avant frais
mais négatif après, ce sont les frais qui font perdre.

### La base de recherche des bots : des études aux règles

`tradingbot/research.py` est la base de connaissances que les bots utilisent. Chaque idée vient d'études de finance
relues par des pairs et suit toujours le même chemin : l'étude documente un effet ; l'effet devient une règle chiffrée,
réglée d'après l'étude et jamais ajustée sur nos données ; le labo la teste sur les vraies données (étude, validation,
test final, seuil durci) ; si elle tient, un tournoi ou le portefeuille la fait tourner en argent fictif, puis
éventuellement le testnet. Un bot n'agit donc jamais « parce qu'une étude le dit » : il applique les règles qui ont
passé le labo.

| Idée | Ce que disent les études | Règles testées |
|---|---|---|
| La tendance des dernières semaines continue | fort momentum en crypto sur 1 à 8 semaines (Liu et Tsyvinski 2021 ; Hong 2017) | Momentum 7 et 28 (bougies d'un jour) |
| Le prix au-dessus de sa moyenne mobile | l'écart prix/moyennes prévoit les rendements journaliers du Bitcoin (Detzel, Liu et Strauss 2021) | Prix au-dessus de la MM 20, de la MM 50 |
| Les supports et les résistances | ils annoncent des arrêts de tendance ; les ordres s'y accumulent, surtout aux chiffres ronds (Osler 2000 et 2003 ; Kavajecz et Odders-White 2004 ; Brock, Lakonishok et LeBaron 1992) | Rebond sur support (avec ou sans MM 200), Cassure de résistance (avec ou sans volume x2) |
| Les chiffres ronds | les prix du Bitcoin s'y accumulent, sans rendement particulier ensuite (Urquhart 2017) | montrés sur les graphiques, pas de règle à part |
| Garder les cryptos qui ont le plus monté | le momentum entre cryptos est un des trois facteurs de leurs rendements (Liu, Tsyvinski et Wu ; Kosc et al. 2019) | labo portefeuille : 6 variantes |
| Parier contre un excès | défavorable : le retournement après un jour excessif n'a pas rapporté (Caporale et Plastun 2019) | aucune nouvelle règle |
| Trader en minutes plutôt qu'en jours | défavorable : en 5 minutes, le Bitcoin se trade moins bien qu'en jours (Resta et al. 2020) ; deux fois plus de day traders perdent qu'ils ne gagnent (Jordan et Diltz 2003) | aucune nouvelle règle |

L'onglet « Comprendre » du site affiche ces idées, leurs sources et où chacune en est dans tes labos.

### Ton trader fictif : un compte, beaucoup de cryptos, chaque trade expliqué

```bash
python main.py trader               # ou « 17 - Mon trader.bat » ; tourne jusqu'à l'arrêt, en argent fictif
python main.py trader --rejouer     # ou « 18 - Rejouer mon trader.bat » : ses règles rejouées sur les derniers mois
```

Le trader (`tradingbot/trader.py`) fait ce que ferait un trader humain, avec des règles testées : il suit les 20
cryptos les plus échangées, joue les stratégies que les labos ont retenues (« prometteur » ou « à surveiller »), et
seulement si ses frais ne dépassent pas ceux du test. Chaque trade risque 1 % du compte si son stop est touché. Il
note la lecture du graphique à l'achat ; à la vente, il écrit ce qui s'est passé (scénario réussi, faux départ, gain
rendu, frais trop lourds, rien ne s'est passé…) et la leçon, à partir du plus haut et du plus bas atteints
(`tradingbot/explain.py`). Ses leçons donnent toujours le nombre de trades derrière, et préviennent quand ils sont
trop peu nombreux pour conclure.

- **Il apprend sans tricher** : il relit les labos chaque heure. Une stratégie qu'une nouvelle recherche retient entre
  dans son jeu ; une stratégie qui perd nettement sur une crypto n'y est plus jouée (le gardien). Il ne change jamais
  ses réglages tout seul.
- **Levier, en argent fictif seulement** (choix de l'utilisateur) : profil `futures` par défaut, levier jusqu'à 3
  (`TRADER_LEVERAGE`, de 1 à 20), frais des contrats à terme, financement toutes les 8 heures, liquidation simulée.
  Le levier ne crée aucun gain : il permet la taille voulue quand le stop est proche. Profil `spot` : sans levier.
  Les réglages (`TRADER_CAPITAL`, `TRADER_PROFILE`, `TRADER_LEVERAGE`, `TRADER_RISK`, `TRADER_POSITIONS`,
  `TRADER_COINS`) se changent dans les Réglages du site. Le bot en argent réel, lui, reste au comptant et sans levier.
- **Le rejeu** montre tout de suite des trades expliqués, mais il est flatteur par nature (les stratégies ont été
  choisies sur ce passé) : ce n'est pas une preuve.
- Si le labo n'a rien retenu, le trader attend et le dit : c'est ce que ferait un bon trader.

### Le scalping avec les frais des futures

```bash
python main.py labo --symbols BTC/USDT,ETH/USDT,SOL/USDT --timeframes 1m,5m,15m --scanner 8 --memecoins \
    --combinaisons --futures --resultats laboratoire-futures.json      # « 16 - Labo scalping futures.bat »
```

Le même labo court terme, avec les frais des contrats à terme : 0,05 % par ordre au marché, 0,02 % en limite, un
glissement plus faible et le financement toutes les 8 heures. Un aller-retour coûte environ 0,14 %, contre 0,30 % au
comptant : de quoi savoir si c'est la seule chose qui manquait au scalping. Argent fictif seulement ; en vrai, vérifie
ce qui t'est autorisé en France.

### Le labo portefeuille : le momentum croisé

```bash
python main.py labo-portefeuille        # ou « 14 - Labo portefeuille.bat » ; 2 à 5 minutes
python main.py portefeuille             # ou « 15 - Portefeuille momentum.bat » ; argent fictif
```

Au lieu de juger chaque crypto seule, cette règle les compare entre elles : chaque semaine, classer les 30 cryptos
les plus échangées selon leur hausse des 7, 14 ou 28 derniers jours, garder les 3 ou 5 meilleures à parts égales,
revendre celles qui sortent du classement. Soit 6 variantes, aux seuils ronds fixés d'avance. Le labo
(`tradingbot/portfolio.py`) les teste sur des années de bougies d'un jour, sans tricher :

- la décision se prend sur la clôture d'un jour et s'exécute à l'ouverture du lendemain ; chaque rotation paie frais
  et glissement sur ce qui change, la vente finale comprise ;
- les semaines sont coupées dans le temps comme dans le labo (étude 50 %, validation 30 %, test final 20 %) et le
  seuil est durci par le nombre de variantes ;
- chaque variante est comparée au **panier de toutes les cryptos à parts égales**. Toujours investi en crypto, un
  portefeuille gagne quand le marché monte : seul ce qu'il gagne **en plus du panier** montre l'effet du momentum.

Verdicts : **prometteur** (bat le panier nettement, seuil durci compris, sur la validation et le test final, et gagne
sur le test final), **à surveiller** (bat le panier, mais pas assez nettement pour exclure le hasard),
**instable** (ne battait pas le panier sur l'étude ou ne le bat plus sur le test final), **ne bat pas le panier**,
**perd de l'argent**, **trop peu de semaines**. Limite connue, rappelée par le verdict : les cryptos testées sont
celles qui s'échangent aujourd'hui ; celles qui ont disparu manquent, ce qui embellit le passé (biais du survivant).

`portefeuille` fait tourner en argent fictif les variantes retenues (2 au plus, `--variantes`), avec 1 000 USDT
fictifs chacune (`--capital`) : une rotation tout de suite, puis tous les 7 jours à 00 h 10 UTC (juste après la
clôture de la bougie du jour), aux prix réels, frais et glissement compris. Rien ne part sur une plateforme. L'état
est gardé dans `data/portefeuille/` et repris au redémarrage ; chaque rotation part en alerte Telegram. Si le labo
n'a rien retenu, le portefeuille ne démarre pas.

### Les prix en direct

```bash
python main.py prix          # ou « 11 - Prix en direct.bat » ; --cryptos BTC,PEPE --plateformes binance,okx
```

Les vrais prix de Binance, OKX, Kraken, Coinbase et Bybit côte à côte, mis à jour toutes les 10 secondes
(`--secondes`), avec l'écart entre la plateforme la plus chère et la moins chère, la variation sur 24 h, et les
cryptos les plus agitées du moment (`--agitees 8`). Ce sont des données publiques : aucun compte n'est nécessaire.
Chaque plateforme est lue dans sa monnaie stable (USDT, sinon USDC, sinon dollars, marqués « $ »). Une plateforme
injoignable n'arrête pas les autres.
À chaque lancement, l'écran liste aussi les **nouvelles cotations** : les paires apparues sur la première
plateforme depuis ta visite précédente (une crypto qui vient d'arriver n'a pas d'historique : aucune stratégie
testée ne peut la juger).

### Les alertes sur ton téléphone (Telegram, optionnel)

1. Dans Telegram, écris à **@BotFather**, envoie `/newbot` et suis les étapes : il te donne un « token ».
2. Mets-le dans `.env` : `TELEGRAM_TOKEN=...`, puis écris n'importe quel message à ton nouveau bot.
3. Lance `python main.py telegram` (ou « 12 - Tester les alertes Telegram.bat ») : la commande affiche
   l'identifiant de ta discussion à recopier dans `TELEGRAM_CHAT_ID`, et t'envoie un message de test.

Ensuite, `run` t'envoie chaque achat, chaque vente, chaque stratégie éliminée et les erreurs graves (un bot qui
s'arrête). Un tournoi, où des dizaines de bots tradent, n'envoie que son départ, les éliminations et un résumé par
heure. Les messages partent d'un fil à part : une panne de Telegram ne ralentit jamais le bot.

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
python main.py tournoi --avec-marches-du-labo                             # « 9 - Tournoi long terme.bat »
python main.py tournoi --labo laboratoire-court-terme.json,laboratoire-court-terme-limites.json   # lanceur 8
```

Le tournoi reprend les stratégies **« à surveiller » ou « prometteur » d'un labo** (`--labo`, par défaut
`laboratoire.json`, celui du labo long terme ; jamais celles qui perdent), 6 au plus, et les fait tourner chacune
sur les cryptos choisies par le scanner et sur les memecoins assez échangés : un bot par stratégie et par crypto,
chacun avec 1 000 USDT fictifs (`--capital`). Tout reste
**en argent fictif**, quel que soit le `MODE` du `.env`. Les achats se font au prix vendeur et les ventes au prix
acheteur, frais et glissement compris : sur les petites cryptos, l'écart coûte cher et le cacher rendrait le test
trop beau.

- `--unite 1m` force une unité de temps pour toutes les stratégies ; sans elle, chacune garde celle du labo.
- `--avec-marches-du-labo` ajoute les marchés sur lesquels le labo a trouvé ses stratégies. Les stratégies long
  terme tradent rarement : plus il y a de cryptos en même temps, plus les trades s'accumulent vite.
- `--symbols PEPE/USDT,WIF/USDT` remplace le scanner, `--top 8` règle sa taille, `--sans-memecoins` les retire.
- Le gardien élimine les stratégies qui perdent nettement. Un bot, ou une stratégie (trades de toutes ses cryptos
  réunis, comme dans le labo), est marqué **« candidate au testnet »** après au moins 30 trades dont la fourchette
  de confiance reste au-dessus de zéro. Le seuil est durci selon le nombre de bots (ou de stratégies) comparés :
  parmi 80 bots sans avantage, environ 2 passeraient sinon le seuil par chance. Ce n'est pas un feu vert pour
  l'argent réel : c'est le signal pour la tester plusieurs semaines en testnet.
- Chaque labo a son tournoi, son dossier et son tableau de bord (`data/tournoi/`, `data/tournoi-court-terme/`).
  Relancé, un tournoi reprend ses bots ; pour repartir de zéro, supprime son dossier. Les bougies de moins de
  15 minutes sont suivies toutes les 15 secondes, les autres au rythme de `POLL_SECONDS`.
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

En France, depuis le 1er juillet 2026, seules les plateformes agréées MiCA peuvent proposer leurs services ;
d'après la presse, Binance ne l'était pas à cette date et a arrêté le trading pour ses clients français. Le bot
n'est lié à aucune plateforme (`EXCHANGE=okx`, `kraken`, `coinbase`...) : en argent fictif, il lit seulement les
prix publics. Vérifie que la plateforme est autorisée dans ton pays (en France : registre de l'AMF / agrément MiCA) et
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
| `python main.py site [--port 8765] [--sans-navigateur] [--ipad]` | ouvrir le site du bot (le programme Windows sans argument fait de même) |
| `python main.py backtest [--days N] [--capital X] [--csv fichier]` | tester la stratégie sur l'historique |
| `python main.py robustesse [--symbols A,B] [--timeframes 15m,1h,1d] [--days N]` | tester plusieurs marchés et périodes, avec verdict statistique |
| `python main.py labo [--symbols A,B] [--timeframes 1h,1d] [--csv-dir dossier] [--scanner N] [--memecoins] [--combinaisons] [--ordres-limites] [--futures] [--resultats fichier]` | comparer les stratégies, validées hors échantillon |
| `python main.py tournoi [--labo fichier] [--unite 1m] [--avec-marches-du-labo] [--top N] [--symbols A,B] [--sans-memecoins] [--capital X] [--sans-navigateur]` | faire s'affronter en argent fictif les stratégies retenues par un labo |
| `python main.py trader [--rejouer] [--une-fois]` | le trader fictif : les stratégies retenues sur beaucoup de cryptos, chaque trade expliqué |
| `python main.py labo-portefeuille [--cryptos 30] [--days N]` | tester le momentum croisé (garder chaque semaine les cryptos qui ont le plus monté) contre le panier |
| `python main.py portefeuille [--capital X] [--variantes 2] [--une-fois]` | les variantes retenues par le labo portefeuille, en argent fictif, une rotation par semaine |
| `python main.py check` | vérifier la connexion, le prix et les soldes de chaque bot |
| `python main.py run` | lancer les bots selon `MODE` et `BOTS` |
| `python main.py prix [--cryptos A,B] [--plateformes binance,okx] [--secondes 10] [--une-fois]` | les vrais prix de plusieurs plateformes, en direct et sans compte |
| `python main.py telegram` | relier les alertes à Telegram et envoyer un message de test |
| `python main.py tableau [--no-open]` | générer et ouvrir le tableau de bord |
| `python main.py reset-guard` | réarmer les bots après un arrêt pour drawdown (à lancer bots arrêtés) |

Fichiers produits dans `data/` : `bot.log` (journal), `state_*.json` (position en cours, reprise au redémarrage),
`trades_*.csv` (historique des trades), `paper_wallet_*.json` (portefeuilles simulés), `robustesse.json`
(dernier test), `laboratoire.json` (dernier labo long terme), `laboratoire-court-terme.json`,
`laboratoire-portefeuille.json` et `tableau-de-bord.html`. Les tournois rangent les leurs dans `data/tournoi/` et
`data/tournoi-court-terme/`, avec `tournoi.json` (cryptos et stratégies en compétition) ; les portefeuilles fictifs
dans `data/portefeuille/` ; le trader dans `data/trader/` (`compte.json` en direct, `rejeu.json`) ; le labo scalping
futures dans `laboratoire-futures.json`.

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
