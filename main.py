"""
Projet ECHO — Jouer avec le temps (V2 : interpolation RIFE)
-----------------------------------------------------------
La webcam filme la personne. Plus elle s'approche de l'ecran, plus la lecture
ralentit ; tout pres, l'image se fige. Quand elle recule, la lecture reprend
puis accelere pour rattraper le direct. Immobile N secondes : la position
courante devient la reference 0 (lecture en direct).

V2 : la capture et l'analyse tournent dans un thread ; l'affichage est cadence
a 60 images/s (ecran 60 Hz), independamment de la camera (30 im/s). L'image
affichee est fabriquee en permanence par RIFE (interpolation GPU) entre les
deux images voisines du buffer — en ralenti comme en direct : la camera donne
30 im/s, l'ecran recoit 60. Touche I pour couper/retablir RIFE.
Pour toujours avoir deux images autour de l'instant affiche, la lecture vit
avec une micro-latence fixe de ~50 ms (LIVE_LATENCY), imperceptible.

Dependances : voir requirements.txt (mediapipe 0.10.21, torch cu124, Py 3.11/3.12)
Lancer :      double-clic sur lancer.bat (Windows) ou python main.py
Touches :     C = calibrer   |   I = interpolation RIFE on/off
              R = reglages par defaut   |   1..9, 0 = duree d'immobilite
              Q ou Echap = quitter

Debug : les anomalies de flux (images camera manquantes, cycles d'affichage
trop longs, sauts dans la continuite de lecture) sont comptees dans le
panneau et journalisees dans la console + echo_debug.log.
"""

import threading
import time
from bisect import bisect_left
from collections import deque

import cv2
import numpy as np
import mediapipe as mp

from rife_interp import RifeInterpolator

# ---------------------------------------------------------------------------
# Parametres par defaut (modifiables en direct via le panneau de reglages)
# ---------------------------------------------------------------------------
CAM_INDEX      = 0        # 0 = webcam par defaut
CAP_WIDTH      = 1280
CAP_HEIGHT     = 720
FPS            = 30       # cadence camera, sert au dimensionnement du buffer

RENDER_FPS     = 60       # cadence d'affichage : ecran 60 Hz (la camera, elle,
                          # reste a 30 im/s ; RIFE fabrique les images entre)
LIVE_LATENCY   = 1.5 / FPS  # ~50 ms de latence fixe pour toujours avoir deux
                            # images autour de l'instant affiche (interpolation
                            # possible meme en direct)

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


# ---------------------------------------------------------------------------
# Debug : anomalies de flux (images perdues, retards de rendu, sauts)
# journalisees dans la console et dans echo_debug.log, au plus une ligne
# par categorie et par seconde (les compteurs, eux, comptent tout).
# ---------------------------------------------------------------------------
DEBUG_LOG  = "echo_debug.log"
_dbg_lock  = threading.Lock()
_dbg_last  = {}

