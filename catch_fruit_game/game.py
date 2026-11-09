"""
Catch Fruit - Pássaro Faminto
=============================
Um pássaro come as frutas que caem do topo da tela.
O jogador move o pássaro para os lados movendo o nariz na frente da webcam.

Menus de início e de fim de jogo: game_menu.py (compartilhado pelos jogos).
"""

import os
import random
import sys
import threading
import time

import pygame

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import database
except ImportError:
    pass

import game_menu

try:
    import cv2
    import mediapipe as mp
except ImportError:
    print(
        "ERRO: opencv-python ou mediapipe nao estao instalados. Rode: pip install opencv-python mediapipe"
    )
    sys.exit(1)

# --- CONSTANTES ---
# Configurações do jogo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITES_DIR = os.path.join(BASE_DIR, "assets", "sprites")
BG_PATH = os.path.join(BASE_DIR, "assets", "bg", "background.png")

SCREEN_W, SCREEN_H = 960, 600
FPS = 60

CAM_INDEX = 0
CAM_PREVIEW_W, CAM_PREVIEW_H = 220, 165
SENSITIVITY = 3.0
SMOOTHING = 0.22

GROUND_Y = SCREEN_H - 30
BIRD_SCALE = 0.8

LIVES_START = 3

DIFFICULTY_TIME_STEP_MS = 15_000
DIFFICULTY_SCORE_STEP = 12
FRUIT_SPEED_BASE = 220
FRUIT_SPEED_PER_LEVEL = 22
FRUIT_SPEED_MAX = 620
SPAWN_INTERVAL_BASE_MS = 1150
SPAWN_INTERVAL_DECREASE_MS = 55
SPAWN_INTERVAL_MIN_MS = 450

FRUIT_NAMES = [
    "fruitmelancia",
    "fruitlaranja",
    "fruitlimao",
    "fruitmorango",
    "fruituva",
]

EAT_SEQUENCE = [
    ("react", 90),
    ("eat1", 110),
    ("eat2", 110),
    ("swallowing", 160),
    ("chewing1", 90),
    ("chewing2", 90),
    ("chewing3", 90),
    ("chewing4", 90),
    ("swallowing2", 140),
    ("satisfied", 220),
]

WHITE = (255, 255, 255)
BLACK = (10, 10, 10)
YELLOW = (255, 210, 40)
RED = (220, 40, 40)
GREEN = (60, 200, 90)
DARK = (20, 20, 30)



class NoseTracker:
    def __init__(self, cam_index=0):
        self.cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(
                "Nao foi possivel abrir a webcam. Verifique se ela esta conectada."
            )

        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._lock = threading.Lock()
        self._nose_x = 0.5
        self._nose_y = 0.5
        self._face_found = False
        self._frame_rgb = None

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.face_mesh.process(rgb)

            found = False
            nx, ny = None, None

            if result.multi_face_landmarks:
                landmarks = result.multi_face_landmarks[0].landmark
                nose = landmarks[1]
                nx = nose.x
                ny = nose.y
                found = True

                h, w, _ = frame.shape
                cx, cy = int(nx * w), int(ny * h)
                cv2.circle(frame, (cx, cy), 7, (60, 60, 255), -1)
                cv2.circle(frame, (cx, cy), 9, (255, 255, 255), 2)

            rgb_preview = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            with self._lock:
                self._frame_rgb = rgb_preview
                self._face_found = found
                if found:
                    self._nose_x = nx
                    self._nose_y = ny

        if hasattr(self, "cap") and self.cap is not None:
            self.cap.release()
            self.cap = None

    def get_state(self):
        with self._lock:
            frame = None if self._frame_rgb is None else self._frame_rgb.copy()
            return self._nose_x, self._nose_y, self._face_found, frame

    def stop(self):
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)


def load_sprite(name, scale=1.0):
    path = os.path.join(SPRITES_DIR, f"{name}.png")
    img = pygame.image.load(path).convert_alpha()
    if scale != 1.0:
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
    return img


