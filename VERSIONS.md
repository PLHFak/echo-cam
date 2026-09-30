# Bibliothèque des versions

Chaque version est figée sur GitHub et reste téléchargeable pour toujours.
Pour récupérer une version précise, coller dans le navigateur (remplacer v1.3
par le numéro voulu) :

    https://github.com/PLHFak/echo-cam/archive/refs/heads/version/v1.3.zip

## v1.13 — 30-09-2026 · Galerie étape 1 : détourage + fond virtuel (touche V)
- La personne est découpée en temps réel (MediaPipe Selfie Segmentation,
  masque par image caméra stocké dans le buffer) et incrustée sur un fond :
  fond de test « galerie » généré, ou votre `fond.jpg` posé dans le dossier.
- Touche **V** + interrupteur « Fond virtuel » du panneau web.
- Plan complet de la galerie Unity (boucle infinie, visiteurs stop-and-go
  latéraux, temps asservi) : `docs/galerie-unity-plan.md`.

## v1.12.1 — 30-09-2026 · Correction distance préréglée, 2 colonnes, barre de retard
- Correction de distance préréglée à **75 %** (mesure IA ~35 % trop longue) ;
  toujours ajustable au curseur ou par la touche **C à 2 m**.
- Panneau web : réglages sur **deux colonnes** ; **barre de retard** sous la
  barre de vitesse (pleine = buffer plein).

## v1.12 — 29-09-2026 · Panneau web repensé, distance corrigée, nouveaux défauts
- **Panneau web redessiné** : jauge de vitesse en %, schéma des zones de
  distance avec la position de la personne en direct, bulles « ? » de
  définition sur chaque réglage et option, thème sombre moderne.
- **Vitesse en %** partout (HUD compris) ; le HUD « vitesse » affiche aussi
  le retard.
- **Échelle distance** : correction de la mesure IA (curseur, ou touche C
  à 2 m qui la règle automatiquement) — corrige le « 2 m affichés = 1 m ».
