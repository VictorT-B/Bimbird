"""
Nosebird
========
Corredor infinito: o personagem pula quando você levanta a cabeça
(MediaPipe FaceMesh). Sem câmera, use ESPAÇO ou a seta para cima.

Menus de início e de fim de jogo: game_menu.py (compartilhado pelos jogos).
"""

import os
import sys

import cv2
import pygame
from numpy import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import database
except ImportError:
    pass

try:
    from entities import Obstacle, Player, load_image
    from settings import (
        COLOR_BG,
        COLOR_GOLD,
        COLOR_GREEN,
        COLOR_RED,
        COLOR_TEXT_MAIN,
        COLOR_TEXT_SEC,
        FPS,
        GROUND_Y,
        HEIGHT,
        WIDTH,
    )
    from tracker import NoseTracker
    import game_menu

except ImportError as e:
    print(f"Erro ao carregar os módulos. Detalhe: {e}")
    sys.exit(1)

# --- CONSTANTES ---
BASE_SPEED = 4.2
MAX_SPEED = 9.0
SPEED_INCREMENT_PER_SECOND = 0.08
SPAWN_MIN = 1800
SPAWN_MAX = 3000
SPAWN_MIN_LIMIT = 1500
SPAWN_MAX_LIMIT = 2300


def random_spawn_delay(spawn_min, spawn_max):
    return int(random.randint(spawn_min, spawn_max + 1))


