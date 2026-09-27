"""
Tableau de controle de la camera (Windows).

1. Mesure ce que la camera sait vraiment faire : pour chaque combinaison
   resolution x cadence demandee, ce que le pilote accorde et la cadence
   reellement mesuree sur 40 images. Resultat affiche et ecrit dans
   camera_controle.txt.
2. Ouvre le panneau de reglages du pilote (exposition, luminosite...) via
   DirectShow, avec un apercu en direct pour voir l'effet des reglages.

Lancer : double-clic sur camera_controle.bat (ou python camera_controle.py)
Quitter l'apercu : Q ou Echap.
"""

import time

import cv2

CAM_INDEX = 0
RAPPORT   = "camera_controle.txt"

# combinaisons a tester : (largeur, hauteur, cadence demandee)
MODES = [
    (640,  480,  30), (640,  480,  60),
    (1280, 720,  30), (1280, 720,  60),
    (1920, 1080, 30), (1920, 1080, 60),
]

lignes = []


def dire(txt=""):
    print(txt)
    lignes.append(txt)


def mesurer_fps(cap, n=40, warmup=5):
    """Cadence reelle : n images chronometrees apres warmup images."""
    for _ in range(warmup):
        cap.read()
    t0 = time.monotonic()
    lues = 0
    for _ in range(n):
        ok, _ = cap.read()
        if ok:
            lues += 1
    dt = time.monotonic() - t0
    return (lues / dt) if dt > 0 else 0.0


def tester_mode(backend, w, h, fps):
    cap = cv2.VideoCapture(CAM_INDEX, backend)
    if not cap.isOpened():
        return None
    # MJPG debloque souvent les cadences elevees en HD (l'USB sature en brut)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    obtenu = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
              int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
              cap.get(cv2.CAP_PROP_FPS))
    reel = mesurer_fps(cap)
    cap.release()
    return obtenu, reel


def main():
    dire("=== Tableau de controle camera — " + time.strftime("%d-%m-%Y %H:%M") + " ===")
    dire()

    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(("DirectShow", cv2.CAP_DSHOW))
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(("MediaFoundation", cv2.CAP_MSMF))
    if not backends:
        backends = [("defaut", cv2.CAP_ANY)]

    for nom, backend in backends:
        dire(f"--- Backend {nom} ---")
        dispo = False
        for w, h, fps in MODES:
            res = tester_mode(backend, w, h, fps)
            if res is None:
                dire("  camera introuvable avec ce backend")
                break
            (ow, oh, ofps), reel = res
            dispo = True
            ok = "OK " if reel >= fps - 3 else "NON"
            dire(f"  demande {w}x{h}@{fps:2d}  ->  accorde {ow}x{oh}@{ofps:.0f}"
                 f"  |  mesure {reel:5.1f} im/s  {ok}")
        if dispo:
            dire()

    try:
        with open(RAPPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(lignes) + "\n")
        dire(f"Rapport ecrit dans {RAPPORT}")
    except OSError:
        pass

    # --- panneau de reglages du pilote + apercu en direct ---
    dire()
    dire("Ouverture du panneau de reglages du pilote (DirectShow)...")
    dire("Reglez, observez l'apercu ; Q ou Echap pour quitter.")
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
    cap = cv2.VideoCapture(CAM_INDEX, backend)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        dire("Impossible d'ouvrir la camera pour l'apercu.")
        return
    cap.set(cv2.CAP_PROP_SETTINGS, 1)          # panneau du constructeur

    fps_meas, prev = 0.0, time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.monotonic()
        dt, prev = now - prev, now
        fps_meas = 0.9 * fps_meas + 0.1 * (1.0 / dt if dt > 0 else 0.0)
        h, w = frame.shape[:2]
        txt = f"{w}x{h}  {fps_meas:.1f} im/s reels"
        cv2.putText(frame, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, txt, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow("Apercu camera", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q'), 27):
            break
        if cv2.getWindowProperty("Apercu camera", cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
