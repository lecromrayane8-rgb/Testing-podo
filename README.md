# Testing-podo : bot de trading spot

Bot de trading automatique en Python, connecté aux plateformes d'échange via [ccxt](https://github.com/ccxt/ccxt)
(Binance par défaut, plus de 100 plateformes possibles). Il trade une seule paire (ex. `BTC/USDT`), uniquement
à l'achat (spot, **sans levier**), avec une stratégie de retour à la moyenne et des garde-fous de risque.

> **À lire avant tout.** Aucun bot ne garantit un profit régulier. Un **taux de réussite élevé ne veut pas
> dire rentable** : une stratégie qui gagne 70 % du temps 0,5 % et perd 30 % du temps 2 % perd de l'argent.
> Ce qui compte, c'est l'**espérance par trade après frais**. Le backtest intégré la calcule et te dit
> franchement si les réglages perdent de l'argent. Commence par le backtest, puis le paper trading, puis le testnet.
> Passe à l'argent réel seulement avec une somme que tu acceptes de perdre entièrement.

## La stratégie

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

## Installation

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

Essaie d'autres paires et unités de temps (`SYMBOL=ETH/USDT`, `TIMEFRAME=4h` dans `.env`). **Méfie-toi de
la sur-optimisation** : des réglages ajustés jusqu'à ce que le backtest soit beau échouent presque toujours
en réel. Garde des réglages simples et vérifie qu'ils tiennent sur plusieurs périodes et plusieurs paires.

## Étape 2 : paper trading (prix réels, ordres simulés, sans clé)

```bash
# .env : MODE=paper
python main.py check   # vérifie l'accès aux prix
python main.py run     # Ctrl+C pour arrêter, la position est reprise au redémarrage
```

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
| `python main.py check` | vérifier la connexion, le prix et les soldes |
| `python main.py run` | lancer le bot selon `MODE` |
| `python main.py reset-guard` | réarmer le bot après un arrêt pour drawdown (à lancer bot arrêté) |

Fichiers produits dans `data/` : `bot.log` (journal), `state_*.json` (position en cours, reprise au redémarrage),
`trades_*.csv` (historique des trades), `paper_wallet_*.json` (portefeuille simulé).

## Limites connues

- Une seule paire, achat seulement.
- En mode limite, le backtest ne voit que les bougies : il ne sait pas si l'ordre aurait été servi dans la file
  d'attente à ton prix. Le testnet donne une idée plus réaliste du taux d'exécution.
- Le stop n'existe que tant que le bot tourne : il n'y a pas d'ordre stop posé sur la plateforme.
- Les prix du testnet Binance peuvent s'écarter fortement du marché réel ; le mode `demo` est plus réaliste.
- Les frais payés en BNB ne sont pas déduits du PnL calculé par le bot.
- Si la réponse d'un ordre se perd sur le réseau, le bot peut ignorer une position ouverte : surveille le journal.

## Tests

```bash
python -m pytest -q
```
