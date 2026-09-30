"""
Projet ECHO — Jouer avec le temps (spec V1 de l'architecte)
-----------------------------------------------------------
La webcam filme la personne ; sa distance a l'ecran pilote la vitesse de
lecture, en TROIS zones :
  d <= Arret (0,5 m)          -> FIGE          (v = 0)
  Arret  < d < Direct (2 m)   -> RALENTI       (v de 0 a 1, lineaire)
  Direct < d < Accel (3 m)    -> ACCELERATION  (v de 1 a Vmax, lineaire)
  d >= Accel                  -> rattrapage plein (v = Vmax)
Le retard se resorbe tant que v > 1 ; a zero, la lecture reste en direct.
Transitions douces : la distance ET la vitesse sont lissees (double lissage),
avec hysteresis anti-oscillation au seuil de gel.

L'affichage est cadence a 60 im/s (ecran 60 Hz), independamment de la camera
(30 im/s) : chaque image affichee est interpolee par RIFE (GPU) a l'instant
exact entre les deux images voisines du buffer — en ralenti comme en direct.
(Ecart assume avec la spec : RIFE reste actif a v = 1, demande explicite de
PLH — 60 images a l'ecran meme quand la camera n'en donne que 30.)

Touches : C calibrer | I interpolation | H mode HUD (complet/vitesse/aucun)
          S sauvegarder la version courante (taper le nom, Entree)
          fleches gauche/droite : version precedente / suivante
          P panneau de reglages | R valeurs par defaut
          1..9, 0 duree d'immobilite | Q ou Echap quitter

Versions baptisees : presets.json (les reglages nommes survivent au
redemarrage) ; charger une version remet le run a zero proprement.

Debug : anomalies + bilan de perf toutes les 5 s dans echo_debug.log.
Dependances : requirements.txt (mediapipe 0.10.21, torch cu124, Py 3.11/3.12).
Lancer : double-clic sur lancer.bat (Windows) ou python main.py.
"""

import json
import threading
import time
from bisect import bisect_left
from collections import deque

import cv2
import numpy as np
import mediapipe as mp

from rife_interp import RifeInterpolator
from depth import DepthEstimator
from bridge import Bridge
from fond import Segmenter, Compositor

ECHO_VERSION   = "1.13.1"

# ---------------------------------------------------------------------------
# Parametres par defaut (modifiables en direct via le panneau, touche P)
# ---------------------------------------------------------------------------
CAM_INDEX      = 0        # 0 = webcam par defaut
CAP_WIDTH      = 1280
CAP_HEIGHT     = 720
FPS            = 30       # cadence camera, sert au dimensionnement du buffer

RENDER_FPS     = 60       # cadence d'affichage : ecran 60 Hz (la camera, elle,
                          # reste a 30 im/s ; RIFE fabrique les images entre)
LIVE_LATENCY   = 1.5 / FPS  # ~50 ms de latence fixe pour toujours avoir deux
                            # images autour de l'instant affiche

DIST_STOP      = 0.5      # m — en dessous, image figee
DIST_FULL      = 2.0      # m — en phase (v = 1)
DIST_ACCEL     = 4.0      # m — rattrapage plein (v = Vmax)
VMAX           = 2.0      # vitesse max de rattrapage
VMIN           = 0.10     # plancher de vitesse quand quelqu'un est present :
                          # a 10 %, l'image ne fige jamais completement (0 = fige)
DIST_SCALE     = 0.75     # correction d'echelle de la distance IA : mesuree
                          # ~35 % trop longue sur la config PLH (touche C a 2 m
                          # pour recaler automatiquement)
BUFFER_SECONDS = 30       # profondeur memoire = retard maxi (30 s * 720p ~ 2.5 Go RAM)
SMOOTH_WINDOW  = 8        # lissage de la distance (nb de mesures)
SMOOTH_SPEED   = 0.15     # lissage de la vitesse (0 = fige, 1 = instantane)
HYSTERESIS     = 0.1      # m — anti-oscillation au seuil de gel

ANALYZE_EVERY  = 3        # analyse de posture 1 image camera sur 3 (~10 Hz) :
ANALYZE_WIDTH  = 640      # sur image reduite. L'analyse ne sert qu'a estimer
                          # la distance ; a pleine cadence elle monopolise le
                          # verrou Python (GIL) et etouffe l'affichage 60 im/s
                          # et les lancements GPU de RIFE (constate aux logs).
ABSENT_TIMEOUT = 10.0     # s — sans detection, on garde la derniere distance
                          #     puis on considere la salle vide -> direct
STABLE_TOL     = 0.15     # ±15 % de variation de largeur d'epaules = immobile
STABLE_SECONDS = 10.0     # duree d'immobilite avant nouvelle reference (1..9, 0)

CALIB_DISTANCE = 2.0      # distance (m) de la calibration manuelle (touche C)

WIN_MAIN  = "ECHO"
WIN_PANEL = "ECHO - Reglages"

PRESETS_FILE = "presets.json"
HUD_MODES    = ("complet", "vitesse", "aucun")

