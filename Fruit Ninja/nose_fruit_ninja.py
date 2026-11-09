"""
Fruit Ninja no Cabeceio
=======================
Corte frutas com o nariz (MediaPipe FaceMesh) e evite as bombas.
Sem câmera, a lâmina segue o mouse.

Menus de início e de fim de jogo: game_menu.py (compartilhado pelos jogos).
Sprites na pasta "sprites": fruit*.png, fruit*corte.png, fruitparticula*.png,
fruitbomba.png, fruitcoracao.png e fruitfundo.png.
"""

import math
import os
import random
import sys
import threading
import time
from collections import deque

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import database
except ImportError:
    pass

import game_menu
import pygame

try:
    import cv2
    import mediapipe as mp

    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False


# ---------------------------------------------------------------------------
# --- CONSTANTES ---
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITES_DIR = os.path.join(BASE_DIR, "sprites")
try:
    HIGH_SCORE_PATH = os.path.join(database.DATA_DIR, "fruit_ninja_highscore.txt")
except NameError:  # database indisponível: guarda o recorde ao lado do jogo
    HIGH_SCORE_PATH = os.path.join(BASE_DIR, "highscore.txt")


def get_sprite_path(filename):
    """Retorna o caminho do sprite, procurando na pasta 'sprites' ou na raiz."""
    path_in_sprites = os.path.join(SPRITES_DIR, filename)
    if os.path.exists(path_in_sprites):
        return path_in_sprites
    path_in_base = os.path.join(BASE_DIR, filename)
    if os.path.exists(path_in_base):
        return path_in_base
    return path_in_sprites


WIDTH, HEIGHT = 900, 600
FPS = 60

WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
RED = (215, 50, 50)
GREEN = (60, 180, 80)
YELLOW = (240, 200, 40)
MOUNTAIN_BLUE = (50, 90, 140)
MOUNTAIN_DARK = (30, 55, 90)
GROUND_BROWN = (70, 50, 35)

SENSITIVITY = 4.0
SMOOTHING = 0.35

TRAIL_LIFETIME_MS = 180
TRAIL_WIDTH = 16

GRAVITY = 0.18
FRUIT_RADIUS = 50
BOMB_RADIUS = 45
LIVES_START = 3

# Dimensões e posição da câmera (Canto Superior Direito)
CAM_RECT_W = 160
CAM_RECT_H = 120
CAM_RECT_X = WIDTH - CAM_RECT_W - 20
CAM_RECT_Y = 20

# Limites do Campo de Força (um pouco maior que a câmera para garantir a colisão)
NO_FLY_ZONE_X = CAM_RECT_X - 15
NO_FLY_ZONE_Y = CAM_RECT_Y + CAM_RECT_H + 15


# ---------------------------------------------------------------------------
# Rastreador de rosto (Webcam)
# ---------------------------------------------------------------------------
class NoseCursor:
    def __init__(self):
        self.available = CAMERA_AVAILABLE
        self.nose_x = None
        self.nose_y = None
        self.baseline_x = None
        self.baseline_y = None
        self.delta_x = 0.0
        self.delta_y = 0.0
        self.face_found = False
        self.running = False
        self.frame_for_preview = None
        self._thread = None

        if self.available:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.available = False

    def start(self):
        if not self.available:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.available and self.cap is not None:
            self.cap.release()
            self.cap = None

    def calibrate(self):
        if self.nose_x is not None:
            self.baseline_x = self.nose_x
            self.baseline_y = self.nose_y

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.face_mesh.process(rgb)

            h, w, _ = frame.shape
            if result.multi_face_landmarks:
                landmarks = result.multi_face_landmarks[0].landmark
                nose = landmarks[1]
                self.nose_x = nose.x
                self.nose_y = nose.y

                if self.baseline_x is None:
                    self.baseline_x = self.nose_x
                    self.baseline_y = self.nose_y

                self.delta_x = self.nose_x - self.baseline_x
                self.delta_y = self.nose_y - self.baseline_y

                cx, cy = int(nose.x * w), int(nose.y * h)
                cv2.circle(frame, (cx, cy), 6, (0, 255, 0), -1)
                self.face_found = True
            else:
                self.face_found = False

            self.frame_for_preview = frame
            time.sleep(0.01)


