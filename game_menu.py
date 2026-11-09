"""Menus padronizados de início e de fim de jogo, controlados pela câmera.

Cada jogo cria um GameMenu passando:
- nose():  retorna (x, y) normalizados (0..1) do nariz na imagem, ou None sem rosto
- frame(): retorna o quadro RGB (numpy) da câmera para a prévia, ou None

Controles (iguais ao menu principal do arcade):
- Nariz para CIMA / BAIXO  -> muda a opção
- Nariz para o LADO, segurando SELECT_HOLD_S -> confirma
- Teclado: setas/W/S navegam, Enter/Espaço/←/→ confirmam, ESC volta ao menu
- Mouse: passar por cima seleciona, clique confirma

Valores retornados: o id da opção escolhida, "menu" (ESC) ou "quit" (fechar janela).
"""

import os
import sys
import time
from statistics import median

import pygame

# ---- Ajustes (posição do nariz normalizada pela imagem da câmera) ------------
NAV_THRESHOLD = 0.045  # deslocamento vertical para mudar de opção
SELECT_THRESHOLD = 0.07  # deslocamento horizontal para confirmar
RESET_FRACTION = 0.5  # precisa voltar abaixo desta fração para disparar de novo
NAV_HOLD_S = 0.10
NAV_REPEAT_S = 0.75
SELECT_HOLD_S = 1.0
SMOOTHING = 0.4
CALIBRATION_SAMPLES = 10
FACE_LOST_RESET_S = 2.0
BASELINE_DRIFT = 0.01  # o neutro acompanha devagar a postura da pessoa
# Tempo mostrando a jogada final antes de abrir o menu de fim de jogo.
DEATH_DELAY_MS = 900

HIGHLIGHT = (255, 230, 90)
CARD_BG = (20, 20, 30)
TEXT = (240, 240, 245)
TEXT_SEC = (190, 190, 205)


def _font_path():
    for base in (getattr(sys, "_MEIPASS", None), os.path.dirname(os.path.abspath(__file__))):
        if base:
            path = os.path.join(base, "PressStart2P.ttf")
            if os.path.isfile(path):
                return path
    return None


