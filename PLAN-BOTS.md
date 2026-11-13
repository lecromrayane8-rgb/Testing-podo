# Plan des bots

Le plan de travail donné par l'utilisateur le 11/11/2026, étape par étape. À relire au début de chaque session et à
mettre à jour à la fin de chaque étape (journal en bas de page).

**Le but : trouver un avantage réel et mesurable, pas embellir les chiffres.**

## Règles permanentes

1. Argent fictif uniquement. Jamais le mode réel, jamais les clés du fichier `.env`, aucun secret affiché.
2. Une étape à la fois : plan court → l'utilisateur approuve → code sans redemander à chaque fichier → tests → compte
   rendu.
3. Avant chaque étape, un commit git pour pouvoir revenir en arrière.
4. Une seule logique de gestion des trades, partagée par les bots en direct et par le backtest. Jamais deux versions.
5. Backtest réaliste : signaux calculés sur des bougies clôturées uniquement, exécution au prix suivant, frais maker
   et taker, glissement (slippage), coût de financement (funding) des positions à levier.
6. Tout ce qui touche à l'argent (stop, objectif, taille de position, frais, liquidation) a des tests automatiques,
   lancés avant de dire qu'une étape est finie.
7. Interface : le style actuel, en français, avec une phrase d'explication sous chaque nouveau réglage.
8. Consigne ambiguë ou bug trouvé dans l'existant : le dire avant de continuer.

L'utilisateur est podologue et apprend : le pourquoi de chaque choix s'explique en français simple, en 5 lignes au
plus. Compte rendu de fin d'étape : ce qui a changé, comment le vérifier sur le site, ce qu'il faut surveiller, l'étape
suivante.

## Ce que l'utilisateur a ajouté en envoyant le plan

- Garder tout ce qui a été demandé avant (l'essaim, le site, les stops qui bougent, le classement en direct...).
- Le **maximum de bots possible** (le plan parlait d'une soixantaine) : tester le plus de positions possible, sur tout.
- Les derniers indicateurs qui pourraient annoncer une hausse ou une baisse.
- Tous les horizons : long terme, très court terme, scalping, jusqu'à la seconde.

Où ces demandes entrent dans le plan :

- Le maximum de bots : l'étape 0 bis, faite le 13/11 (toutes les combinaisons sont mesurées « à l'essai »).
- Les derniers indicateurs : le flux d'ordres (étapes 4 et 5) et le contexte de marché (étape 6). Une nouvelle
  technique sur bougies peut s'ajouter à la bibliothèque à tout moment : elle est alors testée partout, comme les autres.
- Jusqu'à la seconde : impossible avec des bougies d'une minute ; il faut le flux enregistré à l'étape 4.

Dit franchement : aucun indicateur ne prédit le prix de façon fiable, et plus l'horizon est court, plus les frais
pèsent (un aller-retour au marché coûte environ 0,14 % de la position, alors que le prix du Bitcoin bouge d'environ
0,01 % en une seconde). On peut tout tester en argent fictif ; ce sont les mesures qui trancheront.

---

## Étape 0 — Audit (faite le 12/11/2026)

Aucun code du bot n'a été modifié : seulement ce fichier, `CLAUDE.md` et les deux scripts de mesure du dossier
`audit/` (ils ne font pas partie du bot).

### Comment un bot travaille aujourd'hui, en 15 lignes

1. Toutes les 10 minutes, l'essaim prend les 60 cryptos en USDT qui ont le plus bougé sur 24 h (au moins 5 M$
   échangés par jour). Sous 3 % de mouvement, une crypto passe en veille : ses bots n'ouvrent plus de trade.
2. Le labo teste chaque crypto à son arrivée, puis toutes les 3 heures : 39 techniques × 2 sens (achat, vente à
   découvert) × 4 façons de sortir × 5 unités de temps (1 min à 4 h) = 1560 combinaisons.
3. L'historique du test : 2 jours en 1 min, 7 jours en 5 min, 20 jours en 15 min, 60 jours en 1 h, 240 jours en 4 h.
   Il est coupé en trois : étude (la première moitié), validation (30 %), test final (les derniers 20 %).
4. Une combinaison est gardée si elle gagne en moyenne, frais compris, sur chacun des trois morceaux, avec assez de
   trades (25 en 1 min, 8 en 4 h) et sans liquidation. Les 8 mieux classées de la crypto deviennent des bots.
5. Ouverture : le signal est calculé à la clôture d'une bougie ; l'ordre part à l'ouverture de la bougie suivante (en
   direct : au prix du moment, quelques secondes après la clôture).
6. Taille : tout le capital fictif du bot (1000 USDT) × le levier de son horizon (×5 scalping, ×3 court terme, ×1 long
   terme). Le levier est réduit si le stop est loin, pour que le stop passe toujours avant la liquidation.
7. Stop : entre 1,5 et 3 fois la taille moyenne d'une bougie (ATR) du prix d'entrée, selon la technique (3 fois pour
   la plupart). Objectif, quand la sortie en a un : 2 fois la distance du stop (2R).
8. Gestion : à chaque bougie, le stop est regardé d'abord (le pire cas), puis l'objectif. En direct, le prix est aussi
   regardé toutes les 5 secondes.
9. Stop suiveur : il suit le meilleur prix à la distance du départ. Stop sécurisé : il passe au prix d'entrée, frais
   compris, après un gain de 1R. Décidés à la clôture, ils comptent dès la bougie suivante et ne reculent jamais.
10. Fermeture : stop touché, objectif touché, signal de sortie de la règle (exécuté à l'ouverture suivante), durée
    maximale pour certaines techniques (20 à 48 bougies), ou liquidation.
11. Les frais sont comptés à un seul endroit, le moteur `fleet.Book` : 0,05 % à l'entrée (`_open`), 0,05 % à la sortie
    au marché ou 0,02 % sur un objectif, qui est un ordre limite (`_close`), 0,02 % de glissement sur chaque ordre au
    marché (`_fill`), et 0,01 % de financement par tranche de 8 heures de position (`_close`). Réglages :
    `execution.FUTURES`.
12. Résultat d'un trade : `net` = le gain après tous les frais, en % de la position ; `roi` = le même en % du capital du
    bot (donc multiplié par le levier).
13. Un bot s'arrête s'il est liquidé, s'il a perdu la moitié de son capital, s'il perd nettement après 20 trades (sa
    combinaison est alors mise de côté 24 h), ou si le dernier test de sa crypto ne le choisit plus.
14. Classement en direct : chaque trade fini compte pour sa stratégie (une technique dans une unité de temps, toutes
    cryptos réunies). Après 30 trades, elle peut être « prouvée » (prioritaire) ou « recalée » (ses bots s'arrêtent).
15. Le backtest et le direct passent par le même moteur, dans le même ordre : des tests automatiques vérifient qu'un
    bot en direct prend exactement les trades de son backtest, y compris après une coupure.

### La mesure qui résume l'audit : le labo sur un marché tiré au hasard

On a fabriqué des cryptos dont le prix avance au hasard (aucune tendance, aucune mémoire : aucun avantage possible),
puis on a fait travailler le vrai code : le labo choisit ses bots, et on regarde ce qu'ils font ensuite.

| Le labo d'avant l'étape 0 bis | 12 cryptos au hasard | Les 12 plus « agitées » sur 24 h parmi 80 |
|---|---|---|
| Combinaisons testées par crypto | 1560 | 1560 |
| Déclarées « gagnantes sur 3 périodes » | 43 (2,7 %) | 55 (3,5 %) |
| Bots créés par crypto | 5,8 | 6,3 |
| Leur backtest, par trade | +0,89 % | +1,08 % |
| Ensuite, en « direct » simulé | 2078 trades | 1968 trades |
| Trades gagnants | 38 % | 37 % |
| Résultat par trade, frais compris | −0,17 % (± 0,11) | −0,03 % (± 0,11) |
| Résultat par trade, en % du capital du bot | −0,48 % | −0,08 % |
| Bots qui finissent quand même positifs | 26 % | 47 % |

Ce que ça veut dire : même sur du pur hasard, le labo créait environ 6 bots par crypto, leur backtest était beau
(près de +1 % par trade), et ils ne gagnaient rien ensuite (entre zéro et le prix des frais, 0,14 % par trade). **Un
bot créé par le labo, ou un bot en gain, ne prouve donc rien.** Les chiffres réels de l'utilisateur (36 % de trades
gagnants, total un peu négatif) ressemblent à ceux du hasard ; 217 trades ne suffisent pas à dire s'il y a un petit
avantage ou aucun (avec si peu de trades, la marge d'erreur est de l'ordre de ± 0,3 % par trade : plus grande que
l'avantage qu'on cherche).

Correction du 13/11/2026 : la première version de cette mesure (12/11) ajoutait aux bougies des mèches tirées au
hasard. C'était une erreur de la mesure, pas du bot : ces mèches n'appartenaient pas au chemin du prix, donc un
objectif (ordre limite) y gagnait un peu et un stop y perdait un peu. Elle annonçait 56 « gagnantes » (3,6 %), 6,5
bots par crypto, puis −0,20 % par trade. Refaite avec des bougies tirées du seul chemin du prix (un prix toutes les
10 secondes), elle donne le tableau ci-dessus : mêmes conclusions, chiffres un peu plus bas.

Deuxième mesure, même méthode : on refait le test d'une crypto toutes les 3 heures pendant 48 heures, comme l'essaim.

| Sur 12 cryptos au hasard, en 48 heures (labo d'avant l'étape 0 bis) | |
|---|---|
| Bots gardés d'un test au suivant | 82 % (1 sur 5 est remplacé toutes les 3 heures) |
| Bots créés par crypto, pour 8 places | 24 |
| Trades par bot pendant sa vie | 0,6 en moyenne |
| Bots sans un seul trade | 69 % |
| Bots ayant atteint 30 trades | aucun |

Ce que ça veut dire : le classement d'une crypto bouge à chaque test, donc ses bots tournaient sans arrêt (un bot
arrêté par un test avait vécu 6 heures, médiane mesurée le 12/11). Presque aucun ne vivait assez longtemps pour être
jugé.

