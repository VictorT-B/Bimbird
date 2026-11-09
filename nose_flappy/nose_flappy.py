"""
Nose Flappy
===========
Flappy Bird controlado pela altura do nariz (MediaPipe FaceMesh).
Sem câmera, use as setas para cima/baixo.

Menus de início e de fim de jogo: game_menu.py (compartilhado pelos jogos).
"""

import os
import random
import sys
import threading
import time

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
WIDTH, HEIGHT = 800, 500
FPS = 60

# A janela real (tamanho da janela do sistema). O jogo continua a usar
# `WIDTH`/`HEIGHT` como resolução lógica; o conteúdo será escalado para
# esta janela mantendo a proporção.
WINDOW_WIDTH, WINDOW_HEIGHT = int(WIDTH * 1.5), int(HEIGHT * 1.5)

SKY = (135, 206, 235)
WHITE = (245, 245, 245)
BLACK = (30, 30, 30)
RED = (200, 60, 60)
GREEN = (60, 170, 90)
DARK_GREEN = (40, 130, 65)
YELLOW = (240, 200, 60)

BIRD_X = 140
BIRD_RADIUS = 16

PIPE_W = 80
PIPE_GAP = 120
PIPE_INTERVAL_MS = 1250
PIPE_FIRST_DELAY_MS = 500  # atraso extra do primeiro spawn após o pipe inicial

# O intervalo entre canos diminui conforme a pontuação sobe, até este mínimo.
PIPE_INTERVAL_MIN_MS = 650
# Quanto o intervalo diminui por ponto (ms). Ajuste pra calibrar dificuldade.
PIPE_SPAWN_DECREASE_PER_SCORE = 10

# Dificuldade progressiva: a cada SCORE_STEP_FOR_DIFFICULTY pontos, a
# velocidade dos canos sobe SPEED_INCREASE_PER_STEP, até o teto PIPE_SPEED_MAX.
PIPE_SPEED_BASE = 5.2
PIPE_SPEED_MAX = 12.0
SPEED_INCREASE_PER_STEP = 0.4
SCORE_STEP_FOR_DIFFICULTY = 3
PIPE_SPEED = PIPE_SPEED_BASE  # velocidade atual, recalculada em main()

# Sensibilidade: quanto 1 pixel de movimento do nariz na imagem da
# webcam equivale em pixels de movimento do passarinho na tela.
SENSITIVITY = 2.5
SMOOTHING = 0.10  # 0 a 1, quanto maior, mais rápido segue o rosto (menos suavizado)

# ---------------------------------------------------------------------------
# Sprites (carregados uma vez em main(), guardados aqui pra classes usarem)
# ---------------------------------------------------------------------------
SPRITES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
SPR = {}

BIRD_DRAW_W, BIRD_DRAW_H = 54, 43
BIRD_HIT_W, BIRD_HIT_H = 24, 18  # hitbox menor que o sprite, pra ser justo

PARTICLE_LIFETIME_MS = 700


def load_sprites():
    """Carrega os sprites da pasta 'sprites'. Se não existir, o jogo cai
    de volta pras formas geométricas simples (nunca quebra por falta de sprite)."""
    if not os.path.isdir(SPRITES_DIR):
        SPR["ok"] = False
        return

    def load(name):
        return pygame.image.load(os.path.join(SPRITES_DIR, name)).convert_alpha()

    try:
        frames = [load(f"bird_{i}.png") for i in range(1, 5)]
        SPR["bird_frames"] = [
            pygame.transform.smoothscale(f, (BIRD_DRAW_W, BIRD_DRAW_H)) for f in frames
        ]

        pipe_raw = load("pipe_body.png")

        # Como o cano agora está sem bordas transparentes, calculamos a altura exata proporcional
        pipe_h = int(pipe_raw.get_height() * (PIPE_W / pipe_raw.get_width()))

        # Garantir que a altura mínima seja pelo menos 450px para cobrir a tela sem esticar desproporcionalmente
        if pipe_h < 450:
            pipe_h = 450

        pipe_scaled = pygame.transform.smoothscale(pipe_raw, (PIPE_W, pipe_h))

        SPR["pipe_bottom_src"] = pipe_scaled
        SPR["pipe_top_src"] = pygame.transform.flip(pipe_scaled, False, True)
        SPR["pipe_h"] = pipe_h

        bg = load("background_nuclear.png")
        bg_h = HEIGHT
        bg_w = int(bg.get_width() * (bg_h / bg.get_height()))
        SPR["background"] = pygame.transform.smoothscale(bg, (bg_w, bg_h))
        SPR["background_w"] = bg_w

        particles = []
        i = 1
        while os.path.exists(os.path.join(SPRITES_DIR, f"particle_{i}.png")):
            particles.append(load(f"particle_{i}.png"))
            i += 1
        SPR["particles"] = particles

        SPR["ok"] = True
    except Exception as exc:
        print(
            f"Aviso: não consegui carregar os sprites ({exc}). Usando formas simples."
        )
        SPR["ok"] = False


