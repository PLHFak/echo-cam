"""
Projet ECHO — Jouer avec le temps (V2, socle)
---------------------------------------------
La webcam filme la personne. Plus elle s'approche de l'ecran, plus la lecture
ralentit ; tout pres, l'image se fige. Quand elle recule, la lecture reprend
puis accelere pour rattraper le direct. Immobile N secondes : la position
courante devient la reference 0 (lecture en direct).

Socle V2 : panneau lateral de reglages (curseurs + etat en direct) et
verification PyTorch/CUDA au demarrage. Les briques RIFE (interpolation,
touche I) et fond virtuel (touche V) arrivent dans les etapes suivantes.

Dependances : voir requirements.txt (mediapipe 0.10.21, torch cu124, Py 3.11/3.12)
Lancer :      double-clic sur lancer.bat (Windows) ou python main.py
Touches :     C = calibrer   |   1..9, 0 = duree d'immobilite (1..10 s)
              avant nouvelle reference   |   Q = quitter
"""

import time
from bisect import bisect_left
from collections import deque

import cv2
import numpy as np
import mediapipe as mp

# ---------------------------------------------------------------------------
# Parametres par defaut (modifiables en direct via le panneau de reglages)
# ---------------------------------------------------------------------------
CAM_INDEX      = 0        # 0 = webcam par defaut
CAP_WIDTH      = 1280
CAP_HEIGHT     = 720
FPS            = 30       # sert au dimensionnement du buffer

DIST_STOP      = 0.5      # m — en dessous, image figee
DIST_FULL      = 2.0      # m — au dessus, direct / rattrapage
CATCHUP_SPEED  = 2.5      # vitesse de rattrapage du direct
BUFFER_SECONDS = 12       # profondeur memoire (12 s * 30 fps * 720p ~ 1 Go RAM)
SMOOTH_WINDOW  = 8        # lissage de la distance (nb de mesures)
ABSENT_TIMEOUT = 10.0     # s — sans detection, on garde la derniere distance
                          #     puis on considere la salle vide -> direct
STABLE_TOL     = 0.15     # ±15 % de variation de largeur d'epaules = immobile
STABLE_SECONDS = 10.0     # duree d'immobilite avant nouvelle reference (1..9, 0)

CALIB_DISTANCE = 2.0      # distance (m) de la calibration manuelle (touche C)

WIN_MAIN  = "ECHO"
WIN_PANEL = "ECHO - Reglages"

# ---------------------------------------------------------------------------
# Etat GPU (PyTorch/CUDA) — verifie une fois au demarrage
# ---------------------------------------------------------------------------
def gpu_status():
    try:
        import torch
        if torch.cuda.is_available():
            return True, f"CUDA OK : {torch.cuda.get_device_name(0)}"
        return False, "PyTorch installe, CUDA indisponible"
    except Exception as e:                                  # torch absent/casse
        return False, f"PyTorch absent ({type(e).__name__})"


# ---------------------------------------------------------------------------
def speed_for_distance(d, delay, d_stop, d_full, catchup):
    """Vitesse de lecture v selon la distance d et le retard courant (s).
    d = None signifie : pas de calibration ou salle vide -> retour au direct."""
    if d is None or d >= d_full:
        return catchup if delay > 0 else 1.0
    if d <= d_stop:
        return 0.0
    return (d - d_stop) / (d_full - d_stop)                # varie de 0 a 1


def shoulder_width_px(landmarks, w, h):
    """Largeur d'epaules en pixels (landmarks 11 et 12)."""
    ls, rs = landmarks[11], landmarks[12]
    if ls.visibility < 0.5 or rs.visibility < 0.5:
        return None
    return float(np.hypot((ls.x - rs.x) * w, (ls.y - rs.y) * h))


def draw_text(img, text, y, scale=0.9):
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (255, 255, 255), 2, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Panneau lateral de reglages
# ---------------------------------------------------------------------------
def panel_create():
    cv2.namedWindow(WIN_PANEL, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_PANEL, 460, 560)
    nop = lambda v: None
    cv2.createTrackbar("Arret (cm)",      WIN_PANEL, int(DIST_STOP * 100), 300, nop)
    cv2.createTrackbar("Direct (cm)",     WIN_PANEL, int(DIST_FULL * 100), 500, nop)
    cv2.createTrackbar("Rattrapage x10",  WIN_PANEL, int(CATCHUP_SPEED * 10), 60, nop)
    cv2.createTrackbar("Buffer (s)",      WIN_PANEL, BUFFER_SECONDS, 60, nop)
    cv2.createTrackbar("Immobilite (s)",  WIN_PANEL, int(STABLE_SECONDS), 30, nop)


def panel_read():
    """Lit les curseurs ; retourne (d_stop, d_full, catchup, buffer_s, stable_s)."""
    d_stop   = max(10, cv2.getTrackbarPos("Arret (cm)",  WIN_PANEL)) / 100.0
    d_full   = max(20, cv2.getTrackbarPos("Direct (cm)", WIN_PANEL)) / 100.0
    if d_full <= d_stop:
        d_full = d_stop + 0.1
    catchup  = max(11, cv2.getTrackbarPos("Rattrapage x10", WIN_PANEL)) / 10.0
    buffer_s = max(2,  cv2.getTrackbarPos("Buffer (s)",     WIN_PANEL))
    stable_s = max(1,  cv2.getTrackbarPos("Immobilite (s)", WIN_PANEL))
    return d_stop, d_full, catchup, buffer_s, stable_s


