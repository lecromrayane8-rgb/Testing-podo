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

- `main.py` : ligne de commande (`site`, `trader`, `backtest`, `robustesse`, `labo`, `labo-portefeuille`, `tournoi`,
  `portefeuille`, `prix`, `telegram`, `check`, `run`, `tableau`, `reset-guard`). Sans argument (double-clic sur
  l'exécutable Windows), `site`. `NothingRetained` : un labo qui ne retient rien n'est pas une panne (code 0).
- `tradingbot/webapp.py` + `sitepage.py` : le site du bot (`main.py site`, http://127.0.0.1:8765, stdlib seulement).
  Chaque bouton (`ACTIONS`, `steps_for`) lance la même commande que son lanceur .bat (test `test_packaging`) dans un
  sous-processus (`TaskManager`, `Task`) dont le journal s'affiche en direct ; un seul calcul lourd à la fois (`CALCUL`) ;
  « Pilote automatique » = 5 labos (`PORTFOLIO_LAB` d'abord, le plus rapide, puis court terme, limites, `FUTURES_LAB`,
  long terme) puis le trader, son rejeu, les 2 tournois et le portefeuille (`then` ; `TaskManager.start(finishing=)` :
  la tâche qui finit ne bloque pas le calcul qu'elle enchaîne) ; une étape en échec n'arrête pas les suivantes.
  Onglets : Accueil (prochaine étape + le trader : `/api/trader`), Graphiques (`Charts`, `/api/graphique`,
  `/api/marches`), École (`/api/ecole`), Actualité (`/api/actualite`, `news_poller`), et sous « Plus » les anciens
  (Labos et actions, Radar, Prix, Mes essais, Comprendre, Tableau de bord, Journal, Réglages). Accueil : `next_step`
  (le trader d'abord), `lab_summaries`, `tournament_summaries`, `portfolio_summary`. Sous Windows, un job `KILL_ON_JOB_CLOSE` par tâche : fermer
  le site arrête tout. Les commandes reçoivent l'environnement d'avant `.env` (`args.pristine_env`) et relisent `.env` ;
  `TRADINGBOT_SITE=1` passe leur sortie en UTF-8 ligne par ligne. Jamais d'argent réel : « Mes bots » refuse
  `MODE=live`, le formulaire (`FIELDS`, liste blanche) ne touche ni à MODE, ni aux clés, ni à CONFIRM_LIVE_TRADING, ni
  à MAX_CAPITAL. Sécurité : 127.0.0.1, en-tête `X-Demande` exigé pour toute action, contrôle de Host et d'Origin ;
  `--ipad` ouvre au Wi-Fi avec un code à 6 chiffres (`data/site-code.txt`, cookie). Page vérifiée à 1280, 820 et 390 px.
  Les deux tournois du site (et lanceurs 8 et 9) suivent 20 cryptos agitées (`--top 20`) en plus des memecoins.
- `tradingbot/radar.py` : radar des mouvements (onglet du site, allumé dès l'ouverture : `Site.start_background`) :
  tickers complets toutes les 5 min (`update_info` : paires `scanner.tradable` à plus de 5 M$/jour), puis derniers prix
  seulement toutes les 10 s (`fetch_last_prices`, `add_prices`) ; variation sur 1, 5 et 15 min ; une coupure réseau ne
  fabrique pas de faux mouvement. `MoveJournal` note chaque gros mouvement à la hausse (une fois par quart d'heure et
  par crypto) et sa variation 5 min, 15 min et 1 h après (`data/mouvements.jsonl`, `journal_stats` frais compris).
  Information seulement, jamais un ordre.
- `tradingbot/moves.py` : étude d'une opportunité (fiche du radar) sur 30 jours de bougies de 1 min : mêmes hausses
  (signal de la famille impulsion), courbe médiane et quartiles sur 60 min, trois sorties `OPTIONS` (rapide, normale,
  laisser courir) passées par `run_backtest`, verdict franc (`bad`, `neutral`, `good` = piste à confirmer, `few`),
  `trade_plan` = stop et perte si le stop est touché.
- `tradingbot/levels.py` : supports et résistances comme un trader les trace : pivots (plus haut ou plus bas de
  `window` bougies de chaque côté, connus `window` bougies plus tard), zones regroupées (écart < `tol_mult` × taille
  moyenne d'une bougie, `candle_size` = moyenne simple du true range : pas d'EMA, donc identique sur la fenêtre du
  live), touches ; `level_series` (support/resistance « pas encore franchis » à moins d'une largeur de zone,
  next_support/next_resistance au-delà) ; `levels_now`, `nearest`, `round_levels` (chiffres ronds).
- `tradingbot/explain.py` : `read_chart` (tendance MM200 et sa pente, support et résistance avec touches, RSI,
  bougie moyenne face aux frais, chiffres ronds, `scenario` gain/risque d'un trader : une lecture, jamais un ordre),
  `rule_sentence` (pourquoi une règle a acheté), `diagnose` (gagne, gain_partiel, frais, faux_depart, gain_rendu, stop,
  temps, sortie_regle, liquidation, à partir du MFE/MAE et du risque), `lessons` (chiffrées, avec mises en garde).
- `tradingbot/trader.py` : le trader fictif (commande `trader`, lanceurs 17 et 18, action « Mon trader »). Un compte
  (`Account`, `data/trader/compte.json`), les stratégies retenues par les labos (`choose_playbook` : « prometteur » ou
  « à surveiller », frais du trader <= frais du test, pas de labo futures en profil spot), les cryptos `by_volume`,
  risque 1 % par trade (`TRADER_RISK`), levier en argent fictif seulement (profil `futures` : `FUTURES`, levier max
  `TRADER_LEVERAGE`, liquidation sous `MAINTENANCE`), gardien par stratégie et crypto, labos et cryptos relus chaque
  heure (`run(refresh=)`), explications à l'entrée et diagnostic à la sortie. `replay` (`trader --rejouer`,
  `rejeu.json`) : backtests `explain=True` fusionnés en un compte ; test de parité live/rejeu. Le bot en argent réel
  reste au comptant et sans levier.
- `tradingbot/school.py` : l'école (12 leçons, `FIGURES` : candle, chart, risk, leverage, fees, diagnoses ; quiz
  expliqués ; sources ; `examples` = vrais trades du trader). `tradingbot/news.py` : flux RSS (CoinDesk, Cointelegraph,
  Decrypt), `mentions`, `reaction` (mouvement depuis la publication), indice peur et avidité (alternative.me,
  `fng_study` sur 30 jours, épisodes comptés) ; information seulement, jamais d'ordre.
- `tradingbot/research.py` : la base de recherche des bots. `IDEAS` : une idée par effet documenté (clés de
  `knowledge.SOURCES`), avec ses règles fixées d'avance d'après l'étude (`rules` → `RESEARCH_VARIANTS`, ajoutées au
  labo : Momentum 7/28, Prix au-dessus de la MM 20/50, Rebond sur support ± MM200, Cassure de résistance ± volume)
  ou ses variantes de portefeuille (`portfolio`), ou `caution` quand la recherche est défavorable (surréaction,
  intraday) ou que l'idée est seulement informative (`unfavorable=False` : chiffres ronds). Chemin : étude → règle → labo → tournoi/portefeuille →
  testnet ; un bot n'agit jamais « parce qu'une étude le dit ».
- `tradingbot/portfolio.py` : momentum croisé (Liu, Tsyvinski et Wu). `PORTFOLIO_VARIANTS` (7/14/28 j × 3/5 cryptos,
  rotation tous les 7 jours), `simulate` (classement sur la clôture du jour i, achat à l'ouverture de i+1, frais sur
  ce qui change, vente finale payée), `split` 50/30/20, `evaluate` (Bonferroni), `portfolio_verdict` : retenue
  seulement si elle bat le panier de toutes les cryptos à parts égales (étude, validation, test final) ; « prometteur »
  = borne basse durcie de l'écart avec le panier > 0 et test final gagnant ; biais du survivant rappelé dans le
  verdict. `PaperPortfolio` : argent fictif, état dans `data/portefeuille/`, rotation immédiate puis tous les 7 jours à
  00 h 10 UTC, dernier prix connu en secours. Commandes `labo-portefeuille` (30 cryptos les plus échangées,
  `scanner.by_volume`, bougies d'un jour du cache) et `portefeuille` (2 variantes retenues au plus) ; lanceurs 14 et 15.
- `tradingbot/knowledge.py` : onglet « Comprendre » du site (`/api/savoir`) : d'abord « la base des bots »
  (`idea_view` : chaque idée de `research.IDEAS`, ses règles et son statut `a-tester`/`retenue`/`recalee`/
  `defavorable` d'après les labos), puis une fiche par technique (toutes les familles de `STRATEGY_TYPES`, plus
  figures chartistes et momentum croisé), ce que dit la recherche (`SOURCES`, pages SciSpace d'études relues par des
  pairs) et ce qu'en dit le labo de l'utilisateur (`evidence`, `portfolio_evidence`).
- `tradingbot/desk.py` : « Mes essais », compte fictif à part (`data/essais.json`, 1000 USDT) : achat au prix réel,
  frais et glissement compris, taille par le risque (1 %), au plus 1/5 du compte par essai et 5 essais ; revente par
  les règles de l'option (stop au prix du moment, puis temps maximum et essoufflement sur les bougies de 1 min
  clôturées) ou à la main. Surveillé par le site toutes les 15 s (`Site.check_trials`). Jamais d'ordre réel.
- `BOTS=PAIRE@UNITE,...` : plusieurs bots dans une boucle (`live.run_bots`). En paper, un compte fictif par bot ;
  sur un vrai compte, `MAX_CAPITAL` est le montant de chaque bot (validé dans `config.py`).
- `tradingbot/strategy.py` : onze familles (`STRATEGY_TYPE`) : retour_moyenne (RSI, défaut), bollinger, cassure
  (Donchian), bollinger_cassure, croisement, macd, momentum, supertrend, support (rebond venu d'au-dessus sur
  `next_support`, sortie à `next_resistance` ou support cassé), resistance (clôture > résistance + largeur, sortie
  sous le niveau ; niveaux de la bougie précédente), impulsion (hausse d'au moins `impulse_pct`
  en `impulse_bars` bougies, seulement la bougie où elle apparaît ; sortie « essoufflement » sous le plus bas des
  `breakout_exit_period` bougies). `compute_signals` produit `entry`/`exit`
  pour le backtest ET le live (tests de parité par famille). Le backtest respecte le même temps de chauffe que le live.
  Filtres d'achat optionnels pour toutes : volatilité (`min_atr_pct`), volume (`volume_mult`, `volume_period`),
  heures actives UTC (`active_hours`, « 13-21 ») et compression de Bollinger (`squeeze_quantile`, `squeeze_period`).
  Chaque trade du backtest garde le prix du graphique (`entry_mark`, `exit_mark`) : `gross_return` = avant frais.
- `tradingbot/lab.py` : commande `labo`, 32 variantes × 4 unités = 128 combinaisons (7 marchés réunis), étude 50 % /
  validation 30 % / test final 20 % (jamais regardé pour choisir : « prometteur » exige un test final positif,
  sinon « instable »), Bonferroni (approximation normale) sur le nombre d'essais, comparaison au buy & hold.
  Études sans garde-fous live ni élimination (`research_risk`). Pas de levier dans le labo (choix de l'utilisateur,
  à revoir). `--scanner N` / `--memecoins` ajoutent des cryptos ; sous 15 min, historique plafonné (60 j en 1m).
  `--combinaisons` ajoute `COMBOS` (17 variantes avec filtres) et `IMPULSES` (4 impulsions), seuils fixés d'avance :
  `SHORT_TERM_VARIANTS` (53) ; `ALL_VARIANTS` sert à retrouver une variante par son nom. `labo --futures` : frais
  `execution.FUTURES` (0,05 % taker, 0,02 % maker, financement `funding_rate_8h` payé dans le backtest). `VARIANTS` se termine par
  `research.RESEARCH_VARIANTS` (réglages tirés des études, pas de nos données). `run_lab` répartit le calcul par (unité, marché) sur plusieurs
  cœurs (`--coeurs`, repli en série si le parallèle échoue ; `multiprocessing.freeze_support()` dans `main.py`). Le labo affiche l'espérance avant frais
  (`gross_expectancy_pct`) et `cost_diagnosis` dit si ce sont les frais qui font perdre.
- `tradingbot/prices.py` + commande `prix` (lanceur 11) : prix publics de plusieurs plateformes côte à côte (USDT,
  sinon USDC, sinon USD), écart entre elles, cryptos agitées ; une plateforme en panne n'arrête pas les autres.
- `tradingbot/notify.py` + commande `telegram` (lanceur 12) : alertes Telegram optionnelles (TELEGRAM_TOKEN,
  TELEGRAM_CHAT_ID), envoyées d'un fil à part ; `run` envoie les logs JOURNAL, ALERT et ERROR ; un tournoi
  seulement ALERT (départ, éliminations, résumé horaire) et ERROR.
- Labos (`lab.LAB_FILES`) : `laboratoire.json` (long terme), `laboratoire-court-terme.json` (lanceur 7),
  `laboratoire-court-terme-limites.json` (lanceur 10), `laboratoire-futures.json` (lanceur 16, scalping futures) ; une section par labo sur le tableau de bord ; `tournoi --labo`
  accepte plusieurs fichiers (`merge_picks` : meilleure version de chaque stratégie, avec les ordres de son labo).
  Lanceur 13 « Recherche de nuit » : les cinq labos à la suite (portefeuille d'abord). `awake.keep_awake()` empêche la veille Windows
  pendant `labo`, `run` et `tournoi` ; le verdict d'un labo part en alerte Telegram.
- `packaging/windows/` : à la racine du ZIP, `Ouvrir le bot.bat` (`site`) et `Ouvrir le bot sur iPad ou telephone.bat`
  (`site --ipad`) ; les 20 anciens lanceurs (dont `0 - Menu.bat`) dans `autres lanceurs/`, qui remontent d'un dossier
  (`cd /d "%~dp0.."`). Le workflow vérifie que le site de l'exécutable répond et lance une commande.
  `packaging/windows/CLAUDE.md` : consignes pour une session Claude ouverte sur le dossier du ZIP, sur le PC de
  l'utilisateur (commandes de l'exécutable, lecture des résultats, règles non négociables ; test de cohérence).
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
- Plateforme (recherche du 04/11/2026, presse de fin juin 2026, statut actuel non confirmé) : Binance n'avait pas
  l'agrément MiCA au 30/06/2026 et a arrêté le trading pour les clients français (retraits seulement). En paper, ses
  prix publics restent utilisables. Pour testnet/réel, viser une plateforme agréée MiCA (Coinbase, Kraken, OKX,
  Bybit EU, Bitpanda...) et régler FEE_RATE / MAKER_FEE_RATE sur ses vrais frais avant de relancer le labo.

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
- L'utilisateur tient au court terme. Labo court terme réel (ancienne version, 24 variantes × 1m/5m, 13 cryptos) :
  tout perd de −0,18 % à −0,32 % par trade pour 0,30 % de coût d'aller-retour, donc ~0 avant frais en 1m et au
  mieux ~+0,12 % en 5m (Bollinger rebond 20/2,5 + MM200, croisements MM 50/200 et 20/100). Le gain avant frais
  grandit avec l'unité : le labo 7 teste maintenant 1m, 5m et 15m avec les 12 combinaisons ; le lanceur 10 refait
  le même labo en ordres limites. Le labo enregistre `execution` ; le tournoi l'applique (lanceur 8 = tournoi court
  terme, chaque stratégie dans son unité). En attente : photo du tableau et du VERDICT du nouveau labo 7.
- Session autonome du 04/11/2026 (3 h, sans accès au marché depuis le cloud : la politique réseau de
  l'environnement bloque les plateformes ; l'utilisateur peut ajouter data.binance.vision et api.binance.com aux
  domaines autorisés) : test final mis de côté dans le labo, 17 combinaisons (dont heures actives 13-21 UTC et
  compression), labo sur tous les cœurs, graphique « avant frais vs coût », menu « 0 - Menu », prix en direct
  multi-plateformes avec nouvelles cotations, alertes Telegram. Aucune stratégie rentable n'a pu être cherchée sur
  de vraies données pendant cette session : tout dépend du prochain labo 7 lancé sur le PC de l'utilisateur.
- L'utilisateur veut du levier et du court terme : on n'en parle qu'après une structure « prometteuse »
  confirmée en paper puis testnet. Le levier ne change pas le signe de l'espérance, il l'amplifie.
- Session du 05/11/2026 : l'utilisateur ne veut plus jongler avec les fichiers .bat → site du bot (accueil avec la
  prochaine étape, pilote automatique, radar des mouvements, prix, tableau de bord, journal, réglages, accès iPad) et
  famille « impulsion » (son idée : « dès qu'il y a un mouvement, il se positionne dessus ») testée dans le labo
  court terme, jamais tradée sans verdict. Skills : aucun nouveau utile trouvé (SuggestSkills vide) ; connecteur
  CoinGecko branché par l'utilisateur (vue du marché dans la conversation, pas une source du bot). Obsidian reste
  facultatif (journal en notes). Toujours en attente : les résultats du premier pilote/recherche de nuit réel.
- Soir du 05/11/2026 : l'utilisateur, sur l'appli Claude, veut trader en court terme les mouvements jaunes du radar,
  en sécurité, avec le risque dit franchement, des tests et des options → étude d'une opportunité (moves.py), journal
  des mouvements jaunes (test en direct), « Mes essais » en argent fictif (desk.py). Il signale « plein de mauvais
  trucs sur le site » sans préciser : radar rendu toujours allumé et léger ; lui demander des captures de ce qui ne va
  pas. Cette session cloud n'a pas accès à son PC (aucun dossier partagé) : une session Claude Code locale sur le
  dossier du bot le peut.
- Nuit du 05 au 06/11/2026 : réel sur le PC de l'utilisateur : le labo court terme n'a rien retenu (donc pas de tournoi
  court terme : comportement voulu) ; tournoi long terme avec une seule position et zéro trade après quelques heures,
  et « Mes bots » (BTC seul, 15m/1h/1d) qui ont tradé puis plus rien : normal (stratégies longues et rares). Il veut
  plein de cryptos → tournois en `--top 20` ; et une « base comme un livre d'expert » → onglet Comprendre sourcé
  (SciSpace) + variantes Momentum 7/28 issues de la recherche.
- Nuit du 06/11/2026 (session autonome, toujours sans accès aux plateformes depuis le cloud) : l'utilisateur précise
  que la base doit servir aux bots (« une base de données pour les bots », documents de finance) et veut un bot
  opérationnel le lendemain → `research.py` (idées sourcées → règles du labo, dont Prix au-dessus de la MM 20/50),
  labo portefeuille + portefeuille momentum en argent fictif (`portfolio.py`), branchés au pilote, à l'accueil, à
  « Comprendre » et aux lanceurs 13/14/15. Aucun résultat réel encore : tout dépend du prochain pilote sur son PC.
  Avant toute idée nouvelle : attendre les verdicts réels (photo de l'accueil et du journal du pilote).
- Journée du 06/11/2026 (session autonome) : l'utilisateur veut un « trader » qui analyse chaque graphique (supports,
  tendance), entre avec la meilleure stratégie du labo et laisse tourner ; du levier (« c'est de l'argent fictif,
  donc c'est ok » : autorisé en argent fictif seulement), l'actualité, apprendre de ses pertes « jusqu'à ce qu'on
  gagne », le scalping, un site plus simple et une école pour se former. Fait : levels.py, familles support et
  resistance (sourcées : Osler, Kavajecz, Brock), explain.py, trader.py (+ rejeu), labo scalping futures, news.py,
  school.py, site à 4 onglets. Dit franchement : aucun gain promis ; « apprendre » = le labo et le gardien, jamais des
  réglages changés après une perte ; chercher longtemps finit par trouver un gagnant par chance ; pas de trading sur
  les titres. Toujours aucun résultat réel : tout dépend du prochain pilote sur son PC.