class Particle:
    """Pedacinho de destroço/poeira que espalha quando o passarinho bate."""

    def __init__(self, x, y):
        self.img = random.choice(SPR["particles"])
        self.x = x
        self.y = y
        self.vx = random.uniform(-2.5, 2.5)
        self.vy = random.uniform(-4.0, -1.0)
        self.life = PARTICLE_LIFETIME_MS
        self.angle = random.uniform(0, 360)
        self.spin = random.uniform(-6, 6)

    def update(self, dt):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.25  # gravidade
        self.angle += self.spin
        self.life -= dt

    @property
    def alive(self):
        return self.life > 0

    def draw(self, surf):
        alpha = max(0, min(255, int(255 * (self.life / PARTICLE_LIFETIME_MS))))
        img = pygame.transform.rotate(self.img, self.angle)
        img = img.copy()
        img.set_alpha(alpha)
        rect = img.get_rect(center=(int(self.x), int(self.y)))
        surf.blit(img, rect)


# ---------------------------------------------------------------------------
# Rastreador de rosto (thread separada lendo a webcam)
# ---------------------------------------------------------------------------
class NoseTracker:
    """Lê a webcam e calcula a altura (y) do nariz relativa a uma posição
    neutra calibrada. Expõe self.delta: negativo = rosto subiu, positivo = desceu."""

    def __init__(self):
        self.available = CAMERA_AVAILABLE
        self.nose_y = None
        self.nose_norm = None  # (x, y) 0..1 do nariz, None sem rosto (menus)
        self.baseline_y = None
        self.delta = 0.0
        self.running = False
        self.frame_for_preview = None
        self._thread = None
        self.face_mesh = None
        self.cap = None

        if self.available:
            try:
                self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                    max_num_faces=1,
                    refine_landmarks=False,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    raise RuntimeError("não foi possível abrir a câmera")
            except Exception as exc:
                print(f"Aviso: rastreamento facial indisponível ({exc})")
                self.available = False
                self._release_resources()

    def start(self):
        if not self.available:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._release_resources()

    def _release_resources(self):
        cap, self.cap = self.cap, None
        if cap is not None:
            cap.release()

        face_mesh, self.face_mesh = self.face_mesh, None
        if face_mesh is not None:
            face_mesh.close()

    def calibrate(self):
        if self.nose_y is not None:
            self.baseline_y = self.nose_y

    def _loop(self):
        try:
            while self.running:
                ok, frame = self.cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = self.face_mesh.process(rgb)

                h, w, _ = frame.shape
                if result.multi_face_landmarks:
                    landmarks = result.multi_face_landmarks[0].landmark
                    nose = landmarks[1]
                    self.nose_y = nose.y * h
                    self.nose_norm = (nose.x, nose.y)

                    if self.baseline_y is None:
                        self.baseline_y = self.nose_y

                    self.delta = self.nose_y - self.baseline_y

                    cx, cy = int(nose.x * w), int(nose.y * h)
                    cv2.circle(frame, (cx, cy), 6, (0, 255, 0), -1)
                    if self.baseline_y is not None:
                        cv2.line(
                            frame,
                            (0, int(self.baseline_y)),
                            (w, int(self.baseline_y)),
                            (255, 0, 0),
                            1,
                        )
                else:
                    self.nose_norm = None

                self.frame_for_preview = frame
                time.sleep(0.01)
        except Exception as exc:
            print(f"Aviso: rastreamento facial interrompido ({exc})")
            self.available = False
        finally:
            self.running = False
            self._release_resources()


