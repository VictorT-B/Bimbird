"""Arcade Hub: login por teclado digital + menu de jogos, tudo controlável pela câmera.

- Login: o nariz move um cursor e uma piscada longa (ou parar sobre a tecla)
  digita a letra.
- Hub: cabeça para cima/baixo navega pela coluna de opções; virar para o lado
  (segurando) confirma.
Mouse e teclado continuam funcionando como alternativa.
"""

import math
import os
import subprocess
import sys
import time

import pygame

import database
import head_menu

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "imagem_geral.jpeg")
FONT_PATH = os.path.join(BASE_DIR, "PressStart2P.ttf")
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
MAX_W, MAX_H = 1200, 800

HIGHLIGHT_COLOR = (255, 230, 90)

# Hub
MENU_X = 20
MENU_W = 340
MENU_GAP = 10
HUD_W, HUD_PREVIEW_H = 220, 150

# Teclado digital do login
KB_ROWS = ["1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
# (rótulo, ação, largura em colunas, cor)
KB_ACTIONS = [
    ("APAGAR", "backspace", 2, (150, 70, 70)),
    ("LIMPAR", "clear", 2, (110, 80, 80)),
    ("ENTRAR", "login", 3, (200, 120, 25)),
    ("CRIAR", "create", 3, (50, 150, 75)),
]
# Parar o cursor sobre uma tecla por este tempo também a seleciona
# (alternativa para quem usa óculos ou tem dificuldade com a piscada). 0 desativa.
DWELL_SELECT_S = 2.0
MAX_NICK = 15

GAMES = [
    {
        "id": "fruit-ninja",
        "name": "Fruit Ninja",
        "desc": "Multiplicador x1.0",
        "color": (233, 69, 96),
        "dir": "Fruit Ninja",
        "file": "nose_fruit_ninja.py",
    },
    {
        "id": "nose-flappy",
        "name": "Nose Flappy",
        "desc": "Multiplicador x1.5",
        "color": (76, 209, 55),
        "dir": "nose_flappy",
        "file": "nose_flappy.py",
    },
    {
        "id": "catch-fruit",
        "name": "Catch Fruit Game",
        "desc": "Multiplicador x2.0",
        "color": (249, 168, 38),
        "dir": "catch_fruit_game",
        "file": "game.py",
    },
    {
        "id": "nosebird",
        "name": "Nosebird",
        "desc": "Multiplicador x3.0",
        "color": (155, 89, 182),
        "dir": "nosebird",
        "file": "main.py",
    },
]

# ---------------------------------------------------------------------------
# Janela e recursos
# ---------------------------------------------------------------------------
pygame.init()

try:
    bg_image_original = pygame.image.load(IMAGE_PATH)
except Exception:
    bg_image_original = pygame.Surface((MAX_W, MAX_H))
    bg_image_original.fill((30, 30, 40))

# A janela tem o tamanho da imagem de fundo (limitada a MAX_W x MAX_H)
img_w, img_h = bg_image_original.get_size()
scale = min(1.0, MAX_W / img_w, MAX_H / img_h)
WIDTH = int(img_w * scale)
HEIGHT = int(img_h * scale)

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
pygame.display.set_caption("Arcade Hub - Visão Computacional")
clock = pygame.time.Clock()

bg_image = pygame.transform.smoothscale(bg_image_original, (WIDTH, HEIGHT))

try:
    font_med = pygame.font.Font(FONT_PATH, 20)
    font_small = pygame.font.Font(FONT_PATH, 14)
    font_tiny = pygame.font.Font(FONT_PATH, 9)
except Exception:
    font_med = pygame.font.SysFont("arial", 28, bold=True)
    font_small = pygame.font.SysFont("arial", 18)
    font_tiny = pygame.font.SysFont("arial", 13)

try:
    logo_image = pygame.image.load(LOGO_PATH).convert_alpha()
    lw, lh = logo_image.get_size()
    if lh > 120:
        logo_image = pygame.transform.smoothscale(logo_image, (int(lw * 120 / lh), 120))
except Exception:
    logo_image = None

_head_controller = None


def get_head_controller():
    """Controlador da câmera compartilhado entre login e hub."""
    global _head_controller
    if _head_controller is None:
        _head_controller = head_menu.HeadMenuController()
    return _head_controller


# ---------------------------------------------------------------------------
# Utilitários de desenho
# ---------------------------------------------------------------------------
def draw_rounded_rect(surface, color, rect, radius=20, alpha=255):
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(
        shape_surf, (*color[:3], alpha), shape_surf.get_rect(), border_radius=radius
    )
    surface.blit(shape_surf, rect.topleft)


def render_fit(text, font, color, max_width):
    """Renderiza o texto, encolhendo se passar de max_width."""
    surf = font.render(text, True, color)
    if surf.get_width() > max_width:
        h = max(1, int(surf.get_height() * max_width / surf.get_width()))
        surf = pygame.transform.smoothscale(surf, (max_width, h))
    return surf


def draw_select_progress(rect, progress):
    """Barra de confirmação na base de um botão."""
    if progress <= 0:
        return
    bar = pygame.Rect(rect.x + 18, rect.bottom - 10, rect.width - 30, 5)
    pygame.draw.rect(screen, (20, 20, 30), bar, border_radius=3)
    fill = bar.copy()
    fill.width = max(1, int(bar.width * progress))
    pygame.draw.rect(screen, HIGHLIGHT_COLOR, fill, border_radius=3)


def draw_camera_frame(state, rect):
    frame = state["frame"] if state else None
    if frame is not None:
        surf = pygame.image.frombuffer(
            frame.tobytes(), (frame.shape[1], frame.shape[0]), "RGB"
        )
        screen.blit(pygame.transform.smoothscale(surf, rect.size), rect.topleft)
    else:
        pygame.draw.rect(screen, (10, 10, 15), rect)


# ---------------------------------------------------------------------------
# Login (teclado digital)
# ---------------------------------------------------------------------------
def submit_user(mode, input_text):
    """Entra ('login') ou cria ('create') o usuário. Retorna (nickname, mensagem)."""
    nickname = input_text.strip()
    if not nickname:
        return None, "Digite um nome de usuário."

    if mode == "create":
        user = database.create_user(nickname)
        if user is None:
            return None, "Esse usuário já existe. Use o botão ENTRAR."
        return user["nickname"], ""

    user = database.get_user(nickname)
    if user is None:
        return None, "Usuário não encontrado. Use o botão CRIAR."
    return user["nickname"], ""


def build_keyboard(top, bottom):
    cols = 10
    gap = 8
    kb_w = min(WIDTH - 40, 1000)
    unit = kb_w / cols
    left = (WIDTH - kb_w) / 2
    rows_n = len(KB_ROWS) + 1
    row_h = min(90, (bottom - top - gap * (rows_n - 1)) / rows_n)

    keys = []
    for r, row in enumerate(KB_ROWS):
        offset = (cols - len(row)) * unit / 2
        y = top + r * (row_h + gap)
        for c, ch in enumerate(row):
            rect = pygame.Rect(int(left + offset + c * unit + gap / 2), int(y),
                               int(unit - gap), int(row_h))
            keys.append({"label": ch, "action": "char", "rect": rect,
                         "color": (45, 45, 65)})

    y = top + len(KB_ROWS) * (row_h + gap)
    x = left
    for label, action, span, color in KB_ACTIONS:
        rect = pygame.Rect(int(x + gap / 2), int(y), int(unit * span - gap), int(row_h))
        keys.append({"label": label, "action": action, "rect": rect, "color": color})
        x += unit * span

    # Botão X no canto: fecha o arcade sem precisar fazer login
    keys.append({"label": "X", "action": "quit", "rect": pygame.Rect(16, 16, 64, 64),
                 "color": (170, 50, 50)})
    return keys


def draw_nose_cursor(pos, state):
    x, y = pos
    closed = state["eyes_closed"]
    color = HIGHLIGHT_COLOR if closed else (255, 255, 255)
    pygame.draw.circle(screen, (0, 0, 0), (x, y), 15, 3)
    pygame.draw.circle(screen, color, (x, y), 13, 3)
    pygame.draw.circle(screen, color, (x, y), 4)
    progress = state["blink_progress"]
    if closed and progress > 0:
        ring = pygame.Rect(0, 0, 40, 40)
        ring.center = (x, y)
        pygame.draw.arc(screen, HIGHLIGHT_COLOR, ring, math.pi / 2,
                        math.pi / 2 + 2 * math.pi * progress, 5)


def login_screen():
    """Retorna o nickname logado, ou None para fechar o app."""
    text = ""
    message = ""

    head = get_head_controller()
    head.start()
    head.clear_events()

    title_y = 34
    field_rect = pygame.Rect(WIDTH // 2 - 280, 100, 560, 58)
    preview_rect = pygame.Rect(WIDTH - 190, 16, 172, 129)
    keys = build_keyboard(field_rect.bottom + 46, HEIGHT - 16)

    want_quit = False
    dwell_key = None
    dwell_since = 0.0
    dwell_done = False
    flash_key = None
    flash_until = 0.0

    def press(key):
        """Aplica a tecla. Retorna o nickname quando o login/cadastro dá certo."""
        nonlocal text, message, flash_key, flash_until, dwell_since, dwell_done, want_quit
        now = time.monotonic()
        flash_key, flash_until = key, now + 0.2
        dwell_since, dwell_done = now, True  # não repete pela permanência

        action = key["action"]
        if action == "quit":
            want_quit = True
        elif action == "char":
            if len(text) < MAX_NICK:
                text += key["label"]
            message = ""
        elif action == "backspace":
            text = text[:-1]
            message = ""
        elif action == "clear":
            text = ""
            message = ""
        else:
            nickname, message = submit_user(action, text)
            return nickname
        return None

    def key_at(pos):
        for key in keys:
            if key["rect"].collidepoint(pos):
                return key
        return None

    while True:
        if want_quit:
            return None
        now = time.monotonic()
        nickname = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key == pygame.K_RETURN:
                    nickname, message = submit_user("login", text)
                elif event.key == pygame.K_BACKSPACE:
                    text = text[:-1]
                    message = ""
                elif event.key == pygame.K_F5:
                    head.recalibrate()
                elif len(text) < MAX_NICK and event.unicode.isprintable() and event.unicode:
                    text += event.unicode
                    message = ""
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                key = key_at(event.pos)
                if key is not None:
                    nickname = press(key)
            if nickname is not None:
                return nickname

        state = head.snapshot() if head.available else None
        head.poll_events()  # gestos do hub não se aplicam aqui

        cursor_px = None
        if state and state["cursor"] is not None:
            cx, cy = state["cursor"]
            cursor_px = (int(cx * (WIDTH - 1)), int(cy * (HEIGHT - 1)))

        # Piscada longa -> pressiona a tecla sob o cursor
        for bx, by in (head.poll_blinks() if head.available else []):
            key = key_at((int(bx * (WIDTH - 1)), int(by * (HEIGHT - 1))))
            if key is not None:
                nickname = press(key)
                if nickname is not None:
                    return nickname

        # Permanência sobre a tecla
        hovered = key_at(cursor_px) if cursor_px else None
        if state and state["eyes_closed"]:
            hovered = dwell_key  # cursor congelado durante a piscada
        if hovered is not dwell_key:
            dwell_key, dwell_since, dwell_done = hovered, now, False
        dwell_progress = 0.0
        if hovered is not None and DWELL_SELECT_S > 0 and not dwell_done:
            dwell_progress = min(1.0, (now - dwell_since) / DWELL_SELECT_S)
            if dwell_progress >= 1.0:
                nickname = press(hovered)
                if nickname is not None:
                    return nickname
                dwell_progress = 0.0

        # ---- desenho ----
        screen.blit(bg_image, (0, 0))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        screen.blit(overlay, (0, 0))

        title = font_med.render("BEM-VINDO AO ARCADE", True, (255, 255, 255))
        screen.blit(title, title.get_rect(center=(WIDTH // 2, title_y)))
        if head.available:
            sub_text = "Aponte com o nariz e pisque devagar para escolher a letra"
        else:
            sub_text = "Câmera indisponível: use o mouse ou o teclado"
        sub = render_fit(sub_text, font_tiny, (200, 200, 210), field_rect.width + 120)
        screen.blit(sub, sub.get_rect(center=(WIDTH // 2, title_y + 30)))

        # Campo do nome
        pygame.draw.rect(screen, (20, 20, 30), field_rect, border_radius=10)
        pygame.draw.rect(screen, (249, 168, 38), field_rect, 3, border_radius=10)
        if text:
            value = font_med.render(text, True, (255, 255, 255))
        else:
            value = font_med.render("SEU NOME", True, (110, 110, 130))
        value_rect = value.get_rect(midleft=(field_rect.x + 18, field_rect.centery))
        screen.blit(value, value_rect)
        if text and int(now * 2) % 2 == 0:
            pygame.draw.rect(screen, (249, 168, 38),
                             (value_rect.right + 4, field_rect.centery - 12, 4, 24))

        if message:
            msg = render_fit(message, font_tiny, (255, 110, 100), field_rect.width + 120)
            screen.blit(msg, msg.get_rect(center=(WIDTH // 2, field_rect.bottom + 20)))

        # Teclas
        for key in keys:
            rect = key["rect"]
            is_hover = key is hovered
            is_flash = key is flash_key and now < flash_until
            fill = key["color"]
            if is_hover:
                fill = tuple(min(255, c + 45) for c in fill)
            if is_flash:
                fill = HIGHLIGHT_COLOR
            pygame.draw.rect(screen, fill, rect, border_radius=10)
            pygame.draw.rect(screen, HIGHLIGHT_COLOR if is_hover else (90, 90, 120),
                             rect, 3 if is_hover else 2, border_radius=10)
            font = font_med if key["action"] in ("char", "quit") else font_small
            label = render_fit(key["label"], font,
                               (20, 20, 30) if is_flash else (255, 255, 255),
                               rect.width - 10)
            screen.blit(label, label.get_rect(center=rect.center))
            if is_hover and dwell_progress > 0:
                draw_select_progress(rect, dwell_progress)

        # Prévia da câmera
        if head.available:
            draw_camera_frame(state, preview_rect)
            pygame.draw.rect(screen, (100, 150, 255), preview_rect, 2)
            status = render_fit(state["status"], font_tiny, (220, 220, 230),
                                preview_rect.width)
            screen.blit(status, (preview_rect.x, preview_rect.bottom + 5))

        if cursor_px:
            draw_nose_cursor(cursor_px, state)

        pygame.display.flip()
        clock.tick(60)


# ---------------------------------------------------------------------------
# Hub (menu de jogos)
# ---------------------------------------------------------------------------
def get_panel_rect(expanded):
    panel_w = 400 if expanded else 240
    panel_h = HEIGHT - 40 if expanded else 140
    return pygame.Rect(WIDTH - panel_w - 20, 20, panel_w, panel_h)


def build_menu_items():
    """Coluna de opções à esquerda (ordem de navegação cima/baixo)."""
    items = [
        {"kind": "game", "game": game, "label": game["name"],
         "sub": game["desc"], "color": game["color"]}
        for game in GAMES
    ]
    items.append({"kind": "ranking", "label": "Ranking",
                  "sub": "Abrir / fechar ranking", "color": (100, 150, 255)})
    items.append({"kind": "logout", "label": "Trocar login",
                  "sub": "Entrar com outro usuário", "color": (230, 150, 40)})
    items.append({"kind": "quit", "label": "Sair",
                  "sub": "Fechar o arcade", "color": (220, 70, 70)})

    top = 20 + (logo_image.get_height() + 20 if logo_image else 0)
    available = HEIGHT - top - 20
    item_h = min(76, (available - MENU_GAP * (len(items) - 1)) // len(items))
    for i, item in enumerate(items):
        item["rect"] = pygame.Rect(
            MENU_X, top + i * (item_h + MENU_GAP), MENU_W, item_h
        )
        item["anim"] = 0.0
    return items


def draw_menu_item(item, is_selected, progress):
    rect = item["rect"]
    color = item["color"]

    item["anim"] += ((1.0 if is_selected else 0.0) - item["anim"]) * 0.2
    r = rect.move(int(item["anim"] * 14), 0)

    draw_rounded_rect(screen, (20, 20, 30), r, radius=12,
                      alpha=int(200 + 40 * item["anim"]))
    if item["anim"] > 0.01:
        draw_rounded_rect(screen, color, r, radius=12, alpha=int(90 * item["anim"]))

    # Faixa colorida à esquerda
    stripe = pygame.Rect(r.x, r.y, 10, r.height)
    pygame.draw.rect(screen, color, stripe,
                     border_top_left_radius=12, border_bottom_left_radius=12)

    pygame.draw.rect(
        screen,
        HIGHLIGHT_COLOR if is_selected else (*color, 255),
        r, 3 if is_selected else 2, border_radius=12,
    )

    text_x = r.x + 24
    max_text_w = r.width - (64 if is_selected else 36)
    title = render_fit(item["label"].upper(), font_med, (255, 255, 255), max_text_w)
    sub = render_fit(item["sub"], font_tiny,
                     HIGHLIGHT_COLOR if is_selected else (190, 190, 205), max_text_w)
    block_h = title.get_height() + 8 + sub.get_height()
    y = r.centery - block_h // 2 - (3 if progress > 0 and is_selected else 0)
    screen.blit(title, (text_x, y))
    screen.blit(sub, (text_x, y + title.get_height() + 8))

    if is_selected:
        arrow = font_med.render(">", True, HIGHLIGHT_COLOR)
        screen.blit(arrow, arrow.get_rect(midright=(r.right - 12, r.centery)))
        draw_select_progress(r, progress)


def draw_hub_overlay(nickname, expanded):
    """Painel de perfil (e ranking, quando expandido) no canto superior direito."""
    user_info = database.get_user(nickname)
    if user_info is None:
        return

    panel_rect = get_panel_rect(expanded)
    draw_rounded_rect(screen, (20, 20, 30), panel_rect, radius=15, alpha=230)
    pygame.draw.rect(screen, (100, 150, 255), panel_rect, width=2, border_radius=15)

    u_title = font_med.render("PERFIL", True, (100, 200, 255))
    screen.blit(u_title, (panel_rect.x + 20, panel_rect.y + 20))
    u_name = font_small.render(
        f"Nick: {user_info['nickname'][:12]}", True, (255, 255, 255)
    )
    screen.blit(u_name, (panel_rect.x + 20, panel_rect.y + 60))
    u_pts = font_small.render(
        f"Pontos: {user_info['total_points']:.1f}", True, (255, 215, 0)
    )
    screen.blit(u_pts, (panel_rect.x + 20, panel_rect.y + 90))

    if not expanded:
        hint = render_fit("Clique p/ Ranking", font_small, (150, 150, 150),
                          panel_rect.width - 24)
        screen.blit(hint, hint.get_rect(center=(panel_rect.centerx, panel_rect.bottom - 20)))
        return

    pygame.draw.line(
        screen, (100, 150, 255),
        (panel_rect.x + 10, panel_rect.y + 130),
        (panel_rect.right - 10, panel_rect.y + 130), 2,
    )
    l_title = font_med.render("RANKING TOP 5", True, (255, 100, 100))
    screen.blit(l_title, (panel_rect.x + 20, panel_rect.y + 150))

    y_off = panel_rect.y + 190
    for i, row in enumerate(database.get_leaderboard(5)):
        color = (255, 215, 0) if i == 0 else (200, 200, 200)
        rank_txt = font_small.render(f"{i + 1}. {row[0][:15]}", True, color)
        pts_txt = font_small.render(f"{row[1]:.1f}", True, color)
        screen.blit(rank_txt, (panel_rect.x + 20, y_off))
        if nickname.lower() == "admin" and row[0].lower() != "admin":
            # Admin pode apagar usuários clicando no X
            del_txt = font_small.render("X", True, (255, 80, 80))
            screen.blit(del_txt, (panel_rect.right - 35, y_off))
            screen.blit(pts_txt, (panel_rect.right - 50 - pts_txt.get_width(), y_off))
        else:
            screen.blit(pts_txt, (panel_rect.right - 20 - pts_txt.get_width(), y_off))
        y_off += 35

    hint = font_small.render("Clique p/ Fechar", True, (150, 150, 150))
    screen.blit(hint, hint.get_rect(center=(panel_rect.centerx, y_off + 20)))


def draw_head_hud(state):
    """Prévia da câmera + indicador de direção da cabeça (canto inferior direito)."""
    hud_rect = pygame.Rect(WIDTH - HUD_W - 20, HEIGHT - 20 - HUD_PREVIEW_H - 64,
                           HUD_W, HUD_PREVIEW_H + 64)
    draw_rounded_rect(screen, (20, 20, 30), hud_rect, radius=10, alpha=225)
    pygame.draw.rect(screen, (100, 150, 255), hud_rect, 2, border_radius=10)

    preview_rect = pygame.Rect(hud_rect.x + 10, hud_rect.y + 10,
                               HUD_W - 20, HUD_PREVIEW_H - 10)
    draw_camera_frame(state, preview_rect)

    # Indicador: quadrado interno = thresholds, ponto = posição atual da cabeça
    if state and state["calibrated"]:
        half = 22
        box = pygame.Rect(0, 0, half * 2, half * 2)
        box.bottomright = (preview_rect.right - 6, preview_rect.bottom - 6)
        pygame.draw.rect(screen, (0, 0, 0), box)
        pygame.draw.rect(screen, (200, 200, 200), box.inflate(-half, -half), 1)
        nx = max(-1.6, min(1.6, state["yaw"] / head_menu.YAW_THRESHOLD))
        ny = max(-1.6, min(1.6, state["pitch"] / head_menu.PITCH_THRESHOLD))
        dot = (int(box.centerx + nx * half / 2), int(box.centery + ny * half / 2))
        pygame.draw.circle(screen, HIGHLIGHT_COLOR, dot, 4)

    status = state["status"] if state else "Câmera indisponível"
    text_y = preview_rect.bottom + 6
    for line in [status, "CIMA/BAIXO: navegar", "LADO: selecionar | C: calibrar"]:
        surf = render_fit(line, font_tiny, (220, 220, 230), preview_rect.width)
        screen.blit(surf, (preview_rect.x, text_y))
        text_y += surf.get_height() + 5


def launch_game(game_data, nickname):
    """Roda o jogo em outro processo e espera ele terminar."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    load_surf = font_med.render(f"Iniciando {game_data['name']}...", True, (255, 255, 255))
    screen.blit(load_surf, load_surf.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
    pygame.display.flip()

    try:
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--game", game_data["id"], nickname]
            working_dir = os.path.dirname(sys.executable)
        else:
            command = [sys.executable, game_data["file"], nickname]
            working_dir = os.path.join(BASE_DIR, game_data["dir"])
        subprocess.run(command, cwd=working_dir, check=False)
    except Exception as e:
        print(f"Erro ao iniciar o jogo: {e}")

    pygame.event.clear()


def run_hub(nickname):
    """Retorna 'logout' (voltar ao login) ou 'quit' (fechar o app)."""
    hub_expanded = False
    menu_items = build_menu_items()
    selected = 0

    head = get_head_controller()
    head.start()
    head.clear_events()  # descarta gestos feitos na tela anterior

    def activate(item):
        nonlocal hub_expanded
        if item["kind"] == "game":
            # Libera a câmera para o jogo e retoma o controle ao voltar.
            head.stop()
            launch_game(item["game"], nickname)
            head.start()
        elif item["kind"] == "ranking":
            hub_expanded = not hub_expanded
        elif item["kind"] in ("logout", "quit"):
            return item["kind"]
        return None

    def item_at(pos):
        for i, item in enumerate(menu_items):
            if item["rect"].collidepoint(pos):
                return i
        return None

    def handle_panel_click(pos):
        nonlocal hub_expanded
        panel_rect = get_panel_rect(hub_expanded)
        if not panel_rect.collidepoint(pos):
            return
        if hub_expanded and nickname.lower() == "admin":
            y_off = panel_rect.y + 190
            for row in database.get_leaderboard(5):
                if row[0].lower() != "admin":
                    del_rect = pygame.Rect(panel_rect.right - 40, y_off - 5, 30, 30)
                    if del_rect.collidepoint(pos):
                        database.delete_user(row[0])
                        return
                y_off += 35
        hub_expanded = not hub_expanded

    try:
        while True:
            to_activate = None

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "quit"
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected = (selected - 1) % len(menu_items)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(menu_items)
                    elif event.key in (pygame.K_LEFT, pygame.K_RIGHT,
                                       pygame.K_RETURN, pygame.K_SPACE):
                        to_activate = menu_items[selected]
                    elif event.key == pygame.K_c:
                        head.recalibrate()
                if event.type == pygame.MOUSEMOTION:
                    hovered = item_at(event.pos)
                    if hovered is not None:
                        selected = hovered
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    clicked = item_at(event.pos)
                    if clicked is not None:
                        selected = clicked
                        to_activate = menu_items[clicked]
                    else:
                        handle_panel_click(event.pos)

            # Eventos vindos dos movimentos da cabeça
            for head_event in head.poll_events():
                if head_event == "UP":
                    selected = (selected - 1) % len(menu_items)
                elif head_event == "DOWN":
                    selected = (selected + 1) % len(menu_items)
                elif head_event == "SELECT" and to_activate is None:
                    to_activate = menu_items[selected]

            if to_activate is not None:
                result = activate(to_activate)
                if result is not None:
                    return result
                continue

            head_state = head.snapshot() if head.available else None
            select_progress = head_state["select_progress"] if head_state else 0.0

            screen.blit(bg_image, (0, 0))
            # Faixa escura atrás da coluna de opções
            strip = pygame.Surface((MENU_X + MENU_W + 40, HEIGHT), pygame.SRCALPHA)
            strip.fill((0, 0, 0, 110))
            screen.blit(strip, (0, 0))
            if logo_image:
                screen.blit(logo_image, (MENU_X, 20))

            for i, item in enumerate(menu_items):
                draw_menu_item(item, i == selected, select_progress if i == selected else 0.0)

            draw_hub_overlay(nickname, hub_expanded)
            if head.available:
                draw_head_hud(head_state)

            pygame.display.flip()
            clock.tick(60)
    finally:
        # A câmera continua ligada para a tela de login; main() a desliga no fim.
        head.clear_events()


# ---------------------------------------------------------------------------
def main():
    try:
        while True:
            nickname = login_screen()
            if nickname is None or run_hub(nickname) == "quit":
                break
    finally:
        get_head_controller().stop()

    pygame.quit()


if __name__ == "__main__":
    main()