# ---------------------------------------------------------------------------
# Carregadores de Imagens
# ---------------------------------------------------------------------------
def load_fruit_image(filename, fallback_color, size_mult=2.0):
    filepath = get_sprite_path(filename)
    w = int(FRUIT_RADIUS * size_mult)
    if os.path.exists(filepath):
        try:
            img = pygame.image.load(filepath).convert_alpha()
            return pygame.transform.smoothscale(img, (w, w))
        except Exception as e:
            print(f"Erro ao carregar {filepath}: {e}")

    surf = pygame.Surface((w, w), pygame.SRCALPHA)
    pygame.draw.circle(surf, fallback_color, (w // 2, w // 2), w // 2)
    pygame.draw.circle(surf, BLACK, (w // 2, w // 2), w // 2, 3)
    return surf


def load_particle(filename):
    filepath = get_sprite_path(filename)
    if os.path.exists(filepath):
        try:
            img = pygame.image.load(filepath).convert_alpha()
            return pygame.transform.smoothscale(img, (16, 16))
        except Exception as e:
            print(f"Erro ao carregar partícula {filepath}: {e}")
    return None


def load_background():
    for filename in (
        "fruitfundo.png",
        "fruitfundo.jfif",
        "background.png",
        "background.jpg",
    ):
        filepath = get_sprite_path(filename)
        if os.path.exists(filepath):
            try:
                img = pygame.image.load(filepath).convert()
                return pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
            except Exception as e:
                print(f"Erro ao carregar o fundo {filepath}: {e}")

    surf = pygame.Surface((WIDTH, HEIGHT))
    top_color = (75, 115, 155)
    bottom_color = (135, 165, 185)
    for y in range(int(HEIGHT * 0.75)):
        t = y / (HEIGHT * 0.75)
        color = tuple(
            int(top_color[i] + (bottom_color[i] - top_color[i]) * t) for i in range(3)
        )
        pygame.draw.line(surf, color, (0, y), (WIDTH, y))

    m_back = [
        (0, 450),
        (120, 280),
        (280, 420),
        (450, 240),
        (620, 400),
        (800, 260),
        (WIDTH, 450),
    ]
    pygame.draw.polygon(surf, MOUNTAIN_DARK, m_back)

    m_front = [
        (0, 450),
        (90, 320),
        (220, 450),
        (380, 280),
        (550, 450),
        (730, 300),
        (WIDTH, 450),
    ]
    pygame.draw.polygon(surf, MOUNTAIN_BLUE, m_front)

    for i in range(len(m_front) - 1):
        pygame.draw.line(surf, BLACK, m_front[i], m_front[i + 1], 3)

    ground_rect = pygame.Rect(0, int(HEIGHT * 0.75), WIDTH, int(HEIGHT * 0.25))
    pygame.draw.rect(surf, GROUND_BROWN, ground_rect)
    pygame.draw.line(
        surf, BLACK, (0, int(HEIGHT * 0.75)), (WIDTH, int(HEIGHT * 0.75)), 4
    )

    for x in range(20, WIDTH, 45):
        pygame.draw.line(
            surf,
            (30, 80, 30),
            (x, int(HEIGHT * 0.75)),
            (x - 4, int(HEIGHT * 0.75) - 12),
            3,
        )
        pygame.draw.line(
            surf,
            (50, 140, 50),
            (x, int(HEIGHT * 0.75)),
            (x + 3, int(HEIGHT * 0.75) - 15),
            3,
        )
        pygame.draw.line(
            surf, BLACK, (x, int(HEIGHT * 0.75)), (x, int(HEIGHT * 0.75) - 12), 1
        )

    return surf


# ---------------------------------------------------------------------------
# Sistema de Recorde
# ---------------------------------------------------------------------------
def get_high_score():
    if os.path.exists(HIGH_SCORE_PATH):
        try:
            with open(HIGH_SCORE_PATH, "r", encoding="ascii") as f:
                return int(f.read())
        except (OSError, ValueError):
            return 0
    return 0


def save_high_score(score):
    os.makedirs(os.path.dirname(HIGH_SCORE_PATH), exist_ok=True)
    temporary_path = f"{HIGH_SCORE_PATH}.tmp"
    with open(temporary_path, "w", encoding="ascii") as f:
        f.write(str(score))
    os.replace(temporary_path, HIGH_SCORE_PATH)


# ---------------------------------------------------------------------------
# Utilidades Geométricas
# ---------------------------------------------------------------------------
def draw_pixel_heart(surf, color, cx, cy, size):
    r = size // 5
    pygame.draw.circle(surf, BLACK, (cx - r - 1, cy - (r // 2)), r + 2)
    pygame.draw.circle(surf, BLACK, (cx + r + 1, cy - (r // 2)), r + 2)
    pygame.draw.polygon(
        surf,
        BLACK,
        [
            (cx - 2 * r - 2, cy - (r // 2)),
            (cx + 2 * r + 2, cy - (r // 2)),
            (cx, cy + int(r * 2.5) + 2),
        ],
    )
    pygame.draw.circle(surf, color, (cx - r, cy - (r // 2)), r)
    pygame.draw.circle(surf, color, (cx + r, cy - (r // 2)), r)
    pygame.draw.polygon(
        surf,
        color,
        [
            (cx - 2 * r, cy - (r // 2)),
            (cx + 2 * r, cy - (r // 2)),
            (cx, cy + int(r * 2.5)),
        ],
    )


def segment_circle_intersect(p1, p2, center, radius):
    x1, y1 = p1
    x2, y2 = p2
    cx, cy = center
    dx, dy = x2 - x1, y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(cx - x1, cy - y1) <= radius

    t = ((cx - x1) * dx + (cy - y1) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.hypot(cx - closest_x, cy - closest_y) <= radius


# ---------------------------------------------------------------------------
# Entidades do Jogo
# ---------------------------------------------------------------------------
class Fruit:
    def __init__(self, fruit_images, fruit_images_corte=None, is_bomb=False):
        self.is_bomb = is_bomb
        # Restringe um pouco o nascimento no canto direito para evitar acúmulo no escudo
        self.x = random.uniform(WIDTH * 0.1, WIDTH * 0.7)
        self.y = HEIGHT + 40
        self.vx = random.uniform(-1.2, 1.2)
        self.vy = random.uniform(-12.8, -10.0)
        self.radius = BOMB_RADIUS if is_bomb else FRUIT_RADIUS
        self.rotation = random.uniform(0, 360)
        self.spin = random.uniform(-2.0, 2.0)
        self.sliced = False
        self.dead = False

        if not is_bomb:
            self.name, self.image = random.choice(list(fruit_images.items()))
            self.color = (50, 200, 50)
            self.image_corte = (
                fruit_images_corte[self.name] if fruit_images_corte else self.image
            )
        else:
            self.name = "Bomba"
            self.color = (35, 35, 40)
            bomba_file = get_sprite_path("fruitbomba.png")
            if not os.path.exists(bomba_file):
                bomba_file = get_sprite_path("Bomba.png")

            if os.path.exists(bomba_file):
                img_temp = pygame.image.load(bomba_file).convert_alpha()
                larg_orig, alt_orig = img_temp.get_size()
                nova_largura = BOMB_RADIUS * 2
                proporcao = nova_largura / larg_orig
                nova_altura = int(alt_orig * proporcao)
                self.image = pygame.transform.smoothscale(
                    img_temp, (nova_largura, nova_altura)
                )
            else:
                self.image = pygame.Surface(
                    (BOMB_RADIUS * 2, BOMB_RADIUS * 2), pygame.SRCALPHA
                )
                pygame.draw.circle(
                    self.image, (35, 35, 40), (BOMB_RADIUS, BOMB_RADIUS), BOMB_RADIUS
                )
                pygame.draw.circle(
                    self.image, RED, (BOMB_RADIUS, BOMB_RADIUS), BOMB_RADIUS, 4
                )
                pygame.draw.line(
                    self.image,
                    RED,
                    (10, 10),
                    (BOMB_RADIUS * 2 - 10, BOMB_RADIUS * 2 - 10),
                    4,
                )
                pygame.draw.line(
                    self.image,
                    RED,
                    (10, BOMB_RADIUS * 2 - 10),
                    (BOMB_RADIUS * 2 - 10, 10),
                    4,
                )

        self.slice_parts = []

    def update(self):
        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy
        self.rotation += self.spin

        # A BARREIRA FÍSICA INVISÍVEL (No-Fly Zone da Câmera)
        # Se a fruta tentar entrar na área reservada da câmera, ela bate e quica pra esquerda
        if (
            self.x + self.radius > NO_FLY_ZONE_X
            and self.y - self.radius < NO_FLY_ZONE_Y
        ):
            self.vx = -abs(self.vx) * 0.8  # Inverte a velocidade horizontal
            self.x = NO_FLY_ZONE_X - self.radius

        for part in self.slice_parts:
            part[2] += GRAVITY * 0.6
            part[0] += part[3]
            part[1] += part[2]
            part[4] += part[5]

            # A mesma barreira se aplica às metades da fruta cortada
            if (
                part[0] + self.radius > NO_FLY_ZONE_X
                and part[1] - self.radius < NO_FLY_ZONE_Y
            ):
                part[3] = -abs(part[3]) * 0.8
                part[0] = NO_FLY_ZONE_X - self.radius

        if self.y - self.radius > HEIGHT + 60:
            self.dead = True

    def slice(self):
        self.sliced = True
        for side in (-1, 1):
            self.slice_parts.append(
                [
                    self.x,
                    self.y,
                    self.vy * 0.5,
                    self.vx + side * 3.0,
                    self.rotation,
                    self.spin + side * 6,
                ]
            )

    @property
    def center(self):
        return (self.x, self.y)

    def draw(self, surf):
        if not self.sliced:
            rotated_img = pygame.transform.rotate(self.image, self.rotation)
            rect = rotated_img.get_rect(center=(int(self.x), int(self.y)))
            surf.blit(rotated_img, rect.topleft)
        else:
            for part in self.slice_parts:
                px, py, pvy, pvx, prot, pspin = part
                img_to_rotate = self.image_corte if not self.is_bomb else self.image
                rotated = pygame.transform.rotate(img_to_rotate, prot)
                rect = rotated.get_rect(center=(int(px), int(py)))
                surf.blit(rotated, rect.topleft)


class Particle:
    def __init__(self, x, y, color, image=None):
        self.x, self.y = x, y
        angle = random.uniform(0, 360)
        speed = random.uniform(1.5, 4.5)
        self.vx = math.cos(math.radians(angle)) * speed
        self.vy = math.sin(math.radians(angle)) * speed
        self.color = color
        self.life = 400
        self.age = 0
        self.image = image

    def update(self, dt):
        self.age += dt
        self.vy += GRAVITY * 0.4
        self.x += self.vx
        self.y += self.vy

        # A barreira física também rebate os sucos/partículas
        if self.x > NO_FLY_ZONE_X and self.y < NO_FLY_ZONE_Y:
            self.vx = -abs(self.vx) * 0.8
            self.x = NO_FLY_ZONE_X

    def dead(self):
        return self.age >= self.life

    def draw(self, surf):
        alpha = max(0, 255 - int(255 * (self.age / self.life)))

        if self.image:
            img_copy = self.image.copy()
            img_copy.set_alpha(alpha)
            rect = img_copy.get_rect(center=(int(self.x), int(self.y)))
            surf.blit(img_copy, rect.topleft)
        else:
            s = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.rect(s, BLACK, (0, 0, 10, 10))
            pygame.draw.rect(s, (*self.color, alpha), (1, 1, 8, 8))
            surf.blit(s, (self.x - 5, self.y - 5))


# ---------------------------------------------------------------------------
# Loop Principal do Jogo
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    pygame.display.set_caption("Fruit Ninja Retrô - Câmera Reservada")
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Courier New", 20, bold=True)

    background = load_background()

    heart_img_full = None
    heart_img_empty = None
    heart_path = get_sprite_path("fruitcoracao.png")
    if os.path.exists(heart_path):
        try:
            raw_heart = pygame.image.load(heart_path).convert_alpha()
            heart_img_full = pygame.transform.smoothscale(raw_heart, (28, 28))
            heart_img_empty = heart_img_full.copy()
            heart_img_empty.fill(
                (70, 70, 70, 255), special_flags=pygame.BLEND_RGBA_MULT
            )
        except Exception as e:
            print(f"Erro ao carregar o coração: {e}")

    fruit_images = {
        "Laranja": load_fruit_image("fruitlaranja.png", (240, 120, 10)),
        "Limão": load_fruit_image("fruitlimao.png", (220, 230, 20)),
        "Uva": load_fruit_image("fruituva.png", (160, 30, 230)),
        "Morango": load_fruit_image("fruitmorango.png", (230, 20, 100)),
        "Melancia": load_fruit_image("fruitmelancia.png", (40, 230, 40)),
    }

    fruit_images_corte = {
        "Laranja": load_fruit_image("fruitlaranjacorte.png", (240, 120, 10), 1.2),
        "Limão": load_fruit_image("fruitlimaocorte.png", (220, 230, 20), 1.2),
        "Uva": load_fruit_image("fruituvacorte.png", (160, 30, 230), 1.2),
        "Morango": load_fruit_image("fruitmorangocorte.png", (230, 20, 100), 1.2),
        "Melancia": load_fruit_image("fruitmelanciacorte.png", (40, 230, 40), 1.2),
    }

    particle_images = {
        "Laranja": load_particle("fruitparticulalaranja.png"),
        "Limão": load_particle("fruitparticulalimao.png"),
        "Uva": load_particle("fruitparticulauva.png"),
        "Morango": load_particle("fruitparticulamorango.png"),
        "Melancia": load_particle("fruitparticulamelancia.png"),
    }

    cursor = NoseCursor()
    cursor.start()
    calibrated = False

    trail = deque()
    cursor_pos = [WIDTH / 2, HEIGHT / 2]

    fruits = []
    particles = []
    spawn_timer = 0
    score = 0
    lives = LIVES_START
    game_over = False
    elapsed_time = 0
    high_score = get_high_score()
    difficulty_level = 0
    score_saved = False

    # ---- Menus padronizados (início / fim de jogo) controlados pela câmera ----
    def nose_pos():
        if cursor.available and cursor.face_found and cursor.nose_x is not None:
            return (cursor.nose_x, cursor.nose_y)
        return None

    def camera_frame():
        frame = cursor.frame_for_preview
        return None if frame is None else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    menu = game_menu.GameMenu(
        screen, clock, nose=nose_pos, frame=camera_frame, accent=(233, 69, 96)
    )

    def leave_game():
        cursor.stop()
        pygame.quit()
        sys.exit(0)

    def start_round():
        """Contagem 'olhe para o centro' e calibração antes de cada partida."""
        nonlocal calibrated
        if menu.countdown(background) == "quit":
            leave_game()
        if cursor.available and cursor.face_found:
            cursor.calibrate()
            calibrated = True

    historia = [
        "Torne-se um mestre ninja!",
        "Seu nariz agora é uma katana super afiada.",
        "Mova a cabeça pela tela para cortar",
        "frutas e evite as bombas a todo custo!",
    ]

    if menu.start_screen("FRUIT NINJA", historia, background) != "play":
        leave_game()
    start_round()
    death_at = None

    running = True
    while running:
        dt = clock.tick(FPS)
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    if cursor.available:
                        cursor.calibrate()
                        calibrated = True

        # --- Posição da "lâmina" ---
        if cursor.available and calibrated:
            target_x = WIDTH / 2 + cursor.delta_x * WIDTH * SENSITIVITY
            target_y = HEIGHT / 2 + cursor.delta_y * HEIGHT * SENSITIVITY
        else:
            target_x, target_y = pygame.mouse.get_pos()

        cursor_pos[0] += (target_x - cursor_pos[0]) * SMOOTHING
        cursor_pos[1] += (target_y - cursor_pos[1]) * SMOOTHING
        cursor_pos[0] = max(0, min(WIDTH, cursor_pos[0]))
        cursor_pos[1] = max(0, min(HEIGHT, cursor_pos[1]))

        prev_point = trail[-1][:2] if trail else tuple(cursor_pos)
        trail.append((cursor_pos[0], cursor_pos[1], now))

        while trail and now - trail[0][2] > TRAIL_LIFETIME_MS:
            trail.popleft()

        if not game_over:
            elapsed_time += dt
            difficulty_level = min(5, (elapsed_time // 1000) // 45)

            spawn_timer -= dt
            if spawn_timer <= 0:
                # Quantidade de frutas por onda aumenta progressivamente com o tempo (de 1 até 5)
                max_fruits = min(5, 1 + difficulty_level)
                min_fruits = 1 if difficulty_level < 3 else 2
                num_fruits_to_spawn = random.randint(min_fruits, max_fruits)

                has_fruit = False
                for i in range(num_fruits_to_spawn):
                    bomb_chance = 0.08 + (difficulty_level * 0.035)
                    # Garante que na onda haja pelo menos uma fruta jogável caso as anteriores tenham sido bombas
                    if i == num_fruits_to_spawn - 1 and not has_fruit:
                        is_bomb = False
                    else:
                        is_bomb = random.random() < bomb_chance

                    if not is_bomb:
                        has_fruit = True

                    fruits.append(
                        Fruit(
                            fruit_images,
                            fruit_images_corte=fruit_images_corte,
                            is_bomb=is_bomb,
                        )
                    )

                min_spawn = int(1200 - (difficulty_level * 90))
                max_spawn = int(1800 - (difficulty_level * 120))
                spawn_timer = random.randint(min_spawn, max_spawn)

            for f in fruits:
                f.update()

            for p in particles:
                p.update(dt)
            particles = [p for p in particles if not p.dead()]

            new_segment = (prev_point, tuple(cursor_pos))
            for f in fruits:
                if f.sliced or f.dead:
                    continue
                if segment_circle_intersect(
                    new_segment[0], new_segment[1], f.center, f.radius
                ):
                    if f.is_bomb:
                        game_over = True
                    else:
                        f.slice()
                        score += 1

                        p_img = particle_images.get(f.name)
                        for _ in range(14):
                            particles.append(Particle(f.x, f.y, f.color, image=p_img))

            for f in fruits:
                if f.dead and not f.sliced and not f.is_bomb:
                    lives -= 1
            fruits = [f for f in fruits if not f.dead]

            if lives <= 0:
                game_over = True

        if game_over and not score_saved:
            if len(sys.argv) > 1:
                try:
                    database.save_score(sys.argv[1], "Fruit Ninja", score)
                except Exception as e:
                    print(f"Erro ao salvar: {e}")
            score_saved = True

        # --- Menu de fim de jogo (após um instante mostrando a jogada final) ---
        if game_over:
            if death_at is None:
                death_at = now
            elif now - death_at > game_menu.DEATH_DELAY_MS:
                if score > high_score:
                    high_score = score
                    save_high_score(high_score)
                choice = menu.game_over_screen(
                    [f"PONTOS: {score}", f"RECORDE: {high_score}"]
                )
                if choice != "again":
                    running = False
                    continue
                fruits = []
                particles = []
                trail.clear()
                spawn_timer = 0
                score = 0
                lives = LIVES_START
                game_over = False
                score_saved = False
                elapsed_time = 0
                difficulty_level = 0
                death_at = None
                start_round()
                continue

        # --- Desenho da Tela ---
        screen.blit(background, (0, 0))

        for f in fruits:
            f.draw(screen)
        for p in particles:
            p.draw(screen)

        if len(trail) >= 2:
            trail_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pts = list(trail)
            for i in range(1, len(pts)):
                x1, y1, t1 = pts[i - 1]
                x2, y2, t2 = pts[i]
                age = now - t2
                frac = max(0.0, 1 - age / TRAIL_LIFETIME_MS)
                alpha = int(255 * frac)
                width = max(3, int(TRAIL_WIDTH * frac))
                pygame.draw.line(
                    trail_surf,
                    (20, 20, 20, alpha),
                    (x1 + 2, y1 + 2),
                    (x2 + 2, y2 + 2),
                    width,
                )
                pygame.draw.line(
                    trail_surf, (255, 255, 255, alpha), (x1, y1), (x2, y2), width
                )
            screen.blit(trail_surf, (0, 0))

        pygame.draw.circle(screen, BLACK, (int(cursor_pos[0]), int(cursor_pos[1])), 8)
        pygame.draw.circle(screen, YELLOW, (int(cursor_pos[0]), int(cursor_pos[1])), 5)

        # HUD Esquerdo
        score_text = f"SCORE: {score:04d}   |   HIGH: {max(score, high_score):04d}"
        screen.blit(font.render(score_text, True, BLACK), (17, 17))
        screen.blit(font.render(score_text, True, WHITE), (15, 15))

        total_seconds = elapsed_time // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        time_text = f"TEMPO: {minutes:02d}:{seconds:02d}"
        screen.blit(font.render(time_text, True, BLACK), (17, 42))
        screen.blit(font.render(time_text, True, WHITE), (15, 40))

        level_text = f"NÍVEL: {difficulty_level + 1} / 6"
        screen.blit(font.render(level_text, True, BLACK), (17, 67))
        screen.blit(font.render(level_text, True, YELLOW), (15, 65))

        # Vidas (Movido para a esquerda, debaixo do nível para não atrapalhar a câmera)
        for i in range(LIVES_START):
            cx, cy = 30 + (i * 35), 105
            if heart_img_full and heart_img_empty:
                img_to_draw = heart_img_full if i < lives else heart_img_empty
                screen.blit(img_to_draw, (cx - 14, cy - 14))
            else:
                color = RED if i < lives else (70, 70, 70)
                draw_pixel_heart(screen, color, cx, cy, 28)

        # --- DESENHO DO ESPAÇO RESERVADO DA CÂMERA ---
        # Desenha um fundo preto opaco para bloquear a visão do cenário e garantir que nada apareça atrás
        pygame.draw.rect(
            screen, (10, 10, 15), (CAM_RECT_X, CAM_RECT_Y, CAM_RECT_W, CAM_RECT_H)
        )
        # Borda grossa decorativa
        pygame.draw.rect(
            screen, YELLOW, (CAM_RECT_X, CAM_RECT_Y, CAM_RECT_W, CAM_RECT_H), 3
        )

        if cursor.available and cursor.frame_for_preview is not None:
            # Se a câmera estiver ligada, desenha o vídeo dentro da caixa
            preview = cv2.resize(cursor.frame_for_preview, (CAM_RECT_W, CAM_RECT_H))
            preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            preview_surf = pygame.image.frombuffer(
                preview.tobytes(), (CAM_RECT_W, CAM_RECT_H), "RGB"
            )
            screen.blit(preview_surf, (CAM_RECT_X, CAM_RECT_Y))

            status = (
                "CAMERA: OK"
                if calibrated
                else "APERTE ESPAÇO OLHANDO PRO CENTRO PARA CALIBRAR"
            )
            color = GREEN if calibrated else RED
        else:
            # Se não tiver câmera, desenha um texto indicativo dentro do espaço
            no_cam_text = font.render("SEM CAMERA", True, RED)
            screen.blit(
                no_cam_text,
                (
                    CAM_RECT_X + CAM_RECT_W // 2 - no_cam_text.get_width() // 2,
                    CAM_RECT_Y + CAM_RECT_H // 2 - 10,
                ),
            )

            status = "CAMERA INDISPONIVEL — USANDO MOUSE"
            color = RED

        # Movemos o texto de status para o canto inferior esquerdo para não poluir
        screen.blit(font.render(status, True, BLACK), (17, HEIGHT - 27))
        screen.blit(font.render(status, True, color), (15, HEIGHT - 30))
        # ---------------------------------------------

        pygame.display.flip()

    cursor.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
