"""Interpolateur RIFE v4.7 pour ECHO.

Charge les poids (rife47.pth, telecharges par lancer.bat) et fournit
interpolate(frame_a, frame_b, t) -> image intermediaire a l'instant t (0..1).
Images BGR uint8 (OpenCV). Calcul sur GPU (fp16) si CUDA est disponible.
"""

import os

import numpy as np
import torch

from rife_arch import IFNet

WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rife47.pth")
ARCH_VER = "4.7"
SCALE_LIST = [8, 4, 2, 1]


class Rife:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.fp16 = self.device.type == "cuda"
        self.net = IFNet(arch_ver=ARCH_VER)
        sd = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
        self.net.load_state_dict(sd, strict=True)
        self.net.eval().to(self.device)
        if self.fp16:
            self.net.half()

    def _to_tensor(self, img):
        t = torch.from_numpy(img).to(self.device)
        t = t.permute(2, 0, 1).unsqueeze(0).float() / 255.0
        return t.half() if self.fp16 else t

    @torch.no_grad()
    def interpolate(self, frame_a, frame_b, t):
        """Image entre frame_a (t=0) et frame_b (t=1), a l'instant t."""
        if t <= 0.02:
            return frame_a
        if t >= 0.98:
            return frame_b
        h, w = frame_a.shape[:2]
        pad_h = (32 - h % 32) % 32
        pad_w = (32 - w % 32) % 32
        i0 = self._to_tensor(frame_a)
        i1 = self._to_tensor(frame_b)
        if pad_h or pad_w:
            i0 = torch.nn.functional.pad(i0, (0, pad_w, 0, pad_h), mode="replicate")
            i1 = torch.nn.functional.pad(i1, (0, pad_w, 0, pad_h), mode="replicate")
        out = self.net(i0, i1, timestep=float(t),
                       scale_list=SCALE_LIST, training=False)
        out = out[:, :, :h, :w].float().clamp(0, 1)
        return (out[0].permute(1, 2, 0).cpu().numpy() * 255.0).astype(np.uint8)
