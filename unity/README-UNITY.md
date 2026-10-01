# ECHO — La galerie Unity, pas à pas

## Le plus simple : l'installeur automatique

Dans `Documents\echo-cam`, double-cliquez sur **installer_unity.bat** :
il installe Unity Hub, l'éditeur Unity 2022.3 LTS (~7 Go, 20 à 40 min),
crée le projet **echo-galerie**, copie les fichiers ECHO, installe
l'émetteur Spout, **construit la scène**, puis ouvre Unity — il ne reste
qu'à appuyer sur **Play**. Côté ECHO : `lancer.bat` + touche **V**.

En cas d'échec de l'installeur, la méthode manuelle ci-dessous fait la
même chose pas à pas.

---

Objectif : la galerie en 3D tourne dans Unity, envoie son image à ECHO par
Spout (elle devient le fond de l'incrustation) et cale son horloge sur votre
vitesse (ralenti/figé ensemble). Montage : **un seul clic de menu** construit
toute la scène.

## 1. Installer Unity (une seule fois, ~20 min)

1. Téléchargez **Unity Hub** : https://unity.com/download → bouton
   « Download Unity Hub » → installez-le (suivant, suivant).
2. Ouvrez Unity Hub → onglet **Installs** → **Install Editor** →
   choisissez la version **2022.3 LTS** (ou la LTS proposée) → Install.
   Aucun module supplémentaire n'est nécessaire.
3. Créez un compte Unity gratuit si le Hub le demande (licence Personal).

## 2. Créer le projet

1. Unity Hub → onglet **Projects** → **New project**.
2. Modèle : **3D (Built-In Render Pipeline)** — le premier « 3D » proposé.
3. Nom : **echo-galerie** · Emplacement : Documents → **Create project**.
   (Première ouverture : quelques minutes.)

## 3. Ajouter les fichiers ECHO

1. Dans l'Explorateur Windows, ouvrez `Documents\echo-cam\unity\Assets` :
   il contient un dossier **ECHO**.
2. Copiez ce dossier **ECHO** dans
   `Documents\echo-galerie\Assets\` (à côté du dossier Scenes).
3. Revenez dans Unity : il recharge tout seul ; un menu **ECHO** apparaît
   dans la barre du haut (après Window / Help).

## 4. Installer l'émetteur Spout (KlakSpout)

1. Dans l'Explorateur, ouvrez `Documents\echo-galerie\Packages\manifest.json`
   avec le **Bloc-notes** (clic droit → Ouvrir avec).
2. Tout en haut, juste après la première accolade `{`, collez :

   ```
   "scopedRegistries": [
     { "name": "Keijiro", "url": "https://registry.npmjs.com",
       "scopes": [ "jp.keijiro" ] }
   ],
   ```
3. Puis, dans la liste `"dependencies": {`, ajoutez en première ligne :

   ```
   "jp.keijiro.klak.spout": "2.0.3",
   ```
4. Enregistrez (Ctrl+S), revenez dans Unity : le paquet s'installe tout seul.

## 5. Construire la galerie et jouer

1. Menu **ECHO → Construire la galerie** : couloir, œuvres, statues,
   visiteurs, caméra, lumières, émetteur Spout, horloge ECHO — tout se crée.
2. Appuyez sur **Play** (le triangle en haut au centre).
3. Côté ECHO : `lancer.bat` + touche **V** → le fond devient **la galerie
   vivante** (panneau web : « Fond : Spout 'echo-galerie' »).
4. Approchez-vous de la caméra : votre image **et les visiteurs** ralentissent
   ensemble ; figé = tout le monde se fige. ECHO fermé : la galerie vit au réel.

## Ce que fait chaque script (dossier Assets/ECHO)

| Fichier | Rôle |
|---|---|
| `Editor/GalerieBuilder.cs` | Le menu « Construire la galerie » : 3 modules de 12 m (boucle de 36 m), œuvres, statues, visiteurs, caméra + Spout, lumières |
| `Scripts/Visiteur.cs` | Marche/contemplation aléatoires, rails latéraux uniquement (centre vide), sens unique, boucle sans couture, pas de dépassement |
| `Scripts/EchoLink.cs` | Se connecte au pont ECHO (ws://localhost:8765) et règle l'horloge de la scène (`Time.timeScale`) sur votre vitesse |

## Problèmes courants

- **Pas de menu ECHO** : le dossier ECHO n'est pas dans `Assets` (étape 3),
  ou Unity affiche des erreurs rouges en bas — capture d'écran pour Claude.
- **Avertissement « KlakSpout absent »** dans la console : étape 4 incomplète ;
  refaites ECHO → Construire la galerie après l'installation.
- **ECHO ne voit pas la galerie** : la fenêtre Unity doit être en **Play**,
  et le mode Play ne doit pas être en pause.
