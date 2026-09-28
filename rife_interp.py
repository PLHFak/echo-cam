"""
Interpolation RIFE pour le projet ECHO — etage greffe depuis SUPER SLO 600.

La brique d'interpolation est reprise du projet « super slo 600 » (slowcam.py,
installe dans C:\\Users\\evalh\\SUPERSLO\\slowcam\\ sur le PC cible) :
- modele RIFE 4.26, poids flownet_v4.26.pkl (ceux qui marchent la-bas) ;
- execution GPU en demi-precision REELLE : poids ET tenseurs en FP16
  (methode slowcam), plus autocast ;
- ligne « chauffe GPU : X.X s » mesuree au demarrage, comme slowcam —
  c'est la preuve de l'execution GPU (un 720p en ~10 ms est impossible
  sur CPU).
Seule cette brique est greffee : la boucle d'affichage, le buffer et le HUD
restent ceux d'echo-cam (webcam -> buffer -> playhead -> interpolation).

Recherche des poids superslo, dans l'ordre :
  1. models/flownet_v4.26.pkl (copie locale d'echo-cam) ;
  2. installation SUPER SLO 600 : C:\\Users\\evalh\\SUPERSLO\\slowcam\\,
     puis recherche recursive sous C:\\Users\\evalh\\SUPERSLO si le dossier
     a bouge — le fichier trouve est copie dans models/ ;
  3. a defaut : repli sur l'ancien etage (RIFE 4.9, telecharge ~21 Mo),
     l'application reste utilisable ; le repli est journalise.
NB : la variante flownet_v4.25.lite.pkl n'est pas utilisable ici
(rife_arch.py implemente l'architecture 4.26, pas la 4.25.lite).

Usage :
    rife = RifeInterpolator()          # rife.ok, rife.status
    out  = rife.interpolate(img0, img1, t)   # images BGR uint8, t dans [0, 1]
"""

import hashlib
import os
import shutil
import time
import traceback
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))

# --- poids superslo (methode qui marche, cf. consigne de merge 28/09/2026) ---
SUPERSLO_DIR   = r"C:\Users\evalh\SUPERSLO"
SUPERSLO_PKL   = "flownet_v4.26.pkl"
LOCAL_PKL      = os.path.join(_DIR, "models", SUPERSLO_PKL)

# --- repli : ancien etage RIFE 4.9 (architecture 4.7), telecharge ---
WEIGHTS_URL    = ("https://github.com/Fannovel16/ComfyUI-Frame-Interpolation"
                  "/releases/download/models/rife49.pth")
WEIGHTS_SHA256 = "e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533"
WEIGHTS_FILE   = os.path.join(_DIR, "models", "rife49.pth")

# listes d'echelles par architecture (4.26 : 5 blocs)
SCALE_LISTS = {"4.26": [16, 8, 4, 2, 1], "4.7": [8, 4, 2, 1]}


def _journal(msg):
    """Ecrit aussi dans echo_debug.log : une erreur RIFE doit laisser une
    trace exploitable, pas seulement un type d'exception dans le panneau."""
    print(f"[ECHO] {msg}")
    try:
        chemin = os.path.join(_DIR, "echo_debug.log")
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S") + f" [rife] {msg}\n")
    except OSError:
        pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _ensure_weights():
    """Repli 4.9 : telecharge les poids si absents ou corrompus."""
    if os.path.exists(WEIGHTS_FILE) and _sha256(WEIGHTS_FILE) == WEIGHTS_SHA256:
        return WEIGHTS_FILE
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    print("[ECHO] Telechargement du modele RIFE de repli (~21 Mo)...")
    tmp = WEIGHTS_FILE + ".part"
    urllib.request.urlretrieve(WEIGHTS_URL, tmp)
    if _sha256(tmp) != WEIGHTS_SHA256:
        os.remove(tmp)
        raise RuntimeError("modele RIFE telecharge corrompu")
    os.replace(tmp, WEIGHTS_FILE)
    print("[ECHO] Modele RIFE de repli pret.")
    return WEIGHTS_FILE


