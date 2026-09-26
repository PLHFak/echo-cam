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

- Placez-vous à **2 m** de la caméra et pressez **C** pour calibrer.
- **C** = recalibrer · **Q** = quitter.

## Réglages

Tout est en tête de `main.py` (clic droit → Ouvrir avec → Bloc-notes) :
seuils de distance (`DIST_STOP`, `DIST_FULL`), vitesse de rattrapage,
profondeur du buffer, lissage, délai avant retour au direct (`ABSENT_TIMEOUT`).

## Prochaine étape (V2)

Remplacer le ré-affichage d'images par de l'interpolation **RIFE** pour un
ralenti fluide (image à instant *t* entre deux frames). Nécessite un GPU —
pour la 4K accélérée, un PC avec carte NVIDIA + TensorRT.