def load_fruit_sprite(name, target_size=70):
    # Tenta pegar as frutas da pasta do Fruit Ninja Gustavo
    path = os.path.abspath(
        os.path.join(BASE_DIR, "..", "Fruit Ninja", "sprites", f"{name}.png")
    )
    if not os.path.exists(path):
        path = os.path.join(SPRITES_DIR, f"{name}.png")
    img = pygame.image.load(path).convert_alpha()
    
    # Cortar o espaço vazio para a hitbox ficar exata
    bbox = img.get_bounding_rect()
    cropped = pygame.Surface(bbox.size, pygame.SRCALPHA)
    cropped.blit(img, (0, 0), bbox)
    img = cropped
    
    # Redimensiona para que a maior dimensão seja 'target_size'
    w, h = img.get_size()
    scale = target_size / max(w, h)
    if scale != 1.0:
        img = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
    return img


def load_background():
    img = pygame.image.load(BG_PATH).convert()
    return pygame.transform.smoothscale(img, (SCREEN_W, SCREEN_H))


def cv_frame_to_surface(frame_rgb, size):
    frame_rgb = cv2.resize(frame_rgb, size)
    h, w, _ = frame_rgb.shape
    return pygame.image.frombuffer(frame_rgb.tobytes(), (w, h), "RGB")


class Bird:
    def __init__(self, sprites):
        self.sprites = sprites
        self.x = SCREEN_W / 2
        self.smoothed_x = SCREEN_W / 2
        self.y = GROUND_Y

        self.eat_index = 0
        self.eat_timer = 0
        self.ambient_timer = 0
        self.ambient_state = "idle"

    def start_eating(self):
        self.eat_index = 0
        self.eat_timer = EAT_SEQUENCE[0][1]

    def update(self, dt_ms, fruit_is_near):
        if self.eat_index > 0 or self.eat_timer > 0:
            self.eat_timer -= dt_ms
            if self.eat_timer <= 0:
                self.eat_index += 1
                if self.eat_index >= len(EAT_SEQUENCE):
                    self.eat_index = 0
                    self.eat_timer = 0
                else:
                    self.eat_timer = EAT_SEQUENCE[self.eat_index][1]
        else:
            self.ambient_timer -= dt_ms
            if fruit_is_near == "approach":
                self.ambient_state = "approach"
            elif fruit_is_near == "anticipation":
                self.ambient_state = "anticipation"
            else:
                if self.ambient_timer <= 0:
                    self.ambient_state = (
                        "anticipation" if self.ambient_state == "idle" else "idle"
                    )
                    self.ambient_timer = random.randint(900, 1700)

    def current_sprite(self):
        if self.eat_index > 0 or self.eat_timer > 0:
            idx = min(self.eat_index, len(EAT_SEQUENCE) - 1)
            name = EAT_SEQUENCE[idx][0]
        else:
            name = self.ambient_state
        return self.sprites[name]

    def set_target_x(self, target_x):
        self.smoothed_x += (target_x - self.smoothed_x) * SMOOTHING
        self.smoothed_x = max(60, min(SCREEN_W - 60, self.smoothed_x))
        self.x = self.smoothed_x

    def mouth_rect(self):
        sprite_w = 124 * BIRD_SCALE
        sprite_h = 137 * BIRD_SCALE

        hit_w = sprite_w * 0.58
        hit_h = sprite_h * 0.36

        mouth = pygame.Rect(0, 0, hit_w, hit_h)
        mouth.center = (self.x, self.y - sprite_h * 0.74)
        return mouth

    def draw(self, surface):
        img = self.current_sprite()
        rect = img.get_rect(midbottom=(self.x, self.y))
        surface.blit(img, rect)


