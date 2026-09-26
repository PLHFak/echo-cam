"""
Jouer avec le temps — prototype
--------------------------------
La webcam filme la personne. Plus elle s'approche de l'ecran, plus la lecture
ralentit ; tout pres, l'image se fige. Quand elle recule, la lecture reprend
puis accelere pour rattraper le direct.

Prototype volontairement simple : le ralenti se fait en RE-AFFICHANT les images
du buffer (pas encore d'interpolation). Le ralenti profond saccadera donc un peu
-> c'est la brique RIFE qu'on ajoutera en V2 pour le rendre fluide.

Dependances : opencv-python, mediapipe, numpy
Lancer :      python main.py
Touches :     C = (re)calibrer a 2 m   |   Q = quitter
"""

import cv2
import numpy as np
import mediapipe as mp
from collections import deque

# ---------------------------------------------------------------------------
# Parametres (tout se regle ici)
# ---------------------------------------------------------------------------
CAM_INDEX      = 0        # 0 = webcam par defaut
CAP_WIDTH      = 1280
CAP_HEIGHT     = 720
FPS            = 30

DIST_STOP      = 0.5      # m — en dessous, image figee
DIST_FULL      = 2.0      # m — au dessus, direct / rattrapage
CATCHUP_SPEED  = 2.5      # vitesse de rattrapage du direct
BUFFER_SECONDS = 12       # profondeur memoire max (12 s * 30 fps * 720p ~ 1 Go RAM)
SMOOTH_WINDOW  = 8        # lissage de la distance (nb de mesures)

CALIB_DISTANCE = 2.0      # distance (m) a laquelle on calibre la largeur d'epaules

# ---------------------------------------------------------------------------
def speed_for_distance(d, delay):
    """Vitesse de lecture v en fonction de la distance d et du retard courant."""
    if d is None:                       # personne non detectee -> on gele
        return 0.0
    if d >= DIST_FULL:
        return 1.0 if delay <= 0.5 else CATCHUP_SPEED
    if d <= DIST_STOP:
        return 0.0
    return (d - DIST_STOP) / (DIST_FULL - DIST_STOP)   # varie de 0 a 1


def shoulder_width_px(landmarks, w, h):
    """Largeur d'epaules en pixels (landmarks 11 et 12 = epaules gauche/droite)."""
    ls, rs = landmarks[11], landmarks[12]
    if ls.visibility < 0.5 or rs.visibility < 0.5:
        return None
    dx = (ls.x - rs.x) * w
    dy = (ls.y - rs.y) * h
    return float(np.hypot(dx, dy))


def draw_text(img, text, y):
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.9, (255, 255, 255), 2, cv2.LINE_AA)


def main():
    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        raise SystemExit("Impossible d'ouvrir la webcam (verifier CAM_INDEX).")

    pose = mp.solutions.pose.Pose(model_complexity=1,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

    max_frames = int(BUFFER_SECONDS * FPS)
    buffer     = deque(maxlen=max_frames)   # images brutes (BGR)
    widths     = deque(maxlen=SMOOTH_WINDOW) # largeurs d'epaules recentes

    ref_width  = None    # largeur d'epaules mesuree a CALIB_DISTANCE (calibration)
    delay      = 0.0     # retard courant, en images, par rapport au direct

    win = "Jouer avec le temps"
    cv2.namedWindow(win, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        buffer.append(frame)
        h, w = frame.shape[:2]

        # --- estimation de la distance ---
        res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        distance = None
        if res.pose_landmarks:
            sw = shoulder_width_px(res.pose_landmarks.landmark, w, h)
            if sw:
                widths.append(sw)
                sw_smooth = float(np.mean(widths))
                if ref_width:
                    # distance ~ inversement proportionnelle a la largeur d'epaules
                    distance = CALIB_DISTANCE * (ref_width / sw_smooth)

        # --- mise a jour du retard ---
        v = speed_for_distance(distance, delay)
        delay += (1.0 - v)                      # v<1 -> on prend du retard ; v>1 -> on rattrape
        delay = max(0.0, min(delay, len(buffer) - 1))

        # --- image a afficher (V2 : interpoler entre les deux voisines) ---
        idx = len(buffer) - 1 - int(round(delay))
        out = buffer[max(0, idx)].copy()
        out = cv2.flip(out, 1)                  # effet miroir horizontal

        # --- overlay d'etat ---
        if ref_width is None:
            draw_text(out, "Placez-vous a 2 m puis pressez C pour calibrer", 60)
        else:
            d_txt = f"{distance:.2f} m" if distance else "-- (non detecte)"
            draw_text(out, f"Distance {d_txt}   Vitesse {v:.2f}   Retard {delay/FPS:.1f}s", 60)

        cv2.imshow(win, out)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        if key == ord('c') and widths:
            ref_width = float(np.mean(widths))  # calibration a la distance courante (2 m)
            delay = 0.0

    cap.release()
    pose.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
