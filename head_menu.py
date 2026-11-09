"""Navegação do menu por movimentos da cabeça (MediaPipe FaceMesh).

- Cabeça para CIMA / BAIXO (pitch) -> evento "UP" / "DOWN"
- Cabeça para ESQUERDA / DIREITA (yaw), mantida por SELECT_HOLD_S -> "SELECT"

As medidas são razões entre pontos do rosto, então não dependem da distância
nem da posição do rosto na câmera; só da rotação da cabeça. A posição neutra é
calibrada automaticamente quando o rosto aparece (ou com recalibrate()).

Também fornece um cursor controlado pelo nariz (snapshot()["cursor"], 0..1) e
piscadas longas (poll_blinks()), usados no teclado digital do login.
"""

import math
import threading
import time
from collections import deque
from statistics import median

try:
    import cv2
    import mediapipe as mp

    CAMERA_AVAILABLE = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
except Exception:
    CAMERA_AVAILABLE = False


# ---- Ajustes (thresholds) ---------------------------------------------------
# Pitch: deslocamento vertical do nariz em relação à altura do rosto (testa-queixo).
PITCH_THRESHOLD = 0.045
# Yaw: deslocamento horizontal do nariz em relação à largura do rosto.
YAW_THRESHOLD = 0.10
# Para disparar de novo, a cabeça precisa voltar abaixo desta fração do threshold.
RESET_FRACTION = 0.5
# Tempo segurando acima do threshold antes de mover (filtra ruído).
NAV_HOLD_S = 0.10
# Segurando para cima/baixo, repete a navegação a cada X segundos.
NAV_REPEAT_S = 0.75
# Tempo segurando para o lado para confirmar a seleção.
SELECT_HOLD_S = 1.0
# Suavização exponencial (0..1, maior = mais responsivo).
SMOOTHING = 0.4
# Amostras usadas na calibração automática.
CALIBRATION_SAMPLES = 15
# Sem rosto por este tempo -> descarta a calibração.
FACE_LOST_RESET_S = 2.0

# ---- Cursor pelo nariz -------------------------------------------------------
# Quanto o nariz precisa se mover (em larguras de rosto) para ir do centro até a
# borda da tela. Menor = cursor mais sensível.
CURSOR_RANGE_X = 0.30
CURSOR_RANGE_Y = 0.22
# Filtro One Euro: MIN_CUTOFF menor = menos tremor parado; BETA maior = menos atraso.
CURSOR_MIN_CUTOFF = 1.2
CURSOR_BETA = 6.0

# ---- Piscada -------------------------------------------------------------------
# Olho "fechado" quando a abertura cai abaixo desta fração da abertura normal.
BLINK_CLOSE_RATIO = 0.62
# Olho "aberto" de novo acima desta fração (histerese).
BLINK_OPEN_RATIO = 0.78
# Tempo mínimo de olho fechado para contar como piscada intencional
# (piscadas naturais duram ~0,1s).
BLINK_MIN_S = 0.25
# Usa a posição do cursor de um pouco antes do olho fechar (piscar mexe o rosto).
BLINK_LOOKBACK_S = 0.15

# Landmarks do FaceMesh
NOSE_TIP = 1
FOREHEAD = 10
CHIN = 152
CHEEK_A = 234
CHEEK_B = 454
# Olhos: canto, pálpebra sup., pálpebra sup., canto, pálpebra inf., pálpebra inf.
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)


class _LowPass:
    def __init__(self):
        self.value = None

    def __call__(self, x, alpha):
        self.value = x if self.value is None else self.value + alpha * (x - self.value)
        return self.value


