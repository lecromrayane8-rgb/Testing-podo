# Testing-podo

Bibliothèque de tests cliniques en posturologie et en biomécanique, classés par segment : pied, cheville, genou, hanche, bassin, rachis et posturologie globale.

Cliquer sur un test ouvre sa fiche : vidéo de démonstration, objectif, position, déroulement et interprétation.

## Voir le site

Ouvrir le fichier `index.html` dans un navigateur, ou activer GitHub Pages (Settings → Pages → branche `main`).

## Ajouter ou modifier un test

Tous les tests sont dans la liste `TESTS`, en haut du script de `index.html`. Chaque test est un bloc `{ ... }` : il suffit d'en copier un et de changer les textes.

Pour ajouter une vidéo, remplir le champ `video` avec :
- un lien YouTube (une vidéo « non répertoriée » ne s'affiche pas dans les recherches YouTube),
- un lien Vimeo,
- ou le chemin d'un fichier vidéo placé dans un dossier `videos/` (ex. `videos/thomas.mp4`).

Un lien vers un test précis s'obtient en ajoutant `#` et l'identifiant du test à l'adresse du site (ex. `.../#thomas`).

## Plan Masse 14 jours (`prise-de-masse/`)

Application mobile de prise de masse : liste de courses à moins de 100 € pour 14 jours, 5 repas par jour (collations à 10 h et 16 h), 16 recettes et 4 sessions de batch cooking (dimanche + mercredi soir).

- Ouvrir `prise-de-masse/index.html` (ou `.../prise-de-masse/` via GitHub Pages).
- Sur téléphone : menu du navigateur → « Ajouter à l'écran d'accueil » pour l'installer comme une app (fonctionne hors connexion une fois ouverte).
- Les cases cochées (courses, repas, étapes de batch) et le suivi du poids restent enregistrés sur le téléphone.
- `app.html` est la source ; `index.html` est la même page avec le manifeste et le service worker pour l'installation.