def panel_draw(lines):
    img = np.full((250, 460, 3), 30, np.uint8)
    for i, (txt, ok) in enumerate(lines):
        color = (120, 255, 120) if ok else (120, 120, 255)
        cv2.putText(img, txt, (15, 35 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    0.62, color, 1, cv2.LINE_AA)
    cv2.imshow(WIN_PANEL, img)


# ---------------------------------------------------------------------------
def main():
    cuda_ok, cuda_txt = gpu_status()
    print(f"[ECHO] {cuda_txt}")

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        raise SystemExit("Impossible d'ouvrir la webcam (verifier CAM_INDEX).")

    pose = mp.solutions.pose.Pose(model_complexity=1,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

    buffer_s   = BUFFER_SECONDS
    max_frames = int(buffer_s * FPS)
    buffer     = deque(maxlen=max_frames)    # images brutes (BGR)
    stamps     = deque(maxlen=max_frames)    # heure de capture de chaque image
    widths     = deque(maxlen=SMOOTH_WINDOW) # largeurs d'epaules recentes

    ref_width  = None    # largeur d'epaules de la position de reference
    delay      = 0.0     # retard courant (s) par rapport au direct
    last_dist  = None    # derniere distance mesuree
    last_seen  = 0.0     # heure de la derniere detection
    anchor_w     = None  # largeur d'epaules au debut de la periode d'immobilite
    stable_since = 0.0
    stable_keys  = None  # duree fixee par les touches 1..0 (prioritaire sur curseur)
    prev_t     = time.monotonic()
    fps_meas   = 0.0

    cv2.namedWindow(WIN_MAIN, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WIN_MAIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    panel_create()

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.monotonic()
        dt, prev_t = now - prev_t, now
        fps_meas = 0.9 * fps_meas + 0.1 * (1.0 / dt if dt > 0 else 0.0)

        d_stop, d_full, catchup, want_buffer_s, stable_panel = panel_read()
        stable_secs = stable_keys if stable_keys is not None else float(stable_panel)

        # --- redimensionnement du buffer en direct ---
        if want_buffer_s != buffer_s:
            buffer_s   = want_buffer_s
            max_frames = int(buffer_s * FPS)
            buffer = deque(buffer, maxlen=max_frames)
            stamps = deque(stamps, maxlen=max_frames)

        buffer.append(frame)
        stamps.append(now)
        h, w = frame.shape[:2]

        # --- estimation de la distance ---
        res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        distance = None
        if res.pose_landmarks:
            sw = shoulder_width_px(res.pose_landmarks.landmark, w, h)
            if sw:
                widths.append(sw)
                sw_smooth = float(np.mean(widths))

                # immobile depuis stable_secs (±STABLE_TOL) ? -> nouvelle reference
                if anchor_w is None or abs(sw_smooth - anchor_w) > STABLE_TOL * anchor_w:
                    anchor_w, stable_since = sw_smooth, now
                elif now - stable_since >= stable_secs:
                    ref_width = sw_smooth
                    anchor_w, stable_since = sw_smooth, now

                if ref_width:
                    distance = CALIB_DISTANCE * (ref_width / sw_smooth)
                    last_dist, last_seen = distance, now

        # --- personne perdue : garder la derniere distance, puis salle vide ---
        if distance is None and last_dist is not None:
            if now - last_seen < ABSENT_TIMEOUT:
                distance = last_dist
            else:
                last_dist = None
                widths.clear()

        # --- mise a jour du retard (secondes reelles) ---
        v = speed_for_distance(distance, delay, d_stop, d_full, catchup)
        delay += (1.0 - v) * dt
        delay = max(0.0, min(delay, now - stamps[0]))

        # --- image a afficher : celle capturee a (now - delay) ---
        # (etape suivante : interpolation RIFE entre les deux voisines)
        idx = bisect_left(stamps, now - delay)
        out = buffer[min(idx, len(buffer) - 1)].copy()
        out = cv2.flip(out, 1)                  # effet miroir horizontal

        # --- overlays ---
        if ref_width is None:
            draw_text(out, f"Restez immobile {stable_secs:.0f}s (ou C) pour calibrer", 60)
        d_txt = f"{distance:.2f} m" if distance else "--"
        panel_draw([
            (cuda_txt, cuda_ok),
            (f"Distance : {d_txt}", distance is not None),
            (f"Vitesse : {v:.2f}   Retard : {delay:.1f} s", True),
            (f"Camera : {fps_meas:.0f} im/s", fps_meas > 20),
            (f"Reference : {'calibree' if ref_width else 'en attente'}", ref_width is not None),
            (f"Nouvelle ref apres {stable_secs:.0f} s immobile", True),
            (f"Buffer : {len(buffer) / FPS:.0f} / {buffer_s} s", True),
            ("Touches : C ref, 1..0 duree, Q quitter", True),
        ])
        cv2.imshow(WIN_MAIN, out)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('c') and widths:
            ref_width = float(np.mean(widths))
            delay = 0.0
            last_dist = None
            anchor_w = None
        if ord('0') <= key <= ord('9'):         # duree d'immobilite : 1..9 s, 0 = 10 s
            stable_keys = 10.0 if key == ord('0') else float(key - ord('0'))

    cap.release()
    pose.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
