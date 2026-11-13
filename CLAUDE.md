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

## Le plan en cours : `PLAN-BOTS.md`

Depuis le 11/11/2026, le travail suit le plan de l'utilisateur, enregistré dans `PLAN-BOTS.md` (étapes 0 à 8, audit du
12/11, point de référence, journal des étapes). Relis-le au début de chaque session et tiens son journal à jour. Ses
règles permanentes s'ajoutent aux principes ci-dessus :

1. Argent fictif uniquement : jamais le mode réel, jamais les clés du fichier `.env`, aucun secret affiché.
2. Une étape à la fois : plan court, l'utilisateur approuve, puis code sans redemander à chaque fichier, tests, compte
   rendu. Ne commence jamais l'étape suivante sans son accord.
3. Un commit git avant chaque étape (point de retour).
4. Une seule logique de gestion des trades, partagée par le direct et le backtest (`fleet.Book`) : jamais deux versions.
5. Backtest réaliste : signaux sur des bougies clôturées, exécution au prix suivant, frais maker et taker, glissement,
   financement des positions à levier.
6. Tout ce qui touche à l'argent (stop, objectif, taille de position, frais, liquidation) a des tests automatiques,
   lancés avant de dire qu'une étape est finie.
7. Interface : le style actuel, en français, une phrase d'explication sous chaque nouveau réglage.
8. Consigne ambiguë ou bug trouvé dans l'existant : le dire avant de continuer.

L'utilisateur est podologue et apprend : explique le pourquoi de chaque choix en français simple, en 5 lignes au plus.
Compte rendu de fin d'étape : ce qui a changé, comment le vérifier sur le site, ce qu'il faut surveiller, l'étape
suivante. Le but du plan : trouver un avantage réel et mesurable, pas embellir les chiffres.

## Lancer