def speed_for_elapsed(elapsed_ms):
    elapsed_seconds = max(0, elapsed_ms // 1000)
    return min(
        MAX_SPEED, BASE_SPEED + elapsed_seconds * SPEED_INCREMENT_PER_SECOND
    )


def main():
    pygame.init()
    pygame.display.set_caption("NoseBird Evolution")
    # SCALED permite Fullscreen perfeito mantendo a resolução base!
    screen = pygame.display.set_mode(
        (WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED
    )
    clock = pygame.time.Clock()

    # Usando a fonte padrão do Pygame (None), que é uma fonte bitmap bem arcade retro
    font_sm = pygame.font.Font(None, 20)
    font_lg = pygame.font.Font(None, 42)

    def render_text(font, text, color, shadow=True):
        txt_surf = font.render(text, True, color)
        if not shadow:
            return txt_surf
        w, h = txt_surf.get_size()
        surf = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
        shd = font.render(text, True, (10, 10, 10, 200))
        surf.blit(shd, (2, 2))
        surf.blit(txt_surf, (0, 0))
        return surf

    tracker = NoseTracker()
    control_mode = "camera" if tracker.available else "keyboard"
    if tracker.available:
        tracker.start()

    state = "PLAYING"  # "PLAYING" ou "GAMEOVER"; os menus ficam em game_menu
    selected_char = "bimbird"
    debug_hitboxes = False

    player = None
    obstacles = []
    score = 0.0
    high_score = 0
    speed = BASE_SPEED
    bg_scroll = 0.0
    play_started_at = pygame.time.get_ticks()
    next_spawn_at = pygame.time.get_ticks() + random_spawn_delay(
        SPAWN_MIN, SPAWN_MAX
    )
    score_saved = False
    spawn_min = SPAWN_MIN
    spawn_max = SPAWN_MAX

    try:
        bg_raw = load_image("background_dino.png")
        bw, bh = bg_raw.get_size()
        # Escala proporcional mantendo a proporção de aspecto (sem esticamento vertical)
        scale = HEIGHT / max(1, bh)
        bg_w = int(bw * scale)
        bg_image = pygame.transform.scale(bg_raw, (bg_w, HEIGHT))
    except Exception:
        bg_image = None
        bg_w = WIDTH

    def reset_game():
        nonlocal score, speed, play_started_at, next_spawn_at, player, bg_scroll, control_mode, score_saved, spawn_min, spawn_max
        player = Player(selected_char)
        obstacles.clear()
        score = 0.0
        speed = BASE_SPEED
        bg_scroll = 0.0
        score_saved = False
        spawn_min = SPAWN_MIN
        spawn_max = SPAWN_MAX
        play_started_at = pygame.time.get_ticks()
        next_spawn_at = play_started_at + random_spawn_delay(
            spawn_min, spawn_max
        )
        if tracker.available:
            control_mode = "camera"
            if not tracker.running:
                tracker.start()
            if not tracker.calibrated:
                tracker.calibrate()
            tracker.consume_jump()
        else:
            control_mode = "keyboard"
            if tracker.running:
                tracker.stop()

    # ---- Menus padronizados (início / fim de jogo) controlados pela câmera ----
    def camera_frame():
        frame = tracker.frame_for_preview
        return None if frame is None else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    menu = game_menu.GameMenu(
        screen,
        clock,
        nose=lambda: tracker.nose_norm if tracker.available else None,
        frame=camera_frame,
        accent=(155, 89, 182),
    )

    def leave_game():
        tracker.stop()
        pygame.quit()
        sys.exit(0)

    historia = [
        "Controle o personagem com a cabeça!",
        "Mova a cabeça para cima para pular",
        "e desviar dos obstáculos.",
        "Boa sorte!",
    ]
    start_options = [
        ("bimbird", "JOGAR COM BIMBIRD"),
        ("ave_terror", "JOGAR COM AVE TERROR"),
        ("menu", "VOLTAR AO MENU"),
    ]
    game_over_options = [
        ("again", "JOGAR DE NOVO"),
        ("char", "TROCAR PERSONAGEM"),
        ("menu", "VOLTAR AO MENU"),
    ]

    def start_round():
        """Contagem 'olhe para o centro', calibração e início da partida."""
        nonlocal state
        if menu.countdown(bg_image) == "quit":
            leave_game()
        reset_game()  # depois da contagem, para o tempo de jogo começar agora
        if tracker.available:
            tracker.calibrate()
            tracker.consume_jump()
        state = "PLAYING"

    def open_start_menu():
        nonlocal selected_char
        choice = menu.start_screen("NOSEBIRD", historia, bg_image, options=start_options)
        if choice not in ("bimbird", "ave_terror"):
            leave_game()
        selected_char = choice
        start_round()

    open_start_menu()
    death_at = None

    running = True
    while running:
        clock.tick(FPS)
        current_time = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Atalhos universais
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif event.key == pygame.K_h:
                    debug_hitboxes = not debug_hitboxes
                elif event.key == pygame.K_c and control_mode == "camera":
                    tracker.calibrate()

            if state == "PLAYING":
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_SPACE, pygame.K_UP):
                        player.jump()

        if state == "PLAYING" and tracker.running and tracker.consume_jump():
            player.jump()

        if state == "PLAYING":
            player.update()

            speed = speed_for_elapsed(current_time - play_started_at)

            if current_time >= next_spawn_at:
                # Garantir que o último obstáculo já andou uma distância segura para evitar sobreposição
                can_spawn = True
                if obstacles:
                    if obstacles[-1].x > WIDTH - 400:
                        can_spawn = False

                if can_spawn:
                    obstacles.append(Obstacle(speed))
                    spawn_min = max(SPAWN_MIN_LIMIT, int(spawn_min * 0.995))
                    spawn_max = max(SPAWN_MAX_LIMIT, int(spawn_max * 0.995))
                    next_spawn_at = current_time + random_spawn_delay(
                        spawn_min, spawn_max
                    )
                else:
                    next_spawn_at = current_time + 100

            for obs in obstacles:
                obs.update(speed)
                if (
                    not getattr(obs, "scored", False)
                    and obs.x + obs.w < player.rect.x
                ):
                    obs.scored = True
                    score += 1

                if obs.hitbox.colliderect(player.hitbox):
                    state = "GAMEOVER"
                    player.paused = True
                    if int(score) > high_score:
                        high_score = int(score)

                    if not score_saved:
                        if len(sys.argv) > 1:
                            try:
                                database.save_score(
                                    sys.argv[1], "Nosebird", int(score)
                                )
                            except Exception as e:
                                print(f"Erro ao salvar score: {e}")
                        score_saved = True

            obstacles = [obs for obs in obstacles if not obs.offscreen()]

        # --- Menu de fim de jogo (após um instante mostrando a batida) ---
        if state == "GAMEOVER":
            if death_at is None:
                death_at = current_time
            elif current_time - death_at > game_menu.DEATH_DELAY_MS:
                choice = menu.game_over_screen(
                    [f"PONTOS: {int(score)}", f"RECORDE: {high_score}"],
                    options=game_over_options,
                )
                death_at = None
                if choice == "again":
                    start_round()
                elif choice == "char":
                    open_start_menu()
                else:
                    running = False
                continue

        # Desenho Fundo
        screen.fill(COLOR_BG)
        if state == "PLAYING":
            bg_scroll -= speed
            if bg_scroll <= -bg_w:
                bg_scroll += bg_w

        if bg_image:
            rel_x = int(bg_scroll)
            while rel_x < WIDTH:
                screen.blit(bg_image, (rel_x, 0))
                rel_x += bg_w
        else:
            pygame.draw.rect(
                screen, (35, 37, 56), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y)
            )

        for obs in obstacles:
            obs.draw(screen, debug=debug_hitboxes)
        player.draw(screen, debug=debug_hitboxes)

        # Placar
        hud_box = pygame.Surface((140, 60), pygame.SRCALPHA)
        pygame.draw.rect(hud_box, (0, 0, 0, 120), hud_box.get_rect(), border_radius=10)
        screen.blit(hud_box, (WIDTH - 150, 15))
        score_t = render_text(font_lg, f"{int(score):05d}", COLOR_TEXT_MAIN, shadow=False)
        hi_t = render_text(font_sm, f"HI: {high_score:05d}", COLOR_TEXT_SEC, shadow=False)
        screen.blit(score_t, (WIDTH - 140, 20))
        screen.blit(hi_t, (WIDTH - 140, 52))

        # Prévia da webcam no canto inferior direito (modo câmera)
        if (
            control_mode == "camera"
            and tracker.running
            and tracker.frame_for_preview is not None
        ):
            f_rgb = cv2.cvtColor(tracker.frame_for_preview, cv2.COLOR_BGR2RGB)
            f_surf = pygame.image.frombuffer(
                f_rgb.flatten(), f_rgb.shape[1::-1], "RGB"
            )

            cam_rect = pygame.Rect(WIDTH - 150, HEIGHT - 115, 140, 105)

            scaled_cam = pygame.transform.scale(
                f_surf, (cam_rect.width, cam_rect.height)
            )
            screen.blit(scaled_cam, (cam_rect.x, cam_rect.y))

            b_color = COLOR_GOLD if tracker.signal == "JUMP" else COLOR_GREEN
            pygame.draw.rect(screen, b_color, cam_rect, 2, border_radius=4)

            # Etiqueta indicadora
            tag_t = render_text(
                font_sm,
                "PULO!" if tracker.signal == "JUMP" else "CAM",
                b_color,
                shadow=True,
            )
            screen.blit(tag_t, (cam_rect.x + 5, cam_rect.y + 4))

        if state == "PLAYING" and control_mode == "camera":
            if not tracker.available:
                cam_t = render_text(font_sm, "CÂMERA INDISPONÍVEL", COLOR_RED)
                screen.blit(cam_t, (10, 10))
            elif not tracker.calibrated:
                cam_t = render_text(
                    font_sm, "OLHE RETO E APERTE C PARA CALIBRAR", COLOR_GOLD
                )
                screen.blit(cam_t, (10, 10))

        pygame.display.flip()

    tracker.stop()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
