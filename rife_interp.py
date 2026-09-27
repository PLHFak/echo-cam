"""
Interpolation RIFE pour le projet ECHO.

Charge le modele RIFE 4.9 (architecture 4.7) et fabrique l'image intermediaire
entre deux images du buffer, a un instant t quelconque (0 < t < 1).
Les poids (~21 Mo) sont telecharges au premier lancement dans models/.

Usage :
    rife = RifeInterpolator()          # rife.ok, rife.status
    out  = rife.interpolate(img0, img1, t)   # images BGR uint8, t dans [0, 1]
"""

import hashlib
import os
import urllib.request

WEIGHTS_URL    = ("https://github.com/Fannovel16/ComfyUI-Frame-Interpolation"
                  "/releases/download/models/rife49.pth")
WEIGHTS_SHA256 = "e55fd00f3cc184e3c65961f4bb827a9da022e78eed36b055242c0ac30000d533"
WEIGHTS_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "models", "rife49.pth")
ARCH_VER       = "4.7"
SCALE_LIST     = [8, 4, 2, 1]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _ensure_weights():
    """Telecharge les poids si absents ou corrompus. Retourne le chemin."""
    if os.path.exists(WEIGHTS_FILE) and _sha256(WEIGHTS_FILE) == WEIGHTS_SHA256:
        return WEIGHTS_FILE
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    print("[ECHO] Telechargement du modele RIFE (~21 Mo)...")
    tmp = WEIGHTS_FILE + ".part"
    urllib.request.urlretrieve(WEIGHTS_URL, tmp)
    if _sha256(tmp) != WEIGHTS_SHA256:
        os.remove(tmp)
        raise RuntimeError("modele RIFE telecharge corrompu")
    os.replace(tmp, WEIGHTS_FILE)
    print("[ECHO] Modele RIFE pret.")
    return WEIGHTS_FILE


class RifeInterpolator:
    """ok = pret ; status = texte pour le panneau de reglages."""

    def __init__(self, require_cuda=True, warmup_size=(128, 128)):
        self.ok = False
        self.status = "RIFE : non charge"
        self._warmup_size = warmup_size
        try:
            import torch
            self._torch = torch
            if require_cuda and not torch.cuda.is_available():
                self.status = "RIFE : GPU CUDA requis"
                return
            path = _ensure_weights()

            from rife_arch import IFNet
            self.device = torch.device("cuda" if torch.cuda.is_available()
                                       else "cpu")
            # demi-precision + autotune cudnn : necessaires pour tenir
            # 60 im/s (budget 16,7 ms par image interpolee)
            self.autocast = self.device.type == "cuda"
            if self.autocast:
                torch.backends.cudnn.benchmark = True
            net = IFNet(arch_ver=ARCH_VER)
            sd = torch.load(path, map_location="cpu", weights_only=True)
            sd = {k.replace("module.", ""): v for k, v in sd.items()}
            net.load_state_dict(sd)
            net.eval().to(self.device)
            self.net = net
            self.ok = True
            self.status = f"RIFE 4.9 pret ({self.device.type.upper()})"
            self._warmup()
        except Exception as e:
            self.status = f"RIFE : erreur ({type(e).__name__})"
            print(f"[ECHO] RIFE indisponible : {e}")

    def _warmup(self):
        """Passages a vide a la taille reelle des images : initialise les
        kernels CUDA et l'autotune cudnn pour que la premiere vraie
        interpolation ne prenne pas plusieurs centaines de ms."""
        import numpy as np
        vide = np.zeros((*self._warmup_size, 3), np.uint8)
        for _ in range(3):
            self.interpolate(vide, vide, 0.5)

    def interpolate(self, img0, img1, t):
        """Image intermediaire entre img0 et img1 (BGR uint8) a l'instant t."""
        torch = self._torch
        with torch.inference_mode():
            t0 = (torch.from_numpy(img0).to(self.device)
                  .permute(2, 0, 1).unsqueeze(0).float() / 255.0)
            t1 = (torch.from_numpy(img1).to(self.device)
                  .permute(2, 0, 1).unsqueeze(0).float() / 255.0)
            if self.autocast:
                with torch.autocast("cuda", dtype=torch.float16):
                    out = self.net(t0, t1, timestep=float(t),
                                   scale_list=SCALE_LIST, training=False)
            else:
                out = self.net(t0, t1, timestep=float(t),
                               scale_list=SCALE_LIST, training=False)
            out = (out[0].float().clamp(0, 1) * 255.0).byte()
            return out.permute(1, 2, 0).contiguous().cpu().numpy()