- Le site, qui lance tout seul les bots en argent fictif : `python main.py site`, puis http://127.0.0.1:8765
  (`site --ipad` l'ouvre au Wi-Fi avec un code). Sous Windows, sans Python : « Ouvrir le bot.bat » du ZIP `windows-dev`.
- Les bots seuls, dans la console : `python main.py flotte` (`--une-fois` : un seul tour).
- Le bot de tendance, dans la console : `python main.py tendance` ; son test : `python main.py robustesse --tendance`.
- Installation : `pip install -r requirements.txt` (ccxt, numpy, pandas, pytest).
- Ce que les bots écrivent : `data/bots/` (`essaim.json` le résumé du site, `essaim-etat.json` la mémoire,
  `essaim/<id>.json` un compte par bot) ; journal `data/bot.log` ; réglages dans `.env` (copie de `.env.example`).

## Architecture

- `main.py` : ligne de commande (`site`, `flotte`, `tendance`, `trader`, `backtest`, `robustesse`, `labo`, `labo-portefeuille`,
  `tournoi`, `portefeuille`, `prix`, `telegram`, `check`, `run`, `tableau`, `reset-guard`). Sans argument (double-clic
  sur l'exécutable Windows), `site`. `NothingRetained` : un labo qui ne retient rien n'est pas une panne (code 0).
- `tradingbot/swarm.py` : l'essaim de bots en argent fictif (commande `flotte`, lanceur 19, lancé tout seul par le site).
  `SwarmSettings` (`FLOTTE_CAPITAL`, `FLOTTE_CRYPTOS` 60 au plus 80, `FLOTTE_BOTS_PAR_CRYPTO` 8 au plus 20,
  `FLOTTE_MOUVEMENT_MIN` 3 %, `FLOTTE_LEVIER_SCALPING/COURT/LONG` 5/3/1, `FLOTTE_SECURISATION` oui/non,
  `FLOTTE_SECURISATION_SEUIL` 1R de 0,5 à 3, `FLOTTE_SECURISATION_PART` 50 % de 0 à 90 ; `max_bots` = cryptos × bots ;
  `variant` = « avec » ou « sans », `security()` = seuil et part de la variante). `Swarm.cycle`
  (un tour toutes les 5 s, à l'heure de la plateforme : `PlatformClock`, `fetch_time` toutes les 10 min puis horloge
  monotone ; sans elle, horloge du PC) : résultats des re-tests (`apply_test` : les bots en place gardent leur place,
  leur fiche est rafraîchie par `kept`, les places libres reçoivent les mieux classées ; un test ne met plus personne
  en `sortie`), univers toutes les 10 min (`_refresh_universe` : `scanner.liquid_markets` trié par amplitude ; sous
  `min_move` ou hors liste → `veille`, plus d'entrée ; `_stretch` note les périodes où la crypto bouge : `stretches`,
  `moving_since`, close à la dernière fois vue après 30 min sans nouvelles), re-test de chaque crypto agitée toutes
  les 3 h, et 30 min après son premier test (`FIRST_RETEST_S` : la mesure à l'essai démarre vite ;
  `_schedule_tests` → `Retester.submit(symbol, banned, verdicts, keep, trial)` : un fil télécharge
  `TEST_DAYS` sans la bougie en cours, un `ProcessPoolExecutor(1)` calcule, repli dans le fil ; une crypto qui ne
  bouge plus reçoit une heure après, `CLOSE_DELAY_S`, un dernier test `final` qui clôt sa mesure à l'essai), bougies
  par (crypto, unité) via `CandleStore` (tout une fois, puis les 5 dernières ; `closed` : une bougie n'est terminée
  que si la suivante existe, ou si l'heure de la plateforme a dépassé sa fin ; la bougie attendue pas encore finie →
  nouvel essai 5 s plus tard, puis de moins en moins souvent), `_on_candles` (même ordre que le backtest : `range_bar`
  sur les bougies manquées, `close_bar`, `open_bar` au prix du moment), stop et objectif au prix du moment, `_retire`
  (liquidé, moitié du capital, gardien après `ELIMINATE_AFTER` trades → arrêté et `banned` 24 h ; `sortie` =
  stratégie recalée → arrêté sans mise de côté), humeur (`mood` = `fetch_mood`, une fois par heure). Bots endormis
  (`_sleep_and_wake`, dans `_refresh_universe`) : une crypto hors liste depuis 6 h (`UNFOLLOWED_S`) → ses bots sans
  position passent `endormi` : compte gardé, ni bougies ni prix demandés (`cycle` les saute), hors `max_bots` et hors
  rotation des fichiers ; au retour de la crypto, réveil (`last_ts` None, `woke` : aucune entrée sur une bougie finie
  avant le réveil, rien de rejoué) ; arrêt après `ASLEEP_DAYS` = 30 jours ou au-delà de `MAX_ASLEEP` = 1000.
  `retest_coin` : `LIBRARY` (51 techniques : 39 à base d'indicateurs, 12 de lecture du graphique) × `SIDES` ×
  `fleet.EXITS` (règle, 2R, stop suiveur) × `TIMEFRAMES` (1m à 4h) = 1530 combinaisons, chacune simulée deux fois (`VARIANTS` : sans et avec la sécurisation des gains ; la
  variante des bots fournit les lignes qui choisissent ; `secure` = le test final des deux, pour toutes les
  combinaisons et pour les éligibles ; les bots d'avant en `securise` sont simulés à part), `_eligible` (étude et
  validation positives,
  `MIN_TRADES`, pas de liquidation avant le test final ; LE TEST FINAL N'EST JAMAIS REGARDÉ POUR CHOISIR), `_label`
  (ce que dit le test final : « 3 » gagnant, « 1 » perdant, « 2 » trop peu de trades, « 0 » bot en place qui ne
  gagne plus), `_choose(rows, k, verdicts, taken)` (stratégies prouvées d'abord, recalées jamais, familles variées,
  `per_timeframe(k)` par unité : 2 jusqu'à 8 bots ; `taken` = les bots en place), `holdout` (le test final de ce que
  le labo choisirait), `profile`. La mesure à l'essai (ce qui juge) : `Harvest` compte dans chaque test les trades de
  TOUTES les combinaisons, une seule fois (`done` : dernière bougie du test précédent, par unité) et seulement s'ils
  ont été ouverts pendant que la crypto bougeait (`active`) ; la position encore ouverte attend, sauf au test
  `final` (comptée à sa valeur du moment) ; lignes `strategie:` technique|unité, `technique:`, `sortie:`, `sens:`,
  `unite:` (avec le détail par jour) et `detail:` (combinaison complète) : `n`, `total`, `total_sq`, `wins`, `gain`,
  `r` ; les mêmes lignes avec le préfixe `SAFE` (« avec: ») pour la variante sécurisée ; `_merge_trial`,
  `trial_view(variant)` (par défaut la variante des bots : c'est elle qui juge ; 30 jours `TRIAL_DAYS`, fourchette
  `risk.clustered_bounds` qui compare les journées, verdicts après `TRIAL_MIN_DAYS` = 7 jours et `LIVE_MIN_TRADES`
  trades : `recalee` si le haut à 95 % < 0, `prouvee` si le bas durci par Bonferroni > 0), `verdicts`,
  `_judge_strategies` (annonce ; bots d'une recalée en `sortie`, repris si le verdict est levé), `_secure_summary`
  (avec − sans : à l'essai par journées, sur le test final par cryptos, `risk.paired_bounds`), `_apply_security` (au
  démarrage : chaque fiche reçoit le réglage ; seuil ou part changés → la mesure « avec » repart de zéro, et
  `trial["secure_since"]` note ce jour : la comparaison avec/sans ne prend que les journées d'après, mesurées en
  entier par les deux). Classement en direct, à part : `_learn` (chaque trade fini d'un bot, net
  sans levier, mêmes lignes `stat_keys`, jours gardés `LIVE_DAYS`), `ranking` (site ; le verdict affiché vient de la
  mesure à l'essai). Agents : `features` (tendance MM200 et
  pente, ATR %, RSI 14, volume, heure UTC), `buckets`, `profile`, `insights`, `probability` (tirée vers la moyenne,
  `SHRINK`), `trade_analysis` (après chaque trade). Fichiers : `essaim.json` (résumé du site, `summary`, `bot_brief` ;
  `trial`, `holdout`, `secure`, `reference`), `essaim-etat.json` (`STATE_FILE`, la mémoire, écrite si `state_dirty` ou toutes
  les 10 min ; un test perdu au redémarrage est refait), `essaim-essais.json` (`TRIAL_FILE`, la mesure à l'essai,
  écrite quand un test l'a complétée), `reference.json` (`REFERENCE_FILE` : les chiffres du site au premier lancement
  de cette version, lus dans l'ancien résumé avant de le réécrire ; jamais réécrit), `essaim/<id>.json` (compte de
  chaque bot, écrit s'il change, et tous à tour de rôle en 10 min : `rotation`), verrou `en-cours.json` (fil de signal
  de vie toutes les 10 s, à l'horloge du PC). `run` : réseau coupé → tours retentés de plus en plus tard.
  Tests : parité direct/backtest avec et sans sécurisation (`test_swarm`) et signaux de la fenêtre du direct = tout
  l'historique, pour chaque technique dans les deux sens (`test_fleet`), reprise après redémarrage identique à une
  course sans arrêt, trades à l'essai comptés une seule fois quel que soit le nombre de tests, verdicts par journées,
  comparaison avec/sans refaite à la main, sommeil et réveil d'un bot.
- `tradingbot/fleet.py` : le moteur commun au backtest et au direct. `technique` (`lab.ALL_VARIANTS` + `EXTRA` : EMA,
  VWAP, stochastique, Keltner, ADX, Parabolic SAR, Ichimoku, écart à la moyenne, Heikin-Ashi, et les douze lectures
  du graphique : « Zone à combler (FVG) » et « Order block » avec ou sans MM200, « Prise de liquidité », « Cassure de
  structure », « Avalement », « Marteau », « Bougie intérieure », « Divergence RSI », « Retracement de Fibonacci »,
  « Double creux » ; `_ZONE` = stop à 2 ATR, 48 bougies au plus), `Spec` = crypto, unité,
  technique, sens (`long`, ou `short` = même règle sur le graphique retourné, `mirror`), objectif (`target_r` 0 ou 2R),
  levier, `stop_mode` (`fixe` ; `suiveur` : à la distance du départ du meilleur prix ; `securise` : l'ancienne
  sortie, gardée pour les bots d'avant ; décidé à la clôture dans `_move_stop`, compte dès la bougie suivante, ne
  recule jamais ; clé du bot inchangée pour `fixe`), `secure_r` et `secure_part` (la sécurisation des gains, réglage
  commun : hors de la clé du bot, comme le levier ; `with_security`). `Book` (`open_bar`, `range_bar` stop d'abord,
  puis seuil de sécurisation, puis objectif, au prix limite ; `close_bar`). Sécurisation (`_secure`) : au seuil
  (`pos["secure"]` = prix d'entrée ± `secure_r` × distance, aucun si l'objectif vient avant), un ordre limite encaisse
  `secure_part` (frais maker, financement de cette part) ; `left` = part encore ouverte, `banked` = ce qui est
  encaissé ; `qty`, `notional`, `margin`, `fee` restent ceux de l'entrée ; à la clôture de la bougie le stop passe au
  prix d'entrée, frais d'un aller-retour compris (`stop_kind`). UN SEUL trade par position (`_record` : pnl = encaissé
  + reste, `secured`). `value` = `equity` moins les frais de sortie (ce que le site affiche). Tout le capital ×
  levier, levier réduit pour que le stop passe avant la liquidation (`LIQ_SAFETY`), frais `execution.FUTURES`,
  financement compté comme un coût dans les deux sens, liquidation = toute la mise ; `explain=True` : `diagnosis`.
  `simulate`, `judge` (étude 50 % / validation 30 % / test final 20 % ; un trade à cheval sur le test final ne compte
  nulle part ; `test_total`, `test_sq`, `test_wins` ; `liquidated_early` ; `score` = moyenne / dispersion sur étude +
  validation),
  `condition`/`entry_rule`/`exit_rule` (règles en mots, dans les deux sens), `overlays`, `chart_view` (lignes de la
  technique, vrais trades, trades de la règle sur les bougies affichées, position), `fleet_running` (`HEARTBEAT_S`).
- `tradingbot/trend.py` (13/11/2026) : le bot de tendance, en argent fictif, à part de l'essaim. La règle, fixée
  d'avance : Bitcoin et Ether (`SYMBOLS`) en bougies d'un jour ; à chaque clôture, `levels` compte les moyennes
  (`AVERAGES` = 50, 100, 200 jours ; `average` = chaque moyenne sur ses seules n clôtures, donc identique quelle que
  soit la longueur de l'historique) sous le prix ; le compte tient un tiers de sa valeur en crypto par moyenne
  dépassée. `replay(df, start_ts, capital, ex, averages)` : UNE SEULE LOGIQUE pour le backtest et le direct : ce que
  la clôture de la veille a décidé s'exécute à l'ouverture du jour (`_trade` : ordre au marché, `SPOT` = 0,10 % de
  frais et 0,05 % de glissement, jamais d'emprunt), ordres seulement quand la part change ; `Run` (valeur jour par
  jour, « acheter et garder », ordres). Le compte fictif = `replay` depuis `account_since` (`data/tendance/
  compte.json`, écrit une fois au premier lancement du site, jamais changé ; le compte ouvre à l'ouverture du jour
  suivant). La bougie du jour en cours (la dernière) ne décide rien : elle donne le prix du moment (`thresholds` = le
  prix à dépasser ce soir). `Feed` : bougies finies gardées dans `data/tendance/<plateforme>_BTC-USDT_1d.csv` (relues
  au chiffre près), seuls les derniers jours redemandés, un jour est fini quand la plateforme en ouvre un autre
  (jamais l'horloge du PC). `coin_view`/`view` (fiche légère, `/api/tendance`), `chart_view` (730 bougies, les trois
  moyennes, les ordres ; `/api/tendance-graphique`), `report` (console), `growth`, `worst`, `by_year`. La porte :
  `exits` (chaque sortie du marché d'un rejeu à UNE moyenne, jugée en cryptos contre « garder »), `as_backtest`
  (gain d'une sortie en logarithme : une moyenne simple annonce +1,1 % par sortie sur un marché sans avantage, le
  logarithme rend les frais), `robustness_rows` → `robustness.evaluate` (mêmes seuils que `robustesse`), `verdict`.
  Les comptes « à risque » (13/11/2026, définis dans l'en-tête du fichier et enregistrés avant d'être mesurés,
  `7763d02`) : `VARIANTS` = normal, normal avec stop, à risque (`LEVERAGE` ×2), à risque avec stop, tous rejoués par
  `replay(leverage=, stop=)`. Chaque jour, dans cet ordre : intérêts de la nuit sur l'argent emprunté
  (`FUTURES.funding_rate_8h` × 3), ordre de la veille à l'ouverture (`why` = `regle`, `stop`, ou `levier` : un compte
  qui emprunte est remis à son levier au-delà de `BAND` = 10 % d'écart), liquidation si le plus bas du jour (ou
  l'ouverture) ne couvre plus `fleet.MAINTENANCE` (le compte vaut zéro pour toujours, `Run.dead`), valeur à la
  clôture. Stop suiveur = chandelier de LeBeau, réglages d'origine (`STOP_DAYS` 22, `STOP_ATR` 3) : `stop_line`
  (plus haut des 22 derniers jours moins 3 moyennes simples de l'amplitude vraie), `stop_allows` (clôture sous la
  ligne → tout vendu à l'ouverture suivante ; retour quand une clôture repasse au-dessus). Sans levier ni stop, le
  compte normal est inchangé (ses tests au centime près). `coin_view` : `accounts` (les quatre), `history.variants`,
  `stop` ; `chart_view` : la ligne du stop en pointillés. Tests : `tests/test_trend.py`.
- `tradingbot/webapp.py` + `sitepage.py` : le site du bot (`main.py site`, http://127.0.0.1:8765, stdlib seulement).
  Refait le 06/11/2026 au soir autour de l'essaim (onglet Stratégies ajouté le 07/11, à deux mesures depuis le
  13/11 : « À l'essai » = `trial.ranking`, 30 jours, 7 jours, aujourd'hui, fourchette par journées, verdicts ou
  jours manquants ; « En direct » = `ranking`, les seuls bots) : onglets Direct (`/api/bots` = `swarm_data` :
  `swarm_step`, totaux, encadré « La mesure à l'essai » (bots à l'essai, trades comptés, par trade, test final des
  choix du labo, point de référence), tous les bots avec filtres, tri et pages de 30, événements, bouton « Arrêter
  les bots »), Cryptos (liste ;
  `#crypto/SOL` = `/api/crypto` + `/api/crypto-graphique` : bots, graphique par unité, lecture, actualité, `best` du
  dernier test), page d'un bot (`#bot/<id>` = `/api/bot` + `/api/bot-graphique` : position au chiffre près, agents,
  direct contre backtest, trades expliqués, fiche `knowledge.ENTRIES`), Tendance (`renderTrend` : une fiche par crypto bâtie
  une fois puis mise à jour, `Site.trend_view` gardée 10 s, `trend_chart` ; les quatre comptes fictifs côte à côte,
  les ordres du compte choisi (`trendPick`), ce que chaque compte aurait fait sur tout l'historique), Actualité ; sous « Plus » : Prix, École,
  Réglages, Journal. Onglet Stratégies : d'abord « Sécurisation des gains : avec ou sans ? » (`renderSecure`,
  `summary["secure"]`). Bots endormis : statut `endormi`, filtre « Endormis », tuile des bots sans eux. `zoomChart` :
  bougies, volume, lignes, zones, marques (entrée, stop, objectif, liquidation, seuil de sécurisation en pointillés),
  `bands` (zone du risque jusqu'au stop, zone visée jusqu'à l'objectif), triangles des trades, rond d'une sécurisation ; molette, glisser, pincer, boutons, clavier, double-clic ; mise à jour sans perdre le zoom
  (`box._chart.update`). `bot_data` prend le prix, le statut, le signal et la probabilité du dernier tour dans le
  résumé. `ACTIONS` = `flotte`, `check`, `telegram` (même commande que leur lanceur, test `test_packaging`), chacune
  dans un sous-processus (`TaskManager`, `Task`) dont le journal s'affiche en direct. `Site.start_background` lance
  les bots et les relance toutes les 20 s (`keep_fleet_running`), sauf arrêtés à la main (`fleet_stopped`) ;
  `fleet_running` sait qu'un verrou encore frais vient de nos bots arrêtés (pid) ; changer un réglage `FLOTTE_*` ou
  `EXCHANGE` redémarre les bots (`restart_fleet`). Sous Windows, un job `KILL_ON_JOB_CLOSE` par tâche : fermer le site
  arrête tout. Les commandes reçoivent l'environnement d'avant `.env` (`args.pristine_env`) et relisent `.env` ;
  `TRADINGBOT_SITE=1` passe leur sortie en UTF-8 ligne par ligne. Jamais d'argent réel : les bots du site ne passent
  aucun ordre, le site ne lance jamais `run`, le formulaire (`FIELDS`, liste blanche) ne touche ni à MODE, ni aux clés,
  ni à CONFIRM_LIVE_TRADING, ni à MAX_CAPITAL. Sécurité : 127.0.0.1, en-tête `X-Demande` exigé pour toute action et
  pour les graphiques et l'actualité, contrôle de Host et d'Origin ; `--ipad` ouvre au Wi-Fi avec un code à 6 chiffres
  (`data/site-code.txt`, cookie). Page vérifiée à 1280, 820 et 390 px (démo : plateforme fictive, 96 bots).
- `tradingbot/patterns.py` (13/11/2026) : la lecture du graphique écrite comme des règles, une définition de manuel
  par figure, fixée d'avance. `last_swings`/`known_swings` (dernier sommet et dernier creux marquants : pivots de
  `levels.pivot_points`, connus `window` bougies plus tard, oubliés après `lookback`), `structure_break`,
  `liquidity_sweep`, `engulfing`, `hammer`, `inside_break`, `rsi_divergence`, `double_bottom`, `fair_value_gaps`,
  `order_blocks`, `fib_zones` (les bords de la zone née à chaque bougie) et `zone_retest` (une zone attend le prix
  `valid` bougies, la plus récente remplace l'ancienne, meurt si une clôture passe sous son bas, ne sert qu'une
  fois ; `track` = la zone attendue, pour le graphique). Trois garanties testées (`tests/test_patterns.py`) : aucun
  regard vers le futur (signaux inchangés quand on ajoute des bougies), mémoire courte (la fenêtre du direct voit ce
  que voit le backtest), la vente à découvert lit la même figure sur le graphique retourné. Garde-fou : sur un marché
  sans avantage, rien avant frais.
- `tradingbot/levels.py` : supports et résistances comme un trader les trace : pivots (plus haut ou plus bas de
  `window` bougies de chaque côté, connus `window` bougies plus tard), zones regroupées (écart < `tol_mult` × taille
  moyenne d'une bougie, `candle_size` = moyenne simple du true range : pas d'EMA, donc identique sur la fenêtre du
  live), touches ; `level_series` (support/resistance « pas encore franchis » à moins d'une largeur de zone,
  next_support/next_resistance au-delà) ; `levels_now`, `nearest`, `round_levels` (chiffres ronds).
- `tradingbot/explain.py` : `read_chart` (tendance MM200 et sa pente, support et résistance avec touches, RSI,
  bougie moyenne face aux frais, chiffres ronds, `scenario` gain/risque d'un trader : une lecture, jamais un ordre),
  `rule_sentence` (pourquoi une règle a acheté), `diagnose` (gagne, gain_partiel, frais, faux_depart, gain_rendu, stop,
  temps, sortie_regle, liquidation, à partir du MFE/MAE et du risque), `lessons` (chiffrées, avec mises en garde).
- `tradingbot/trader.py` : le trader fictif (commande `trader`, lanceurs 17 et 18, plus sur le site). Un compte
  (`Account`, `data/trader/compte.json`), les stratégies retenues par les labos (`choose_playbook` : « prometteur » ou
  « à surveiller », frais du trader <= frais du test, pas de labo futures en profil spot), les cryptos `by_volume`,
  risque 1 % par trade (`TRADER_RISK`), levier en argent fictif seulement (profil `futures` : `FUTURES`, levier max
  `TRADER_LEVERAGE`, liquidation sous `MAINTENANCE`), gardien par stratégie et crypto, labos et cryptos relus chaque
  heure (`run(refresh=)`), explications à l'entrée et diagnostic à la sortie. `replay` (`trader --rejouer`,
  `rejeu.json`) : backtests `explain=True` fusionnés en un compte ; test de parité live/rejeu. Le bot en argent réel
  reste au comptant et sans levier.
- `tradingbot/school.py` : l'école (14 leçons, dont la vente à découvert, l'objectif des bots et « Lire le graphique comme un trader », `FIGURES` : candle, chart, risk, leverage, fees, diagnoses ; quiz
  expliqués ; sources ; `examples` = vrais trades des bots, `data/bots/essaim/`). `tradingbot/news.py` : flux RSS (CoinDesk, Cointelegraph,
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
- `tradingbot/knowledge.py` : les fiches par technique (`ENTRIES`, montrées sur la page de chaque bot) et les sources
  de l'école ; `knowledge_view` (plus sur le site) : d'abord « la base des bots »
  (`idea_view` : chaque idée de `research.IDEAS`, ses règles et son statut `a-tester`/`retenue`/`recalee`/
  `defavorable` d'après les labos), puis une fiche par technique (toutes les familles de `STRATEGY_TYPES`, plus
  figures chartistes et momentum croisé), ce que dit la recherche (`SOURCES`, pages SciSpace d'études relues par des
  pairs) et ce qu'en dit le labo de l'utilisateur (`evidence`, `portfolio_evidence`).
- `BOTS=PAIRE@UNITE,...` : plusieurs bots dans une boucle (`live.run_bots`). En paper, un compte fictif par bot ;
  sur un vrai compte, `MAX_CAPITAL` est le montant de chaque bot (validé dans `config.py`).
- `tradingbot/strategy.py` : trente familles (`STRATEGY_TYPES`) : retour_moyenne (RSI, défaut), bollinger, cassure
  (Donchian), bollinger_cassure, croisement, macd, momentum, supertrend, support (rebond venu d'au-dessus sur
  `next_support`, sortie à `next_resistance` ou support cassé), resistance (clôture > résistance + largeur, sortie
  sous le niveau ; niveaux de la bougie précédente), impulsion (hausse d'au moins `impulse_pct`
  en `impulse_bars` bougies, seulement la bougie où elle apparaît ; sortie « essoufflement » sous le plus bas des
  `breakout_exit_period` bougies), et depuis le 06/11/2026 ema_croisement, vwap (glissant), stochastique, keltner,
  adx, psar, ichimoku (nuage décalé : seulement du passé), zscore, heikin (`indicators.py`), et depuis le 13/11/2026
  les dix `PATTERN_FAMILIES` (fvg, order_block, balayage, structure, avalement, marteau, interieure, divergence,
  fibonacci, double_creux : `_pattern_signals` appelle `patterns.py` ; sortie « essoufflement », sauf structure :
  retour sous le dernier creux ; `pattern_marks` = ce que la technique regarde, pour `fleet.overlays`). `compute_signals` produit `entry`/`exit`
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
  Lanceur 13 « Recherche de nuit » : les cinq labos à la suite (portefeuille d'abord). Lanceur 19 « Mes bots en
  direct » (`flotte`) ; menu jusqu'au choix 20. Les labos, tournois et le trader ne sont plus sur le site (demande de
  l'utilisateur : « les bots, ce sera des labos en direct ») mais restent dans `autres lanceurs`. `awake.keep_awake()`
  empêche la veille Windows pendant `labo`, `run`, `tournoi` et `flotte` ; le verdict d'un labo part en alerte Telegram.
- `packaging/windows/` : à la racine du ZIP, `Ouvrir le bot.bat` (`site`) et `Ouvrir le bot sur iPad ou telephone.bat`
  (`site --ipad`) ; les 19 autres lanceurs (dont `0 - Menu.bat`) dans `autres lanceurs/`, qui remontent d'un dossier
  (`cd /d "%~dp0.."`). Le workflow vérifie `flotte --une-fois`, que le site de l'exécutable répond (« Tous les bots »,
  `/api/bots`) et qu'il lance une commande.
  `packaging/windows/CLAUDE.md` : consignes pour une session Claude ouverte sur le dossier du ZIP, sur le PC de
  l'utilisateur (commandes de l'exécutable, lecture des résultats, règles non négociables ; test de cohérence).
- `tradingbot/scanner.py` : cryptos spot USDT les plus agitées sur 24 h, volume ≥ 5 M$, sans stables, tokens à
  levier ni actions en jetons (`tokenized_stock` : nom en « B » ET paire fermée au groupe d'échange `TRD_GRP_016`
  dans `info.permissionSets` ; 105 paires NVDAB, GOOGLB… le 13/11/2026, aucune crypto touchée) ; `MEMECOINS` (DOGE, SHIB, PEPE, FLOKI, BONK, WIF) gardés seulement s'ils sont assez échangés.
- Commande `tournoi` (`main.py`) : stratégies « à surveiller »/« prometteur » d'un labo (`--labo`, défaut
  `laboratoire.json` ; le labo court terme écrit `laboratoire-court-terme.json` via `labo --resultats`) × cryptos du
  scanner (+ `--avec-marches-du-labo`), toujours en paper, un compte fictif par bot (`bot_label` = variante), données
  partagées par crypto (`CcxtBroker` avec cache), un dossier par labo (`data/tournoi/`, `data/tournoi-court-terme/`).
- `risk.student_t` et `risk.clustered_bounds` : la fourchette d'une moyenne quand les trades d'un même groupe (une
  journée) se ressemblent ; loi de Student faite maison (pas de scipy), vérifiée contre les tables.
  `risk.paired_bounds` : la fourchette de l'écart entre deux mesures faites sur les mêmes groupes (avec et sans
  sécurisation, mêmes journées ou mêmes cryptos).
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
- `audit/` : les mesures de contrôle, hors du bot (rien n'est lu sur une plateforme, rien n'est écrit dans `data/`).
  `hasard.py` : des cryptos en marche au hasard (un prix toutes les 10 s, bougies tirées de ce chemin : AUCUNE mèche
  ajoutée, sinon les objectifs gagnent artificiellement), le vrai `retest_coin` choisit ses bots, puis on regarde
  leur test final, leur « direct » sur la suite et la mesure à l'essai de toutes les combinaisons, sans et avec
  sécurisation, puis chaque technique à part (`python audit/hasard.py 80 12 hasard.json`). `vrai.py` : les mêmes mesures sur de VRAIES bougies
  Binance (prix publics par le miroir `data-api.binance.vision`, cache hors du dépôt) : `essai --jours 14` rejoue la
  mesure à l'essai (univers reconstitué heure par heure, trades ouverts pendant que la crypto bougeait), `aujourdhui`
  fait le test du moment sur chaque crypto suivie ; les deux comparent avec et sans sécurisation ; `essai` classe
  aussi chaque technique (`--fin` rejoue exactement une période déjà mesurée). `contexte.py` (étape 1 ter) : pour
  chaque trade à l'essai (`Harvest.rows`, demandé seulement par cet outil), ce qu'on savait à la clôture du signal
  (flux acheteurs/vendeurs et nombre de trades des bougies complètes `publicGetKlines`, tendance de l'unité
  au-dessus et du Bitcoin, comptes acheteurs/vendeurs et intérêt ouvert des archives des contrats à terme), puis
  « condition vraie » contre « fausse » jour par jour (`paired_bounds`, seuil durci), avec deux témoins (pile ou
  face, et la bougie d'entrée connue après coup) : `trades`, `donnees`, `mesure` (`--dossier`, `--unites`) ;
  conditions depuis le 13/11 : flux, flux net (55 %), activité, pic de volume (×2), unité au-dessus, Bitcoin, foule,
  argent engagé, carnet d'ordres à 1 % et à 0,2 % du prix (archives `bookDepth`, une photo toutes les 30 s), les
  trois d'accord ; `matrice` : technique × unité × sens × condition, cherchée sur une période et confirmée sur une
  autre (`--decouverte`, `--confirmation`). `long.py` : le long terme, en bougies d'un jour depuis 2020 (univers
  reconstitué jour par jour, paires retirées de la cote comprises ; chaque trade aussi mesuré contre le panier du
  marché ; première période puis seconde), le portefeuille momentum, et les règles simples en argent composé (filtre
  de tendance sur le Bitcoin et l'Ether depuis 2017, rejoué par le moteur du bot : `trend_rules` appelle
  `trend.replay` ; panier filtré, portefeuilles de la semaine). `secondes.py` : le
  très court terme, en bougies de 15 secondes fabriquées à partir de chaque transaction (`aggTrades`), résultat
  avant et après frais. `marches.py` : la règle du bot de tendance, inchangée (`trend.replay`), sur d'autres marchés :
  prix d'un jour de la banque centrale américaine (FRED, sans clé : Nasdaq depuis 1971, Nikkei depuis 1949, Brent,
  cinq monnaies ; Bitcoin et Ether de Coinbase en recoupement), cryptos du bot et or en jetons par Binance. Le
  PROTOCOLE est écrit en tête du fichier et a été enregistré dans git avant le premier calcul (`fe44aec`) : la règle
  contre « garder » par décennie, le test du mélange (les mêmes journées dans le désordre, 1 000 fois : la règle
  exploite-t-elle de vraies tendances ?), la porte du projet, les sorties réunies année par année, un témoin sans
  tendance refait 20 fois ; hors protocole : l'effet du jour de retard et des frais ; `--csv-dir` pour des fichiers
  fournis à la main (or, S&P 500).
  `rotation.py` : le test refait toutes les 3 h pendant 48 h avec le
  vrai `Swarm.apply_test`, pour compter les bots remplacés. Les deux tournent aussi sur une copie de l'ancien code
  (`git worktree add ... bac35d5`) pour comparer avant et après.

## Vérifications et conventions

- Tests : `python -m pytest -q`. Les tests de parité live/backtest doivent rester verts.
- Lint : `python -m pyflakes main.py tradingbot tests packaging`.
- Lis et écris les fichiers en UTF-8 explicite : les tests tournent aussi sur Windows (workflow).
- Code, commentaires, textes du site et messages en français ; noms de tests en anglais, qui disent le comportement
  (`test_a_trailing_stop_follows_the_best_price_and_never_goes_back`). Les tests de l'argent sont dans
  `tests/test_fleet.py` (moteur : stop, objectif, levier, frais, financement, liquidation) et `tests/test_swarm.py`
  (parité direct/backtest, reprise, re-tests, classement) ; le bot de tendance dans `tests/test_trend.py` (la règle,
  l'ordre au lendemain, les frais au centime, aucun ordre passé ne change quand on ajoute des jours, la relève des
  bougies, le garde-fou « marché sans avantage ») ; les lectures du graphique dans `tests/test_patterns.py`
  (chaque figure sur un graphique dessiné à la main, puis les garanties communes).
- Les réglages d'une technique sont fixés d'avance, jamais ajustés sur les données. Les frais et le glissement des bots
  sont dans `execution.FUTURES`, comptés dans `fleet.Book` (`_open`, `_fill`, `_secure`, `_close`) et nulle part
  ailleurs. Garde-fou : sur un marché fabriqué sans avantage, le moteur doit rendre exactement les frais, avec ou
  sans sécurisation (`test_fleet`).
- Un réglage du site passe par `webapp.FIELDS` (liste blanche, phrase d'aide `help`, bornes ; `switch` = oui ou non,
  écrit seulement s'il change ; `switch_value` = le choix tel que les bots le lisent, « 0 » ou « false » compris) et
  `swarm.SwarmSettings`.
  La page est dans `tradingbot/sitepage.py` (CSS et JS dans des chaînes Python) : un texte venu des données s'insère
  avec `textContent` ; après une modification, `node --check` sur le JS et vérification à 1280, 820 et 390 px.
- Pas de nouvelle dépendance sans nécessité : le site et les bots n'utilisent que la bibliothèque standard, ccxt,
  numpy et pandas (l'exécutable Windows est construit avec PyInstaller).

## Environnement

- Sessions cloud : depuis le 13/11/2026, l'environnement « Ray » de l'utilisateur autorise les prix publics de
  Binance. `data-api.binance.vision` (miroir officiel : bougies, tickers, liste des paires) et `data.binance.vision`
  (archives, dont contrats à terme et financement) répondent ; `api.binance.com` et `fapi.binance.com` répondent 451
  (région refusée par Binance). Le vrai code tourne donc sur de vraies bougies avec `audit/vrai.py` (ccxt :
  `urls["api"]["public"]` vers le miroir et `session.trust_env = True`). Les bots en direct, eux, tournent sur le PC
  de l'utilisateur (version Windows) ; ses résultats (`data\bots`) ne sont lisibles d'ici que s'il partage son dossier
  (Remote Control). Vu le 13/11 au soir : l'environnement « Ray » est en accès réseau libre. `fred.stlouisfed.org`
  répond sans clé (`/graph/fredgraph.csv?id=SERIE` : séries d'un jour officielles). Refusent les robots : `stooq.com`
  (vérification du navigateur), `prices.lbma.org.uk` (403) ; l'or n'est plus chez FRED : pas de longue série de l'or
  sans un fichier donné par l'utilisateur.
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
- Soir du 06/11/2026 : l'utilisateur veut tout reprendre de zéro : 15 bots sur différentes cryptos (dont les très
  agitées) et techniques, trois sections (long terme, court terme, scalping), du risque assumé (« arrête avec tes
  1 % »), du levier, des TP, un écran en direct, un graphique par bot avec entrées, sorties et signaux, très peu
  d'items, et les labos gardés. Fait : `fleet.py` (choix par backtest, vente à découvert, objectif 2R, tout le capital
  × levier réduit avant liquidation, direct identique au backtest, remplacements), site refait (Direct, 3 équipes, page
  d'un bot, Labos), leçon « vendre à découvert », lanceurs 19/20, réglages `FLOTTE_*`. Dit franchement : le meilleur de
  milliers d'essais est souvent chanceux, le direct tranche ; un bot peut être liquidé. Démo vérifiée avec une
  plateforme fictive ; aucun choix réel encore : il se fait au premier clic sur son PC (les plateformes sont bloquées
  depuis le cloud).
- Nuit du 06 au 07/11/2026 : l'utilisateur veut « des centaines de bots, le maximum qu'on peut », en continu et sans
  bugs, sur les 30 à 60 cryptos qui bougent le plus (en veille quand ça ne bouge pas), toutes les stratégies (il a
  demandé de chercher les meilleures sur les sites et réseaux : ajoutées EMA 9/21, VWAP, stochastique, Keltner, ADX,
  Parabolic SAR, Ichimoku, écart à la moyenne, Heikin-Ashi ; la recherche dit que le momentum a le plus d'appui et
  que les frais tuent l'intraday), des agents qui expliquent gains et pertes avec des probabilités, des bots qui se
  retestent (« des labos en direct »), une liste de tous les bots et une page par crypto, des graphiques zoomables
  avec TP et SL précis, et le reste retiré (Mes essais, labos, tableau de bord, radar, trader : retirés du site ;
  `radar.py`, `moves.py`, `desk.py` supprimés). Il vise 3-4 % par jour : dit franchement que rien ne le garantit et
  que le levier amplifie aussi les pertes. Fait : `swarm.py` (essaim, 480 bots au plus par défaut), nouveau site,
  lanceur 19 « Mes bots en direct ». Bug trouvé et corrigé avant l'envoi : l'essaim relisait son résumé au lieu de son
  état au redémarrage (`essaim-etat.json` à part). Démo avec une plateforme fictive : 12 cryptos testées en 17 s
  (780 combinaisons chacune), 96 bots. Aucun résultat réel encore : tout se fera à l'ouverture du site sur son PC.
- 07/11/2026 : l'essaim tourne chez l'utilisateur, à peu près à l'équilibre (−0,2 % après quelques heures : normal,
  les frais d'abord et beaucoup de hasard). Il demande de garder les stratégies qui marchent le mieux chaque jour et de
  remonter le stop quand un trade gagne. Fait : stop suiveur et stop sécurisé (`stop_mode`, testés comme des façons de
  sortir : 1560 combinaisons par crypto ; parité direct/backtest et rattrapage vérifiés), classement en direct par
  stratégie (technique × unité, toutes cryptos) avec verdicts prouvée/recalée qui pilotent les re-tests, onglet
  Stratégies, leçon « le stop suiveur ». Dit franchement : un classement sur 24 h est surtout du hasard ; on ne
  « prouve » qu'avec 30 trades et un seuil durci.
- 11 et 12/11/2026 : l'utilisateur envoie un plan en 8 étapes (`PLAN-BOTS.md`) et ses règles permanentes, et demande en
  plus le maximum de bots, les derniers indicateurs et tous les horizons jusqu'à la seconde. Chiffres réels rapportés :
  environ 217 trades, 36 % de gagnants, −0,3 % au total, une soixantaine de bots sur 35 cryptos. Étape 0 (audit) faite
  sans toucher au code. Mesuré avec le vrai code sur des marchés tirés au hasard (première mesure, corrigée le 13/11 :
  voir l'entrée suivante) : le labo y déclare 3,6 % de
  combinaisons « gagnantes sur 3 périodes » (56 par crypto), crée 6,5 bots par crypto au backtest de +0,96 % par trade,
  qui font ensuite −0,20 % par trade avec 35 % de gagnants ; d'un test au suivant 1 bot sur 5 est remplacé, un bot vit
  6 h et 7 sur 10 s'arrêtent sans un trade. Donc un bot du labo, ou un bot en gain, ne prouve rien pour l'instant.
  Aussi : le test final sert à choisir (`swarm._eligible`, contrairement à ce que dit `fleet.judge`), les bots à terme
  tournent sur les prix du comptant, « bougie finie » dépend de l'horloge du PC. Proposée et en attente d'accord :
  l'étape 0 bis (test final mis de côté, trades de toutes les combinaisons gardés comme « bots à l'essai », bots plus
  arrêtés pour un changement de classement, bougie finie d'après la plateforme, point de référence enregistré au
  lancement). Les deux mesures se refont avec `audit/hasard.py` et `audit/rotation.py` (à relancer après chaque
  changement du labo ou du moteur : c'est le repère « aucun avantage »).
- 12 et 13/11/2026 : l'utilisateur approuve l'étape 0 bis (« Oui »). Faite, point de retour `bac35d5` : test final
  mis à part (`_eligible`), mesure à l'essai de toutes les combinaisons (`Harvest`, `essaim-essais.json`, verdicts par
  journées), bots gardés d'un test à l'autre (`apply_test`), bougie finie d'après la plateforme (`PlatformClock`,
  `CandleStore.closed`), point de référence (`reference.json`), site (encadré « La mesure à l'essai », onglet
  Stratégies à deux mesures), jusqu'à 20 bots par crypto. Erreur de MA mesure trouvée et dite : `audit/hasard.py`
  ajoutait des mèches au hasard aux bougies, ce qui avantageait les objectifs (ordres limites) ; refait avec des
  bougies tirées du seul chemin du prix. Chiffres justes, sur du pur hasard : avant, 43 combinaisons « gagnantes sur
  3 périodes » (2,7 %), 5,8 bots par crypto, backtest +0,89 % puis −0,17 % par trade, 82 % des bots gardés d'un test
  au suivant, 0,6 trade par bot en 48 h ; après, test final −0,10 %, direct −0,13 %, mesure à l'essai −0,14 % sur
  340 000 trades (le prix des frais : la mesure est honnête), 100 % des bots gardés, 4,3 trades par bot en 48 h.
  Reste à trancher (étape 3) : un bot sans position dont la crypto a quitté la liste depuis 6 h laisse sa place, et
  les bots en 1 h et 4 h mettront des semaines à faire 30 trades. Prochaine étape, à faire approuver : l'étape 1.
- 13/11/2026 : l'utilisateur approuve l'étape 1 (« passe à l'objectif 1 »), demande de corriger ce qui reste
  d'important de l'étape 0, et autorise les prix publics de Binance dans l'environnement cloud (carte approuvée). Fait,
  point de retour `3b234da` : sécurisation des gains (part encaissée à +1R et stop au prix d'entrée, réglage commun,
  chaque combinaison mesurée sans et avec), bots endormis au lieu d'arrêtés quand leur crypto quitte la liste, valeur
  d'une position frais de sortie compris, `audit/vrai.py`. PREMIERS CHIFFRES RÉELS (vraies bougies Binance, 14 jours,
  132 cryptos, 5,5 millions de trades à l'essai) : toutes les combinaisons réunies font −0,136 % par trade (de −0,152
  à −0,121), soit le prix des frais (−0,14 %) : aucun avantage avant frais ; 0 stratégie nettement gagnante sur 195,
  89 nettement perdantes ; la sécurisation fait +0,007 % par trade de mieux (de +0,001 à +0,013), dont la moitié vient
  des frais. Test du jour (59 cryptos) : test final des choix du labo −0,20 % par trade. Sur du pur hasard, mêmes
  ordres de grandeur (5,4 % de combinaisons éligibles contre 6,5 % en vrai). Trouvé et dit à l'utilisateur, à
  trancher : 15 des 66 paires assez échangées sont des actions en jetons (NVDAB, GOOGLB, SOXLB...) que le filtre du
  scanner ne reconnaît pas, plus quatre monnaies stables récentes ; et il s'échange environ 4 000 USDT par minute
  sur une crypto suivie, moins que la position d'un bot de scalping (M1). Inventaire « lecture du graphique » fait
  (order blocks, zones à combler, prises de liquidité, structure, chandeliers, divergences, Fibonacci : absents) ;
  l'utilisateur demande de tout ajouter (« des bots très très complets », plus l'actualité) : c'est l'étape 1 bis de
  `PLAN-BOTS.md` (dix familles, définitions fixées d'avance ; l'actualité reste des règles testées, étape 6). Il
  demande aussi d'économiser les tokens (sa limite d'utilisation a été atteinte par des vérifications en parallèle) :
  travailler seul, une relecture groupée au plus par étape.
- 13/11/2026 (suite) : étape 1 bis faite, point de retour `38b843b` : douze techniques de lecture du graphique
  (`patterns.py` : zone à combler et order block avec ou sans MM200, prise de liquidité, cassure de structure,
  avalement, marteau, bougie intérieure, divergence RSI, Fibonacci, double creux), 51 techniques et 1530 combinaisons
  par crypto, zones dessinées en rectangle sur le graphique, leçon 14 de l'École. Relecture de l'étape 1 : deux
  défauts corrigés (comparaison avec/sans sur des journées différentes après un changement de réglage ; case oui/non
  écrite « 0 » dans `.env` relue « oui » par la page) ; le relecteur du moteur n'a pas pu tourner (limite
  d'utilisation), le moteur a été relu à la main. CHIFFRES RÉELS (mêmes 14 jours, mêmes 132 cryptos, 6,66 millions
  de trades à l'essai) : les 12 lectures font −0,134 % par trade (de −0,153 à −0,115), les 39 autres −0,136 % : le
  prix des frais pour toutes ; 0 stratégie nettement gagnante sur 247, 123 nettement perdantes ; test final des
  choix du labo −0,181 %. Sur du pur hasard, chaque technique rend ses frais (−0,10 à −0,17 %). À faire approuver :
  l'étape 2 (gestion du risque). Toujours à trancher par l'utilisateur : exclure les actions en jetons et les
  monnaies stables récentes de l'univers. Pas fait, dit : épaule-tête-épaule, triangles, lignes de tendance ;
  l'actualité et le multi-unités restent pour l'étape 6.
- 13/11/2026 (soir) : l'utilisateur veut des bots « intelligents » : la lecture du graphique combinée à ce qui se
  passe en direct (qui achète, qui vend, volume, tendance du marché, actualité). Proposé et EN ATTENTE D'ACCORD :
  l'étape 1 ter de `PLAN-BOTS.md` (six conditions de contexte, chacune mesurée « avec ou sans » sur les mêmes trades,
  puis les combinaisons). Vérifié : les bougies Binance donnent le nombre de trades et le volume acheté au marché
  (champs 9 et 10 de `/api/v3/klines`, que `fetch_ohlcv` ne rend pas) ; `data.binance.vision/data/futures/um/daily/
  metrics/` donne toutes les 5 min l'intérêt ouvert et le nombre de comptes acheteurs pour un vendeur ; le carnet
  d'ordres n'a pas d'historique (étape 4). Il a montré un live TikTok d'un « bot d'arbitrage Polymarket » (lien en
  bio) : dit de ne pas s'en inspirer (chiffres affichés incohérents, gains invraisemblables, autre produit) ; seule la
  présentation est bonne à prendre, et elle est déjà prévue à l'étape 3.
- 13/11/2026 (nuit) : accord donné pour l'étape 1 ter (« vas-y »), avec la crainte de « cramer » ses tokens → la
  mesure d'abord, hors des bots (`audit/contexte.py`), point de retour `8308621`. RÉSULTAT (14 jours, 108 cryptos,
  5,36 millions de trades réels, tous à −0,141 %) : aucune des sept conditions (flux acheteurs/vendeurs, activité,
  unité au-dessus, Bitcoin, foule des contrats à terme, intérêt ouvert, les trois d'accord) ne sépare les bons
  trades des mauvais ; témoins conformes (pile ou face +0,002 %, triche +0,361 %). Deux pistes vues unité par unité
  (4 h dans le sens de la tendance du jour ; contre-pied du Bitcoin en 1 h et 4 h) revérifiées sur 60 jours puis 60
  jours encore avant : aucune ne tient. Donc RIEN n'est branché dans les bots ni le site. Fait dans le bot, approuvé :
  actions en jetons écartées (`scanner.tokenized_stock`, 105 paires) et cinq monnaies stables de plus. Pas encore
  mesuré : carnet d'ordres (étape 4, à enregistrer sur le PC), entrées par ordre limite (frais plus bas), horizons
  de plusieurs jours. Leçon de méthode : une piste « significative » sur une période se revérifie toujours sur une
  autre avant d'y croire. À faire approuver : la suite (étape 4 d'abord, pour lancer l'enregistrement, ou étape 2).
- 13/11/2026 (fin) : l'utilisateur demande s'il existe un moyen d'éviter les semaines d'enregistrement de l'étape 4.
  Vérifié : oui en grande partie. Les archives de Binance (`data.binance.vision/data/futures/um/daily/`) ont
  `bookDepth` (carnet résumé toutes les 30 s par bandes de ±0,2 à ±5 %, depuis mai 2026 au moins ; `1000PEPEUSDT`
  pour les petits prix) et `aggTrades`/`trades` (chaque transaction avec `is_buyer_maker`) ; pas de `bookTicker` ni
  de `liquidationSnapshot` (404). Les trades à l'essai des trois périodes sont déjà notés dans le cache
  (`contexte*/rows-*.npz`) : il suffit d'ajouter des conditions à `audit/contexte.py`. Aucun connecteur Claude ne
  donne cet historique en gros (et des données qui passent par la conversation coûtent des tokens, pas celles que la
  machine télécharge). Proposé, EN ATTENTE D'ACCORD : mesurer le carnet d'ordres sur l'historique avant de
  construire l'enregistreur.
- 13/11/2026 (soir ; noté par erreur « 14/11 » jusqu'ici) : l'utilisateur trouve que je le freine ; il croit au court terme (beaucoup de trades, levier) et demande
  des tests sur les trois horizons, avec des combinaisons liées au volume (« je te laisse faire »). Fait, hors des
  bots, point de retour `4517daa` : 15,8 millions de trades réels. 15 secondes (`audit/secondes.py`) : +0,003 % avant
  frais, −0,131 % après, 0 technique sur 98. 1 min à 4 h (`contexte.py matrice`, deux fois 14 jours et deux fois 60
  jours) : aucune combinaison technique × condition confirmée (en 1 min, aucune n'est même positive en moyenne ; les
  ventes à découvert en 1 h gagnent du 16/10 au 13/11 parce que 85 % des cryptos baissaient). Carnet d'ordres
  (`bookDepth`), pic de volume, flux net : aucun écart. 1 jour depuis 2020 (`audit/long.py`, 465 cryptos) : 0
  technique candidate ; le panier des 50 cryptos les plus échangées fait ×0,08 ; le portefeuille momentum 28 jours
  est une loterie (×1,15 à ×18,6, −90 % en route). CE QUI TIENT : Bitcoin et Ether gardés, et mieux encore la règle
  « au-dessus de sa moyenne 50, 100 et 200 jours, un tiers chacune » : Bitcoin ×15,5 (pire baisse −50 %) contre
  ×6,2 (−77 %) de 2018 à 2026, mieux que garder sur les trois périodes dont 2018-2019 jamais vue ; levier ×2 → ×37
  mais −80 %, ×5 → liquidé. Leçons : sur une période qui baisse, les ventes à découvert « gagnent » sans
  mérite (comparer au marché) ; une moyenne par semaine cache la casse d'un portefeuille très agité (toujours
  regarder l'argent composé et la pire baisse).
- 13/11/2026 (nuit) : l'utilisateur demande pourquoi le court terme « marche chez les autres » et vise 2 000 € par
  mois ; répondu franchement (on ne voit que les gagnants, 9 clients sur 10 perdent d'après l'AMF ; à +20 % par an,
  2 000 € par mois demandent environ 120 000 € placés). Il dit « on passe aux étapes d'après, tests en direct » →
  BOT DE TENDANCE FAIT, point de retour `95db6b4` : `tradingbot/trend.py`, onglet « Tendance » du site (« Prix » passe
  sous « Plus »), commandes `tendance` et `robustesse --tendance`, `audit/long.py` branché sur le même moteur. Avec
  le moteur du bot, sur les vraies bougies (05/03/2018 → 13/11/2026, frais compris) : Bitcoin ×15,8 (pire baisse
  −50 %) contre ×6,0 gardé (−77 %) ; Ether ×15,7 (−56 %) contre ×2,3 (−90 %) ; la règle gagne moins quand tout monte
  (2020 : +215 % contre +302 %) et perd bien moins quand tout baisse (2022 : −26 % contre −64 %) ; à 0,50 % par
  ordre, Bitcoin ×10,5. LA PORTE DIT NON : les six lignes (2 cryptos × 3 moyennes, 28 à 89 sorties) sont positives
  mais « positif, peut-être de la chance » : l'avantage tient à quelques grandes chutes évitées. Donc argent fictif
  seulement. Le 13/11 la règle est dehors sur les deux cryptos (prix sous les trois moyennes). Deux erreurs de ma
  part corrigées et dites : « 13 ordres par an » était faux (37 ordres par an, chacun sur un tiers du compte ; les
  frais étaient bien comptés) ; et le gain d'une sortie se compte en logarithme, pas en moyenne simple (leçon :
  toujours passer une nouvelle mesure sur un marché sans avantage avant de la croire). Pas fait, dit : alerte
  Telegram quand le bot de tendance change de position, leçon de l'École sur la tendance, lanceur Windows dédié.
  À faire approuver : la suite (étape 2 du plan, ou ces compléments).
- 13/11/2026 (fin de soirée) : l'utilisateur choisit l'option A (« la A ») : la règle de tendance sur d'autres
  marchés. Fait, hors des bots (`audit/marches.py`, protocole enregistré avant le calcul : `fe44aec`). RÉSULTAT sur
  huit marchés indépendants (Nasdaq 55 ans, Nikkei 77 ans, Brent 39 ans, cinq monnaies 55 ans ; frais du bot, ordre
  au lendemain) : la règle ne finit plus haut que « garder » sur AUCUN (Nasdaq ×139 contre ×246, Nikkei ×159 contre
  ×564) ; sa pire baisse est plus petite sur 4 (Nasdaq −50 % contre −78 %, Nikkei −38 % contre −82 %) ; la porte :
  0 ligne robuste sur 24, 21 « perd de l'argent » ; sorties réunies −0,20 % (de −0,47 à +0,06), témoin sans tendance
  −0,31 % (les frais). POURTANT les tendances sont réelles : la règle fait mieux sur le vrai marché que sur ses
  mélanges (réunis : hasard exclu ; net sur Nasdaq, Nikkei, yen). Ce qui mange l'avantage : le temps dehors pendant
  que ça monte et une trentaine d'ordres par an ; sans jour de retard 2 marchés sur 8, avec des frais de 0,03 %
  6 sur 8. Cryptos : sur les 9 ans de Binance le test du mélange n'est pas net (94,8 % et 96,0 %) ; sur Coinbase
  (Bitcoin depuis 2015, Ether depuis 2016) la règle bat « garder » (×383 contre ×254 ; ×743 contre ×297) et le test
  est net, mais c'est le même actif. CONCLUSION dite à l'utilisateur : la règle est une protection (chutes moins
  profondes), pas une façon de gagner plus ; elle n'a battu « garder » que là où les chutes sont énormes et
  fréquentes (les cryptos jusqu'ici). Argent fictif seulement. L'or n'a pas pu être testé (sources fermées aux
  robots) ; phrase ajoutée dans l'onglet « Tendance ». À faire approuver : la suite.
- 13/11/2026 (nuit) : l'utilisateur demande « tu vois du potentiel dans le fictif ? » (répondu : peu sur le court
  terme, une protection sur la tendance), puis « et si je te dis de prendre des risques », puis approuve un compte à
  risque et demande des « stop-loss suiveurs… pour éviter, si on est en gain, une chute. Je sais pas si ça marche
  comme ça ». Fait : comptes à risque du bot de tendance (définitions enregistrées avant mesure, `7763d02`), quatre
  comptes fictifs côte à côte sur l'onglet « Tendance ». MESURÉ sur les vraies bougies (05/03/2018 → 12/11/2026),
  Bitcoin puis Ether : normal ×15,8 (−50 %) et ×15,7 (−56 %) ; normal avec stop ×7,5 (−58 %) et ×7,9 (−68 %) ; à
  risque ×2 : ×41,8 (−80 %) et ×13,4 (−88 %) ; à risque avec stop ×9,9 (−84 %) et ×4,9 (−96 %) ; garder ×6,2
  (−77 %) et ×2,3 (−90 %). Donc : le stop suiveur n'a protégé dans aucun des quatre cas (moins de gain ET pire
  baisse plus profonde : il vend sur des baisses ordinaires et rachète plus haut ; recoupé par un calcul
  indépendant) ; le levier ×2 a multiplié le gain du Bitcoin, pas celui de l'Ether, avec des chutes de −80 % et
  plus ; à ×3 l'Ether est liquidé (19/05/2021), à ×5 les deux (Bitcoin 27/06/2019, Ether 12/03/2020). Dit
  franchement à l'utilisateur. Les comptes à risque sont là pour voir, pas pour être imités ; argent fictif.
