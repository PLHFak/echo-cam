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
| **1** à **9** | Durée d'immobilité avant nouvelle référence : 1 à 9 s |
| **0** | Durée d'immobilité : 10 s |
| **C** | Calibration manuelle : la position courante devient la référence (2 m) |
| **I** | Interpolation RIFE : couper / rétablir |
| **R** | Remettre tous les curseurs aux valeurs par défaut |
| **Q** ou **Échap** | Quitter (cliquer d'abord sur la fenêtre vidéo) |

Une variation de largeur d'épaules sous **±15 %** compte comme immobile
(`STABLE_TOL` dans `main.py`).

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
| **Rattrapage x10** | 25 (= x2,5) | Vitesse de la lecture quand elle rattrape le direct en reculant. |
| **Buffer (s)** | 12 | Mémoire d'images : c'est le retard maximum possible. 12 s en 720p ≈ 1 Go de RAM. |
| **Immobilité (s)** | 10 | Durée sans bouger avant que la position devienne la nouvelle référence (touches 1..9, 0 en direct). |

Les réglages plus fins (lissage, délai salle vide `ABSENT_TIMEOUT`, tolérance
d'immobilité) restent en tête de `main.py`.

## Debug (continuité du flux)

Le panneau affiche une ligne **Anomalies** : `cam` = images caméra manquantes,
`retard` = cycles d'affichage au-delà des 33 ms, `saut` = discontinuités dans
la lecture (le plus souvent : buffer trop court pour le retard demandé).
Le détail est journalisé dans la console et dans `echo_debug.log` — à
m'envoyer si quelque chose semble saccadé.

## Interpolation RIFE (ralenti fluide)

En ralenti, l'image affichée est fabriquée par **RIFE** (GPU NVIDIA requis) :
une image intermédiaire est calculée à l'instant exact entre les deux images
voisines du buffer, au lieu de répéter la plus proche. L'affichage est cadencé
à **30 images/s minimum**, indépendamment de la caméra.

- Les poids du modèle (~21 Mo) sont téléchargés automatiquement au premier
  lancement dans `models/`.
- Sans GPU CUDA, le programme fonctionne normalement, sans interpolation
  (l'état est affiché dans le panneau de réglages).
- Si l'interpolation est trop lente pour tenir 30 im/s, elle est coupée
  automatiquement (et retentée périodiquement) — la cadence prime.

## Prochaine étape

Fond virtuel (touche V) ; pour la 4K accélérée, TensorRT.
