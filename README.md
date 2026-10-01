# Jouer avec le temps — prototype

Installation vidéo interactive : la lecture ralentit quand on s'approche de
l'écran, se fige tout près, et rattrape le direct quand on recule.

## Installation sur Windows (une seule fois)

### 1. Installer Python 3.12
1. Menu **Démarrer** → tapez **Microsoft Store** → ouvrez-le.
2. Dans la recherche du Store, tapez **Python 3.12**.
3. Cliquez sur **Python 3.12** (éditeur : Python Software Foundation) → **Obtenir**.

> Prenez **3.12** (ou gardez une 3.11 déjà installée), pas 3.13 ni 3.14 : la brique de détection du corps
> (MediaPipe) ne fonctionne pas encore avec les versions plus récentes.

### 2. Télécharger le programme
1. Ouvrez **github.com/PLHFak/echo-cam**.
2. Cliquez sur le bouton vert **Code** → **Download ZIP**.
3. Ouvrez le dossier **Téléchargements**, clic droit sur **echo-cam-main.zip**
   → **Extraire tout…** → **Extraire**.

### 3. Lancer
1. Dans le dossier extrait, double-cliquez sur **lancer.bat**.
2. Si Windows affiche « Windows a protégé votre ordinateur » :
   **Informations complémentaires** → **Exécuter quand même**.
3. La première fois, une fenêtre noire installe tout (quelques minutes).
   Les fois suivantes, le programme démarre directement.

## Utilisation

Au lancement, restez simplement immobile ~10 s : votre position devient la
référence (lecture en direct). Approchez-vous : l'image ralentit, puis se fige.
Si vous restez immobile 10 s quelque part, la lecture rattrape le direct et
cette position devient la nouvelle référence.

### Touches

