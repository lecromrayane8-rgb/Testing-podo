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