def debug_log(cat, msg, every=1.0):
    now = time.monotonic()
    with _dbg_lock:
        if now - _dbg_last.get(cat, -1e9) < every:
            return
        _dbg_last[cat] = now
    line = time.strftime("%H:%M:%S") + f" [{cat}] {msg}"
    print("[DEBUG]", line)
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def draw_text(img, text, y, scale=0.9):
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (30, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (255, 255, 255), 2, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Panneau lateral de reglages
# ---------------------------------------------------------------------------
# curseur -> (valeur par defaut, maximum)
PANEL_DEFAULTS = {
    "Arret (cm)":     (int(DIST_STOP * 100),     300),
    "Direct (cm)":    (int(DIST_FULL * 100),     500),
    "Rattrapage x10": (int(CATCHUP_SPEED * 10),  60),
    "Buffer (s)":     (BUFFER_SECONDS,           60),
    "Immobilite (s)": (int(STABLE_SECONDS),      30),
}

# une ligne d'explication par curseur (defaut rappele entre parentheses)
PANEL_HELP = [
    "Curseurs — R = remettre les valeurs par defaut",
    "Arret (50 cm) : plus pres, l'image se fige",
    "Direct (200 cm) : plus loin, retour au direct",
    "  entre Arret et Direct : ralenti progressif",
    "Rattrapage (x2.5) : vitesse de retour au direct",
    "Buffer (12 s) : memoire d'images = retard maxi",
    "Immobilite (10 s) : duree avant nouvelle reference",
]


def panel_create():
    cv2.namedWindow(WIN_PANEL, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_PANEL, 470, 760)
    nop = lambda v: None
    for nom, (defaut, maxi) in PANEL_DEFAULTS.items():
        cv2.createTrackbar(nom, WIN_PANEL, defaut, maxi, nop)


def panel_reset():
    """Touche R : remet tous les curseurs aux valeurs par defaut."""
    for nom, (defaut, _) in PANEL_DEFAULTS.items():
        cv2.setTrackbarPos(nom, WIN_PANEL, defaut)


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
    img = np.full((300 + 26 * len(PANEL_HELP), 470, 3), 30, np.uint8)
    for i, (txt, ok) in enumerate(lines):
        color = (120, 255, 120) if ok else (120, 120, 255)
        cv2.putText(img, txt, (15, 35 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    0.62, color, 1, cv2.LINE_AA)
    y0 = 35 + 30 * len(lines) + 14
    cv2.line(img, (15, y0 - 24), (455, y0 - 24), (90, 90, 90), 1)
    for i, txt in enumerate(PANEL_HELP):
        color = (200, 200, 200) if i == 0 else (170, 170, 170)
        cv2.putText(img, txt, (15, y0 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, color, 1, cv2.LINE_AA)
    cv2.imshow(WIN_PANEL, img)


# ---------------------------------------------------------------------------
# Etat partage entre le thread de capture/analyse et la boucle d'affichage
# ---------------------------------------------------------------------------
class Shared:
    def __init__(self, max_frames):
        self.lock       = threading.Lock()
        self.buffer     = deque(maxlen=max_frames)   # images brutes (BGR)
        self.stamps     = deque(maxlen=max_frames)   # heure de capture
        self.running    = True
        self.distance   = None      # derniere distance estimee (m)
        self.ref_width  = None      # largeur d'epaules de reference
        self.fps_cam    = 0.0       # cadence camera mesuree
        self.stable_secs = STABLE_SECONDS   # ecrit par l'affichage (touches/panneau)
        self.want_max_frames = max_frames   # redimensionnement demande du buffer
        self.calib_request   = False        # touche C
        self.cam_drops       = 0            # images camera manquantes (debug)


def capture_thread(cap, pose, st):
    """Capture + detection de posture + estimation de distance, a la cadence
    de la camera. L'affichage tourne dans la boucle principale, a part."""
    widths       = deque(maxlen=SMOOTH_WINDOW)
    anchor_w     = None    # largeur d'epaules au debut de la periode d'immobilite
    stable_since = 0.0
    last_dist    = None
    last_seen    = 0.0
    start_t      = time.monotonic()
    prev_t       = start_t
    fps_meas     = 0.0

    while st.running:
        ok, frame = cap.read()
        if not ok:
            st.running = False
            break
        now = time.monotonic()
        dt, prev_t = now - prev_t, now
        fps_meas = 0.9 * fps_meas + 0.1 * (1.0 / dt if dt > 0 else 0.0)

        # --- debug : trou dans le flux camera = image(s) manquante(s) ---
        # (les 2 premieres secondes sont ignorees, le temps que tout demarre)
        if now - start_t > 2.0 and dt > 1.8 / FPS:
            perdues = max(1, round(dt * FPS) - 1)
            st.cam_drops += perdues
            debug_log("camera", f"{perdues} image(s) manquante(s), trou de "
                                f"{dt * 1000:.0f} ms (total {st.cam_drops})")

        with st.lock:
            if st.want_max_frames != st.buffer.maxlen:
                st.buffer = deque(st.buffer, maxlen=st.want_max_frames)
                st.stamps = deque(st.stamps, maxlen=st.want_max_frames)
            st.buffer.append(frame)
            st.stamps.append(now)
        h, w = frame.shape[:2]

        # --- calibration manuelle (touche C, demandee par l'affichage) ---
        if st.calib_request:
            st.calib_request = False
            if widths:
                st.ref_width = float(np.mean(widths))
                anchor_w, last_dist = None, None

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
                elif now - stable_since >= st.stable_secs:
                    st.ref_width = sw_smooth
                    anchor_w, stable_since = sw_smooth, now

                if st.ref_width:
                    distance = CALIB_DISTANCE * (st.ref_width / sw_smooth)
                    last_dist, last_seen = distance, now

        # --- personne perdue : garder la derniere distance, puis salle vide ---
        if distance is None and last_dist is not None:
            if now - last_seen < ABSENT_TIMEOUT:
                distance = last_dist
            else:
                last_dist = None
                widths.clear()

        st.distance = distance
        st.fps_cam  = fps_meas


# ---------------------------------------------------------------------------
def main():
    cuda_ok, cuda_txt = gpu_status()
    print(f"[ECHO] {cuda_txt}")

    # telecharge les poids au premier lancement ; warm-up a la taille reelle
    # pour que la premiere interpolation soit deja dans le budget des 16,7 ms
    rife = RifeInterpolator(warmup_size=(CAP_HEIGHT, CAP_WIDTH))
    print(f"[ECHO] {rife.status}")

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        raise SystemExit("Impossible d'ouvrir la webcam (verifier CAM_INDEX).")

    pose = mp.solutions.pose.Pose(model_complexity=1,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

    buffer_s = BUFFER_SECONDS
    st = Shared(int(buffer_s * FPS))
    worker = threading.Thread(target=capture_thread, args=(cap, pose, st),
                              daemon=True)
    worker.start()

    delay       = 0.0     # retard courant (s) par rapport au direct
    stable_keys = None    # duree fixee par les touches 1..0 (prioritaire)
    rife_on     = True    # touche I
    fps_render  = 0.0
    rife_cost   = 0.0     # cout d'une interpolation (s, moyenne mobile)
    budget      = 1.0 / RENDER_FPS
    prev_t      = time.monotonic()
    n_frame     = 0
    late        = 0       # debug : cycles d'affichage au dela du budget
    jumps       = 0       # debug : sauts dans la continuite de lecture
    prev_target = None    # instant de lecture affiche au cycle precedent

    cv2.namedWindow(WIN_MAIN, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WIN_MAIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    panel_create()

    while st.running:
        loop_start = time.monotonic()
        now = loop_start
        dt, prev_t = now - prev_t, now
        fps_render = 0.9 * fps_render + 0.1 * (1.0 / dt if dt > 0 else 0.0)
        n_frame += 1

        # --- debug : cycle d'affichage trop long = cadence non tenue ---
        if n_frame > 30 and dt > 1.5 * budget:
            late += 1
            debug_log("rendu", f"cycle de {dt * 1000:.0f} ms (budget "
                               f"{budget * 1000:.0f} ms, total {late})")

        d_stop, d_full, catchup, want_buffer_s, stable_panel = panel_read()
        st.stable_secs = stable_keys if stable_keys is not None else float(stable_panel)
        if want_buffer_s != buffer_s:
            buffer_s = want_buffer_s
            st.want_max_frames = int(buffer_s * FPS)   # applique par la capture

        # --- mise a jour du retard (secondes reelles) ---
        distance = st.distance
        v = speed_for_distance(distance, delay, d_stop, d_full, catchup)
        delay += (1.0 - v) * dt

        # --- choix des deux images voisines de l'instant (now - delay) ---
        with st.lock:
            if not st.stamps:
                if cv2.waitKey(20) & 0xFF in (ord('q'), ord('Q'), 27):
                    break
                continue
            delay = max(0.0, min(delay, now - LIVE_LATENCY - st.stamps[0]))
            target = now - LIVE_LATENCY - delay

            # --- debug : saut dans la continuite de lecture ---
            # sans a-coup, l'instant affiche avance exactement de v*dt ;
            # un ecart = clamp du retard (buffer trop court, transition direct)
            if prev_target is not None and n_frame > 30:
                saut, attendu = target - prev_target, v * dt
                if saut < -0.005 or abs(saut - attendu) > 2.0 / FPS:
                    jumps += 1
                    debug_log("continuite",
                              f"saut de {saut * 1000:+.0f} ms (attendu "
                              f"{attendu * 1000:.0f} ms, vitesse {v:.2f}, "
                              f"retard {delay:.2f} s, total {jumps})")
            prev_target = target
            idx = bisect_left(st.stamps, target)
            idx = min(idx, len(st.stamps) - 1)
            img_next, t_next = st.buffer[idx], st.stamps[idx]
            if idx > 0:
                img_prev, t_prev = st.buffer[idx - 1], st.stamps[idx - 1]
            else:
                img_prev, t_prev = img_next, t_next

        # --- interpolation RIFE entre les deux voisines, a l'instant exact ---
        # (coupee si trop lente pour tenir la cadence d'affichage ; nouvel
        #  essai periodique pour re-mesurer son cout)
        frac = (target - t_prev) / (t_next - t_prev) if t_next > t_prev else 1.0
        used_rife = False
        too_slow = rife_cost >= 0.75 * budget
        if (rife_on and rife.ok and 0.04 < frac < 0.96
                and (not too_slow or n_frame % 90 == 0)):
            t0 = time.monotonic()
            out = rife.interpolate(img_prev, img_next, frac)
            cost = time.monotonic() - t0
            # apres une periode "trop lent", repartir de la mesure fraiche
            rife_cost = cost if (rife_cost == 0.0 or too_slow) \
                        else 0.8 * rife_cost + 0.2 * cost
            used_rife = True
        else:
            out = img_prev if frac < 0.5 else img_next
        out = cv2.flip(out, 1)                  # effet miroir horizontal

        # --- overlays ---
        if st.ref_width is None:
            draw_text(out, f"Restez immobile {st.stable_secs:.0f}s (ou C) pour calibrer", 60)
        d_txt = f"{distance:.2f} m" if distance else "--"
        if not rife.ok:
            rife_txt, rife_ok = rife.status, False
        elif not rife_on:
            rife_txt, rife_ok = "RIFE coupe (touche I)", False
        elif rife_cost >= 0.75 * budget:
            rife_txt, rife_ok = "RIFE trop lent -> image la plus proche", False
        else:
            rife_txt = f"RIFE actif 60 im/s ({rife_cost * 1000:.1f} ms)" \
                       if used_rife else "RIFE pret"
            rife_ok = True
        panel_draw([
            (cuda_txt, cuda_ok),
            (rife_txt, rife_ok),
            (f"Distance : {d_txt}", distance is not None),
            (f"Vitesse : {v:.2f}   Retard : {delay:.1f} s", True),
            (f"Camera : {st.fps_cam:.0f} im/s   Rendu : {fps_render:.0f} im/s",
             fps_render > RENDER_FPS - 3),
            (f"Reference : {'calibree' if st.ref_width else 'en attente'}",
             st.ref_width is not None),
            (f"Nouvelle ref apres {st.stable_secs:.0f} s immobile", True),
            (f"Buffer : {len(st.buffer) / FPS:.0f} / {buffer_s} s", True),
            (f"Anomalies : cam {st.cam_drops}  retard {late}  saut {jumps}",
             st.cam_drops + late + jumps == 0),
            ("Touches : C ref, I interp, R defauts, Q quitter", True),
        ])
        cv2.imshow(WIN_MAIN, out)

        # --- cadence d'affichage : RENDER_FPS minimum garanti ---
        elapsed = time.monotonic() - loop_start
        wait_ms = max(1, int((budget - elapsed) * 1000))
        key = cv2.waitKey(wait_ms) & 0xFF
        if key in (ord('q'), ord('Q'), 27):     # Q ou Echap
            break
        if cv2.getWindowProperty(WIN_MAIN, cv2.WND_PROP_VISIBLE) < 1:
            break                               # fenetre fermee a la souris
        if key in (ord('i'), ord('I')):
            rife_on = not rife_on
        if key in (ord('c'), ord('C')):
            st.calib_request = True
            delay = 0.0
        if key in (ord('r'), ord('R')):        # valeurs par defaut
            panel_reset()
            stable_keys = None
        if ord('0') <= key <= ord('9'):         # duree d'immobilite : 1..9 s, 0 = 10 s
            stable_keys = 10.0 if key == ord('0') else float(key - ord('0'))

    st.running = False
    worker.join(timeout=2.0)
    cap.release()
    pose.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