| Touche | Effet |
|---|---|
| **C** | Calibration manuelle : la position courante devient la référence (2 m) |
| **I** | Interpolation RIFE : couper / rétablir |
| **V** | Fond virtuel : personne incrustée sur le fond (test ou fond.jpg) |
| **H** | Mode du HUD incrusté : complet → vitesse seule → aucun |
| **S** | Sauvegarder la version courante (taper un nom, **Entrée**) |
| **←/→** | Version précédente / suivante (reset propre du run) |
| **R** | Remettre tous les curseurs aux valeurs par défaut |
| **1** à **9**, **0** | Durée d'immobilité avant nouvelle référence (1..9 s, 0 = 10 s) |
| **Q** ou **Échap** | Quitter (cliquer d'abord sur la fenêtre vidéo) |

### Les trois zones de distance

- plus près que **Arrêt** (0,5 m) : image **figée** (avec 10 cm d'hystérésis
  pour ne pas osciller au seuil) ;
- entre **Arrêt** et **Direct** (2 m) : **ralenti** progressif (v de 0 à 1) ;
- entre **Direct** et **Accel** (3 m) : **accélération** progressive
  (v de 1 à Vmax) — le retard se résorbe en douceur ;
- au-delà d'**Accel** : rattrapage plein (Vmax). Une fois le retard à zéro,
  la lecture reste en direct.

La distance **et** la vitesse sont lissées (double lissage) : pas d'à-coup
en entrée ni en sortie de zone.

### Versions baptisées

**S** sauvegarde tous les réglages courants sous un nom (ex. « douce »,
« nerveuse », « démo ») dans `presets.json` — elles survivent au redémarrage.
Les flèches **←/→** passent de l'une à l'autre avec un reset propre (buffer
et retard remis à zéro). La liste apparaît dans le panneau, la version active
dans le HUD.

Une variation de largeur d'épaules sous **±15 %** compte comme immobile
(`STABLE_TOL` dans `main.py`).

## Panneau de contrôle web

L'application ouverte, double-cliquez sur **panneau.bat** : la page de
contrôle s'ouvre dans le navigateur à l'adresse http://localhost:8766 —
elle est servie par l'application elle-même, donc toujours à sa version.
Tout s'applique immédiatement, sans redémarrer. Si la page ne s'ouvre pas :
lancez d'abord l'application (lancer.bat).

## Mettre à jour

Double-cliquez sur **mettre_a_jour.bat** : la dernière version est téléchargée
depuis GitHub, sans réinstallation.

## Réglages (panneau « ECHO — Réglages »)

Chaque curseur est expliqué directement dans le panneau, avec sa valeur par
défaut entre parenthèses. La touche **R** remet tout aux valeurs par défaut.

| Curseur | Défaut | Ce qu'il fait |
|---|---|---|
| **Arrêt (cm)** | 50 | Plus près que cette distance, l'image se fige. |
| **Direct (cm)** | 200 | Plus loin, lecture en direct (ou rattrapage). Entre Arrêt et Direct : ralenti progressif. |
| **Vmax x10** | 20 (= 200 %) | Vitesse de rattrapage du direct en reculant. |
| **Vmin (%)** | 10 | Plancher : la lecture ne descend jamais sous ce % (0 = l'image fige sous Arrêt). |
| **Échelle dist (%)** | 82 | Facteur de la correction : réel = brut × échelle − décalage. Touche C à 2 m = réglage auto. |
| **Décalage (cm)** | 65 | Décalage constant soustrait après l'échelle. |
| **Buffer (s)** | 30 | Mémoire d'images : c'est le retard maximum possible. 30 s en 720p ≈ 2,5 Go de RAM. |
| **Immobilité (s)** | 10 | Durée sans bouger avant que la position devienne la nouvelle référence (touches 1..9, 0 en direct). |

Les réglages plus fins (lissage, délai salle vide `ABSENT_TIMEOUT`, tolérance
d'immobilité) restent en tête de `main.py`.

## Fond vivant par Spout (étape 2 galerie)

Dès qu'un émetteur **Spout** tourne sur le PC (Unity, OBS, TouchDesigner,
Resolume…), son image devient automatiquement le fond d'incrustation
(touche V) ; s'il s'arrête, retour au fond fixe. Pour tester sans Unity :
lancez l'application, activez le fond (V), puis double-cliquez sur
**emetteur_test.bat** — le fond devient un décor animé.

## Caméra : tableau de contrôle

Double-cliquez sur **camera_controle.bat** :
1. il mesure ce que la caméra sait vraiment faire (chaque résolution ×
   cadence demandée → ce que le pilote accorde et la cadence réellement
   mesurée), résultat aussi dans `camera_controle.txt` ;
2. il ouvre le **panneau de réglages du pilote** (exposition, luminosité,
   formats…) avec un aperçu en direct affichant la cadence réelle.

Une caméra « simplement HD » plafonne souvent à 30 im/s en 720p : ce n'est
pas un problème, l'écran reste alimenté à 60 im/s par l'interpolation RIFE.

## Debug (continuité du flux)

Le panneau affiche une ligne **Anomalies** : `cam` = images caméra manquantes,
`retard` = cycles d'affichage au-delà des 16,7 ms, `saut` = discontinuités dans
la lecture (le plus souvent : buffer trop court pour le retard demandé).
Le détail est journalisé dans la console et dans `echo_debug.log` — à
m'envoyer si quelque chose semble saccadé.

## Interpolation RIFE (60 im/s à l'écran)

L'affichage est cadencé à **60 images/s** (écran 60 Hz), indépendamment de la
caméra qui reste à 30. À chaque image affichée, **RIFE** (GPU NVIDIA requis)
calcule l'image exacte entre les deux images voisines du buffer — en ralenti
comme en direct : la caméra donne 30 im/s, l'écran en reçoit 60. Pour cela,
la lecture vit avec une micro-latence fixe d'environ 50 ms, imperceptible.

- Les poids du modèle (~21 Mo) sont téléchargés automatiquement au premier
  lancement dans `models/`. Calcul en demi-précision (fp16) sur le GPU.
- Sans GPU CUDA, le programme fonctionne normalement, sans interpolation
  (l'état est affiché dans le panneau de réglages).
- Si l'interpolation est trop lente pour tenir 60 im/s (budget 16,7 ms),
  elle est coupée automatiquement (et retentée périodiquement) — la
  cadence prime.

## Prochaine étape

Galerie animée Unity autour de la personne (plan : `docs/galerie-unity-plan.md`) ;
pour la 4K accélérée, TensorRT.
