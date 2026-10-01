"""Emetteur Spout de test : envoie un decor anime (1280x720, 30 im/s)
sous le nom "ECHO-TEST". Sert a valider la chaine fond vivant -> ECHO
sans Unity : lancer ECHO (lancer.bat), activer le fond (touche V), puis
double-cliquer emetteur_test.bat -> le fond de test devient anime.
Ctrl+C ou fermer la fenetre pour arreter.
"""

import math
import time

import numpy as np

GL_RGBA = 0x1908
W, H = 1280, 720


def image(t):
    """Decor anime : bandes verticales qui defilent + horizon."""
    img = np.zeros((H, W, 4), np.uint8)
    x = (np.arange(W) + int(t * 120)) % 240
    bande = (x < 120).astype(np.uint8)
    img[:, :, 0] = 40 + 50 * bande                      # R
    img[:, :, 1] = 45 + 40 * bande
    img[:, :, 2] = 60 + 30 * bande
    y0 = int(H * (0.72 + 0.03 * math.sin(t)))
    img[y0:, :, :3] = (70, 62, 55)
    img[:, :, 3] = 255
    return img


def main():
    import SpoutGL
    sender = SpoutGL.SpoutSender()
    sender.setSenderName("ECHO-TEST")
    print("Emetteur Spout 'ECHO-TEST' en cours (Ctrl+C pour arreter)...")
    t0 = time.monotonic()
    while True:
        img = image(time.monotonic() - t0)
        sender.sendImage(img.tobytes(), W, H, GL_RGBA, False, 0)
        sender.setFrameSync("ECHO-TEST")
        time.sleep(1.0 / 30.0)


if __name__ == "__main__":
    main()