# fleches gauche/droite (codes waitKeyEx Windows, puis Linux pour les tests)
KEYS_LEFT  = (2424832, 65361)
KEYS_RIGHT = (2555904, 65363)

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
def speed_target(d, p):
    """Vitesse cible selon les trois zones de distance (sans lissage).
    d = None signifie : pas de calibration ou salle vide -> rattrapage plein
    (une fois le retard a zero, la lecture reste simplement en direct)."""
    if d is None:
        return p["vmax"]
    if d <= p["stop"]:
        return 0.0
    if d < p["full"]:
        return (d - p["stop"]) / (p["full"] - p["stop"])
    if d < p["accel"]:
        return 1.0 + (d - p["full"]) / (p["accel"] - p["full"]) * (p["vmax"] - 1.0)
    return p["vmax"]


def shoulder_width_px(landmarks, w, h):
    """Largeur d'epaules en pixels (landmarks 11 et 12)."""
    ls, rs = landmarks[11], landmarks[12]
    if ls.visibility < 0.5 or rs.visibility < 0.5:
        return None
    return float(np.hypot((ls.x - rs.x) * w, (ls.y - rs.y) * h))


# ---------------------------------------------------------------------------
# Debug : anomalies de flux et bilans de performance dans echo_debug.log
# (au plus une ligne par categorie et par seconde ; les compteurs comptent tout)
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