class NoseGestures:
    """Transforma a posição do nariz em eventos UP / DOWN / SELECT."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.base = None
        self.samples = []
        self.smooth = None
        self.last_face = 0.0
        self.nav_dir = None
        self.nav_since = 0.0
        self.nav_last = 0.0
        self.nav_armed = True
        self.sel_since = None
        self.sel_armed = True
        self.select_progress = 0.0
        self.dx = self.dy = 0.0

    @property
    def calibrated(self):
        return self.base is not None

    def update(self, pos, now):
        events = []
        if pos is None:
            self.select_progress = 0.0
            self.sel_since = None
            self.nav_dir = None
            if self.base is not None and now - self.last_face > FACE_LOST_RESET_S:
                self.reset()
            return events

        self.last_face = now
        if self.smooth is None:
            self.smooth = pos
        else:
            self.smooth = tuple(s + (p - s) * SMOOTHING for s, p in zip(self.smooth, pos))

        if self.base is None:
            self.samples.append(pos)
            if len(self.samples) >= CALIBRATION_SAMPLES:
                self.base = (median(p[0] for p in self.samples),
                             median(p[1] for p in self.samples))
                self.smooth = self.base
            return events

        dx = self.smooth[0] - self.base[0]
        dy = self.smooth[1] - self.base[1]
        self.dx, self.dy = dx, dy

        neutral_x = abs(dx) < SELECT_THRESHOLD * RESET_FRACTION
        neutral_y = abs(dy) < NAV_THRESHOLD * RESET_FRACTION
        if neutral_x and neutral_y:
            self.base = tuple(b + (s - b) * BASELINE_DRIFT for b, s in zip(self.base, self.smooth))

        # Confirmação (lado) tem prioridade
        if neutral_x:
            self.sel_armed = True
        if self.sel_armed and abs(dx) >= SELECT_THRESHOLD:
            if self.sel_since is None:
                self.sel_since = now
            self.select_progress = min(1.0, (now - self.sel_since) / SELECT_HOLD_S)
            if self.select_progress >= 1.0:
                events.append("SELECT")
                self.sel_armed = False
                self.sel_since = None
                self.select_progress = 0.0
            self.nav_dir = None
            return events
        self.sel_since = None
        self.select_progress = 0.0
        if not neutral_x:
            self.nav_dir = None
            return events

        # Navegação (cima/baixo)
        if neutral_y:
            self.nav_armed = True
            self.nav_dir = None
            return events
        if abs(dy) < NAV_THRESHOLD:
            self.nav_dir = None
            return events
        direction = "UP" if dy < 0 else "DOWN"
        if self.nav_dir != direction:
            self.nav_dir = direction
            self.nav_since = now
            return events
        if self.nav_armed and now - self.nav_since >= NAV_HOLD_S:
            events.append(direction)
            self.nav_armed = False
            self.nav_last = now
        elif not self.nav_armed and now - self.nav_last >= NAV_REPEAT_S:
            events.append(direction)
            self.nav_last = now
        return events


class GameMenu:
    def __init__(self, screen, clock, nose=None, frame=None, accent=(76, 209, 55)):
        self.screen = screen
        self.clock = clock
        self.nose = nose or (lambda: None)
        self.frame = frame or (lambda: None)
        self.accent = accent

        w, h = screen.get_size()
        self.s = min(w / 900, h / 600)
        path = _font_path()

        def pixel_font(size):
            size = max(7, int(size * self.s))
            if path:
                return pygame.font.Font(path, size)
            return pygame.font.SysFont("arial", int(size * 1.4), bold=True)

        self.font_title = pixel_font(26)
        self.font_btn = pixel_font(15)
        self.font_big = pixel_font(72)
        self.font_tiny = pixel_font(9)
        name = "trebuchetms" if "trebuchetms" in pygame.font.get_fonts() else "arial"
        self.font_text = pygame.font.SysFont(name, max(12, int(19 * self.s)))
        self.font_text_bold = pygame.font.SysFont(name, max(13, int(22 * self.s)), bold=True)

    # ---- API pública ------------------------------------------------------------
    def start_screen(self, title, lines, background=None, options=None):
        options = options or [("play", "JOGAR"), ("menu", "VOLTAR AO MENU")]
        return self._run(title, lines, options, background)

    def game_over_screen(self, lines, background=None, options=None, title="FIM DE JOGO"):
        options = options or [("again", "JOGAR DE NOVO"), ("menu", "VOLTAR AO MENU")]
        if background is None:
            background = self.screen.copy()
        return self._run(title, lines, options, background, emphasize_lines=True)

    def countdown(self, background=None, seconds=3):
        """'Olhe para o centro' antes da partida. Retorna 'ok' ou 'quit'.
        Ao terminar, o jogo deve calibrar seu rastreador."""
        if background is None:
            background = self.screen.copy()
        background = self._fit(background)
        w, h = self.screen.get_size()
        end = time.monotonic() + seconds
        while True:
            now = time.monotonic()
            remaining = end - now
            if remaining <= 0:
                return "ok"
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN and event.key in (
                        pygame.K_SPACE, pygame.K_RETURN):
                    return "ok"

            self.screen.blit(background, (0, 0))
            self._dim(170)
            number = str(int(remaining) + 1)
            num = self.font_big.render(number, True, HIGHLIGHT)
            self.screen.blit(num, num.get_rect(center=(w // 2, h // 2 - int(20 * self.s))))
            msg = self.font_btn.render("OLHE PARA O CENTRO DA TELA", True, TEXT)
            self.screen.blit(msg, msg.get_rect(center=(w // 2, h // 2 + int(60 * self.s))))
            sub = self.font_tiny.render("calibrando a câmera...", True, TEXT_SEC)
            self.screen.blit(sub, sub.get_rect(center=(w // 2, h // 2 + int(90 * self.s))))
            pygame.display.flip()
            self.clock.tick(60)

    # ---- interno ------------------------------------------------------------------
    def _fit(self, surface):
        size = self.screen.get_size()
        if surface is None:
            surf = pygame.Surface(size)
            surf.fill((30, 30, 40))
            return surf
        if surface.get_size() != size:
            return pygame.transform.smoothscale(surface, size)
        return surface

    def _dim(self, alpha):
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        self.screen.blit(overlay, (0, 0))

    def _rounded(self, color, rect, radius, alpha=255, width=0):
        if alpha >= 255 or width:
            pygame.draw.rect(self.screen, color, rect, width, border_radius=radius)
            return
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (*color[:3], alpha), surf.get_rect(), border_radius=radius)
        self.screen.blit(surf, rect.topleft)

    def _fit_text(self, font, text, color, max_w):
        surf = font.render(text, True, color)
        if surf.get_width() > max_w:
            h = max(1, int(surf.get_height() * max_w / surf.get_width()))
            surf = pygame.transform.smoothscale(surf, (max_w, h))
        return surf

    def _layout(self, lines, n_options):
        w, h = self.screen.get_size()
        s = self.s
        pad = int(22 * s)
        btn_h = max(28, int(48 * s))
        gap = max(6, int(10 * s))
        cam_w = int(210 * s)
        cam_h = cam_w * 3 // 4

        title_h = self.font_title.get_height()
        line_h = self.font_text.get_linesize()
        content_h = len(lines) * line_h + gap * 2 + n_options * (btn_h + gap) - gap
        content_h = max(content_h, cam_h + int(40 * s))
        card_h = min(h - 20, pad * 3 + title_h + content_h)
        card_w = min(w - 30, int(760 * s))
        card = pygame.Rect(0, 0, card_w, card_h)
        card.center = (w // 2, h // 2)

        left_x = card.x + pad
        col_w = card_w - cam_w - pad * 3
        top = card.y + pad * 2 + title_h
        cam = pygame.Rect(card.right - pad - cam_w, top, cam_w, cam_h)

        btn_top = top + len(lines) * line_h + gap * 2
        # Garante que os botões caibam no cartão
        btn_top = min(btn_top, card.bottom - pad - n_options * (btn_h + gap) + gap)
        buttons = [pygame.Rect(left_x, btn_top + i * (btn_h + gap), col_w, btn_h)
                   for i in range(n_options)]
        return card, top, left_x, col_w, line_h, cam, buttons

    def _draw_camera(self, rect, gestures):
        frame = self.frame()
        if frame is not None:
            surf = pygame.image.frombuffer(frame.tobytes(), (frame.shape[1], frame.shape[0]), "RGB")
            self.screen.blit(pygame.transform.smoothscale(surf, rect.size), rect.topleft)
        else:
            pygame.draw.rect(self.screen, (10, 10, 15), rect)
        pygame.draw.rect(self.screen, (100, 150, 255), rect, 2)

        # Indicador: quadrado interno = thresholds, ponto = posição atual
        if gestures.calibrated:
            half = max(14, int(20 * self.s))
            box = pygame.Rect(0, 0, half * 2, half * 2)
            box.bottomright = (rect.right - 5, rect.bottom - 5)
            pygame.draw.rect(self.screen, (0, 0, 0), box)
            pygame.draw.rect(self.screen, (200, 200, 200), box.inflate(-half, -half), 1)
            nx = max(-1.6, min(1.6, gestures.dx / SELECT_THRESHOLD))
            ny = max(-1.6, min(1.6, gestures.dy / NAV_THRESHOLD))
            dot = (int(box.centerx + nx * half / 2), int(box.centery + ny * half / 2))
            pygame.draw.circle(self.screen, HIGHLIGHT, dot, max(3, int(4 * self.s)))

        if self.frame() is None and self.nose() is None:
            status = "Câmera indisponível"
        elif self.nose() is None:
            status = "Posicione o rosto"
        elif not gestures.calibrated:
            status = "Calibrando..."
        else:
            status = "Controle pela cabeça ativo"
        y = rect.bottom + int(6 * self.s)
        for line in (status, "CIMA/BAIXO: navegar", "LADO: confirmar"):
            surf = self._fit_text(self.font_tiny, line, TEXT_SEC, rect.width)
            self.screen.blit(surf, (rect.x, y))
            y += surf.get_height() + int(5 * self.s)

    def _draw_button(self, rect, label, selected, progress, anim):
        shift = int(anim * 10 * self.s)
        r = rect.move(shift, 0)
        radius = max(6, int(12 * self.s))
        color = self.accent
        self._rounded((35, 35, 50), r, radius)
        if anim > 0.01:
            self._rounded(color, r, radius, alpha=int(110 * anim))
        stripe = pygame.Rect(r.x, r.y, max(5, int(9 * self.s)), r.height)
        pygame.draw.rect(self.screen, color, stripe,
                         border_top_left_radius=radius, border_bottom_left_radius=radius)
        pygame.draw.rect(self.screen, HIGHLIGHT if selected else (90, 90, 120), r,
                         3 if selected else 2, border_radius=radius)
        text = self._fit_text(self.font_btn, label, TEXT, r.width - int(60 * self.s))
        self.screen.blit(text, text.get_rect(midleft=(r.x + int(22 * self.s), r.centery)))
        if selected:
            arrow = self.font_btn.render(">", True, HIGHLIGHT)
            self.screen.blit(arrow, arrow.get_rect(midright=(r.right - int(12 * self.s), r.centery)))
            if progress > 0:
                bar = pygame.Rect(r.x + int(16 * self.s), r.bottom - max(6, int(9 * self.s)),
                                  r.width - int(28 * self.s), max(3, int(5 * self.s)))
                pygame.draw.rect(self.screen, (20, 20, 30), bar, border_radius=3)
                fill = bar.copy()
                fill.width = max(1, int(bar.width * progress))
                pygame.draw.rect(self.screen, HIGHLIGHT, fill, border_radius=3)

    def _run(self, title, lines, options, background, emphasize_lines=False):
        background = self._fit(background)
        gestures = NoseGestures()
        selected = 0
        anims = [0.0] * len(options)
        pygame.event.clear()

        while True:
            now = time.monotonic()
            card, top, left_x, col_w, line_h, cam, buttons = self._layout(lines, len(options))
            to_activate = None

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "menu"
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected = (selected - 1) % len(options)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(options)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE,
                                       pygame.K_LEFT, pygame.K_RIGHT):
                        to_activate = selected
                if event.type == pygame.MOUSEMOTION:
                    for i, rect in enumerate(buttons):
                        if rect.collidepoint(event.pos):
                            selected = i
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for i, rect in enumerate(buttons):
                        if rect.collidepoint(event.pos):
                            selected = to_activate = i

            for ev in gestures.update(self.nose(), now):
                if ev == "UP":
                    selected = (selected - 1) % len(options)
                elif ev == "DOWN":
                    selected = (selected + 1) % len(options)
                elif ev == "SELECT" and to_activate is None:
                    to_activate = selected

            if to_activate is not None:
                return options[to_activate][0]

            # ---- desenho ----
            self.screen.blit(background, (0, 0))
            self._dim(160)
            shadow = card.move(0, int(6 * self.s))
            self._rounded((0, 0, 0), shadow, int(18 * self.s), alpha=90)
            self._rounded(CARD_BG, card, int(18 * self.s), alpha=238)
            pygame.draw.rect(self.screen, self.accent, card, 3, border_radius=int(18 * self.s))

            title_surf = self._fit_text(self.font_title, title, TEXT, card.width - 40)
            self.screen.blit(title_surf, title_surf.get_rect(
                center=(card.centerx, card.y + int(22 * self.s) + title_surf.get_height() // 2)))

            y = top
            font = self.font_text_bold if emphasize_lines else self.font_text
            for i, line in enumerate(lines):
                color = HIGHLIGHT if emphasize_lines and i == 0 else TEXT_SEC
                surf = self._fit_text(font, line, color, col_w)
                self.screen.blit(surf, (left_x, y))
                y += line_h

            for i, ((_, label), rect) in enumerate(zip(options, buttons)):
                anims[i] += ((1.0 if i == selected else 0.0) - anims[i]) * 0.2
                self._draw_button(rect, label, i == selected,
                                  gestures.select_progress if i == selected else 0.0, anims[i])

            self._draw_camera(cam, gestures)

            pygame.display.flip()
            self.clock.tick(60)
