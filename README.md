# Jouer avec le temps — prototype

Installation vidéo interactive : la lecture ralentit quand on s'approche de
l'écran, se fige tout près, et rattrape le direct quand on recule.

## Installation (Mac, une seule fois)

```bash
python3 -m venv venv
source venv/bin/activate
pip install opencv-python mediapipe numpy
```

## Lancer

```bash
python main.py
```

- Placez-vous à **2 m** de la caméra et pressez **C** pour calibrer.
- **C** = recalibrer · **Q** = quitter.

## Réglages

Tout est en tête de `main.py` : seuils de distance (`DIST_STOP`, `DIST_FULL`),
vitesse de rattrapage, profondeur du buffer, lissage.

## Prochaine étape (V2)

Remplacer le ré-affichage d'images par de l'interpolation **RIFE** pour un
ralenti fluide (image à instant *t* entre deux frames). Nécessite un GPU —
sur Mac, via Metal/MPS ; pour la 4K accélérée, un PC avec carte NVIDIA + TensorRT.
