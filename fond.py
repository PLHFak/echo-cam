"""Detourage temps reel + incrustation sur fond virtuel (galerie, etapes 1-2).

- Segmenter : MediaPipe Selfie Segmentation, masque personne/fond calcule a
  chaque image camera en basse resolution (rapide, ~2-4 ms CPU).
- Compositor : incruste la personne sur un fond. Si un fichier fond.jpg ou
  fond.png existe dans le dossier, il est utilise ; sinon, fond de test
  "galerie" genere (murs, sol, cadres). Les etapes suivantes remplaceront ce
  fond par l'image vivante de la galerie Unity (via Spout).
"""

import os
import threading
import time

import cv2
import numpy as np

MASK_W = 256          # largeur du masque calcule (basse resolution, suffit)
FEATHER = 7           # adoucissement du bord (pixels, a la resolution finale)


class Segmenter:
    def __init__(self):
        self.ok = False
        self.status = "Detourage : non charge"
        try:
            import mediapipe as mp
            self._seg = mp.solutions.selfie_segmentation.SelfieSegmentation(
                model_selection=1)
            self.ok = True
            self.status = "Detourage : MediaPipe pret"
        except Exception as e:
            self.status = f"Detourage indisponible ({type(e).__name__})"

    def mask(self, frame_bgr):
        """Masque float32 [0..1] basse resolution (1 = personne), ou None."""
        h, w = frame_bgr.shape[:2]
        small = cv2.resize(frame_bgr, (MASK_W, MASK_W * h // w))
        res = self._seg.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        if res.segmentation_mask is None:
            return None
        return res.segmentation_mask.astype(np.float32)

    def close(self):
        if self.ok:
            self._seg.close()


def fond_test(w, h):
    """Fond de test facon galerie : murs degrades, sol, cadres."""
    img = np.zeros((h, w, 3), np.uint8)
    for y in range(h):                                   # mur degrade
        t = y / h
        img[y, :] = (int(38 + 30 * t), int(34 + 26 * t), int(30 + 22 * t))
    sol_y = int(h * 0.78)
    img[sol_y:, :] = (54, 48, 44)                        # sol
    cv2.line(img, (0, sol_y), (w, sol_y), (80, 72, 66), 2)
    rng = np.random.default_rng(7)
    for cx in range(int(w * 0.06), w, int(w * 0.22)):    # cadres au mur
        cw, ch = int(w * 0.10), int(h * 0.22)
        y0 = int(h * 0.22)
        cv2.rectangle(img, (cx, y0), (cx + cw, y0 + ch), (26, 24, 22), -1)
        couleur = tuple(int(c) for c in rng.integers(60, 180, 3))
        cv2.rectangle(img, (cx + 6, y0 + 6), (cx + cw - 6, y0 + ch - 6),
                      couleur, -1)
        cv2.rectangle(img, (cx, y0), (cx + cw, y0 + ch), (90, 84, 78), 2)
    return img


class Compositor:
    def __init__(self, w, h, log=None):
        self.source = "fond de test"
        fond = None
        for nom in ("fond.jpg", "fond.png"):
            chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), nom)
            if os.path.exists(chemin):
                fond = cv2.imread(chemin)
                if fond is not None:
                    self.source = nom
                    break
        if fond is None:
            fond = fond_test(w, h)
        self.fond = cv2.resize(fond, (w, h))
        self.spout = SpoutFond(w, h, log=log)

    def source_txt(self):
        return self.spout.status if self.spout.active else f"fixe ({self.source})"

    def apply(self, img, m_small):
        """Incruste img (personne) sur le fond selon le masque basse res.
        Fond vivant Spout prioritaire quand un emetteur est present."""
        h, w = img.shape[:2]
        m = cv2.resize(m_small, (w, h), interpolation=cv2.INTER_LINEAR)
        m = cv2.GaussianBlur(m, (FEATHER, FEATHER), 0)
        np.clip(m, 0.0, 1.0, out=m)
        if self.spout.active and self.spout.frame is not None:
            fond = self.spout.frame
        else:
            fond = self.fond
        # melange natif OpenCV (SIMD, multi-coeurs) : ~5x plus rapide que
        # l'arithmetique numpy 16 bits plein cadre utilisee avant.
        return cv2.blendLinear(img, fond, m, 1.0 - m)


GL_RGBA = 0x1908          # constante OpenGL (evite d'importer PyOpenGL)
SPOUT_TIMEOUT = 2.0       # s sans image -> retour au fond fixe


class SpoutFond:
    """Fond vivant recu par Spout (etape 2 : Unity, OBS, TouchDesigner...).
    Thread de reception ; self.frame (BGR, taille ECHO) quand self.active."""

    def __init__(self, w, h, log=None):
        self.w, self.h = w, h
        self.frame = None
        self.active = False
        self.ok = False
        self.status = "Spout : non disponible"
        self._log = log if log is not None else (
            lambda cat, msg: print(f"[{cat}] {msg}"))
        try:
            import SpoutGL                       # Windows uniquement
            self._SpoutGL = SpoutGL
            self.ok = True
            self.status = "Spout : en attente d'un emetteur"
            self._log("spout", "recepteur demarre, en attente d'un emetteur")
            threading.Thread(target=self._run, daemon=True).start()
        except Exception as e:
            self.status = f"Spout : non disponible ({type(e).__name__})"
            self._log("spout", self.status)

    def _run(self):
        import array
        SpoutGL = self._SpoutGL
        receiver = SpoutGL.SpoutReceiver()
        receiver.setReceiverName("")             # premier emetteur trouve
        buf, w, h, last = None, 0, 0, 0.0
        while True:
            try:
                res = receiver.receiveImage(buf, GL_RGBA, False, 0)
                if receiver.isUpdated():
                    w = receiver.getSenderWidth()
                    h = receiver.getSenderHeight()
                    if w > 0 and h > 0:
                        buf = array.array('B', bytes(w * h * 4))
                    continue
                if res and buf is not None and w > 0:
                    img = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                    self.frame = cv2.resize(img, (self.w, self.h))
                    if not self.active:
                        self.status = (f"Spout : '{receiver.getSenderName()}' "
                                       f"{w}x{h}")
                        self._log("spout", f"emetteur trouve : "
                                           f"'{receiver.getSenderName()}' {w}x{h}")
                    self.active = True
                    last = time.monotonic()
                elif self.active and time.monotonic() - last > SPOUT_TIMEOUT:
                    self.active = False
                    self.status = "Spout : emetteur perdu, fond fixe"
                    self._log("spout", "emetteur perdu, retour au fond fixe")
            except Exception as e:               # jamais fatal
                self.ok = False
                self.active = False
                self.status = f"Spout : erreur ({type(e).__name__})"
                self._log("spout", f"erreur, reception arretee : {e}")
                return
            time.sleep(1.0 / 60.0)