# ---------------------------------------------------------------------------
# Versions baptisees (presets nommes, persistes dans presets.json)
# ---------------------------------------------------------------------------
def presets_load():
    try:
        with open(PRESETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except (OSError, ValueError):
        return {}


def presets_save(presets):
    try:
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
    except OSError as e:
        debug_log("presets", f"sauvegarde impossible : {e}")


# ---------------------------------------------------------------------------
# Panneau lateral de reglages (touche P pour le masquer / afficher)
# ---------------------------------------------------------------------------
# curseur -> (valeur par defaut, maximum)
PANEL_DEFAULTS = {
    "Arret (cm)":       (int(DIST_STOP * 100),   300),
    "Direct (cm)":      (int(DIST_FULL * 100),   500),
    "Accel (cm)":       (int(DIST_ACCEL * 100),  600),
    "Vmax x10":         (int(VMAX * 10),         60),
    "Vmin (%)":         (int(VMIN * 100),        50),
    "Echelle dist (%)": (int(DIST_SCALE * 100),  250),   # defaut 75 : mesure IA ~35 % trop longue
    "Buffer (s)":       (BUFFER_SECONDS,         60),
    "Lissage dist":     (SMOOTH_WINDOW,          30),
    "Lissage vit x100": (int(SMOOTH_SPEED * 100), 100),
    "Hysteresis (cm)":  (int(HYSTERESIS * 100),  50),
    "Immobilite (s)":   (int(STABLE_SECONDS),    30),
}

PANEL_HELP = [
    "Curseurs — R = defauts, P = masquer, S = sauver version",
    "Arret (50) : plus pres, FIGE",
    "Direct (200) : EN PHASE (v=1) ; entre les 2 : RALENTI",
    "Accel (300) : v monte de 1 a Vmax entre Direct et Accel",
    "Vmax (x2) : vitesse de rattrapage plein",
    "Vmin (10%) : plancher - l'image ne fige jamais sous ce %",
    "Echelle dist (75%) : correction de la distance IA (C a 2 m)",
    "Buffer (30 s) : memoire d'images = retard maxi",
    "Lissage dist (8) / vit (0.15) : transitions douces",
    "Hysteresis (10 cm) : anti-oscillation au seuil FIGE",
    "Immobilite (10 s) : duree avant nouvelle reference",
]


def panel_create():
    cv2.namedWindow(WIN_PANEL, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN_PANEL, 470, 900)
    nop = lambda v: None
    for nom, (defaut, maxi) in PANEL_DEFAULTS.items():
        cv2.createTrackbar(nom, WIN_PANEL, defaut, maxi, nop)


def panel_positions():
    return {n: cv2.getTrackbarPos(n, WIN_PANEL) for n in PANEL_DEFAULTS}


def panel_apply(vals):
    for n, v in vals.items():
        if n in PANEL_DEFAULTS:
            maxi = PANEL_DEFAULTS[n][1]
            cv2.setTrackbarPos(n, WIN_PANEL, min(int(v), maxi))


def params_from_positions(g):
    """Positions brutes des curseurs -> parametres physiques coherents."""
    p = {
        "stop":         max(10, g["Arret (cm)"]) / 100.0,
        "full":         max(20, g["Direct (cm)"]) / 100.0,
        "accel":        max(30, g["Accel (cm)"]) / 100.0,
        "vmax":         max(10, g["Vmax x10"]) / 10.0,
        "vmin":         g["Vmin (%)"] / 100.0,
        "echelle":      max(25, g["Echelle dist (%)"]) / 100.0,
        "buffer_s":     max(2,  g["Buffer (s)"]),
        "smooth_win":   max(1,  g["Lissage dist"]),
        "smooth_speed": max(1,  g["Lissage vit x100"]) / 100.0,
        "hyst":         g["Hysteresis (cm)"] / 100.0,
        "stable_s":     max(1,  g["Immobilite (s)"]),
    }
    if p["full"] <= p["stop"]:
        p["full"] = p["stop"] + 0.1
    if p["accel"] <= p["full"]:
        p["accel"] = p["full"] + 0.1
    return p


def panel_draw(lines):
    img = np.full((320 + 26 * len(PANEL_HELP), 470, 3), 30, np.uint8)
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
# HUD incruste dans l'image (touche H : complet / vitesse / aucun)
# ---------------------------------------------------------------------------
ETAT_COLORS = {
    "FIGE":         (70, 70, 255),
    "RALENTI":      (0, 190, 255),
    "EN PHASE":     (120, 255, 120),
    "ACCELERATION": (255, 190, 80),
}


def rounded_box(img, x1, y1, x2, y2, r=16, color=(24, 24, 24), alpha=0.55):
    """Rectangle a coins arrondis, fond translucide."""
    over = img.copy()
    cv2.rectangle(over, (x1 + r, y1), (x2 - r, y2), color, -1)
    cv2.rectangle(over, (x1, y1 + r), (x2, y2 - r), color, -1)
    for cx, cy in ((x1 + r, y1 + r), (x2 - r, y1 + r),
                   (x1 + r, y2 - r), (x2 - r, y2 - r)):
        cv2.circle(over, (cx, cy), r, color, -1)
    cv2.addWeighted(over, alpha, img, 1 - alpha, 0, img)


def hud_text(img, txt, x, y, scale, color=(235, 235, 235), thick=1):
    cv2.putText(img, txt, (x, y), cv2.FONT_HERSHEY_DUPLEX,
                scale, color, thick, cv2.LINE_AA)


def hud_draw(img, mode, info):
    """info : dict etat, v, retard, distance, version, device, fps_r, fps_c,
    rife, naming (None ou texte en cours de frappe)."""
    if info.get("naming") is not None:
        h = img.shape[0]
        rounded_box(img, 24, h - 96, 760, h - 24)
        hud_text(img, f"Nouvelle version : {info['naming']}_", 44, h - 52, 0.9)
        hud_text(img, "Entree = sauver   Echap = annuler", 44, h - 32, 0.5,
                 (170, 170, 170))
    if mode == "aucun":
        return
    if mode == "vitesse":
        rounded_box(img, 24, 24, 300, 120)
        hud_text(img, f"{info['v'] * 100:.0f} %", 44, 74, 1.5,
                 ETAT_COLORS.get(info["etat"], (235, 235, 235)), 2)
        hud_text(img, f"retard {info['retard']:.1f} s", 44, 106, 0.62)
        return
    # mode complet
    rounded_box(img, 24, 24, 470, 268 + (28 if info.get("extra") else 0))
    hud_text(img, info["etat"], 44, 66, 1.0,
             ETAT_COLORS.get(info["etat"], (235, 235, 235)), 2)
    d_txt = f"{info['distance']:.2f} m" if info["distance"] else "--"
    lignes = [
        f"vitesse   {info['v'] * 100:.0f} %",
        f"retard    {info['retard']:5.1f} s",
        f"distance  {d_txt}",
        f"version   {info['version']}",
        f"{info['device']}   {info['fps_r']:.0f}/{info['fps_c']:.0f} im/s"
        f"   {CAP_WIDTH}x{CAP_HEIGHT}",
        info["rife"],
    ]
    if info.get("extra"):
        lignes.append(info["extra"])
    for i, txt in enumerate(lignes):
        hud_text(img, txt, 44, 102 + 28 * i, 0.62)


# ---------------------------------------------------------------------------
# Etat partage entre le thread de capture/analyse et la boucle d'affichage
# ---------------------------------------------------------------------------
class Shared:
    def __init__(self, max_frames):
        self.lock       = threading.Lock()
        self.buffer     = deque(maxlen=max_frames)   # images brutes (BGR)
        self.stamps     = deque(maxlen=max_frames)   # heure de capture
        self.masks      = deque(maxlen=max_frames)   # masques personne (ou None)
        self.running    = True
        self.distance   = None      # derniere distance estimee (m)
        self.ref_width  = None      # largeur d'epaules de reference
        self.fps_cam    = 0.0       # cadence camera mesuree
        self.stable_secs = STABLE_SECONDS   # ecrit par l'affichage
        self.smooth_window = SMOOTH_WINDOW  # lissage distance (curseur)
        self.depth_mode  = "epaules"        # "ia" (Depth Anything) ou "epaules"
        self.depth_ms    = 0.0              # cout d'une inference profondeur
        self.want_max_frames = max_frames   # redimensionnement demande du buffer
        self.calib_request   = False        # touche C
        self.cam_drops       = 0            # images camera manquantes (debug)
        self.pose_ms         = 0.0          # cout d'une analyse de posture


def torso_center(landmarks):
    """Centre du torse (epaules 11-12, hanches 23-24) en coordonnees
    normalisees ; tete (0) en secours. None si rien de visible."""
    pts = [landmarks[i] for i in (11, 12, 23, 24) if landmarks[i].visibility > 0.5]
    if not pts and landmarks[0].visibility > 0.5:
        pts = [landmarks[0]]
    if not pts:
        return None
    return (float(np.mean([p.x for p in pts])),
            float(np.mean([p.y for p in pts])))


def capture_thread(cap, pose, st, depth, seg):
    """Capture + detection de posture + estimation de distance, a la cadence
    de la camera. L'affichage tourne dans la boucle principale, a part."""
    widths       = deque(maxlen=30)     # fenetre de lissage max (curseur)
    dists        = deque(maxlen=30)     # distances profondeur IA recentes
    anchor_w     = None    # largeur d'epaules au debut de l'immobilite
    stable_since = 0.0
    last_dist    = None
    last_seen    = 0.0
    start_t      = time.monotonic()
    prev_t       = start_t
    fps_meas     = 0.0
    n_cap        = 0

    def moyenne():
        k = max(1, int(st.smooth_window))
        return float(np.mean(list(widths)[-k:]))

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

        # --- masque personne/fond (pour l'incrustation, touche V) ---
        m = None
        if seg is not None and seg.ok:
            try:
                m = seg.mask(frame)
            except Exception as e:
                seg.ok = False
                seg.status = f"Detourage : erreur ({type(e).__name__})"
                debug_log("fond", f"erreur de segmentation, detourage coupe : {e}")

        with st.lock:
            if st.want_max_frames != st.buffer.maxlen:
                st.buffer = deque(st.buffer, maxlen=st.want_max_frames)
                st.stamps = deque(st.stamps, maxlen=st.want_max_frames)
                st.masks  = deque(st.masks,  maxlen=st.want_max_frames)
            st.buffer.append(frame)
            st.stamps.append(now)
            st.masks.append(m)
        st.fps_cam = fps_meas

        # --- calibration manuelle (touche C, demandee par l'affichage) ---
        if st.calib_request:
            st.calib_request = False
            if widths:
                st.ref_width = moyenne()
                anchor_w, last_dist = None, None

        # --- analyse de posture : 1 image sur ANALYZE_EVERY, en reduit ---
        # (le reste du temps, la derniere distance est conservee telle quelle)
        n_cap += 1
        if n_cap % ANALYZE_EVERY:
            continue
        t_pose = time.monotonic()
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (ANALYZE_WIDTH, ANALYZE_WIDTH * h // w))
        hs, ws = small.shape[:2]
        res = pose.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        st.pose_ms = 0.8 * st.pose_ms + 0.2 * (time.monotonic() - t_pose) * 1000.0

        distance = None
        if res.pose_landmarks:
            lm = res.pose_landmarks.landmark

            # --- methode principale : profondeur IA au centre du torse ---
            if st.depth_mode == "ia" and depth is not None and depth.ok:
                centre = torso_center(lm)
                if centre is not None:
                    try:
                        d_raw = depth.distance_at(small, centre[0], centre[1])
                    except Exception as e:      # panne GPU -> secours epaules
                        depth.ok = False
                        depth.status = (f"Profondeur IA : erreur "
                                        f"({type(e).__name__}) -> secours epaules")
                        st.depth_mode = "epaules"
                        debug_log("profondeur", f"erreur d'inference, passage "
                                                f"en secours epaules : {e}")
                        d_raw = None
                    st.depth_ms = depth.last_ms
                    if d_raw is not None:
                        dists.append(d_raw)
                        k = max(1, int(st.smooth_window))
                        distance = float(np.mean(list(dists)[-k:]))
                        last_dist, last_seen = distance, now

            # --- secours : largeur d'epaules (calibration a 2 m) ---
            if distance is None and st.depth_mode != "ia":
                sw = shoulder_width_px(lm, ws, hs)
                if sw:
                    widths.append(sw)
                    sw_smooth = moyenne()

                    # immobile depuis stable_secs (±STABLE_TOL) ? -> nouvelle ref
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


# ---------------------------------------------------------------------------
def main():
    cuda_ok, cuda_txt = gpu_status()
    print(f"[ECHO] {cuda_txt}")

    # telecharge les poids au premier lancement ; warm-up a la taille reelle
    rife = RifeInterpolator(warmup_size=(CAP_HEIGHT, CAP_WIDTH))
    print(f"[ECHO] {rife.status}")

    # distance par profondeur IA (spec V1 §2) ; secours epaules si absente
    depth = DepthEstimator()
    print(f"[ECHO] {depth.status}")

    # pont local pour l'interface HTML (spec V1 §1)
    bridge = Bridge()
    print(f"[ECHO] {bridge.status}")

    # detourage + fond virtuel (galerie, etape 1 ; touche V)
    seg = Segmenter()
    comp = Compositor(CAP_WIDTH, CAP_HEIGHT) if seg.ok else None
    print(f"[ECHO] {seg.status}" + (f" (fond : {comp.source})" if comp else ""))
    debug_log("config", f"ECHO v{ECHO_VERSION} | {cuda_txt} | {rife.status} | "
                        f"rendu vise {RENDER_FPS} im/s (budget "
                        f"{1000.0 / RENDER_FPS:.1f} ms) | camera demandee "
                        f"{CAP_WIDTH}x{CAP_HEIGHT}@{FPS}")

    cap = cv2.VideoCapture(CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAP_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAP_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        raise SystemExit("Impossible d'ouvrir la webcam (verifier CAM_INDEX).")

    # modele leger (complexity 0) : suffisant pour une largeur d'epaules,
    # et 2 a 3 fois moins de temps CPU sous le verrou Python
    pose = mp.solutions.pose.Pose(model_complexity=0,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)

    st = Shared(int(BUFFER_SECONDS * FPS))
    st.depth_mode = "ia" if depth.ok else "epaules"
    worker = threading.Thread(target=capture_thread,
                              args=(cap, pose, st, depth, seg), daemon=True)
    worker.start()

    delay       = 0.0       # retard courant (s) par rapport au direct
    v_smooth    = 1.0       # vitesse lissee (double lissage, spec §1)
    frozen      = False     # etat FIGE avec hysteresis
    stable_keys = None      # duree fixee par les touches 1..0 (prioritaire)
    rife_on     = True      # touche I
    fond_on     = False     # touche V : incrustation sur fond virtuel
    reset_on    = True      # touche T : rattrapage du direct autorise (spec §3)
    hud_mode    = 0         # index dans HUD_MODES (touche H)
    naming      = None      # texte en cours de frappe (touche S), sinon None
    fps_render  = 0.0
    budget      = 1.0 / RENDER_FPS
    # RIFE par paliers : pleine res -> demi-res (~4x moins cher) -> coupe
    rife_mode   = "pleine"
    rife_costs  = {"pleine": 0.0, "demi": 0.0}   # moyennes mobiles (s)
    rife_budget = 0.85 * budget   # le reste du cycle coute ~2 ms
    prev_t      = time.monotonic()
    n_frame     = 0
    late        = 0         # debug : cycles d'affichage au dela du budget
    jumps       = 0         # debug : sauts dans la continuite de lecture
    prev_target = None

    # versions baptisees
    presets       = presets_load()
    active_preset = None

    # accumulateurs du bilan de performance (ligne perf toutes les 5 s)
    acc = dict(logic=0.0, image=0.0, draw=0.0, wait=0.0, autre=0.0,
               rife_ms=0.0, rife_n=0, n=0)
    last_perf = time.monotonic()
    t_wait_prev = None

    cv2.namedWindow(WIN_MAIN, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WIN_MAIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    panel_create()
    panel_visible = True
    saved_positions = panel_positions()
    p = params_from_positions(saved_positions)
    buffer_s = p["buffer_s"]

    def reset_run():
        """Charger une version = repartir proprement (spec §4)."""
        nonlocal delay, v_smooth, frozen, prev_target, rife_mode, rife_costs
        with st.lock:
            st.buffer.clear()
            st.stamps.clear()
            st.masks.clear()
        delay, v_smooth, frozen = 0.0, 1.0, False
        prev_target = None
        rife_mode, rife_costs = "pleine", {"pleine": 0.0, "demi": 0.0}

    def charger_version(nom):
        nonlocal active_preset, saved_positions, reset_on
        vals = presets.get(nom)
        if vals is None:
            return
        if panel_visible:
            panel_apply(vals)
        saved_positions = {n: int(vals.get(n, d)) for n, (d, _) in
                           PANEL_DEFAULTS.items()}
        reset_on = bool(vals.get("_reset", True))
        active_preset = nom
        reset_run()
        debug_log("presets", f"version '{nom}' chargee")

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

        # --- commandes du panneau web (appliquees a chaud) ---
        for cmd in bridge.poll():
            try:
                t = cmd.get("t")
                if t == "reglage" and cmd.get("nom") in PANEL_DEFAULTS:
                    nom_c = cmd["nom"]
                    maxi = PANEL_DEFAULTS[nom_c][1]
                    val = max(0, min(int(cmd.get("v", 0)), maxi))
                    saved_positions[nom_c] = val
                    if panel_visible:
                        cv2.setTrackbarPos(nom_c, WIN_PANEL, val)
                elif t == "option":
                    nom_o, v_o = cmd.get("nom"), cmd.get("v")
                    if nom_o == "interpolation":
                        rife_on = bool(v_o)
                    elif nom_o == "reset":
                        reset_on = bool(v_o)
                    elif nom_o == "profondeur" and depth.ok:
                        st.depth_mode = "ia" if v_o else "epaules"
                    elif nom_o == "fond" and comp is not None:
                        fond_on = bool(v_o)
                    elif nom_o == "hud" and v_o in HUD_MODES:
                        hud_mode = HUD_MODES.index(v_o)
                elif t == "defauts":
                    saved_positions = {n: d for n, (d, _) in PANEL_DEFAULTS.items()}
                    if panel_visible:
                        panel_apply(saved_positions)
                    stable_keys = None
                elif t == "version":
                    action, nom_v = cmd.get("action"), str(cmd.get("nom", ""))
                    if action == "charger":
                        charger_version(nom_v)
                    elif action == "sauver" and nom_v.strip():
                        presets[nom_v.strip()[:24]] = dict(saved_positions,
                                                           _reset=reset_on)
                        presets_save(presets)
                        active_preset = nom_v.strip()[:24]
                    elif action == "supprimer" and nom_v in presets:
                        del presets[nom_v]
                        presets_save(presets)
                        if active_preset == nom_v:
                            active_preset = None
                    elif action == "renommer" and nom_v in presets:
                        nouveau = str(cmd.get("nouveau", "")).strip()[:24]
                        if nouveau and nouveau not in presets:
                            presets[nouveau] = presets.pop(nom_v)
                            presets_save(presets)
                            if active_preset == nom_v:
                                active_preset = nouveau
            except Exception as e:              # jamais fatal pour l'affichage
                debug_log("web", f"commande invalide {cmd} : {e}")

        if panel_visible:
            saved_positions = panel_positions()
        p = params_from_positions(saved_positions)
        st.stable_secs = stable_keys if stable_keys is not None else float(p["stable_s"])
        st.smooth_window = p["smooth_win"]
        if p["buffer_s"] != buffer_s:
            buffer_s = p["buffer_s"]
            st.want_max_frames = int(buffer_s * FPS)   # applique par la capture

        # --- vitesse cible (3 zones) + gel avec hysteresis + double lissage ---
        distance = st.distance
        if distance is not None and st.depth_mode == "ia":
            distance *= p["echelle"]        # correction d'echelle (touche C a 2 m)
        if distance is None:
            frozen = False
        elif frozen:
            frozen = distance <= p["stop"] + p["hyst"]
        else:
            frozen = distance <= p["stop"]
        v_cible = 0.0 if frozen else speed_target(distance, p)
        if distance is not None and p["vmin"] > 0.0:
            v_cible = max(v_cible, p["vmin"])   # plancher : ne fige jamais sous Vmin
        if not reset_on:                # reset OFF : jamais plus vite que le direct,
            v_cible = min(v_cible, 1.0) # le retard acquis reste (spec §3)
        v_smooth += (v_cible - v_smooth) * p["smooth_speed"]
        delay += (1.0 - v_smooth) * dt

        # --- choix des deux images voisines de l'instant affiche ---
        with st.lock:
            if not st.stamps:
                if cv2.waitKey(20) & 0xFF in (ord('q'), ord('Q'), 27):
                    break
                continue
            delay = max(0.0, min(delay, now - LIVE_LATENCY - st.stamps[0]))
            target = now - LIVE_LATENCY - delay

            # --- debug : saut dans la continuite de lecture ---
            if prev_target is not None and n_frame > 30:
                saut, attendu = target - prev_target, v_smooth * dt
                if saut < -0.005 or abs(saut - attendu) > 2.0 / FPS:
                    jumps += 1
                    debug_log("continuite",
                              f"saut de {saut * 1000:+.0f} ms (attendu "
                              f"{attendu * 1000:.0f} ms, vitesse {v_smooth:.2f}, "
                              f"retard {delay:.2f} s, total {jumps})")
            prev_target = target
            idx = bisect_left(st.stamps, target)
            idx = min(idx, len(st.stamps) - 1)
            img_next, t_next = st.buffer[idx], st.stamps[idx]
            m_next = st.masks[idx]
            if idx > 0:
                img_prev, t_prev = st.buffer[idx - 1], st.stamps[idx - 1]
                m_prev = st.masks[idx - 1]
            else:
                img_prev, t_prev = img_next, t_next
                m_prev = m_next

        t_logic = time.monotonic()

        # --- interpolation RIFE entre les deux voisines, a l'instant exact ---
        # chaque image affichee est un instant interpole unique. Si la pleine
        # resolution depasse le budget : demi-resolution (fluide quand meme)
        # plutot que l'image la plus proche ; remontee re-essayee periodiquement.
        frac = (target - t_prev) / (t_next - t_prev) if t_next > t_prev else 1.0
        used_rife = False
        essai = rife_mode
        if rife_mode == "coupe" and n_frame % 90 == 0:
            essai = "demi"
        elif rife_mode == "demi" and n_frame % 180 == 0:
            essai = "pleine"
        if rife_on and rife.ok and 0.04 < frac < 0.96 and essai != "coupe":
            try:
                t0 = time.monotonic()
                out = rife.interpolate(img_prev, img_next, frac,
                                       pair_key=(t_prev, t_next),
                                       half=(essai == "demi"))
                cost = time.monotonic() - t0
                c = rife_costs[essai]
                c = cost if (c == 0.0 or essai != rife_mode) \
                    else 0.8 * c + 0.2 * cost
                rife_costs[essai] = c
                if c >= rife_budget:
                    nouveau = "demi" if essai == "pleine" else "coupe"
                    if nouveau != rife_mode:
                        debug_log("rife", f"{essai} res : {c * 1000:.1f} ms > "
                                          f"budget {rife_budget * 1000:.1f} ms "
                                          f"-> {nouveau}")
                    rife_mode = nouveau if essai == rife_mode else rife_mode
                else:
                    if essai != rife_mode:
                        debug_log("rife", f"passage en {essai} res "
                                          f"({c * 1000:.1f} ms)")
                    rife_mode = essai
                acc["rife_ms"] += cost * 1000.0
                acc["rife_n"] += 1
                used_rife = True
            except Exception as e:              # jamais fatal pour l'affichage
                rife.ok = False
                rife.status = f"RIFE : erreur ({type(e).__name__})"
                debug_log("rife", f"erreur pendant l'interpolation, "
                                  f"interpolation coupee : {e}")
        if not used_rife:
            out = img_prev if frac < 0.5 else img_next

        # --- incrustation sur fond virtuel (touche V) ---
        if fond_on and comp is not None:
            if m_prev is not None and m_next is not None:
                m_mix = m_prev * (1.0 - frac) + m_next * frac
            else:
                m_mix = m_next if m_next is not None else m_prev
            if m_mix is not None:
                out = comp.apply(out, m_mix)
        out = cv2.flip(out, 1)                  # effet miroir horizontal
        t_image = time.monotonic()

        # --- HUD (spec §3) ---
        v_eff = v_smooth if delay > 0.0 else min(v_smooth, 1.0)
        if distance is not None and v_cible <= 0.001:
            etat = "FIGE"
        elif distance is not None and distance < p["full"]:
            etat = "RALENTI"
        elif delay > 0.05 and v_smooth > 1.02:
            etat = "ACCELERATION"
        else:
            etat = "EN PHASE"
        if not rife.ok:
            rife_txt, rife_ok = rife.status, False
        elif not rife_on:
            rife_txt, rife_ok = "RIFE coupe (touche I)", False
        elif rife_mode == "coupe":
            rife_txt, rife_ok = "RIFE trop lent -> image la plus proche", False
        else:
            c_ms = rife_costs[rife_mode] * 1000.0
            rife_txt = f"RIFE {rife_mode} res ({c_ms:.1f} ms)"
            rife_ok = rife_mode == "pleine"
        if st.depth_mode != "ia" and st.ref_width is None:
            rounded_box(out, 24, out.shape[0] - 84, 700, out.shape[0] - 24)
            hud_text(out, f"Restez immobile {st.stable_secs:.0f} s "
                          f"(ou touche C) pour calibrer",
                     44, out.shape[0] - 46, 0.7)
        hud_draw(out, HUD_MODES[hud_mode], {
            "etat": etat, "v": v_eff, "retard": delay, "distance": distance,
            "version": active_preset or "--",
            "device": "GPU" if (rife.ok and cuda_ok) else "CPU",
            "fps_r": fps_render, "fps_c": st.fps_cam,
            "rife": rife_txt, "naming": naming,
            "extra": None if reset_on else "reset OFF : le retard reste (T)",
        })

        # --- panneau (rafraichi a ~10 Hz, masquable touche P) ---
        if panel_visible and n_frame % 6 == 0:
            noms = sorted(presets)
            liste = ", ".join(f"[{n}]" if n == active_preset else n
                              for n in noms) if noms else "aucune (touche S)"
            panel_draw([
                (cuda_txt, cuda_ok),
                (rife_txt, rife_ok),
                (f"Etat : {etat}   Vitesse : {v_eff * 100:.0f} %", True),
                (f"Distance : "
                 f"{f'{distance:.2f} m' if distance else '--'}   "
                 f"Retard : {delay:.1f} s", distance is not None),
                (f"Camera : {st.fps_cam:.0f} im/s   Rendu : {fps_render:.0f} im/s",
                 fps_render > RENDER_FPS - 3),
                (f"Distance : {'IA ' + f'{st.depth_ms:.0f} ms' if st.depth_mode == 'ia' else 'epaules (secours)'}",
                 st.depth_mode == "ia"),
                (f"Reference : "
                 f"{'auto (IA)' if st.depth_mode == 'ia' else ('calibree' if st.ref_width else 'en attente')}",
                 st.depth_mode == "ia" or st.ref_width is not None),
                (f"Buffer : {len(st.buffer) / FPS:.0f} / {buffer_s} s", True),
                (f"Versions : {liste[:44]}", True),
                (f"Anomalies : cam {st.cam_drops}  retard {late}  saut {jumps}",
                 st.cam_drops + late + jumps == 0),
                (f"Reset position : {'ON' if reset_on else 'OFF (retard garde)'}",
                 reset_on),
                (f"Fond virtuel : {'ON' if fond_on else 'OFF'} (touche V)",
                 fond_on),
                ("Touches : C D I T V H S P R fleches Q", True),
            ])
        # --- etat pour le panneau web (~10 Hz) ---
        if n_frame % 6 == 0:
            bridge.publish({
                "etat": etat, "v": v_eff, "retard": delay,
                "distance": distance, "device": "GPU" if (rife.ok and cuda_ok) else "CPU",
                "fps_r": fps_render, "fps_c": st.fps_cam,
                "rife": rife_txt,
                "profondeur": (f"Profondeur : IA ({st.depth_ms:.0f} ms)"
                               if st.depth_mode == "ia"
                               else f"Profondeur : epaules (secours) - {depth.status}"),
                "profondeur_dispo": depth.ok,
                "reglages": dict(saved_positions),
                "options": {"interpolation": rife_on, "reset": reset_on,
                            "profondeur_ia": st.depth_mode == "ia",
                            "fond": fond_on, "hud": HUD_MODES[hud_mode]},
                "fond_dispo": comp is not None,
                "versions": {"liste": sorted(presets), "active": active_preset},
                "version_app": ECHO_VERSION,
            })

        cv2.imshow(WIN_MAIN, out)
        t_draw = time.monotonic()

        # --- cadence d'affichage : waitKeyEx(1) + sommeil precis (~1 ms) ---
        kx = cv2.waitKeyEx(1)
        key = kx & 0xFF if 0 <= kx < 256 else (255 if kx == -1 else 254)
        reste = budget - (time.monotonic() - loop_start)
        if reste > 0.002:
            time.sleep(reste - 0.001)
        t_wait = time.monotonic()

        # --- bilan de performance toutes les 5 s dans echo_debug.log ---
        if t_wait_prev is not None:
            acc["autre"] += loop_start - t_wait_prev
        t_wait_prev = t_wait
        acc["logic"] += t_logic - loop_start
        acc["image"] += t_image - t_logic
        acc["draw"]  += t_draw - t_image
        acc["wait"]  += t_wait - t_draw
        acc["n"]     += 1
        if t_wait - last_perf >= 5.0:
            n = max(1, acc["n"])
            pct = 100.0 * acc["rife_n"] / n
            r_ms = acc["rife_ms"] / max(1, acc["rife_n"])
            debug_log("perf",
                      f"rendu {fps_render:.1f} im/s (vise {RENDER_FPS}) | "
                      f"camera {st.fps_cam:.1f} | analyse {st.pose_ms:.1f} ms | "
                      f"rife {r_ms:.1f} ms ({rife_mode}) sur {pct:.0f}% "
                      f"des images | gpu {rife.gpu_mem_mb()} Mo | cycle : "
                      f"logique {acc['logic'] / n * 1000:.1f} + image "
                      f"{acc['image'] / n * 1000:.1f} + affichage "
                      f"{acc['draw'] / n * 1000:.1f} + attente "
                      f"{acc['wait'] / n * 1000:.1f} + autre "
                      f"{acc['autre'] / n * 1000:.1f} ms | anomalies : cam "
                      f"{st.cam_drops} retard {late} saut {jumps}")
            acc = dict(logic=0.0, image=0.0, draw=0.0, wait=0.0, autre=0.0,
                       rife_ms=0.0, rife_n=0, n=0)
            last_perf = t_wait

        if cv2.getWindowProperty(WIN_MAIN, cv2.WND_PROP_VISIBLE) < 1:
            break                               # fenetre fermee a la souris

        # --- clavier ---
        if naming is not None:                  # saisie du nom de version
            if key == 13 or key == 10:          # Entree -> sauver
                nom = naming.strip()
                if nom:
                    presets[nom] = dict(saved_positions, _reset=reset_on)
                    presets_save(presets)
                    active_preset = nom
                    debug_log("presets", f"version '{nom}' sauvegardee")
                naming = None
            elif key == 27:                     # Echap -> annuler
                naming = None
            elif key == 8:                      # retour arriere
                naming = naming[:-1]
            elif 32 <= key < 127 and len(naming) < 24:
                naming += chr(key)
            continue

        if key in (ord('q'), ord('Q'), 27):     # Q ou Echap
            break
        if key in (ord('i'), ord('I')):
            rife_on = not rife_on
        if key in (ord('d'), ord('D')) and depth.ok:   # IA <-> epaules
            st.depth_mode = "epaules" if st.depth_mode == "ia" else "ia"
        if key in (ord('t'), ord('T')):                # reset de position on/off
            reset_on = not reset_on
        if key in (ord('v'), ord('V')) and comp is not None:   # fond virtuel
            fond_on = not fond_on
        if key in (ord('h'), ord('H')):         # mode HUD
            hud_mode = (hud_mode + 1) % len(HUD_MODES)
        if key in (ord('s'), ord('S')):         # sauver une version nommee
            naming = ""
        if key in (ord('p'), ord('P')):         # masquer/afficher le panneau
            if panel_visible:
                saved_positions = panel_positions()
                cv2.destroyWindow(WIN_PANEL)
                panel_visible = False
            else:
                panel_create()
                panel_apply(saved_positions)
                panel_visible = True
        if key in (ord('c'), ord('C')):
            if st.depth_mode == "ia":           # recalage : je suis a 2 m
                if st.distance:
                    e = int(round(100.0 * CALIB_DISTANCE / st.distance))
                    e = max(25, min(250, e))
                    saved_positions["Echelle dist (%)"] = e
                    if panel_visible:
                        cv2.setTrackbarPos("Echelle dist (%)", WIN_PANEL, e)
                    debug_log("profondeur", f"recalage a {CALIB_DISTANCE} m : "
                                            f"echelle {e} %")
            else:
                st.calib_request = True
            delay = 0.0
        if key in (ord('r'), ord('R')):         # valeurs par defaut
            if panel_visible:
                for nom_c, (defaut, _) in PANEL_DEFAULTS.items():
                    cv2.setTrackbarPos(nom_c, WIN_PANEL, defaut)
            saved_positions = {n: d for n, (d, _) in PANEL_DEFAULTS.items()}
            stable_keys = None
        if ord('0') <= key <= ord('9'):         # duree d'immobilite : 1..9, 0=10
            stable_keys = 10.0 if key == ord('0') else float(key - ord('0'))
        if kx in KEYS_LEFT or kx in KEYS_RIGHT: # version precedente / suivante
            noms = sorted(presets)
            if noms:
                if active_preset in noms:
                    i = noms.index(active_preset)
                    i = (i + (1 if kx in KEYS_RIGHT else -1)) % len(noms)
                else:
                    i = 0
                charger_version(noms[i])

    st.running = False
    worker.join(timeout=2.0)
    cap.release()
    pose.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
