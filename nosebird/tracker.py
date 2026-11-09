import threading
import time
from collections import deque
from statistics import median

from settings import JUMP_RESET_THRESHOLD, JUMP_THRESHOLD, NOSE_SMOOTHING

try:
    # pyrefly: ignore [missing-import]
    import cv2

    # pyrefly: ignore [missing-import]
    import mediapipe as mp

    if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
        CAMERA_AVAILABLE = True
    else:
        CAMERA_AVAILABLE = False
except Exception:
    CAMERA_AVAILABLE = False


class NoseTracker:
    def __init__(self):
        self.available = CAMERA_AVAILABLE
        self.signal = "NONE"
        self.nose_y = None
        self.nose_norm = None  # (x, y) 0..1 do nariz, None sem rosto (menus)
        self.baseline_y = None
        self.running = False
        self.frame_for_preview = None
        self._thread = None
        self.cap = None
        self.calibrated_flash = 0
        self.calibrated = False
        self.face_detected = False
        self._samples = deque(maxlen=12)
        self._last_face_at = 0.0
        self._jump_armed = True
        self._jump_pending = False
        self._lock = threading.Lock()

        if self.available:
            try:
                self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception:
                self.available = False

            if self.available:
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.available = False
                    self.cap = None

    def start(self):
        if not self.available or self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def calibrate(self):
        with self._lock:
            if not self._samples or time.monotonic() - self._last_face_at > 0.5:
                return False

            self.baseline_y = float(median(self._samples))
            self.nose_y = self.baseline_y
            self.calibrated = True
            self.calibrated_flash = 25
            self._jump_armed = True
            self._jump_pending = False
            self.signal = "NONE"
            return True

    def consume_jump(self):
        with self._lock:
            jump_pending = self._jump_pending
            self._jump_pending = False
            return jump_pending

    def _update_nose_position(self, raw_nose_y):
        with self._lock:
            self._samples.append(raw_nose_y)
            self._last_face_at = time.monotonic()
            self.face_detected = True

            if self.nose_y is None:
                self.nose_y = raw_nose_y
            else:
                self.nose_y += (raw_nose_y - self.nose_y) * NOSE_SMOOTHING

            if not self.calibrated or self.baseline_y is None:
                self.signal = "NONE"
                return

            delta = self.nose_y - self.baseline_y
            if delta > -JUMP_RESET_THRESHOLD:
                self._jump_armed = True

            if self._jump_armed and delta < -JUMP_THRESHOLD:
                self._jump_armed = False
                self._jump_pending = True

            self.signal = "JUMP" if delta < -JUMP_THRESHOLD else "NONE"

    def _mark_face_missing(self):
        with self._lock:
            self.face_detected = False
            self.signal = "NONE"

    def _loop(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.2)
                continue

            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)

            if frame.mean() < 1.0:
                h, w, _ = frame.shape
                cv2.putText(
                    frame,
                    "FECHE O APP DA CAM",
                    (10, h // 2 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 220, 255),
                    1,
                )
                self.frame_for_preview = frame
                time.sleep(0.05)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.face_mesh.process(rgb)

            h, w, _ = frame.shape

            if result.multi_face_landmarks:
                landmarks = result.multi_face_landmarks[0].landmark
                nose = landmarks[1]
                self._update_nose_position(nose.y * h)
                self.nose_norm = (nose.x, nose.y)

                cx, cy = int(nose.x * w), int(nose.y * h)
            else:
                self._mark_face_missing()
                self.nose_norm = None
                cx, cy = None, None

            ref_y = self.baseline_y if self.baseline_y is not None else (h / 2.0)
            jump_line_y = int(ref_y - JUMP_THRESHOLD)

            color_jump = (80, 83, 239) if self.signal == "JUMP" else (107, 203, 119)

            # Linha de limite da zona de detecção de pulo (threshold)
            cv2.line(frame, (0, jump_line_y), (w, jump_line_y), color_jump, 2)
            cv2.putText(
                frame,
                "LIMITE PULO",
                (6, max(14, jump_line_y - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color_jump,
                2,
            )

            # Linha de posição base de calibração
            if self.baseline_y is not None:
                base_y_int = int(self.baseline_y)
                cv2.line(frame, (0, base_y_int), (w, base_y_int), (180, 180, 180), 1)

            if cx is not None and cy is not None:
                dot_color = (80, 83, 239) if self.signal == "JUMP" else (107, 203, 119)
                cv2.circle(frame, (cx, cy), 7, dot_color, -1)
                cv2.circle(frame, (cx, cy), 10, (255, 255, 255), 2)
            else:
                cv2.putText(
                    frame,
                    "POSICIONE O ROSTO",
                    (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (0, 220, 255),
                    1,
                )

            self.frame_for_preview = frame
            time.sleep(0.01)

        if self.cap is not None:
            self.cap.release()
            self.cap = None