def _trouver_poids_superslo():
    """Chemin des poids flownet_v4.26.pkl, ou None.
    Une copie trouvee dans l'installation SUPER SLO 600 est dupliquee dans
    models/ pour qu'echo-cam reste autonome ensuite."""
    if os.path.exists(LOCAL_PKL):
        return LOCAL_PKL
    source = os.path.join(SUPERSLO_DIR, "slowcam", SUPERSLO_PKL)
    if not os.path.exists(source):
        source = None
        if os.path.isdir(SUPERSLO_DIR):     # le dossier a pu bouger
            for racine, _, fichiers in os.walk(SUPERSLO_DIR):
                if SUPERSLO_PKL in fichiers:
                    source = os.path.join(racine, SUPERSLO_PKL)
                    break
    if source is None:
        return None
    try:
        os.makedirs(os.path.dirname(LOCAL_PKL), exist_ok=True)
        shutil.copy2(source, LOCAL_PKL)
        _journal(f"poids superslo copies : {source} -> models/{SUPERSLO_PKL}")
        return LOCAL_PKL
    except OSError as e:
        _journal(f"copie des poids superslo impossible ({e}), "
                 f"utilisation directe de {source}")
        return source


class RifeInterpolator:
    """ok = pret ; status = texte pour le panneau de reglages."""

    def __init__(self, require_cuda=True, warmup_size=(128, 128)):
        self.ok = False
        self.status = "RIFE : non charge"
        self._warmup_size = warmup_size
        self._cache_key = None      # cache GPU du couple d'images courant
        self._t0 = self._t1 = None
        try:
            import torch
            self._torch = torch
            if require_cuda and not torch.cuda.is_available():
                self.status = "RIFE : GPU CUDA requis"
                _journal(f"CUDA indisponible (torch {torch.__version__}, "
                         f"build CUDA {torch.version.cuda}) : verifier que "
                         f"lancer.bat a bien installe torch cu124")
                return
            self.device = torch.device("cuda" if torch.cuda.is_available()
                                       else "cpu")
            # FP16 reel (methode superslo) : poids et tenseurs en demi-
            # precision — necessaire pour tenir 60 im/s (budget 16,7 ms)
            self.fp16 = self.device.type == "cuda"
            if self.fp16:
                torch.backends.cudnn.benchmark = True

            chemin = _trouver_poids_superslo()
            if chemin is not None:
                try:
                    self.net = self._charger(chemin, "4.26")
                    self.modele, self.arch = "RIFE 4.26 superslo", "4.26"
                except Exception as e:
                    _journal(f"poids superslo illisibles ou incompatibles "
                             f"({chemin}) : {e} -> repli sur RIFE 4.9")
                    chemin = None
            if chemin is None:
                _journal(f"poids superslo introuvables (models/{SUPERSLO_PKL}"
                         f" puis {SUPERSLO_DIR}) : repli sur RIFE 4.9 — "
                         f"verifier dir C:\\Users\\evalh\\SUPERSLO")
                self.net = self._charger(_ensure_weights(), "4.7")
                self.modele, self.arch = "RIFE 4.9 repli", "4.7"
            self.scale_list = SCALE_LISTS[self.arch]

            self._warmup()
            # ok seulement une fois le warm-up passe : une init a moitie
            # reussie ferait planter la boucle d'affichage a chaque image
            self.ok = True
            self.status = (f"{self.modele} pret ({self.device.type.upper()}"
                           f"{', fp16' if self.fp16 else ''})")
            nom_gpu = (torch.cuda.get_device_name(0)
                       if self.device.type == "cuda" else "CPU")
            h, w = self._warmup_size
            _journal(f"verif GPU : {self.modele} sur "
                     f"{next(self.net.parameters()).device} ({nom_gpu}) | "
                     f"fp16 reel : {'oui' if self.fp16 else 'non'} | "
                     f"warm-up {w}x{h} synchronise : pleine "
                     f"{self.warmup_ms['pleine']:.1f} ms, demi "
                     f"{self.warmup_ms['demi']:.1f} ms | memoire GPU "
                     f"{self.gpu_mem_mb()} Mo")
        except Exception as e:
            self.status = f"RIFE : erreur ({type(e).__name__})"
            _journal(f"init impossible : {e}\n{traceback.format_exc()}")

    def _charger(self, chemin, arch):
        """Charge un jeu de poids sur le device (en FP16 reel sur CUDA)."""
        torch = self._torch
        from rife_arch import IFNet
        net = IFNet(arch_ver=arch)
        sd = torch.load(chemin, map_location="cpu", weights_only=True)
        sd = {k.replace("module.", ""): v for k, v in sd.items()}
        net.load_state_dict(sd)
        net.eval().to(self.device)
        if self.fp16:
            net = net.half()
        return net

    def _warmup(self):
        """Chauffe GPU (comme slowcam) : passages a vide a la taille reelle
        des images (pleine et demie), qui initialisent les kernels CUDA et
        l'autotune cudnn, puis un passage synchronise chronometre par
        palier — c'est la preuve mesuree de l'execution GPU (un 720p en
        ~10 ms est impossible sur CPU)."""
        import numpy as np
        torch = self._torch
        vide = np.zeros((*self._warmup_size, 3), np.uint8)
        debut = time.monotonic()
        self.warmup_ms = {}
        for half, nom in ((False, "pleine"), (True, "demi")):
            for _ in range(2):
                self.interpolate(vide, vide, 0.5, half=half)
            if self.device.type == "cuda":
                torch.cuda.synchronize()
            t0 = time.monotonic()
            self.interpolate(vide, vide, 0.4, half=half)
            if self.device.type == "cuda":
                torch.cuda.synchronize()
            self.warmup_ms[nom] = (time.monotonic() - t0) * 1000.0
            self._cache_key = None
        _journal(f"chauffe GPU : {time.monotonic() - debut:.1f} s")

    def gpu_mem_mb(self):
        """Memoire GPU allouee par ce processus (Mo) ; 0 hors CUDA."""
        if getattr(self, "device", None) is None or self.device.type != "cuda":
            return 0
        return int(self._torch.cuda.memory_allocated() // (1 << 20))

    def _to_tensor(self, img):
        torch = self._torch
        t = (torch.from_numpy(img).to(self.device)
             .permute(2, 0, 1).unsqueeze(0).float() / 255.0)
        return t.half() if self.fp16 else t

    def interpolate(self, img0, img1, t, pair_key=None, half=False):
        """Image intermediaire entre img0 et img1 (BGR uint8) a l'instant t.

        pair_key : identifiant du couple (img0, img1). En ralenti, le meme
        couple sert a des dizaines d'images de suite : ses tenseurs GPU sont
        gardes en cache, seul t change (economise les transferts CPU->GPU).
        half : interpole en demi-resolution puis remonte a la taille d'origine
        (~4x moins cher) — mode degrade quand la pleine resolution ne tient
        pas dans le budget des 60 im/s. (Sans rapport avec le FP16, qui est
        la precision de calcul, active en permanence sur CUDA.)
        """
        import cv2
        torch = self._torch
        with torch.inference_mode():
            key = (pair_key, half)
            if pair_key is None or key != self._cache_key:
                if half:
                    h, w = img0.shape[:2]
                    a = cv2.resize(img0, (w // 2, h // 2))
                    b = cv2.resize(img1, (w // 2, h // 2))
                else:
                    a, b = img0, img1
                self._t0, self._t1 = self._to_tensor(a), self._to_tensor(b)
                self._cache_key = key
            t0, t1 = self._t0, self._t1
            out = self.net(t0, t1, timestep=float(t),
                           scale_list=self.scale_list, training=False)
            out = (out[0].float().clamp(0, 1) * 255.0).byte()
            res = out.permute(1, 2, 0).contiguous().cpu().numpy()
        if half:
            res = cv2.resize(res, (img0.shape[1], img0.shape[0]),
                             interpolation=cv2.INTER_LINEAR)
        return res
