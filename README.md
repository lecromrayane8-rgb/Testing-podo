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

## Démonstrations 3D

Le dossier `demos/` contient des animations 3D interactives (praticien et patient sans visage, table d'examen), affichées dans la fiche du test grâce au champ `demo3d`.

- `demos/thomas.html` : test de Thomas, avec les résultats négatif, positif psoas et positif droit fémoral.
- Options d'adresse : `?resultat=negatif|psoas|droit` et `?vue=profil|troisquarts|face`.

Les pages 3D utilisent [three.js](https://threejs.org) (licence MIT), copié dans `demos/lib/`. Elles doivent être ouvertes via un serveur web (GitHub Pages, ou `npx http-server` en local) : un double-clic sur le fichier ne suffit pas.