Pour refaire ces mesures (quelques minutes chacune, sans connexion à une plateforme) : `python audit/hasard.py 80 12
hasard.json` et `python audit/rotation.py rotation.json 101 102 103 104 105 106 107 108 109 110 111 112`. À relancer
après chaque changement du labo ou du moteur : c'est le repère « aucun avantage ». Une mesure honnête doit y afficher
le prix des frais (environ −0,14 % par trade), ni plus, ni moins.

### Ce qui peut fausser les résultats, par gravité

**Grave : ça change la conclusion**

- **G1. Le labo prend la chance pour un avantage.** 1560 essais par crypto, et « gagner sur 3 périodes » est un
  critère que le hasard passe 2,7 % du temps (`swarm._eligible`) : voir le tableau. Rien ne tient compte du nombre
  d'essais. *Depuis l'étape 0 bis : le choix reste un pari, mais on le mesure honnêtement (mesure à l'essai, test final).*
- **G2. Le « test final » sert à choisir.** `fleet.judge` annonce un test final « jamais regardé pour choisir », mais
  `swarm._eligible` exige qu'il soit gagnant. Il ne reste donc aucune donnée jamais vue : le backtest affiché sur la page
  d'un bot est toujours trop beau, et « comparer sur le test final » (étapes 1 et 6) ne voudrait rien dire.
  *Corrigé à l'étape 0 bis.*
- **G3. Trop peu d'historique en très court terme.** 2 jours en 1 min, 7 jours en 5 min (`swarm.TEST_DAYS`) : une seule
  humeur de marché.
- **G4. Les bots changent trop vite pour être jugés.** Toutes les 3 heures, un bot qui n'est plus parmi les 8 mieux
  classés de sa crypto s'arrête (`Swarm.apply_test`), même s'il gagne encore sur son historique. Mesuré : un bot vit
  6 heures et 7 sur 10 s'arrêtent sans un seul trade (tableau ci-dessus). Chez l'utilisateur : 217 trades pour une
  soixantaine de bots en place. Aucun n'atteindra les 30 trades de l'étape 3. *Corrigé à l'étape 0 bis pour les tests ;
  reste l'arrêt d'un bot dont la crypto a quitté la liste depuis 6 heures (à décider à l'étape 3).*
- **G5. Des contrats à terme simulés avec les prix du comptant.** La liste des cryptos et les bougies viennent du
  marché au comptant (`scanner.tradable`, `data.make_exchange`), alors que le moteur compte un levier, des ventes à
  découvert et un financement. Certaines cryptos très agitées n'ont pas de contrat à terme : leur vente à découvert
  serait impossible en vrai. Le financement réel et la liquidité ne sont pas ceux du modèle.

**Moyen : ça embellit ou ça brouille**

- **M1. Exécution trop optimiste sur les petites cryptos.** Glissement fixe de 0,02 % pour toutes, stops compris, alors
  qu'un bot peut passer 5000 USDT d'un coup sur une crypto qui n'échange que 3500 USDT par minute. Et un stop est compté
  rempli à son prix, même quand le prix a sauté plus loin (c'est justement là que les stops glissent).
- **M2. Financement fixe.** 0,01 % par 8 heures, compté comme un coût dans les deux sens. Sur une crypto qui s'envole,
  le vrai taux peut être dix fois plus haut ; l'effet est faible en scalping, réel sur les bots en 4 h.
- **M3. L'heure du PC décide qu'une bougie est finie** (`CandleStore.closed`, `Swarm.cycle`). Si l'horloge de
  l'ordinateur avance de plus de 2 secondes, un bot peut décider sur une bougie pas terminée : le direct s'écarte alors
  du backtest (surtout en 1 min). *Corrigé à l'étape 0 bis.*
- **M4. Des verdicts « prouvée » et « recalée » trop faciles.** Les trades sont comptés comme indépendants, alors que
  plusieurs bots tradent la même crypto et que les cryptos montent et baissent ensemble : 40 ventes à découvert gagnantes
  pendant une seule chute du marché comptent pour 40 preuves. Et « recalée » est définitif (la stratégie ne trade plus).
  *Corrigé à l'étape 0 bis : les verdicts comparent les journées entre elles, et un verdict peut être levé.*
- **M5. Des cryptos choisies sur leur mouvement des dernières 24 h**, alors que le backtest contient ce même mouvement.
  Mesuré : l'effet existe (4,4 % de fausses gagnantes au lieu de 3,6 %) mais il est petit.
- **M6. Un risque très inégal d'un trade à l'autre.** Tout le capital × le levier à chaque trade : dans la simulation,
  la moitié des trades perdants coûtent plus de 3 % du capital du bot, un sur dix plus de 6,6 %, le pire 14 %. Quelques
  gros trades font le résultat d'un bot (c'est l'objet de l'étape 2).

**Faible : à corriger au passage**

- **F1.** Les trades rattrapés après une coupure (PC éteint) sont rejoués sur les bougies, puis comptés dans le
  classement comme des trades vus en direct.
- **F2.** Les probabilités des « agents » sont calculées sur le backtest qui a choisi le bot : elles sont trop belles.
- **F3.** Un bot arrêté parce que sa stratégie est recalée affiche « le dernier test ne le garde plus » : texte trompeur.
  *Corrigé à l'étape 0 bis.*
- **F4.** La valeur d'une position ouverte ne compte pas encore les frais de sortie (environ 0,07 % de la position).
- **F5.** Liquidation simplifiée : même marge de maintenance (0,5 %) pour toutes les cryptos, toute la mise perdue.
  C'est prudent, mais les petites cryptos ont en vrai des règles plus dures et des leviers plus bas.
- **F6.** Le site met en avant le pourcentage de trades gagnants, qui ne dit rien seul (avec un objectif à 2R, on peut
  gagner avec 36 % de trades gagnants). Ce qui compte : le résultat moyen par trade (étape 3).
- **F7.** Le total en % est rapporté au capital de tous les bots, dont la plupart attendent : il paraît petit.

**Vérifié et correct**

- Les signaux n'utilisent que des bougies clôturées : un test automatique compare, pour les 39 techniques et dans les
  deux sens, les signaux de la fenêtre du direct à ceux de tout l'historique (un regard vers le futur le ferait échouer).
- L'ordre part à l'ouverture de la bougie suivante, jamais sur la bougie du signal.
- Frais taker et maker, glissement et financement sont tous comptés, à un seul endroit.
- Une seule logique pour le backtest et le direct (`fleet.Book`), vérifiée par des tests de parité, y compris après un
  redémarrage.
- Dans une même bougie, le stop passe avant l'objectif (hypothèse prudente) ; un objectif n'est compté que si le prix
  l'a dépassé.
- Le total affiché compte aussi les bots arrêtés : pas de « on ne montre que les survivants ».
- Supports, résistances et Ichimoku n'utilisent que le passé (testé).

### Point de référence (avant toute modification du plan)

| | Valeur |
|---|---|
| Date | 11/11/2026 (chiffres donnés avec le plan) ; code en place : `7148d95`, dernière version Windows publiée |
| Trades terminés | environ 217 |
| Trades gagnants | 36 % |
| Résultat total | −0,3 % |
| Bots | une soixantaine, sur 35 cryptos, de 1 min à 4 h |
| Repère « aucun avantage » (marché au hasard, même code) | 35 % de trades gagnants, −0,20 % par trade |

Ces chiffres sont ceux rapportés par l'utilisateur : le détail par stratégie est sur son PC (`data\bots\essaim.json` et
`essaim-etat.json`), illisible depuis une session cloud. Depuis l'étape 0 bis, le bot en garde une copie au premier
lancement de la nouvelle version (`data\bots\reference.json`), et l'écran Direct l'affiche.

---

## Étape 0 bis — Réparer la mesure et tout tester (faite le 13/11/2026)

Approuvée par l'utilisateur le 12/11. Pourquoi avant l'étape 1 : les étapes 1 et 6 se terminent par « comparer sur le
test final », et l'étape 3 par « juger après 30 trades ». Le test final servait à choisir (G2) et presque aucun bot
n'atteignait 30 trades (G4).

### Ce qui a changé

1. **Le test final ne sert plus à choisir.** Le labo choisit sur l'étude et la validation (les premiers 80 % de
   l'historique). Le test final (les derniers 20 %) ne fait que mesurer : le site affiche « Test final des choix du
   labo ». Un trade à cheval sur les deux ne compte ni d'un côté ni de l'autre.
2. **Tout est mesuré, en argent fictif : les bots à l'essai.** À chaque test d'une crypto, les trades de toutes les
   combinaisons sont comptés, pas seulement ceux des bots choisis : jusqu'à 60 × 1560 = 93 600 bots à l'essai. Un trade
   compte une seule fois, et seulement s'il a été ouvert pendant que la crypto bougeait, comme un vrai bot. C'est
   cette mesure qui juge les stratégies : sa fourchette compare les journées entre elles (mille trades le même jour
   ne valent pas mille preuves), et il faut 7 jours avant tout verdict. Le maximum de bots en direct passe de 800 à
   1600 (jusqu'à 20 par crypto dans Réglages).
3. **Un bot garde sa place d'un test à l'autre.** Le test rafraîchit sa fiche et remplit les places libres. Un bot ne
   s'arrête plus que par ses garde-fous (liquidation, moitié du capital, pertes nettes après 20 trades), si sa
   stratégie est recalée, ou si sa crypto a quitté la liste depuis 6 heures.
4. **Une bougie n'est « terminée » que lorsque la plateforme a ouvert la suivante**, ou que l'heure de la plateforme
   (demandée toutes les 10 minutes) a dépassé sa fin. Jamais d'après la seule horloge du PC.
5. **Le point de référence est enregistré tout seul** au premier lancement : `data\bots\reference.json`, jamais
   réécrit, et affiché sur l'écran Direct.

### Les mesures de contrôle, avant et après (marchés tirés au hasard : rien à gagner)

| 12 cryptos au hasard | Avant | Après |
|---|---|---|
| Combinaisons qui peuvent devenir un bot | 43 (2,7 %) | 86 (5,5 %) |
| Leur backtest (étude et validation), par trade | +0,89 % | +0,81 % |
| Test final des combinaisons choisies, jamais regardé pour choisir | n'existait pas | −0,10 % (707 trades) |
| Les bots choisis, ensuite en « direct » simulé | −0,17 % (± 0,11) | −0,13 % (± 0,09) |
| Mesure à l'essai : toutes les combinaisons, 2 jours | n'existait pas | −0,14 % (340 035 trades) |
| Bots gardés d'un test au suivant | 82 % | 100 % |
| Bots créés par crypto en 48 heures, pour 8 places | 24 | 8 |
| Trades par bot en 48 heures | 0,6 | 4,3 |
| Bots sans un seul trade en 48 heures | 69 % | 30 % |

Comment le lire. Sur un marché où il n'y a rien à gagner, une mesure honnête doit afficher le prix des frais, environ
−0,14 % par trade. C'est ce que disent maintenant le test final (−0,10 %), le direct (−0,13 %) et la mesure à
l'essai (−0,14 %, sur 340 000 trades). Seul le backtest qui sert à choisir reste beau (+0,81 %) : c'est normal, on
choisit ce qui a gagné. Avant, rien sur le site ne permettait de voir cet écart.

Ce que ça ne change pas : le labo choisit toujours des combinaisons qui ont eu de la chance (86 sur 1560 passent sur du
pur hasard). La différence, c'est qu'on le voit, et qu'un verdict « prouvée » demande maintenant de gagner sur
plusieurs journées, toutes cryptos réunies, sans choix préalable.

### Ce qui reste des problèmes de l'audit

- G3 (peu d'historique en très court terme), G5 (contrats à terme simulés sur les prix du comptant), M1 (glissement
  fixe), M2 (financement fixe), M5, M6 (étape 2), F1, F2, F4 à F7 : inchangés.
- Trouvé pendant l'étape : un bot sans position dont la crypto a quitté la liste depuis 6 heures laisse sa place. C'est
  une autre source de rotation, voulue à l'origine. Dans une simulation de 7,6 jours (petite liste fictive de 8
  cryptos sur 16, qui change souvent), 155 arrêts sur 158 venaient de cette règle, et ces bots avaient fait 1 trade
  (médiane). À trancher à l'étape 3 : garder ces bots endormis, avec leur historique, jusqu'au retour de leur crypto ?
- Les bots en 1 h et 4 h font peu de trades (1,3 et 0,2 en 48 heures) : ils n'atteindront 30 trades qu'après des
  semaines ou des mois. Pour eux, c'est la mesure par stratégie, toutes cryptos réunies, qui parlera la première.
- À surveiller à partir du 7e jour : si aucune stratégie n'a d'avantage, elles seront recalées une à une et leurs
  bots s'arrêteront. L'écran Direct le dit alors (« Aucun bot en ce moment : les stratégies perdent à l'essai »). Ce
  serait une information, pas une panne : la mesure à l'essai continue, et des bots renaissent dès qu'une stratégie ne
  perd plus nettement.
- Nouveau garde-fou automatique (`tests/test_fleet.py`) : sur un marché fabriqué où il n'y a rien à gagner, le moteur
  doit rendre exactement les frais (−0,138 % par trade mesuré pour 0,14 % de frais). Tout changement du moteur
  (étapes 1 et 2) qui embellirait l'exécution ou oublierait des frais le ferait échouer.

---

## Étape 0, suite — Ce qui restait d'important (fait le 13/11/2026)

Demandé par l'utilisateur le 13/11 avec l'accord pour l'étape 1 (« modifie s'il y a des trucs encore à modifier sur
l'objectif 0 »). Trois corrections, choisies parce qu'elles changent ce qu'on peut conclure :

1. **Un bot dont la crypto quitte la liste s'endort au lieu d'être arrêté** (le reste de G4). Avant, un bot sans
   position était arrêté 6 heures après la sortie de sa crypto de la liste : dans la simulation, 155 arrêts sur 158
   venaient de là, après 1 trade. Maintenant il garde son compte et son historique, ne demande plus rien à la
   plateforme, ne prend la place de personne, et reprend à son retour (sans rejouer son sommeil ni entrer sur un vieux
   signal). Arrêt définitif après 30 jours sans retour. Sans cela, aucun bot n'atteindrait les 30 trades de l'étape 3.
2. **La valeur d'une position ouverte compte les frais de sa sortie** (F4) : une position ne paraît plus un peu plus
   belle qu'elle n'est (environ 0,07 % de la position, multiplié par le levier).
3. **Un trade rattrapé après une coupure compte pour son vrai jour** dans le classement en direct (F1) : il ne gonfle
   plus « aujourd'hui ».

Laissé pour plus tard, et pourquoi : G3 (plus d'historique en 1 et 5 min : triplerait le calcul, à décider quand les
mesures tourneront), G5, M1 et M2 (vrais contrats à terme, glissement et financement réels : il faut les données de
l'étape 4), M6 (étape 2), F2, F5 à F7 (étape 3).

Trouvé en route, à trancher par l'utilisateur : voir « Ce que montrent les vraies données » plus bas.

---

## Étape 1 — Sécurisation des gains (faite le 13/11/2026)

La demande :

- Break-even : quand le prix a avancé de 1R (R = distance entre l'entrée et le stop initial), le stop passe au prix
  d'entrée plus les frais aller-retour.
- Objectif partiel : au même moment, fermer 50 % de la position. Le reste suit la règle de sortie du bot.
- Seuil et pourcentage réglables dans Réglages, et désactivables.
- Graphique : zone du stop, zone de l'objectif, seuil de sécurisation en pointillés, puis le nouveau stop. Journal :
  chaque sécurisation.

Terminé quand : le labo compare avec et sans sécurisation sur le test final, et montre le résultat.

### Ce qui a changé

1. **Le moteur** (`fleet.Book`, le même pour le direct et le backtest). Au seuil (+1R par défaut), un ordre limite
   encaisse la part réglée (50 %) ; à la clôture de la bougie, le stop du reste passe au prix d'entrée, frais d'un
   aller-retour compris, et compte dès la bougie suivante. Le reste suit la règle de sortie du bot. Une position
   reste UN trade : son résultat réunit les deux sorties (sinon on compterait deux trades, et « 30 trades » ne
   voudrait plus rien dire).
2. **La prudence d'abord.** Dans une bougie qui touche à la fois le stop et le seuil, on ne sait pas lequel est venu
   en premier : le moteur compte le pire (le stop sur toute la position), comme il le fait déjà pour l'objectif.
3. **Un réglage commun à tous les bots**, pas une sortie de plus : `FLOTTE_SECURISATION` (oui/non),
   `FLOTTE_SECURISATION_SEUIL` (en R), `FLOTTE_SECURISATION_PART` (en %). L'ancienne quatrième sortie « objectif 2R +
   stop sécurisé » disparaît de la grille (c'était la moitié de ce réglage) : 39 techniques × 2 sens × 3 sorties ×
   5 unités = 1170 combinaisons. Les bots créés avant gardent leur sortie.
4. **Le labo calcule tout deux fois**, sans et avec, sur les mêmes bougies, même si tu désactives la sécurisation
   pour tes bots. Les deux sont comptés dans la mesure à l'essai et comparés sur le test final. L'écart est jugé sur
   les mêmes journées (à l'essai) ou les mêmes cryptos (test final) : c'est ce qui permet de voir une petite
   différence au milieu de journées très différentes les unes des autres.
5. **Le site** : onglet Stratégies, tableau « Sécurisation des gains : avec ou sans ? » ; Réglages (trois lignes, une
   phrase d'explication chacune) ; page d'un bot : zone du risque, zone visée, seuil en pointillés, « nouveau stop »,
   un rond à chaque sécurisation, et la ligne « Sécurisation des gains » de la position ; écran Direct : une ligne par
   sécurisation dans « Ce qui vient de se passer » (et dans le journal `data\bot.log`).

### Relecture indépendante de l'étape 1 (13/11/2026) : deux défauts trouvés et corrigés

Un relecteur indépendant a relu l'essaim et le site (celui du moteur n'a pas pu tourner : limite d'utilisation
atteinte). Deux défauts réels, chacun reproduit puis corrigé avec son test :

- **Le tableau « avec ou sans » pouvait comparer des journées différentes.** Quand on change le seuil ou la part (ou au
  premier lancement de cette version sur un dossier d'avant), la mesure « avec » repart de zéro mais « sans » garde ses
  30 jours : l'écart affiché comparait alors deux périodes, donc deux marchés (exemple reproduit : « +1,2 %, mieux
  avec » affiché pour un écart vrai de +0,01 %). Corrigé : la comparaison repart du lendemain du changement, sur des
  journées mesurées en entier par les deux, et le site dit depuis quand il compare.
- **Une case « oui / non » écrite à la main dans `.env` avec `0`, `false` ou `off`** était lue « non » par les bots
  mais affichée « oui » par la page Réglages, et le premier enregistrement réactivait la sécurisation sans le dire.
  Corrigé : la page montre ce que les bots appliquent, et n'écrit rien si rien ne change.

### Ce qu'il faut savoir avant de lire les chiffres

- **Sécuriser ne crée pas d'avantage.** Sur un marché fabriqué où il n'y a rien à gagner, le moteur rend toujours
  exactement les frais : −0,137 % par trade sans, −0,135 % avec (test automatique, 78 000 trades). Avant frais, les
  deux valent zéro.
- **Le petit mieux de « avec » sur ce marché vient des frais** : la part encaissée sort par un ordre limite (0,02 %)
  au lieu d'une sortie au marché (0,07 % avec le glissement). Soit environ +0,003 % par trade, sans rapport avec un
  avantage.
- **Ce que la sécurisation change vraiment, c'est la forme des résultats** : plus de trades gagnants (31,5 % au lieu
  de 27,9 % sur ce marché), des résultats plus réguliers (dispersion 0,295 % au lieu de 0,326 %), des gros gains
  moins gros. Sur un vrai marché, elle peut donc aider les techniques qui rendent souvent leurs gains, et pénaliser
  celles qui vivent de quelques grands mouvements. C'est la mesure qui le dit, technique par technique.

### Ce que montrent les vraies données (13/11/2026)

Depuis le 13/11, cette session reçoit les prix publics de Binance (accord de l'utilisateur) : le vrai code du labo
tourne donc sur de vraies bougies, sans attendre des jours sur le PC (`audit/vrai.py`). Argent fictif, aucune clé.

**Le test du jour** (ce que ferait le bot en ce moment : 59 cryptos assez agitées, 1170 combinaisons chacune).
Le test final est la partie de l'historique qui ne sert jamais à choisir.

| Sur le test final, par trade, frais compris | Sans | Avec sécurisation | Écart |
|---|---|---|---|
| Toutes les combinaisons (646 000 trades) | −0,196 % | −0,177 % | +0,019 % (de +0,005 à +0,034) : mieux avec |
| Celles qui peuvent devenir un bot (36 000 trades) | −0,398 % | −0,336 % | +0,062 % (de +0,005 à +0,119) : mieux avec |
| Les choix du labo, avec (3 182 trades) | | −0,200 % (de −0,35 à −0,05) | |

Comment le lire :

- **Rien ne gagne.** Le repère « aucun avantage » est −0,14 % par trade (le prix des frais). Toutes les combinaisons
  réunies font −0,18 % : à peu près les frais. Les combinaisons que le labo peut choisir font pire (−0,34 %) : avoir
  gagné sur l'étude et la validation n'annonce pas un gain ensuite, plutôt l'inverse sur cette période.
- **La sécurisation aide un peu** sur ces vraies bougies : entre +0,02 % et +0,06 % par trade, plus que le simple effet
  des frais (+0,003 %). Elle ne rend pas les stratégies gagnantes.
- Sur de vraies cryptos, 6,5 % des combinaisons « peuvent devenir un bot » ; sur des marchés tirés au hasard, 5,4 %.
  Presque la même chose : le tri du labo, seul, ne distingue pas un vrai marché du hasard.
- Limite : ce test final couvre les mêmes derniers jours pour toutes les cryptos. La fourchette compare les cryptos
  entre elles, pas des périodes différentes. La mesure sur 14 jours (ci-dessous) compare les journées.

**La mesure à l'essai rejouée sur 14 jours** (du 30/10 au 13/11/2026 : les 132 cryptos qui ont « bougé » au sens
du bot, toutes les combinaisons, seulement les trades ouverts pendant que la crypto bougeait : 5,5 millions de trades).
La fourchette compare les 15 journées entre elles.

| À l'essai, par trade, frais compris | Résultat | Fourchette à 95 % |
|---|---|---|
| Toutes les combinaisons, avec sécurisation | −0,136 % | de −0,152 % à −0,121 % |
| Toutes les combinaisons, sans | −0,144 % | |
| Écart avec − sans | +0,007 % | de +0,001 % à +0,013 % : mieux avec, de très peu |
| En 1 min / 5 min / 15 min | −0,134 % / −0,147 % / −0,140 % | |
| En 1 h / 4 h | −0,129 % / −0,142 % | très larges (peu de trades) |
| À l'achat / à la vente à découvert | −0,171 % / −0,104 % | le marché a baissé sur la période |
| Stratégies nettement gagnantes (sur 195) | 0 | |
| Stratégies nettement perdantes (« recalées ») | 89 | |

Ce que ça veut dire :

- **L'ensemble des 39 techniques ne gagne rien avant frais.** −0,136 % par trade, c'est le prix des frais (−0,14 %), à
  la marge d'erreur près. Sur 5,5 millions de trades, ce n'est plus une question de chance.
- **Aucune stratégie n'est prouvée**, et près d'une sur deux serait recalée au bout d'une semaine. C'est ce que le
  site affichera sur le PC à partir du 7e jour : ce ne sera pas une panne.
- **La sécurisation fait mieux, de très peu** : +0,007 % par trade, dont environ la moitié vient seulement des frais
  (une sortie en ordre limite coûte moins cher). Elle rend les résultats plus réguliers ; elle ne crée pas d'avantage.
- Les meilleures lignes sont toutes en 4 h, avec quelques centaines de trades et des fourchettes de plusieurs
  pourcents de chaque côté : du bruit, pas une piste.

La suite logique : ce n'est pas en réglant mieux ces techniques qu'on trouvera un avantage. Il faut d'autres
informations (la lecture du graphique de l'étape 1 bis, le flux d'ordres des étapes 4 et 5, le contexte de l'étape 6),
mesurées de la même façon, et accepter que la réponse puisse rester « rien ».

**Trouvé en route : un quart des « cryptos » suivies sont des actions en jetons.** Sur les 66 paires assez échangées
de Binance ce jour-là, 15 sont des actions ou des fonds américains (Nvidia, Google, MicroStrategy, et des fonds à
levier ×3 comme SOXL), cotés en USDT. Le filtre du bot ne les reconnaît pas (il écarte les jetons à levier dont le nom
finit par UP ou DOWN, pas ceux-là), ni quatre monnaies stables récentes (U, RLUSD, XUSD, RWUSD). Leurs résultats sont
moins mauvais que ceux des vraies cryptos (−0,08 % contre −0,23 % par trade), ce qui est suspect : ces jetons
s'échangent peu, et le moteur leur prête la même facilité d'exécution qu'au Bitcoin. Autre constat : sur la plupart
des cryptos suivies, il s'échange environ 4 000 USDT par minute, moins que la position d'un seul bot de scalping
(1000 USDT × 5) : l'exécution simulée est trop belle sur les petites cryptos (point M1 de l'audit). À décider par
l'utilisateur : écarter les actions en jetons (recommandé), et à l'étape 2 limiter la taille d'une position à une
part du volume réellement échangé.

## Étape 1 bis — La lecture du graphique (faite le 13/11/2026)

La demande : des bots « très très complets », qui ne regardent pas seulement des indicateurs mais lisent le graphique
comme un trader (zones à combler, order blocks, sommets et creux, structure, chandeliers...), et qui tiennent compte de
l'actualité. « Le plus de paramètres possible, le plus de tests, voir les stratégies qui en ressortent. »

### Ce qui a changé

Douze techniques de plus (51 au lieu de 39), donc 1530 combinaisons par crypto au lieu de 1170. Chacune a UNE
définition, celle des manuels, fixée d'avance et jamais ajustée sur nos données (`tradingbot/patterns.py`) :

| Technique | Ce que le bot attend pour acheter (à l'envers pour vendre à découvert) |
|---|---|
| Zone à combler (FVG), avec ou sans MM200 | Trois bougies laissent un trou ; le prix y revient puis clôture au-dessus |
| Order block, avec ou sans MM200 | Le prix revient sur la dernière bougie baissière d'avant une envolée, puis clôture au-dessus |
| Prise de liquidité | Une mèche passe sous le dernier creux marquant, la bougie clôture au-dessus, en hausse |
| Cassure de structure | Le prix clôture au-dessus du dernier sommet marquant ; sortie sous le dernier creux marquant |
| Avalement | Une bougie verte recouvre la rouge d'avant, au plus bas des 10 dernières bougies |
| Marteau | Longue mèche basse (2 fois le corps au moins), au plus bas des 10 dernières bougies |
| Bougie intérieure | Une bougie contenue dans la précédente, puis une clôture au-dessus de celle-ci |
| Divergence RSI | Le prix fait un creux plus bas, le RSI un creux plus haut |
| Retracement de Fibonacci | Après une jambe de hausse, le prix en reperd entre 50 % et 61,8 % et clôture en hausse |
| Double creux | Deux creux au même prix, puis une clôture au-dessus du sommet qui les sépare |

Un sommet ou un creux « marquant » est le plus haut ou le plus bas de 5 bougies de chaque côté ; le bot ne le connaît
donc que 5 bougies plus tard, comme un trader. Une zone attend le prix 30 bougies, ne sert qu'une fois, et est
abandonnée si le prix clôture de l'autre côté. Stop à 2 fois la taille moyenne d'une bougie, 48 bougies au plus.

Sur le site : la page d'un bot de ces techniques montre ce qu'il regarde (la zone attendue en rectangle bleu, le dernier
sommet et le dernier creux marquants en lignes), sa règle en mots dans les deux sens, sa fiche (ce que dit vraiment la
recherche : presque rien, ces lectures viennent des traders) ; l'École a une quatorzième leçon, « Lire le graphique
comme un trader ».

### Les garanties, toutes testées (`tests/test_patterns.py`)

- **Chaque définition** sur un petit graphique dessiné à la main, signal attendu calculé à la main.
- **Aucun regard vers le futur** : les signaux d'une bougie ne changent pas quand on ajoute les bougies suivantes.
- **Le direct voit ce que voit le backtest** : sur sa fenêtre de dernières bougies, mêmes signaux que sur tout
  l'historique, pour chaque technique et dans les deux sens.
- **La vente à découvert lit la même figure à l'envers.**
- **Rien à gagner avant frais sur un marché sans avantage** : sur un prix tiré au hasard, les 12 lectures font
  +0,008 % par trade avant frais (41 000 trades ; le reste vient du marché fabriqué, où un stop est servi à son prix
  exact) et −0,128 % après frais.

### Ce que disent les mesures (13/11/2026)

**Sur du pur hasard** (`audit/hasard.py`, 24 cryptos fabriquées) : chacune des 51 techniques rend le prix des frais,
entre −0,10 % et −0,17 % par trade ; aucune ne fait mieux que le coût le plus bas possible. Le labo y trouve 5,5 % de
combinaisons « gagnantes sur l'étude et la validation » (comme avant) : c'est le niveau de la chance.

**Sur de vraies bougies Binance** (`audit/vrai.py essai`, les mêmes 14 jours et les mêmes 132 cryptos que pour
l'étape 1, pour comparer) :

| Mesure à l'essai | Trades | Par trade | Fourchette à 95 % | Gagnants |
|---|---|---|---|---|
| Toutes les combinaisons | 6 655 119 | −0,136 % | de −0,152 % à −0,120 % | 33 % |
| Les 39 techniques d'avant | 5 502 784 | −0,136 % | de −0,152 % à −0,121 % | 32 % |
| **Les 12 lectures du graphique** | 1 152 335 | **−0,134 %** | de −0,153 % à −0,115 % | 38 % |

| Lecture du graphique (toutes unités réunies) | Trades | Par trade | Fourchette à 95 % | Gagnants |
|---|---|---|---|---|
| Marteau | 58 186 | −0,119 % | de −0,143 % à −0,095 % | 39 % |
| Order block | 88 752 | −0,128 % | de −0,148 % à −0,107 % | 37 % |
| Prise de liquidité | 125 870 | −0,130 % | de −0,152 % à −0,109 % | 39 % |
| Bougie intérieure | 98 258 | −0,132 % | de −0,164 % à −0,101 % | 40 % |
| Zone à combler (FVG) | 193 389 | −0,133 % | de −0,151 % à −0,116 % | 39 % |
| Order block + MM200 | 49 142 | −0,134 % | de −0,176 % à −0,092 % | 36 % |
| Avalement | 122 389 | −0,134 % | de −0,150 % à −0,118 % | 38 % |
| Divergence RSI | 40 192 | −0,135 % | de −0,159 % à −0,110 % | 39 % |
| Retracement de Fibonacci | 82 249 | −0,136 % | de −0,157 % à −0,114 % | 36 % |
| Double creux | 46 974 | −0,136 % | de −0,174 % à −0,098 % | 40 % |
| Zone à combler (FVG) + MM200 | 127 449 | −0,139 % | de −0,166 % à −0,113 % | 38 % |
| Cassure de structure | 119 485 | −0,145 % | de −0,195 % à −0,096 % | 39 % |

- **Les lectures du graphique ne font pas mieux que les indicateurs : le prix des frais (−0,14 %), ni plus ni moins.**
  Elles gagnent plus souvent (38 % des trades contre 32 %) mais de plus petits gains : la moyenne est la même.
- Sur 255 stratégies (une technique dans une unité de temps), 247 ont au moins 200 trades : **aucune n'est nettement
  gagnante, 123 sont nettement perdantes** (dont 34 des 57 stratégies de lecture). Aucune « prouvée ».
- En bougies de 4 h, « Order block » (+1,15 %) et « Zone à combler + MM200 » (+1,08 %) sont dans les dix premières,
  « Divergence RSI » (−2,32 %) et « Prise de liquidité » (−1,39 %) dans les dix dernières : 250 à 600 trades sur 14
  jours, des fourchettes de plusieurs pour cent. C'est du bruit, pas un classement.
- Le test final des choix du labo : −0,181 % par trade (8 776 trades, de −0,262 % à −0,100 %), contre −0,160 % avec 39
  techniques : pas de différence qui compte. 7,7 % des combinaisons « peuvent devenir un bot », comme avant (7,9 %).
- La sécurisation des gains fait toujours +0,008 % par trade de mieux (de +0,001 % à +0,014 %).

Dit franchement : c'était le résultat le plus probable. Ces lectures sont connues de tous les traders, donc déjà dans
les prix ; et avec 0,14 % de frais par aller-retour, il faut un avantage net que le graphique seul ne donne pas ici.
Les ajouter n'était pas inutile : on sait maintenant, mesure à l'appui, qu'elles ne suffisent pas, et la mesure à
l'essai continuera de les suivre sur ton PC (14 jours ne jugent pas les unités de 1 h et 4 h).

### Ce qui n'est pas fait, et pourquoi

- **Épaule-tête-épaule, triangles, drapeaux, lignes de tendance** : pas de définition sans ambiguïté ; à écrire si tu y
  tiens, avec la même méthode.
- **Plusieurs unités de temps à la fois, tendance du Bitcoin, sessions** : c'est l'étape 6 (filtres de contexte).
- **L'actualité** : pas d'IA qui trade sur les titres (principe du projet : des règles testées). Ce qui se teste : une
  pause autour des grandes annonces économiques et l'humeur du marché comme filtre. Étape 6 aussi.
- **Plus de réglages par technique** (autres tailles de sommets, autres seuils) : chaque variante de plus est une
  chance de plus de trouver un faux gagnant. À ajouter seulement pour une famille que la mesure aura distinguée.

### Ce qu'il faut surveiller

- Onglet Stratégies, mesure « À l'essai » : les nouvelles techniques y apparaissent une demi-heure à une heure après
  le lancement ; un verdict demande 7 jours et 30 trades.
- Le test de chaque crypto prend environ un tiers de temps en plus (51 techniques au lieu de 39).
- Trouvé en route, à trancher : parmi les paires assez échangées de Binance, 15 sont des actions en jetons (NVDAB,
  GOOGLB, SOXLB...) et 4 des monnaies stables récentes ; le filtre du bot ne les reconnaît pas.

## Étape 1 ter — Le contexte autour du signal (la mesure : faite le 13/11/2026 ; rien à brancher)

La demande, le 13/11 au soir : des bots « intelligents », pas de la technique pure. Lire le graphique ET regarder ce
qui se passe en direct : qui achète, qui vend, le volume, la tendance du marché, l'actualité. Accord donné (« vas-y »),
avec une inquiétude sur les tokens. D'où la méthode : **mesurer d'abord, avec un outil à part, sans toucher aux
bots** ; ne brancher une condition dans les bots et le site que si la mesure montre qu'elle sert à quelque chose.

### Ce qui a été fait

- **L'outil `audit/contexte.py`.** Pour chacun des trades à l'essai (toutes les combinaisons, vraies bougies Binance),
  il note ce qu'on savait à la clôture de la bougie du signal, donc avant l'entrée, puis compare les trades pris
  « condition vraie » aux autres, jour par jour. Sept conditions, écrites d'avance, un seul seuil chacune.
- **Les données**, toutes gratuites et avec historique : le volume acheté « au marché » et le nombre de trades de
  chaque bougie ; toutes les 5 minutes, le nombre de comptes acheteurs pour un vendeur et l'argent engagé sur les
  contrats à terme (104 des 108 cryptos en ont un).
- **Deux témoins**, pour savoir si la mesure sait voir quelque chose : un tirage à pile ou face (l'écart doit être
  nul : +0,002 %, et sur 40 tirages 3 fausses alertes pour 2 attendues) et une « triche » (le sens de la bougie
  d'entrée, connu seulement après coup : +0,361 %, et ces trades-là gagnent après frais). La mesure voit un avantage
  quand il y en a un.
- **Dans les bots (approuvé le 13/11)** : les actions en jetons de Binance ne sont plus suivies (105 paires : NVDAB,
  GOOGLB, TSLAB... ; reconnues à leur nom en « B » et au groupe d'échange auquel elles sont fermées, aucune crypto
  touchée), ni cinq monnaies stables récentes (U, RLUSD, XUSD, RWUSD, USDS).

### Le résultat : 14 jours, 108 cryptos, 5 355 096 trades réels (tous : −0,141 % par trade)

| Condition (dans le sens du trade) | Quand elle est vraie | Quand elle est fausse | Écart | Fourchette (durcie : 7 questions) |
|---|---|---|---|---|
| Qui pousse : acheteurs ou vendeurs « au marché » | −0,145 % | −0,137 % | −0,007 % | de −0,029 % à +0,014 % |
| L'activité est au-dessus de sa moyenne | −0,142 % | −0,141 % | 0,000 % | de −0,023 % à +0,022 % |
| L'unité au-dessus va dans le même sens | −0,140 % | −0,143 % | +0,004 % | de −0,045 % à +0,052 % |
| Le Bitcoin va dans le même sens | −0,162 % | −0,120 % | −0,041 % | de −0,093 % à +0,010 % |
| La foule des traders n'est pas déjà de ce côté | −0,134 % | −0,149 % | +0,015 % | de −0,030 % à +0,059 % |
| L'argent engagé sur les contrats augmente | −0,144 % | −0,139 % | −0,005 % | de −0,017 % à +0,007 % |
| Flux, unité au-dessus et Bitcoin d'accord | −0,161 % | −0,137 % | −0,023 % | de −0,072 % à +0,025 % |

**Aucune condition ne sépare les bons trades des mauvais.** Que le contexte soit « d'accord » ou non, un trade fait
le prix des frais. Même résultat pour les lectures du graphique et pour les indicateurs, à l'achat et à la vente.
Le seul écart qui frôle le seuil (le Bitcoin : les trades pris dans son sens font 0,04 % de moins bien) est trois
fois plus petit que les frais : même vrai, il ne rendrait aucun bot gagnant.

### Deux pistes sont apparues ; vérifiées sur d'autres périodes, aucune ne tient

En regardant unité par unité (35 comparaisons : il en sort toujours une ou deux par chance), deux écarts dépassaient.
Chacun a été revérifié sur une période que la piste n'avait pas vue, la question fixée avant de regarder :

| Piste (bots en bougies de 1 h et 4 h) | Là où elle est apparue | Vérification | Verdict |
|---|---|---|---|
| En 4 h, trader dans le sens de la tendance du jour | 14 jours : +3,15 % (de +1,28 à +5,02) | 60 jours d'avant : +0,18 % (de −0,77 à +1,13) ; 60 jours encore avant : −0,29 % (de −0,94 à +0,35) | Du bruit |
| Trader à contre-pied du Bitcoin | 60 jours du 31/08 au 30/10 : 0,54 % de mieux (de 0,15 à 0,93) | 60 jours du 02/07 au 31/08 : 0,09 % de moins bien (de −0,56 à +0,39) | Pas confirmée |

C'est l'intérêt de vérifier ailleurs : sur une seule période, la seconde piste avait l'air « prouvée ».

### Ce que ça veut dire, et la décision

- **Rien n'est branché dans les bots ni sur le site** : aucune de ces conditions ne changerait leurs résultats. La
  partie coûteuse de l'étape (moteur, parité direct/backtest, site) n'a pas été faite, et n'a pas à l'être.
- Indicateurs, lecture du graphique, flux, positions des traders, tendances : tout ce qui se lit dans des données
  publiques à la bougie donne le même résultat, **le prix des frais (0,14 % par aller-retour)**. Ce n'est pas un
  défaut du bot : ces informations sont vues par tout le monde, donc déjà dans les prix.
- Ce qui n'a pas encore été mesuré : le **carnet d'ordres** et les liquidations (étape 4 : pas d'historique gratuit,
  il faut enregistrer en direct sur ton PC pendant des semaines) ; des **frais plus bas** (entrer par un ordre limite
  fait passer l'aller-retour de 0,14 % à 0,04-0,09 %, mais un ordre limite n'est servi que quand le prix vient à
  lui : à mesurer en direct, pas sur des bougies) ; des **horizons de plusieurs jours** (le seul effet appuyé par
  la recherche, le momentum : le labo portefeuille du bot existe déjà) ; le calendrier des annonces (étape 6).

## Le grand test sur trois horizons (13/11/2026)

La demande : « fais en sorte que les tests soient surtout long terme, moyen terme et très très court terme, avec des
techniques et des combinaisons de 1 ou 2 indicateurs liés au volume… je te laisse faire ». Avec l'idée qu'une
stratégie de court terme peut payer par le nombre de trades et le levier.

La méthode, la même partout : **chercher large sur une période, ne croire que ce qui se confirme sur une autre**. Tout
est dans `audit/` (`contexte.py matrice`, `long.py`, `secondes.py`) ; rien n'a été changé dans les bots. 15,8 millions
de trades réels en argent fictif, frais compris.

### Le résultat, horizon par horizon

| Horizon | Ce qui a été testé | Ce qui en sort |
|---|---|---|
| 15 secondes | 51 techniques, achat et vente, sur les 10 cryptos les plus échangées, 14 jours (1,97 million de trades) | Avant frais : +0,003 % par trade. Après frais : −0,131 %. Aucune des 98 techniques jugées ne gagne. Une bougie de 15 secondes bouge de 0,03 % ; un aller-retour coûte 0,14 %. |
| 1 minute | Chaque technique seule, puis avec chacune des 11 conditions (volume, flux, carnet d'ordres…), deux périodes de 14 jours (12,2 millions de trades pour 1 min à 4 h) | 2 325 combinaisons jugées : aucune n'est même positive en moyenne. |
| 5 minutes | Idem | 2 312 combinaisons : 112 positives en moyenne, aucune nettement (le hasard seul en donnerait 58). |
| 15 minutes | Idem | 2 167 combinaisons : 32 nettement positives (54 par hasard), aucune prouvée. |
| 1 heure | Idem, plus deux périodes de 60 jours (1,06 million de trades) | Du 16/10 au 13/11 : 94 nettement positives (30 par hasard), presque toutes des ventes à découvert, pendant que 85 % des cryptos baissaient : c'est le marché, pas la technique. Sur les 120 jours d'avant : 1 (45 par hasard). Aucune prouvée. |
| 4 heures | Idem | Aucune prouvée. La famille qui revient le plus en tête (acheter une forte baisse : « écart à la moyenne », « Bollinger rebond ») fait −0,37 %, +0,38 % et +0,77 % par trade selon la période : pas stable. |
| 1 jour | 51 techniques sur 465 cryptos depuis 2020, retirées de la cote comprises (629 240 trades) | Aucune candidate sur 101. L'ensemble fait moins bien que de garder le panier du marché (−0,68 % par trade contre lui sur 2020-2023). |

« Prouvée » : fourchette durcie par le nombre de combinaisons essayées, et confirmée sur l'autre période. Aucune
combinaison ne passe, à aucun horizon.

### Ce que tu voulais voir combiné : volume, flux, carnet d'ordres

Écart entre les trades pris quand la condition est vraie et les autres (tous à −0,13 % ou −0,14 % en moyenne) :

| Condition | Du 16/10 au 30/10 (6,8 millions de trades) | Du 30/10 au 13/11 (5,4 millions) |
|---|---|---|
| Pic de volume (2 fois la moyenne) | −0,004 % (de −0,014 à +0,006) | −0,004 % (de −0,037 à +0,029) |
| Flux net du côté du trade (55 % du volume) | +0,010 % (de −0,016 à +0,036) | 0,000 % (de −0,028 à +0,028) |
| Le carnet d'ordres penche du côté du trade, à 1 % du prix | −0,028 % (de −0,087 à +0,031) | −0,019 % (de −0,075 à +0,038) |
| Le carnet penche du côté du trade, à 0,2 % du prix | +0,005 % (de −0,021 à +0,032) | −0,005 % (de −0,029 à +0,019) |

Le carnet d'ordres vient des archives de Binance (une photo toutes les 30 secondes) : il n'a donc pas fallu attendre
des semaines. Résultat : qu'il penche du bon côté ou non, un trade fait la même chose.

### Pourquoi « beaucoup de trades et du levier » ne suffit pas ici

Le levier et le nombre de trades multiplient ce qu'un trade rapporte en moyenne. En bougies de 15 secondes, un trade
rapporte +0,003 % avant frais et coûte 0,134 % : il faudrait des frais quarante fois plus bas. Plus de trades, c'est
plus de frais ; plus de levier, c'est la même perte en plus gros.

### Le long terme : ce qui ressort vraiment

En argent composé (ce que devient 1 placé au début), avec la pire baisse en route entre parenthèses :

- **Les cryptos « les plus échangées du moment » sont un très mauvais terrain à tenir.** Le panier des 50 plus
  échangées, à parts égales, revu chaque jour : ×0,08 depuis 2020 (−99 %). C'est le terrain des bots actuels.
- **Garder les 3 cryptos qui montent le plus depuis 28 jours** (l'ancien labo le classait « à surveiller ») : de ×1,15
  à ×18,6 selon le jour où l'on commence, avec −90 % à −97 % en route. Une loterie. Sur 7 jours : la ruine. Le
  contraire (garder celles qui baissent le plus) : la ruine aussi.
- **Le Bitcoin et l'Ether, simplement gardés, ont fait mieux que tout le reste.** Et une règle toute simple a fait
  mieux encore, avec des baisses moins profondes : ne les tenir que quand leur clôture est au-dessus de leur moyenne
  des 50, 100 et 200 derniers jours (un tiers par moyenne, pour ne pas choisir un réglage après coup). Une décision
  par jour, environ 37 ordres par an, chacun sur un tiers du compte (j'avais écrit « 13 ordres par an » : c'était le
  nombre de fois où le compte entier change de main, pas le nombre d'ordres ; les frais étaient bien comptés) :

| | 2018-03 à 2019 | 2020 à 2023 | 2024 à 2026-11 | Tout |
|---|---|---|---|---|
| Bitcoin gardé | ×0,63 (−70 %) | ×6,14 (−77 %) | ×1,62 (−53 %) | ×6,24 (−77 %) |
| Bitcoin, règle des trois moyennes | ×1,23 (−37 %) | ×7,35 (−50 %) | ×1,71 (−30 %) | ×15,49 (−50 %) |
| Ether gardé | ×0,15 (−90 %) | ×17,99 (−79 %) | ×0,86 (−68 %) | ×2,38 (−90 %) |
| Ether, règle des trois moyennes | ×0,92 (−44 %) | ×9,67 (−55 %) | ×1,80 (−37 %) | ×16,10 (−56 %) |

  Pour le Bitcoin : mieux que « garder » sur les trois périodes, dont 2018-2019 que la règle n'avait jamais vue, et
  une pire baisse plus petite à chaque fois. Pour l'Ether : pire baisse plus petite à chaque fois, moins de gain
  pendant la grande hausse de 2020-2023. Sur d'autres cryptos anciennes (XRP, LTC), c'est mitigé : la règle protège
  des chutes, elle ne fabrique pas une hausse qui n'existe pas.
- **Le levier sur cette règle (Bitcoin, 2018-2026)** : ×1 → ×15,5 (−50 %) ; ×2 → ×37 (−80 %) ; ×3 → ×22 (−93 %) ;
  ×5 → liquidé en route. Le levier aide un peu une règle qui marche, puis il la détruit.

Dit franchement : c'est le passé d'un seul actif, et −50 % en route reste très dur à vivre. Rien ne garantit la suite.
Mais c'est la seule chose, de tout ce qui a été mesuré depuis le début, qui tient sur plusieurs périodes séparées.

## Le bot de tendance (13/11/2026, fait)

Accord du 13/11 (« on passe aux étapes d'après, pour faire des tests en direct »). Point de retour : `95db6b4`.
Les bots actuels restent comme laboratoire : ils mesurent honnêtement, ils ne sont pas un revenu.

### Ce qui a été fait

1. **Le moteur** (`tradingbot/trend.py`) : la règle des trois moyennes sur le Bitcoin et l'Ether, en bougies d'un
   jour, au comptant. Décidée à la clôture, exécutée à l'ouverture du jour suivant, 0,10 % de frais et 0,05 % de
   glissement par ordre. Jamais de levier ni de vente à découvert. Une seule logique : le compte fictif du site est
   le rejeu de la règle depuis sa date de création ; chaque jour ajoute une bougie, donc le direct est le backtest
   qui continue.
2. **Les tests de l'argent** (`tests/test_trend.py`) : la règle, l'ordre au lendemain, les frais au centime, les
   parts d'un tiers, jamais d'emprunt, aucun ordre passé ne change quand on ajoute des jours, la bougie du jour ne
   décide rien, et le garde-fou « marché sans avantage ».
3. **Le site** : onglet « Tendance » (dedans ou dehors, depuis quand, le prix à dépasser ce soir, le compte fictif
   contre « acheter et garder », le graphique, l'histoire année par année, le test de robustesse). « Prix » passe
   sous « Plus ».
4. **La porte** : `python main.py robustesse --tendance`, avec les mêmes seuils que `robustesse`.
5. **L'outil de mesure** (`audit/long.py`) rejoue la règle avec le moteur du bot : il n'en existe qu'une version.

### Les chiffres du moteur du bot (vraies bougies, du 05/03/2018 au 13/11/2026, frais compris)

| | La règle | Acheter et garder |
|---|---|---|
| Bitcoin | ×15,8 (pire baisse −50 %) | ×6,0 (pire baisse −77 %) |
| Ether | ×15,7 (pire baisse −56 %) | ×2,3 (pire baisse −90 %) |

Bitcoin, année par année (la règle / garder) : 2018 −35 % / −68 % · 2019 +91 % / +94 % · 2020 +215 % / +302 % ·
2021 +50 % / +60 % · 2022 −26 % / −64 % · 2023 +105 % / +156 % · 2024 +74 % / +121 % · 2025 −3 % / −6 % · 2026
+6 % / −21 %. La règle gagne moins quand tout monte, et perd beaucoup moins quand tout baisse. Avec des frais de
0,50 % par ordre au lieu de 0,15 % : Bitcoin ×10,5 au lieu de ×15,8.

### Le test de robustesse dit non

Ce qui est jugé : chaque sortie du marché, comme un pari (vendre pour racheter moins cher), contre « garder ». Six
lignes (2 cryptos × 3 moyennes), de 28 à 89 sorties chacune. Toutes sont positives en moyenne (+0,1 % à +4,6 % par
sortie), mais une sortie sur quatre seulement est gagnante et toutes les fourchettes contiennent zéro : « positif,
peut-être de la chance ». L'avantage vient de quelques grandes chutes évitées (2018, 2022, 2026). Conclusion : la
règle est la meilleure chose mesurée jusqu'ici, et elle n'est pas prouvée. Argent fictif seulement.

### Ce que j'ai corrigé en route

- « 13 ordres par an » était faux : 37 ordres par an (voir plus haut).
- Compter le gain moyen d'une sortie en moyenne simple fait croire à un avantage qui n'existe pas (+1,1 % par sortie
  sur un marché tiré au hasard). Le test compte les sorties comme le compte les enchaîne : sur le même marché au
  hasard, il rend exactement les frais (−0,30 %).
- Le grand test était daté du 14/11 : c'était le 13/11.

### À surveiller

- Le 13/11/2026, la règle est dehors sur les deux cryptos (prix sous les trois moyennes) : le compte fictif attend,
  il ne se passera rien tant que le prix ne repasse pas au-dessus d'une moyenne. C'est la règle, pas une panne.
- Le compte fictif suppose que l'ordre passe à l'ouverture du jour (1 h du matin en hiver), même site fermé.
- Pas fait : alerte Telegram quand le bot change de position, leçon de l'École sur la tendance, lanceur Windows.

## La règle de tendance sur d'autres marchés (13/11/2026, fait)

Accord du 13/11 (« la A »). La question : la réussite de la règle sur le Bitcoin et l'Ether tient-elle à la règle, ou
à la chance ? Tout est dans `audit/marches.py` ; rien n'est changé dans les bots.

**La méthode.** La liste des marchés, la façon de compter et ce qui vaut preuve ont été écrits et enregistrés dans git
(`fe44aec`) avant le premier calcul, pour ne rien choisir après coup. Huit marchés indépendants, en prix d'un jour de
la banque centrale américaine : actions américaines (Nasdaq, 55 ans), actions japonaises (Nikkei, 77 ans), pétrole
(Brent, 39 ans) et cinq monnaies face au dollar (55 ans). La règle est celle du bot, inchangée, avec ses frais ;
l'ordre passe à la clôture du lendemain, ce qui est plus dur que la réalité. L'or manque : aucune source officielle
ne répond aux robots sans clé (il faudrait un fichier téléchargé à la main).

### Ce qui en sort

| Marché | La règle | Garder | Test du mélange |
|---|---|---|---|
| Actions américaines (Nasdaq, 1971-2026) | ×139 (pire baisse −50 %) | ×246 (−78 %) | mieux que 99,9 % des mélanges : net |
| Actions japonaises (Nikkei, 1950-2026) | ×159 (−38 %) | ×564 (−82 %) | 100 % : net |
| Pétrole (Brent, 1988-2026) | ×3,0 (−69 %) | ×6,6 (−94 %) | 78 % : non |
| Yen | ×1,74 (−60 %) | ×2,08 (−54 %) | 99,7 % : net |
| Livre sterling | ×0,53 (−66 %) | ×0,54 (−60 %) | 97,6 % : pas net |
| Franc suisse | ×1,69 (−61 %) | ×4,87 (−50 %) | 95,5 % : pas net |
| Dollar canadien | ×0,29 (−72 %) | ×0,71 (−41 %) | 39,5 % : non |
| Dollar australien | ×0,42 (−67 %) | ×0,59 (−68 %) | 82 % : non |

Le test du mélange : les mêmes journées tirées dans le désordre, 1 000 fois. Mêmes hausses, mêmes baisses, même prix
d'arrivée, mais plus aucune tendance. Si la règle exploite de vraies tendances, elle doit finir plus haut sur le vrai
marché que sur presque tous ses mélanges.

1. **La règle ne finit plus haut que « garder » sur aucun des huit marchés.** Sa pire baisse est plus petite sur
   quatre (surtout les actions : deux fois moins profonde), plus grande sur quatre (les monnaies).
2. **Les tendances existent pourtant.** Les huit tests du mélange réunis excluent le hasard, et trois marchés sont nets
   à eux seuls. Sur le Nasdaq mélangé, la règle finit à ×10 ; sur le vrai, à ×139. Elle capte donc quelque chose de réel.
3. **Ce qui mange l'avantage : le temps passé dehors pendant que le marché monte, et les frais** (une trentaine
   d'ordres par an). Hors protocole, pour comprendre : sans le jour de retard, la règle passe devant « garder » sur 2
   marchés sur 8 ; avec en plus des frais de professionnel (0,03 % par ordre), sur 6 sur 8.
4. **La porte du projet** : 0 ligne « robuste » sur 24, 21 « perd de l'argent ». Toutes les sorties réunies font
   −0,20 % contre « garder » (de −0,47 à +0,06) ; sur des marchés sans tendance, la même mesure rend les frais
   (−0,31 % en moyenne sur 20 essais, pour −0,30 % attendus).
5. **Les cryptos.** Sur les 9 ans de bougies du bot (Binance), le test du mélange n'est pas net : mieux que 94,8 %
   des mélanges pour le Bitcoin, 96,0 % pour l'Ether. Sur les prix de Coinbase, plus longs (Bitcoin depuis 2015, Ether
   depuis 2016), la règle bat « garder » (×383 contre ×254, pire baisse −63 % contre −84 % ; ×743 contre ×297,
   −61 % contre −94 %) et le test est net (99,7 % et 99,9 %). C'est le même actif vu d'ailleurs : pas une preuve
   de plus. L'or en jetons (6 ans, pour information) : ×1,70 contre ×2,23.

### Ce que ça veut dire

- **La règle est une protection, pas une façon de gagner plus.** Elle coupe les très grandes chutes ; en échange, elle
  rapporte moins quand le marché monte longtemps.
- **Elle n'a battu « garder » que sur les cryptos**, parce que leurs chutes ont été énormes (−77 % à −94 %) et
  fréquentes. Si les cryptos deviennent un marché plus calme, il faut s'attendre au résultat des actions : des chutes
  moins dures, et moins de gain que « garder ».
- **Les frais décident, encore une fois.** Le bot de tendance reste en argent fictif.

## Étape 2 — Gestion du risque

- Taille de position calculée pour risquer un % fixe du capital du bot par trade (1 % par défaut), dans la limite des
  leviers actuels.
- Perte maximale par jour pour l'ensemble des bots : au-delà, aucune nouvelle position jusqu'au lendemain.
- Nombre maximal de positions ouvertes en même temps.

Terminé quand : ces trois limites sont réglables, testées et visibles sur la page Direct.

Existant : `risk.position_size` et `risk.RiskGuard` font déjà ces calculs pour le bot au comptant ; à réutiliser dans
le moteur des bots plutôt qu'à réécrire.

## Étape 3 — Classement fiable

- Aucun bot jugé avant 30 trades terminés.
- Pour chaque bot : espérance par trade en R, taux de gain, gain moyen et perte moyenne, profit factor, drawdown
  maximal.
- Classement par un score prudent : l'espérance moins sa marge d'erreur.
- Des bots témoins qui entrent au hasard avec les mêmes stops et objectifs, pour mesurer la part de chance.

Terminé quand : la page Direct trie par score prudent et affiche l'écart avec les témoins.

À prévoir d'après l'audit (M4) : compter les jours et les cryptos différents, pas seulement les trades, pour qu'une
seule chute du marché ne « prouve » pas une stratégie.

## Étape 4 — Enregistrement du flux d'ordres

- Via les WebSocket de la plateforme, pour les 10 cryptos les plus liquides : chaque transaction avec son côté
  (acheteur ou vendeur agressif), le carnet d'ordres (20 niveaux, une photo par seconde), les liquidations, le taux de
  financement, l'open interest.
- Stockage local compact, limité à 5 Go avec rotation. Un voyant sur le site indique si l'enregistrement tourne.
- Si ces données ne sont pas accessibles sur Binance depuis la France, proposer une autre plateforme déjà gérée par le
  site.

Terminé quand : 24 h de données sont enregistrées sans coupure.

À prévoir d'après l'audit (G5) : c'est le moment de passer aux vrais contrats à terme (liste des cryptos, prix,
financement réel) au lieu du comptant.

À savoir (vérifié le 13/11/2026) : une grande partie de ces données existe déjà, gratuitement et avec des mois
d'historique, dans les archives publiques de Binance (`data.binance.vision`, lisibles depuis le cloud), pour les
contrats à terme : le carnet d'ordres résumé toutes les 30 secondes (`bookDepth` : ce qui attend à ±0,2 %, 1 %, 2 %,
3 %, 4 % et 5 % du prix, 2 880 photos par jour, au moins depuis mai 2026) et chaque transaction avec son côté
(`aggTrades`, `trades` ; aussi pour le comptant). Absents des archives : les liquidations et le carnet fin (meilleur
prix à chaque instant, 20 niveaux par seconde), qui ne s'obtiennent qu'en enregistrant en direct ou chez un vendeur de
données payant. On peut donc mesurer « le carnet penche-t-il du bon côté ? » sur l'historique, avec la méthode de
l'étape 1 ter, AVANT de construire l'enregistreur : proposé, en attente d'accord.

## Étape 5 — Signaux de flux d'ordres

- Delta cumulé, déséquilibre du carnet, murs d'ordres, pics de liquidations, financement extrême, ajoutés comme
  techniques dans le labo.
- À lancer après 2 à 3 semaines d'enregistrement.

Terminé quand : le labo les teste sur 3 périodes comme les autres techniques.

C'est ici que se jouent les bots « à la seconde » : ils ont besoin du flux enregistré à l'étape 4.

## Étape 6 — Filtres de contexte

- Régime de marché (tendance ou range), tendance du BTC, horaires de liquidité, volatilité minimale et maximale, pause
  autour des grosses annonces économiques.

Terminé quand : chaque filtre est testé, et seuls restent ceux qui améliorent le test final sur la majorité des
cryptos.

## Étape 7 — Combinaisons

- Stratégies combinant une seule technique par famille : tendance, excès, volatilité (ATR pour le stop et l'objectif),
  volume ou flux d'ordres. 2 à 4 paramètres maximum.

Terminé quand : les meilleures combinaisons tournent en fictif avec leur score prudent.

## Étape 8 — Critères avant tout passage au testnet

Afficher pour chaque bot s'il remplit ces conditions : 100 trades fictifs au moins, score prudent positif après frais,
drawdown maximal sous 15 %, résultats stables sur 4 semaines. Rien ne change de mode automatiquement.

---

## Journal des étapes

| Date | Étape | État | Commit de départ |
|---|---|---|---|
| 12/11/2026 | 0 — Audit | Faite : résumé, problèmes par gravité, point de référence | `7148d95` |
| 13/11/2026 | 0 bis — Réparer la mesure et tout tester | Faite : test final mis à part, bots à l'essai, places gardées, heure de la plateforme, point de référence | `bac35d5` |
| 13/11/2026 | 0, suite — bots endormis, valeur d'une position, jour d'un trade rattrapé | Faite | `3b234da` |
| 13/11/2026 | 1 — Sécurisation des gains | Faite : moteur, réglages, labo avec et sans, site, mesures sur de vraies bougies | `3b234da` |
| 13/11/2026 | 1 bis — La lecture du graphique | Faite : 12 techniques (51 en tout), garanties testées, mesures sur du hasard et sur de vraies bougies ; deux défauts de l'étape 1 corrigés après relecture | `38b843b` |
| 13/11/2026 | 1 ter — Le contexte autour du signal | Mesure faite (sept conditions, 5,36 millions de trades, deux pistes revérifiées sur d'autres périodes) : aucun avantage, rien à brancher ; actions en jetons écartées | `8308621` |
| 13/11/2026 | Le grand test sur trois horizons (15 secondes à 1 jour, techniques seules et combinées au volume, au flux et au carnet d'ordres) | Fait : 15,8 millions de trades, aucune combinaison confirmée ; seule tient une règle de tendance simple sur le Bitcoin et l'Ether | `4517daa` |
| 13/11/2026 | Le bot de tendance (argent fictif) | Fait : moteur et tests de l'argent, onglet « Tendance », porte `robustesse --tendance` (verdict : pas robuste, argent fictif seulement), outil de mesure sur le même moteur | `95db6b4` |
| 13/11/2026 | La règle de tendance sur d'autres marchés (option A) | Fait : huit marchés, 39 à 77 ans, protocole enregistré avant le calcul. La règle ne bat « garder » sur aucun ; les tendances sont réelles mais les frais et le temps dehors mangent l'avantage. Une protection, pas un gain | `fe44aec` |