# ---------------------------------------------------------------------------
# Entidades do jogo
# ---------------------------------------------------------------------------
class Bird:
    ANIM_ORDER = [0, 1, 2, 3, 2, 1]
    ANIM_FRAME_TICKS = 6

    def __init__(self):
        self.y = HEIGHT / 2
        self.display_y = HEIGHT / 2
        self.vel = 0.0
        self._anim_counter = 0

    def set_target(self, target_y):
        self.y = target_y

    def update(self):
        prev_y = self.display_y
        self.display_y += (self.y - self.display_y) * SMOOTHING
        self.display_y = max(BIRD_RADIUS, min(HEIGHT - BIRD_RADIUS, self.display_y))
        self.vel = self.display_y - prev_y
        self._anim_counter += 1

    @property
    def rect(self):
        return pygame.Rect(
            BIRD_X - BIRD_HIT_W // 2,
            int(self.display_y) - BIRD_HIT_H // 2,
            BIRD_HIT_W,
            BIRD_HIT_H,
        )

    def draw(self, surf):
        if SPR.get("ok"):
            frame_i = self.ANIM_ORDER[
                (self._anim_counter // self.ANIM_FRAME_TICKS) % len(self.ANIM_ORDER)
            ]
            img = SPR["bird_frames"][frame_i]
            angle = max(-25, min(35, -self.vel * 4))
            img = pygame.transform.rotate(img, angle)
            rect = img.get_rect(center=(BIRD_X, int(self.display_y)))
            surf.blit(img, rect)
        else:
            pygame.draw.circle(surf, YELLOW, (BIRD_X, int(self.display_y)), BIRD_RADIUS)
            pygame.draw.circle(
                surf, BLACK, (BIRD_X, int(self.display_y)), BIRD_RADIUS, 2
            )
            pygame.draw.circle(surf, WHITE, (BIRD_X + 5, int(self.display_y) - 4), 4)
            pygame.draw.circle(surf, BLACK, (BIRD_X + 6, int(self.display_y) - 4), 2)
            pygame.draw.polygon(
                surf,
                RED,
                [
                    (BIRD_X + BIRD_RADIUS - 2, int(self.display_y)),
                    (BIRD_X + BIRD_RADIUS + 8, int(self.display_y) - 3),
                    (BIRD_X + BIRD_RADIUS + 8, int(self.display_y) + 3),
                ],
            )


class PipePair:
    def __init__(self, x):
        self.x = float(x)
        margin = 60
        gap_center = random.randint(
            margin + PIPE_GAP // 2, HEIGHT - margin - PIPE_GAP // 2
        )
        self.gap_top = gap_center - PIPE_GAP // 2
        self.gap_bottom = gap_center + PIPE_GAP // 2
        self.scored = False

    def update(self):
        self.x -= PIPE_SPEED

    def offscreen(self):
        return self.x + PIPE_W < 0

    @property
    def top_rect(self):
        return pygame.Rect(int(self.x), 0, PIPE_W, self.gap_top)

    @property
    def bottom_rect(self):
        return pygame.Rect(
            int(self.x), self.gap_bottom, PIPE_W, HEIGHT - self.gap_bottom
        )

    def draw(self, surf):
        if SPR.get("ok"):
            if self.gap_top > 0:
                y_pos = self.gap_top - SPR["pipe_h"]
                surf.blit(SPR["pipe_top_src"], (int(self.x), y_pos))
            bottom_h = HEIGHT - self.gap_bottom
            if bottom_h > 0:
                surf.blit(SPR["pipe_bottom_src"], (int(self.x), self.gap_bottom))
        else:
            pygame.draw.rect(surf, GREEN, self.top_rect)
            pygame.draw.rect(surf, DARK_GREEN, self.top_rect, 3)
            pygame.draw.rect(surf, GREEN, self.bottom_rect)
            pygame.draw.rect(surf, DARK_GREEN, self.bottom_rect, 3)
            pygame.draw.rect(
                surf, DARK_GREEN, (int(self.x) - 4, self.gap_top - 24, PIPE_W + 8, 24)
            )
            pygame.draw.rect(
                surf, DARK_GREEN, (int(self.x) - 4, self.gap_bottom, PIPE_W + 8, 24)
            )


def difficulty_speed(score):
    """Velocidade dos canos pro placar atual: sobe em degraus a cada
    SCORE_STEP_FOR_DIFFICULTY pontos, até o teto PIPE_SPEED_MAX."""
    steps = score // SCORE_STEP_FOR_DIFFICULTY
    return min(PIPE_SPEED_MAX, PIPE_SPEED_BASE + steps * SPEED_INCREASE_PER_STEP)


def spawn_interval_for_score(score):
    """Retorna o intervalo (ms) entre spawns para o placar atual, levando
    em conta um mínimo para não ficar impossível."""
    return max(
        PIPE_INTERVAL_MIN_MS, PIPE_INTERVAL_MS - score * PIPE_SPAWN_DECREASE_PER_SCORE
    )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------
def main():
    global PIPE_SPEED

    pygame.init()
    pygame.display.set_caption("Flappy Bird no Cabeceio")
    screen = pygame.display.set_mode(
        (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN | pygame.SCALED
    )
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 22)
    big_font = pygame.font.SysFont("arial", 40, bold=True)

    load_sprites()

    tracker = NoseTracker()
    tracker.start()

    bird = Bird()
    pipes = [PipePair(WIDTH + 200)]
    score = 0
    game_over = False
    was_game_over = False
    score_saved = False
    calibrated = False
    particles = []
    bg_x = 0.0
    PIPE_SPEED = PIPE_SPEED_BASE
    spawn_timer = spawn_interval_for_score(score) + PIPE_FIRST_DELAY_MS

    shake_timer = 0
    display_surface = pygame.Surface((WIDTH, HEIGHT))

    key_target_offset = 0.0

    # ---- Menus padronizados (início / fim de jogo) controlados pela câmera ----
    def camera_frame():
        frame = tracker.frame_for_preview
        return None if frame is None else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    menu = game_menu.GameMenu(
        screen,
        clock,
        nose=lambda: tracker.nose_norm if tracker.available else None,
        frame=camera_frame,
        accent=(76, 209, 55),
    )
    menu_background = SPR.get("background") if SPR.get("ok") else None

    def leave_game():
        tracker.stop()
        pygame.quit()
        sys.exit(0)

    def start_round():
        """Contagem 'olhe para o centro' e calibração antes de cada partida."""
        nonlocal calibrated
        if menu.countdown(menu_background) == "quit":
            leave_game()
        if tracker.available and tracker.nose_norm is not None:
            tracker.calibrate()
            calibrated = True

    historia = [
        "O clássico Flappy Bird, mas jogado com a cabeça!",
        "Movimente o nariz para cima e para baixo",
        "para desviar dos canos verdes e chegar o",
        "mais longe possível.",
    ]

    if menu.start_screen("NOSE FLAPPY", historia, menu_background) != "play":
        leave_game()
    start_round()
    death_at = None

    running = True
    while running:
        dt = clock.tick(FPS)

        keys_pressed = pygame.key.get_pressed()

        screen_w, screen_h = screen.get_size()
        scale = min(screen_w / WIDTH, screen_h / HEIGHT)
        dest_w = max(1, int(WIDTH * scale))
        dest_h = max(1, int(HEIGHT * scale))
        offset_x = (screen_w - dest_w) // 2
        offset_y = (screen_h - dest_h) // 2

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE and not game_over:
                    # Só calibra se a câmera encontrou um rosto de verdade!
                    if tracker.available and tracker.nose_y is not None:
                        tracker.calibrate()
                        calibrated = True

        if tracker.available and calibrated and not game_over:
            target_y = HEIGHT / 2 + tracker.delta * SENSITIVITY
            bird.set_target(target_y)
        elif not game_over:
            if keys_pressed[pygame.K_UP] or keys_pressed[pygame.K_w]:
                key_target_offset -= 6
            if keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]:
                key_target_offset += 6
            key_target_offset = max(
                -HEIGHT / 2 + 40, min(HEIGHT / 2 - 40, key_target_offset)
            )
            bird.set_target(HEIGHT / 2 + key_target_offset)

        if not game_over:
            bird.update()

            spawn_timer -= dt
            if spawn_timer <= 0:
                pipes.append(PipePair(WIDTH + 20))
                spawn_timer = spawn_interval_for_score(score)

            for p in pipes:
                p.update()
            pipes = [p for p in pipes if not p.offscreen()]

            for p in pipes:
                if bird.rect.colliderect(p.top_rect) or bird.rect.colliderect(
                    p.bottom_rect
                ):
                    if not game_over:
                        shake_timer = 15
                        game_over = True
                if not p.scored and p.x + PIPE_W < BIRD_X:
                    p.scored = True
                    score += 1
                    PIPE_SPEED = difficulty_speed(score)

        if game_over and not was_game_over and SPR.get("ok"):
            particles = [Particle(BIRD_X, bird.display_y) for _ in range(10)]

        if game_over and not score_saved:
            if len(sys.argv) > 1:
                try:
                    database.save_score(sys.argv[1], "Nose Flappy", score)
                except Exception as e:
                    print(f"Erro ao salvar score: {e}")
            score_saved = True

        was_game_over = game_over

        # --- Menu de fim de jogo (após um instante mostrando a batida) ---
        if game_over:
            now_ms = pygame.time.get_ticks()
            if death_at is None:
                death_at = now_ms
            elif now_ms - death_at > game_menu.DEATH_DELAY_MS:
                choice = menu.game_over_screen([f"PONTOS: {score}"])
                if choice != "again":
                    running = False
                    continue
                bird = Bird()
                pipes = [PipePair(WIDTH + 200)]
                score = 0
                game_over = False
                was_game_over = False
                score_saved = False
                particles = []
                PIPE_SPEED = PIPE_SPEED_BASE
                spawn_timer = spawn_interval_for_score(score) + PIPE_FIRST_DELAY_MS
                key_target_offset = 0.0
                shake_timer = 0
                death_at = None
                start_round()
                continue

        for particle in particles:
            particle.update(dt)
        particles = [p for p in particles if p.alive]

        if SPR.get("ok") and not game_over:
            bg_x += PIPE_SPEED * 0.4
            bg_x %= SPR["background_w"]

        # --- Desenho ---
        if SPR.get("ok"):
            draw_x = -bg_x
            x_bg = draw_x
            while x_bg < WIDTH:
                display_surface.blit(SPR["background"], (int(x_bg), 0))
                x_bg += SPR["background_w"]
        else:
            display_surface.fill(SKY)
        for p in pipes:
            p.draw(display_surface)
        bird.draw(display_surface)
        for particle in particles:
            particle.draw(display_surface)

        score_surf = big_font.render(str(score), True, WHITE)
        outline = big_font.render(str(score), True, BLACK)
        for ox, oy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            display_surface.blit(outline, (WIDTH // 2 - 10 + ox, 20 + oy))
        display_surface.blit(score_surf, (WIDTH // 2 - 10, 20))

        if tracker.available:
            status = (
                "Câmera: OK"
                if calibrated
                else "Aperte ESPAÇO olhando reto pra calibrar"
            )
        else:
            status = "Câmera indisponível — use as setas (cima/baixo)"
        status_surf = font.render(status, True, BLACK)
        display_surface.blit(status_surf, (15, 15))

        esc_surf = font.render("ESC: voltar ao menu", True, WHITE)
        display_surface.blit(esc_surf, (15, HEIGHT - 30))

        if tracker.available and tracker.frame_for_preview is not None:
            preview = cv2.resize(tracker.frame_for_preview, (160, 120))
            preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            preview_surf = pygame.image.frombuffer(preview.tobytes(), (160, 120), "RGB")
            display_surface.blit(preview_surf, (WIDTH - 170, HEIGHT - 130))

        # Efeito de tremer a tela (Screen Shake)
        shake_x, shake_y = 0, 0
        if shake_timer > 0:
            shake_x = random.randint(-12, 12)
            shake_y = random.randint(-12, 12)
            shake_timer -= 1

        # Escalamos a `display_surface` (resolução lógica WIDTHxHEIGHT)
        # para o tamanho atual da janela mantendo a proporção.
        scaled = pygame.transform.smoothscale(display_surface, (dest_w, dest_h))

        draw_offset_x = offset_x + shake_x
        draw_offset_y = offset_y + shake_y

        screen.fill(BLACK)
        screen.blit(scaled, (draw_offset_x, draw_offset_y))
        pygame.display.flip()

    tracker.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