- **Vitesse plancher (Vmin)** : la lecture ne descend jamais sous ce %
  (défaut 10 % — l'image ne fige plus complètement).
- **Nouveaux défauts** : arrêt 50 cm · direct 2 m · accélération jusqu'à
  4 m · vitesse max ×2 · plancher 10 % · buffer 30 s.

## v1.11 — 28-09-2026 · Spec V1 : panneau web, distance IA, reset (tag v1)
- **Panneau de contrôle HTML** (`controle.html`, double-clic sur
  `panneau.bat`) relié à l'app par un pont WebSocket local : état en direct,
  9 curseurs, options, versions de réglages — tout à chaud, sans redémarrer.
- **Distance par profondeur IA** : Depth Anything V2 metric (GPU, fp16),
  lue au centre du torse — stable quand la personne pivote, sans calibration.
  Secours « largeur d'épaules » conservé (touche D, bascule auto en panne).
- **Reset de position** activable/désactivable (touche T) : OFF, le retard
  acquis reste — la personne peut demeurer décalée dans le temps.
- Les versions de réglages mémorisent aussi l'état du reset.

## v1.10 — 27-09-2026 · Spec V1 de l'architecte : 3 zones, HUD, versions baptisées
- **Trois zones** : figé (< 0,5 m, hystérésis 10 cm) · ralenti 0→1 (0,5→2 m) ·
  accélération progressive 1→Vmax (2→3 m) · rattrapage plein (> 3 m).
  **Double lissage** distance + vitesse : transitions sans à-coup.
- **HUD incrusté** (touche **H** : complet / vitesse seule / aucun) : état,
  vitesse, retard, distance, version active, device GPU/CPU, im/s réels,
  résolution de traitement, état RIFE — coins arrondis, fond translucide.
- **Versions baptisées** : **S** sauvegarde les réglages sous un nom
  (`presets.json`, persistant), **←/→** bascule avec reset propre du run,
  liste dans le panneau. Touche **P** : masquer le panneau.
- Écart assumé avec la spec : RIFE reste actif à v=1 (demande PLH : 60
  images à l'écran même quand la caméra n'en donne que 30).

## v1.9.1 — 27-09-2026 · Preuve d'exécution GPU mesurée
- Au démarrage, ligne « verif GPU » dans `echo_debug.log` : device du
  modèle, nom de la carte, fp16, warm-up chronométré (synchronisé CUDA)
  pleine et demi résolution, mémoire GPU allouée. Un 720p en ~10 ms est
  impossible sur CPU (~0,5-1 s) : le chrono est la preuve.
- Mémoire GPU allouée ajoutée à la ligne « perf » (toutes les 5 s).

## v1.9 — 27-09-2026 · Ralenti profond fluide : RIFE par paliers + cache GPU
- En ralenti fort, les saccades venaient de la coupure automatique de RIFE
  (seuil 12,5 ms trop agressif) : retour à « l'image la plus proche » =
  paliers visibles. Chaque image affichée doit être un instant interpolé
  unique (à 10 % de vitesse : ~20 instants entre deux images caméra).
- RIFE par paliers : pleine résolution → **demi-résolution** (~4× moins
  cher, toujours fluide) → coupé, avec remontée automatique ; seuil relevé
  à 85 % du budget. État du palier affiché dans le panneau et les logs.
- Cache GPU du couple d'images courant : en ralenti, seul l'instant t
  change — plus de renvoi des images au GPU à chaque rafraîchissement.

## v1.8 — 27-09-2026 · Le 60 im/s tient : analyse allégée (diagnostic aux logs)
- Diagnostic (echo_debug.log de PLH) : la détection de posture à pleine
  cadence monopolisait le verrou Python (GIL) — affichage plafonné à 30,
  RIFE mesuré 10× trop lent donc coupé, images caméra perdues.
- Analyse de posture 1 image sur 3 (~10 Hz), sur image réduite (640 px),
  modèle léger (complexity 0) : la distance reste fiable, le GIL respire.
- Cadencement précis : `waitKey(1)` + `time.sleep` (~1 ms) au lieu du
  `waitKey(n)` de Windows (granularité ~15 ms).
- Ligne « perf » enrichie : coût d'analyse et temps « autre » mesurés.

## v1.7 — 27-09-2026 · 60 im/s à l'écran (écran 60 Hz)
- Affichage cadencé à **60 im/s** : RIFE fabrique l'image intermédiaire à
  chaque rafraîchissement, en ralenti comme en direct (caméra toujours à
  30 im/s). Micro-latence fixe d'~50 ms pour toujours avoir deux images
  autour de l'instant affiché.
- RIFE en demi-précision (fp16, autocast) + autotune cudnn + warm-up à la
  taille réelle : l'interpolation 720p tient dans le budget de 16,7 ms.
- `camera_controle.bat` : mesure les modes réels de la caméra (résolution ×
  cadence) et ouvre le panneau de réglages du pilote avec aperçu en direct.

## v1.6 — 27-09-2026 · Rendu 30 im/s garanti, réglages expliqués, debug
- Refonte : capture et analyse dans un thread ; affichage cadencé à
  **30 im/s minimum**. Si RIFE dépasse le budget de 33 ms, il est coupé
  automatiquement (et retenté périodiquement) — la cadence prime.
- Poids RIFE (rife49.pth, ~21 Mo, empreinte sha256 vérifiée) téléchargés
  par le programme dans `models/` — plus de téléchargement dans
  `lancer.bat` ; `rife.py`/rife47.pth remplacés par `rife_interp.py`.
- Panneau : une ligne d'explication par curseur avec sa valeur par défaut ;
  touche **R** = remise aux valeurs par défaut ; C/I/R aussi en majuscule.
- Debug : compteurs d'anomalies dans le panneau (images caméra manquantes,
  cycles d'affichage trop longs, sauts de continuité de lecture), détail
  journalisé dans la console et `echo_debug.log`.
- Quitter aussi avec **Échap** ou la croix de la fenêtre (en plus de Q).

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