class Fruit:
    def __init__(self, sprite, name, speed):
        self.sprite = sprite
        self.name = name
        w, h = sprite.get_size()
        self.w, self.h = w, h
        self.x = random.randint(40, SCREEN_W - 40)
        self.y = -h
        self.speed = speed

    def update(self, dt_ms):
        self.y += self.speed * (dt_ms / 1000.0)

    def rect(self):
        return pygame.Rect(self.x - self.w / 2, self.y - self.h / 2, self.w, self.h)

    def draw(self, surface):
        surface.blit(self.sprite, self.sprite.get_rect(center=(self.x, self.y)))


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Catch Fruit - Passaro Faminto")
        self.screen = pygame.display.set_mode(
            (SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.SCALED
        )
        self.clock = pygame.time.Clock()
        self.font_med = pygame.font.SysFont("arial", 28, bold=True)
        self.font_small = pygame.font.SysFont("arial", 18)

        self.background = load_background()


        self.sprites = {}
        for name in [
            "idle",
            "anticipation",
            "approach",
            "react",
            "eat1",
            "eat2",
            "swallowing",
            "chewing1",
            "chewing2",
            "chewing3",
            "chewing4",
            "swallowing2",
            "satisfied",
        ]:
            self.sprites[name] = load_sprite(name, BIRD_SCALE)

        self.fruit_sprites = {
            name: load_fruit_sprite(name, 70) for name in FRUIT_NAMES
        }

        try:
            self.tracker = NoseTracker(CAM_INDEX)
        except RuntimeError as e:
            print(str(e))
            pygame.quit()
            sys.exit(1)

        self.center_x_norm = 0.5
        self.show_hitbox = False
        self.menu = game_menu.GameMenu(
            self.screen,
            self.clock,
            nose=self._menu_nose,
            frame=lambda: self.tracker.get_state()[3],
            accent=(249, 168, 38),
        )
        self.reset()

    def _menu_nose(self):
        nx, ny, found, _frame = self.tracker.get_state()
        return (nx, ny) if found else None

    def reset(self):
        self.bird = Bird(self.sprites)
        self.fruits = []
        self.score = 0
        self.lives = LIVES_START
        self.spawn_timer = 0
        self.game_over = False
        self.score_saved = False
        self.elapsed = 0
        self.bg_y = 0.0
        self.death_at = None

    def difficulty(self):
        time_level = self.elapsed // DIFFICULTY_TIME_STEP_MS
        score_level = self.score // DIFFICULTY_SCORE_STEP
        level = int(time_level + score_level)
        speed = min(
            FRUIT_SPEED_MAX, FRUIT_SPEED_BASE + level * FRUIT_SPEED_PER_LEVEL
        )
        spawn_interval = max(
            SPAWN_INTERVAL_MIN_MS,
            SPAWN_INTERVAL_BASE_MS - level * SPAWN_INTERVAL_DECREASE_MS,
        )
        return level, speed, spawn_interval

    def spawn_fruit(self):
        name = random.choice(FRUIT_NAMES)

        _level, speed, _spawn_interval = self.difficulty()
        speed = min(FRUIT_SPEED_MAX, speed * random.uniform(0.90, 1.20))
        self.fruits.append(Fruit(self.fruit_sprites[name], name, speed))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.quit()
                elif event.key == pygame.K_SPACE:
                    nx, _ny, found, _f = self.tracker.get_state()
                    if found:
                        self.center_x_norm = nx
                elif event.key == pygame.K_h:
                    self.show_hitbox = not self.show_hitbox

    def update(self, dt_ms):
        if self.game_over:
            return

        self.elapsed += dt_ms

        bg_speed = 60
        self.bg_y = (self.bg_y + bg_speed * (dt_ms / 1000.0)) % SCREEN_H

        nx, _ny, found, _frame = self.tracker.get_state()
        if found:
            deviation = (nx - self.center_x_norm) * SENSITIVITY
            target_norm = 0.5 + deviation
            target_norm = max(0.0, min(1.0, target_norm))
            target_x = target_norm * SCREEN_W
            self.bird.set_target_x(target_x)

        _level, _speed, spawn_interval = self.difficulty()
        self.spawn_timer -= dt_ms
        if self.spawn_timer <= 0:
            self.spawn_fruit()
            self.spawn_timer = spawn_interval

        mouth = self.bird.mouth_rect()
        fruit_is_near = None
        for fruit in self.fruits:
            if abs(fruit.x - self.bird.x) < 70:
                dy = mouth.centery - fruit.y
                if 0 < dy < 90:
                    fruit_is_near = "approach"
                    break
                elif 0 < dy < 260:
                    fruit_is_near = fruit_is_near or "anticipation"

        self.bird.update(dt_ms, fruit_is_near)

        still_alive = []
        for fruit in self.fruits:
            fruit.update(dt_ms)
            caught = mouth.colliderect(fruit.rect())
            if caught:
                self.score += 1
                self.bird.start_eating()
                continue
            if fruit.y - fruit.h / 2 > SCREEN_H:
                self.lives -= 1
                if self.lives <= 0:
                    self.game_over = True
                    if not getattr(self, "score_saved", False):
                        if len(sys.argv) > 1:
                            try:
                                database.save_score(
                                    sys.argv[1], "Catch Fruit Game", self.score
                                )
                            except Exception as e:
                                print(f"Erro ao salvar score: {e}")
                        self.score_saved = True
                continue
            still_alive.append(fruit)
        self.fruits = still_alive

    def draw_hud(self):
        score_surf = self.font_med.render(f"Pontos: {self.score}", True, WHITE)
        self.screen.blit(score_surf, (16, 14))

        for i in range(LIVES_START):
            color = RED if i < self.lives else (90, 90, 90)
            pygame.draw.circle(self.screen, color, (24 + i * 26, 56), 9)
            pygame.draw.circle(self.screen, BLACK, (24 + i * 26, 56), 9, 2)

        level, speed, _spawn_interval = self.difficulty()
        lvl_surf = self.font_small.render(
            f"Nivel {level}  Velocidade {int(speed)}", True, YELLOW
        )
        self.screen.blit(lvl_surf, (16, 76))

        hint_str = f"ESPAÇO: calibrar centro   H: hitbox ({'ON' if self.show_hitbox else 'OFF'})   ESC: voltar ao menu"
        hint = self.font_small.render(hint_str, True, (220, 220, 220))
        self.screen.blit(hint, (16, SCREEN_H - 26))

    def draw_camera_preview(self):
        _nx, _ny, found, frame = self.tracker.get_state()
        x0 = SCREEN_W - CAM_PREVIEW_W - 14
        y0 = 36  # Canto superior direito, deixando espaço para o texto
        border_color = GREEN if found else RED

        if frame is not None:
            surf = cv_frame_to_surface(frame, (CAM_PREVIEW_W, CAM_PREVIEW_H))
            surf.set_alpha(150)  # Reduz a opacidade para ver as frutas por trás
            self.screen.blit(surf, (x0, y0))
        else:
            pygame.draw.rect(self.screen, DARK, (x0, y0, CAM_PREVIEW_W, CAM_PREVIEW_H))

        pygame.draw.rect(
            self.screen, border_color, (x0, y0, CAM_PREVIEW_W, CAM_PREVIEW_H), 3
        )
        label = self.font_small.render(
            "camera: nariz detectado" if found else "camera: procurando rosto...",
            True,
            WHITE,
        )
        self.screen.blit(label, (x0, y0 - 22))

    def draw(self):
        y_offset = int(self.bg_y)
        self.screen.blit(self.background, (0, y_offset))
        self.screen.blit(self.background, (0, y_offset - SCREEN_H))

        for fruit in self.fruits:
            fruit.draw(self.screen)

        self.bird.draw(self.screen)

        if self.show_hitbox:
            mouth = self.bird.mouth_rect()
            pygame.draw.rect(self.screen, (0, 255, 0), mouth, 2)
            for fruit in self.fruits:
                pygame.draw.rect(self.screen, (255, 0, 0), fruit.rect(), 2)

        self.draw_hud()
        self.draw_camera_preview()

        pygame.display.flip()

    def show_welcome_screen(self):
        """Menu inicial padronizado (controlado pela câmera)."""
        historia = [
            "BimBird está com muita fome!",
            "Mova sua cabeça para os lados para",
            "pegar as frutas deliciosas e encher",
            "a barriga do pequeno pássaro!",
        ]
        if self.menu.start_screen("CATCH FRUIT", historia, self.background) != "play":
            self.quit()
        self.start_round()

    def start_round(self):
        """Contagem 'olhe para o centro' e calibração antes de cada partida."""
        if self.menu.countdown(self.background) == "quit":
            self.quit()
        nx, _ny, found, _frame = self.tracker.get_state()
        if found:
            self.center_x_norm = nx

    def quit(self):
        self.tracker.stop()
        pygame.quit()
        sys.exit(0)

    def run(self):
        self.show_welcome_screen()
        while True:
            dt_ms = self.clock.tick(FPS)
            self.handle_events()
            self.update(dt_ms)
            self.draw()

            # Menu de fim de jogo (após um instante mostrando a jogada final)
            if self.game_over:
                now = pygame.time.get_ticks()
                if self.death_at is None:
                    self.death_at = now
                elif now - self.death_at > game_menu.DEATH_DELAY_MS:
                    choice = self.menu.game_over_screen([f"PONTOS: {self.score}"])
                    if choice != "again":
                        self.quit()
                    self.reset()
                    self.start_round()


if __name__ == "__main__":
    Game().run()