class OneEuroFilter:
    """Suavização adaptativa: forte com o cursor parado, leve em movimento."""

    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        self._x = _LowPass()
        self._dx = _LowPass()
        self._t = None

    def __call__(self, x, t):
        if self._t is None:
            self._t = t
            self._dx(0.0, 1.0)
            return self._x(x, 1.0)
        dt = max(1e-3, t - self._t)
        self._t = t
        prev = self._x.value
        dx = self._dx((x - prev) / dt, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(dx)
        return self._x(x, self._alpha(cutoff, dt))


class HeadMenuController:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.available = CAMERA_AVAILABLE
        self.status = "Câmera indisponível" if not self.available else "Iniciando câmera..."

        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._events = deque()
        self._blinks = deque()
        self._filter_x = OneEuroFilter(CURSOR_MIN_CUTOFF, CURSOR_BETA)
        self._filter_y = OneEuroFilter(CURSOR_MIN_CUTOFF, CURSOR_BETA)

        # Estado lido pelo menu (protegido por _lock)
        self.face_detected = False
        self.calibrated = False
        self.pitch = 0.0  # relativo ao neutro; negativo = cima
        self.yaw = 0.0  # relativo ao neutro; negativo = esquerda
        self.select_progress = 0.0  # 0..1 enquanto segura para o lado
        self.frame_rgb = None

        self._reset_tracking_state()

    # ---- ciclo de vida -------------------------------------------------------
    def start(self):
        if not self.available or self._running:
            return
        self._running = True
        self._reset_tracking_state()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Para o rastreamento e libera a câmera (para o jogo poder usá-la)."""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._events.clear()
            self._blinks.clear()
            self.frame_rgb = None
            self.select_progress = 0.0
            self.cursor = None

    def recalibrate(self):
        with self._lock:
            self._calib_samples.clear()
            self._baseline = None
            self.calibrated = False
            self._reset_pointer_state()

    def poll_events(self):
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def poll_blinks(self):
        """Piscadas longas desde a última chamada, como posições (x, y) 0..1 do
        cursor no momento em que o olho começou a fechar."""
        with self._lock:
            blinks = list(self._blinks)
            self._blinks.clear()
            return blinks

    def clear_events(self):
        with self._lock:
            self._events.clear()
            self._blinks.clear()

    def snapshot(self):
        with self._lock:
            return {
                "frame": self.frame_rgb,
                "face": self.face_detected,
                "calibrated": self.calibrated,
                "pitch": self.pitch,
                "yaw": self.yaw,
                "select_progress": self.select_progress,
                "status": self.status,
                "cursor": self.cursor,
                "eyes_closed": self.eyes_closed,
                "blink_progress": self.blink_progress,
            }

    # ---- interno -------------------------------------------------------------
    def _reset_tracking_state(self):
        self._baseline = None
        self._calib_samples = deque(maxlen=CALIBRATION_SAMPLES)
        self._smooth = None
        self._last_face_at = 0.0
        self._nav_dir = None
        self._nav_since = 0.0
        self._nav_last_fire = 0.0
        self._nav_armed = True
        self._sel_since = None
        self._sel_armed = True
        self.calibrated = False
        self.face_detected = False
        self.pitch = self.yaw = 0.0
        self.select_progress = 0.0
        self._reset_pointer_state()

    def _reset_pointer_state(self):
        self._ptr_base = None
        self._ptr_history = deque(maxlen=30)
        self._filter_x.reset()
        self._filter_y.reset()
        self._ear_open = None
        self._closed_since = None
        self._blink_fired = False
        self._blink_pos = None
        self.cursor = None
        self.eyes_closed = False
        self.blink_progress = 0.0

    def _cancel_blink(self):
        self._closed_since = None
        self._blink_fired = False
        self._blink_pos = None
        self.eyes_closed = False
        self.blink_progress = 0.0

    @staticmethod
    def _eye_aspect_ratio(landmarks, idx, w, h):
        p = [(landmarks[i].x * w, landmarks[i].y * h) for i in idx]
        horizontal = math.dist(p[0], p[3])
        if horizontal <= 1e-6:
            return None
        return (math.dist(p[1], p[5]) + math.dist(p[2], p[4])) / (2.0 * horizontal)

    def _cursor_at(self, t):
        """Posição do cursor no instante t (ou a mais antiga disponível)."""
        chosen = None
        for ts, pos in self._ptr_history:
            if ts > t:
                break
            chosen = pos
        if chosen is None and self._ptr_history:
            chosen = self._ptr_history[0][1]
        return chosen if chosen is not None else self.cursor

    def _process_pointer(self, landmarks, now, w, h):
        """Cursor pelo nariz + detecção de piscada longa. Chamar com _lock."""
        if not self.calibrated:
            self.cursor = None
            return

        nose = landmarks[NOSE_TIP]
        face_w = abs(landmarks[CHEEK_B].x - landmarks[CHEEK_A].x)
        if face_w <= 1e-6:
            return
        if self._ptr_base is None:
            self._ptr_base = (nose.x, nose.y)

        # --- Piscada (média dos dois olhos) ---
        ears = [self._eye_aspect_ratio(landmarks, eye, w, h) for eye in (LEFT_EYE, RIGHT_EYE)]
        ears = [e for e in ears if e is not None]
        ear = sum(ears) / len(ears) if ears else None
        if ear is not None:
            if self._ear_open is None:
                self._ear_open = ear
            if self._closed_since is None:
                if ear < self._ear_open * BLINK_CLOSE_RATIO:
                    self._closed_since = now
                    self._blink_pos = self._cursor_at(now - BLINK_LOOKBACK_S)
                    self.eyes_closed = True
                elif ear > self._ear_open * 0.85:
                    # Adapta devagar à abertura normal do olho desta pessoa.
                    self._ear_open += (ear - self._ear_open) * 0.03
            elif ear > self._ear_open * BLINK_OPEN_RATIO:
                self._cancel_blink()
            else:
                held = now - self._closed_since
                self.blink_progress = min(1.0, held / BLINK_MIN_S)
                if not self._blink_fired and held >= BLINK_MIN_S:
                    self._blink_fired = True
                    if self._blink_pos is not None:
                        self._blinks.append(self._blink_pos)

        # Com o olho fechando/fechado o cursor fica parado.
        if self.eyes_closed:
            return

        # --- Cursor ---
        dx = (nose.x - self._ptr_base[0]) / face_w
        dy = (nose.y - self._ptr_base[1]) / face_w
        raw_x = 0.5 + 0.5 * dx / CURSOR_RANGE_X
        raw_y = 0.5 + 0.5 * dy / CURSOR_RANGE_Y
        x = min(1.0, max(0.0, self._filter_x(raw_x, now)))
        y = min(1.0, max(0.0, self._filter_y(raw_y, now)))
        self.cursor = (x, y)
        self._ptr_history.append((now, self.cursor))

    @staticmethod
    def _measure(landmarks):
        nose = landmarks[NOSE_TIP]
        top = landmarks[FOREHEAD]
        bottom = landmarks[CHIN]
        a, b = landmarks[CHEEK_A], landmarks[CHEEK_B]

        face_h = bottom.y - top.y
        left_x, right_x = min(a.x, b.x), max(a.x, b.x)
        face_w = right_x - left_x
        if face_h <= 1e-6 or face_w <= 1e-6:
            return None

        pitch = (nose.y - top.y) / face_h
        yaw = (nose.x - left_x) / face_w
        return pitch, yaw

    def _process(self, measure, now):
        """Atualiza calibração, suavização e gera eventos. Chamar com _lock."""
        if self._smooth is None:
            self._smooth = measure
        else:
            self._smooth = tuple(
                s + (m - s) * SMOOTHING for s, m in zip(self._smooth, measure)
            )

        if self._baseline is None:
            self._calib_samples.append(measure)
            self.status = "Calibrando: olhe para a tela"
            if len(self._calib_samples) >= CALIBRATION_SAMPLES:
                self._baseline = (
                    median(s[0] for s in self._calib_samples),
                    median(s[1] for s in self._calib_samples),
                )
                self._smooth = self._baseline
                self.calibrated = True
                self._nav_armed = self._sel_armed = True
            return

        self.status = "Controle pela cabeça ativo"
        pitch = self._smooth[0] - self._baseline[0]
        yaw = self._smooth[1] - self._baseline[1]
        self.pitch, self.yaw = pitch, yaw

        # --- Seleção (esquerda/direita) tem prioridade sobre a navegação ---
        if abs(yaw) < YAW_THRESHOLD * RESET_FRACTION:
            self._sel_armed = True
        if self._sel_armed and abs(yaw) >= YAW_THRESHOLD:
            if self._sel_since is None:
                self._sel_since = now
            self.select_progress = min(1.0, (now - self._sel_since) / SELECT_HOLD_S)
            if self.select_progress >= 1.0:
                self._events.append("SELECT")
                self._sel_armed = False
                self._sel_since = None
                self.select_progress = 0.0
            # Enquanto vira para o lado, não navega.
            self._nav_dir = None
            return
        self._sel_since = None
        self.select_progress = 0.0
        if abs(yaw) >= YAW_THRESHOLD * RESET_FRACTION:
            # Zona intermediária lateral: ignora cima/baixo para evitar diagonais.
            self._nav_dir = None
            return

        # --- Navegação (cima/baixo) ---
        if abs(pitch) < PITCH_THRESHOLD * RESET_FRACTION:
            self._nav_armed = True
            self._nav_dir = None
            return
        if abs(pitch) < PITCH_THRESHOLD:
            self._nav_dir = None
            return

        direction = "UP" if pitch < 0 else "DOWN"
        if self._nav_dir != direction:
            self._nav_dir = direction
            self._nav_since = now
            return
        held = now - self._nav_since
        if self._nav_armed and held >= NAV_HOLD_S:
            self._events.append(direction)
            self._nav_armed = False
            self._nav_last_fire = now
        elif not self._nav_armed and now - self._nav_last_fire >= NAV_REPEAT_S:
            self._events.append(direction)
            self._nav_last_fire = now

    def _draw_overlay(self, frame, landmarks):
        h, w, _ = frame.shape
        if landmarks is not None:
            nose = landmarks[NOSE_TIP]
            cx, cy = int(nose.x * w), int(nose.y * h)
            color = (80, 220, 120) if self.calibrated else (0, 200, 255)
            cv2.circle(frame, (cx, cy), 6, color, -1)
            cv2.circle(frame, (cx, cy), 9, (255, 255, 255), 2)

    def _loop(self):
        cap = None
        face_mesh = None
        try:
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                with self._lock:
                    self.status = "Webcam não encontrada"
                return
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            while self._running:
                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.02)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = face_mesh.process(rgb)
                now = time.monotonic()

                landmarks = None
                if result.multi_face_landmarks:
                    landmarks = result.multi_face_landmarks[0].landmark

                with self._lock:
                    measure = self._measure(landmarks) if landmarks else None
                    if measure is not None:
                        self.face_detected = True
                        self._last_face_at = now
                        self._process(measure, now)
                        h, w, _ = frame.shape
                        self._process_pointer(landmarks, now, w, h)
                    else:
                        self.face_detected = False
                        self.select_progress = 0.0
                        self._sel_since = None
                        self._nav_dir = None
                        self._cancel_blink()
                        if (
                            self._baseline is not None
                            and now - self._last_face_at > FACE_LOST_RESET_S
                        ):
                            self._baseline = None
                            self._calib_samples.clear()
                            self.calibrated = False
                            self._reset_pointer_state()
                        self.status = "Posicione o rosto na câmera"

                    self._draw_overlay(frame, landmarks)
                    self.frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception as exc:
            with self._lock:
                self.status = f"Erro na câmera: {exc}"
        finally:
            if face_mesh is not None:
                face_mesh.close()
            if cap is not None:
                cap.release()
