# ECHO V2 — Galerie d'art animée autour de la personne (plan)

Vision (PLH) : la personne au centre, incrustée dans une galerie d'art
(statues, œuvres modernes). Des visiteurs circulent **dans le sens de la
marche, tous vers l'avant**, alternant **arrêts contemplation** et
**déplacements**, **toujours du même côté** — le **centre reste vide**
(c'est la place de la personne réelle). La galerie **boucle sur elle-même**
pour paraître infinie avec un seul tronçon à fabriquer.

## Étapes

### 1. Détourage + incrustation (fait — v1.13, touche V)
MediaPipe Selfie Segmentation à chaque image caméra (basse résolution,
masque stocké dans le buffer à côté des images) ; incrustation sur un fond
de test (ou `fond.jpg` posé dans le dossier). C'est la brique de composition
qui recevra l'image de la galerie.

### 2. Tuyau Unity → ECHO (Python)
- Unity envoie son rendu par **Spout** (partage de texture GPU Windows,
  zéro copie). Côté Python : `SpoutGL`, le fond virtuel devient l'image
  vivante reçue ; repli sur le fond de test si aucun émetteur.
- Unity se connecte au **pont WebSocket existant** (port 8765) et reçoit
  l'état : vitesse, retard, distance, état. Aucun nouveau canal à créer.

### 3. La galerie qui boucle (Unity, machine PLH)
- Un **module de couloir** d'environ 12 m : murs, sol, éclairage, socles,
  statues, œuvres modernes (assets libres ou génériques).
- Le module est instancié 3 fois (précédent / courant / suivant). Quand la
  caméra ou un visiteur dépasse une extrémité, **téléportation silencieuse**
  d'une longueur de module : boucle sans couture → galerie infinie.
- Caméra Unity fixe au centre du couloir, axe aligné avec le regard de la
  personne réelle (elle « habite » le centre vide).

### 4. Les visiteurs (Unity)
- Personnages sur **deux rails latéraux** (splines), **jamais au centre**,
  chacun reste sur son côté, tous orientés **vers l'avant**.
- Machine à états simple par visiteur : `marche (vitesse aléatoire lente)
  → arrêt contemplation devant une œuvre (durée aléatoire) → marche`.
- Espacement minimal entre visiteurs d'un même rail (pas de dépassement
  au centre : celui de derrière s'arrête).

### 5. Le temps asservi à ECHO (Unity)
- `Time.timeScale = vitesse` reçue du pont : la galerie ralentit et se fige
  avec la lecture.
- **Reset OFF** : le retard reste → le monde autour vit « en avance » sur
  la personne (option « univers plus vieux »).

## Répartition
- Étapes 1–2 : Claude Code (Python, testable en conteneur).
- Étapes 3–5 : scripts C# + guide pas à pas fournis par Claude Code,
  scène montée dans l'éditeur Unity sur la machine PLH (RTX 4090).
