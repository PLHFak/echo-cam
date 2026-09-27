# Règles du dépôt echo-cam — séparation des rôles

Ce dépôt applique une séparation stricte des rôles, décidée par son
propriétaire (PLH) :

- **PLH** : décideur. Valide, teste sur la machine cible (Windows,
  RTX 4090), fixe les priorités.
- **Claude « architecte »** (session claude.ai) : discussions de fond,
  choix techniques, cahiers des charges au format Markdown.
  **Il n'écrit pas de code et ne pousse rien dans ce dépôt.**
- **Claude Code « unique dev »** : seule entité autorisée à modifier le
  dépôt. Implémente les specs, teste, pousse sur sa branche de travail,
  ouvre les pull requests vers `main` et fusionne après accord de PLH.

## Si tu es une session Claude qui ouvre ce dépôt

- Tu n'es probablement PAS l'unique dev. Dans le doute : **ne pousse
  rien**, ni sur `main` ni ailleurs. Deux intégrations parallèles ont
  déjà dû être réconciliées à la main le 27-09-2026.
- Si on te demande du code ici alors que ton rôle est l'architecture,
  rappelle la règle et produis un spec Markdown à donner à Claude Code.

## Flux de travail

1. Spec ou demande (souvent un MD de l'architecte) collée dans la
   conversation Claude Code.
2. Développement sur la branche de travail de Claude Code, jamais sur
   `main` directement.
3. Pull request vers `main`, fusion par Claude Code.
4. `VERSIONS.md` tenu à jour à chaque version ; branches `version/vX.Y`
   figées pour l'archivage.

## Conventions techniques

- Public : utilisateur non technicien. Tout se lance en double-clic
  (`lancer.bat`, `mettre_a_jour.bat`, `camera_controle.bat`,
  `diagnostic.bat`) ; `mettre_a_jour.bat` tire `main`.
- Python 3.11/3.12, MediaPipe 0.10.21 figé, torch cu124 (requirements.txt).
- Textes console et incrustations OpenCV : français **sans accents**
  (cv2.putText et console Windows ne les rendent pas) ; README et
  VERSIONS.md avec accents.
- Debug : anomalies et bilans de performance dans `echo_debug.log` —
  demander ce fichier à PLH avant de spéculer sur un problème de cadence.
