# Bibliothèque des versions

Chaque version est figée sur GitHub et reste téléchargeable pour toujours.
Pour récupérer une version précise, coller dans le navigateur (remplacer v1.3
par le numéro voulu) :

    https://github.com/PLHFak/echo-cam/archive/refs/heads/version/v1.3.zip

## v1.5 — 27-09-2026 · Ralenti fluide (interpolation RIFE)
- Interpolation RIFE v4.7 sur GPU (fp16) entre les deux images qui encadrent
  le retard : le ralenti profond devient fluide. Touche **I** = on/off
  (ON par défaut quand CUDA est disponible).
- Poids (rife47.pth, 20 Mo) téléchargés automatiquement par `lancer.bat`.
- Architecture IFNet reprise (licence MIT) de ComfyUI-Frame-Interpolation,
  validée ici contre les poids réels (objet déplacé retrouvé à mi-chemin).

## v1.4 — 27-09-2026 · Socle V2 : panneau de réglages + PyTorch CUDA
- Panneau latéral « ECHO — Réglages » : curseurs seuils arrêt/direct,
  vitesse de rattrapage, profondeur du buffer (redimensionné en direct),
  durée d'immobilité + état en direct (distance, vitesse, retard, im/s, GPU).
- PyTorch CUDA (cu124) installé par `lancer.bat`, état CUDA affiché au
  lancement et dans le panneau. Prépare RIFE (étape suivante).

## v1.3 — 27-09-2026 · Référence automatique
- Immobile pendant N secondes (±15 % de largeur d'épaules) : la lecture
  rattrape le direct et la position courante devient la référence 0.
- Touches **1..9** = N en secondes, **0** = 10 s. Calibration initiale automatique.
- `mettre_a_jour.bat` : récupère la dernière version sans réinstaller.

## v1.2 — 27-09-2026 · Installation Windows sans commandes
- `lancer.bat` : installation et lancement en double-clic.
- `diagnostic.bat` : analyse de la machine en double-clic.
- Version MediaPipe figée (0.10.21) — les récentes plantaient au démarrage.
- Python 3.11 ou 3.12. Guide pas à pas dans le README.

## v1.1 — 26-09-2026 · Corrections de comportement
- Lecture en direct avant calibration (on se voit pour se placer).
- Salle vide : retour au direct après 10 s au lieu de rester figé.
- Retard calculé en secondes réelles (horodatage), insensible aux
  ralentissements de la machine.

## v1.0 — 26-09-2026 · Prototype initial
- Webcam + détection de posture (MediaPipe), distance estimée par la
  largeur d'épaules, calibration à 2 m sur la touche C.
- Plus on approche, plus la lecture ralentit ; figée tout près ;
  rattrapage du direct en reculant. Mémoire tampon de 12 s.
