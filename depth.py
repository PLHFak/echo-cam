"""Distance par profondeur IA — Depth Anything V2 (metric, interieur).

Remplace la largeur d'epaules comme mesure principale (spec V1 §2) :
- carte de profondeur dense en METRES (variante "metric indoor"), robuste
  quand la personne pivote ;
- MediaPipe Pose ne sert plus qu'a localiser le torse ; on lit la profondeur
  MEDIANE d'une fenetre autour de ce point.

Modele telecharge au premier lancement (Hugging Face, ~100 Mo), puis en
cache local. GPU (fp16) si CUDA est disponible. L'ancienne methode
"largeur d'epaules" reste en secours, selectionnable dans l'interface.
"""

import time

import cv2
import numpy as np

MODEL_ID = "depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf"
INFER_WIDTH = 518          # largeur d'inference (le modele travaille en ~518)
WINDOW_FRAC = 0.06         # demi-fenetre de lecture autour du torse (fraction)


class DepthEstimator:
    """Charge Depth Anything V2 metric ; distance_at() rend des metres."""

    def __init__(self):
        self.ok = False
        self.status = "Profondeur IA : non chargee"
        self.last_ms = 0.0
        self.device = "cpu"
        try:
            import torch
            from transformers import (AutoImageProcessor,
                                      AutoModelForDepthEstimation)
            self._torch = torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self._fp16 = self.device == "cuda"
            self._proc = AutoImageProcessor.from_pretrained(MODEL_ID)
            self._model = AutoModelForDepthEstimation.from_pretrained(
                MODEL_ID,
                torch_dtype=torch.float16 if self._fp16 else torch.float32)
            self._model.eval().to(self.device)
            self._infer(np.zeros((240, 320, 3), np.uint8))     # warm-up
            self.ok = True
            self.status = f"Profondeur IA : Depth Anything V2 ({self.device})"
        except Exception as e:                  # modele absent / pas de reseau
            self.status = (f"Profondeur IA indisponible ({type(e).__name__}) "
                           f"-> secours epaules")

    def _infer(self, frame_bgr):
        """Carte de profondeur (metres), meme rapport d'aspect que l'image."""
        torch = self._torch
        h, w = frame_bgr.shape[:2]
        small = cv2.resize(frame_bgr, (INFER_WIDTH, max(2, INFER_WIDTH * h // w)))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        inputs = self._proc(images=rgb, return_tensors="pt")
        pix = inputs["pixel_values"].to(self.device)
        if self._fp16:
            pix = pix.half()
        with torch.no_grad():
            out = self._model(pixel_values=pix)
        depth = out.predicted_depth[0].float().cpu().numpy()
        return depth

    def distance_at(self, frame_bgr, cx, cy):
        """Distance (m) au point normalise (cx, cy) : mediane d'une fenetre.
        Rend None si la lecture n'est pas exploitable."""
        t0 = time.monotonic()
        depth = self._infer(frame_bgr)
        self.last_ms = 0.8 * self.last_ms + 0.2 * (time.monotonic() - t0) * 1000.0
        dh, dw = depth.shape
        x, y = int(cx * dw), int(cy * dh)
        r = max(2, int(WINDOW_FRAC * dw))
        y0, y1 = max(0, y - r), min(dh, y + r + 1)
        x0, x1 = max(0, x - r), min(dw, x + r + 1)
        zone = depth[y0:y1, x0:x1]
        zone = zone[np.isfinite(zone)]
        zone = zone[(zone > 0.1) & (zone < 25.0)]
        if zone.size < 8:
            return None
        return float(np.median(zone))
