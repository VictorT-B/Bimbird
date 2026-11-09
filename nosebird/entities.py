import os
import random

import pygame
from settings import (
    GRAVITY,
    GROUND_Y,
    JUMP_VELOCITY,
    PLAYER_X,
    SPRITES_DIR,
    STAND_H,
    WIDTH,
)

IMAGE_CACHE = {}


def load_image(filename, default_size=(64, 64)):
    """Carrega uma imagem da pasta."""
    if filename in IMAGE_CACHE:
        return IMAGE_CACHE[filename]

    base_dir = os.path.dirname(__file__)
    search_paths = [
        os.path.join(SPRITES_DIR, filename),
        os.path.join(base_dir, SPRITES_DIR, filename),
        os.path.join(base_dir, filename),
        filename,
    ]
    for path in search_paths:
        if os.path.exists(path):
            try:
                surf = pygame.image.load(path).convert_alpha()
                IMAGE_CACHE[filename] = surf
                return surf
            except Exception:
                pass

    fallback = pygame.Surface(default_size, pygame.SRCALPHA)
    pygame.draw.rect(
        fallback,
        (230, 235, 245),
        (8, 4, default_size[0] - 16, default_size[1] - 8),
        border_radius=6,
    )
    IMAGE_CACHE[filename] = fallback
    return fallback


def load_sequence(prefix, count):
    return [load_image(f"{prefix}{i}.png") for i in range(1, count + 1)]


class Particle:
    """Partícula genérica para efeitos de poeira e impacto."""

    def __init__(self, x, y, vx, vy, color, radius, lifetime, shape="circle"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.radius = radius
        self.max_lifetime = lifetime
        self.lifetime = lifetime
        self.shape = shape

    def update(self, dt=1.0):
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= dt
        self.radius = max(0.5, self.radius * 0.96)

    def is_dead(self):
        return self.lifetime <= 0

    def draw(self, surf):
        if self.lifetime <= 0:
            return
        alpha = int(255 * (self.lifetime / self.max_lifetime))
        r, g, b = self.color[:3]

        particle_surf = pygame.Surface(
            (int(self.radius * 2 + 4), int(self.radius * 2 + 4)), pygame.SRCALPHA
        )
        center = (int(self.radius + 2), int(self.radius + 2))

        if self.shape == "circle":
            pygame.draw.circle(
                particle_surf, (r, g, b, alpha), center, int(self.radius)
            )
        elif self.shape == "square":
            rect = pygame.Rect(
                center[0] - int(self.radius),
                center[1] - int(self.radius),
                int(self.radius * 2),
                int(self.radius * 2),
            )
            pygame.draw.rect(particle_surf, (r, g, b, alpha), rect)

        surf.blit(particle_surf, (self.x - self.radius - 2, self.y - self.radius - 2))


class Player:
    """O Pássaro controlado pelo jogador: corre e pula."""

    RUN_FRAME_TIME = 8

    def __init__(self, char_name="bimbird"):
        self.char_name = char_name
        self.y_bottom = GROUND_Y
        self.vel_y = 0.0
        self.on_ground = True
        self.paused = False

        prefix = "bimbird_" if char_name == "bimbird" else "ptero_"
        all_frames = load_sequence(prefix, 6)

        # Correção: quadros 1 a 3 para correr, 4 a 6 para voar (pulo)
        if len(all_frames) == 6:
            self.run_frames = all_frames[0:3]
            self.fly_frames = all_frames[3:6]
        else:
            self.run_frames = all_frames
            self.fly_frames = all_frames

        if len(self.run_frames) == 0:
            self.run_frames = [load_image("fallback.png")]
            self.fly_frames = [load_image("fallback.png")]

        self.frame_index = 0
        self.frame_timer = 0

        self.particles = []
        self.dust_timer = 0

    def get_current_frame(self):
        if not self.on_ground:
            # O usuário pediu: 4 (index 0) no começo do pulo, 5 (index 1) subindo, 6 (index 2) caindo.
            if self.vel_y < -7:
                fly_index = 0
            elif self.vel_y < 0:
                fly_index = 1
            else:
                fly_index = 2

            # Garantir que não dê IndexError caso os sprites não tenham sido carregados corretamente
            fly_index = min(fly_index, len(self.fly_frames) - 1)
            return self.fly_frames[fly_index]
        else:
            if not self.paused:
                self.frame_timer += 1
                if self.frame_timer >= self.RUN_FRAME_TIME:
                    self.frame_timer = 0
                    self.frame_index = (self.frame_index + 1) % len(self.run_frames)
            return self.run_frames[self.frame_index]

    def get_current_image_and_size(self):
        img = self.get_current_frame()
        orig_w, orig_h = img.get_size()
        aspect_ratio = orig_w / max(1, orig_h)
        target_h = STAND_H
        target_w = int(target_h * aspect_ratio)
        return img, target_w, target_h

    def get_rect(self):
        _, target_w, target_h = self.get_current_image_and_size()
        top = self.y_bottom - target_h
        return pygame.Rect(PLAYER_X, top, target_w, target_h)

    @property
    def rect(self):
        return self.get_rect()

    @property
    def hitbox(self):
        """Hitbox fixa para que a dificuldade seja EXATAMENTE a mesma para a Ave Terror e Bimbird, independente do sprite."""
        # Cria uma hitbox centralizada justa para ambos
        return pygame.Rect(PLAYER_X + 16, self.y_bottom - 44, 26, 36)

    def jump(self):
        if self.on_ground:
            self.vel_y = JUMP_VELOCITY
            self.on_ground = False
            self.frame_index = 0
            self.frame_timer = 0

            for _ in range(8):
                vx = random.uniform(-3, -0.5)
                vy = random.uniform(-2, 0)
                self.particles.append(
                    Particle(
                        PLAYER_X + 20,
                        GROUND_Y - 4,
                        vx,
                        vy,
                        (220, 200, 160),
                        random.uniform(3, 6),
                        random.randint(15, 25),
                    )
                )

    def update(self):
        if not self.on_ground:
            self.vel_y += GRAVITY
            self.y_bottom += self.vel_y

            if self.y_bottom >= GROUND_Y:
                self.y_bottom = GROUND_Y
                self.vel_y = 0
                self.on_ground = True
                self.frame_index = 0
                self.frame_timer = 0
                for _ in range(10):
                    vx = random.uniform(-3, 3)
                    vy = random.uniform(-2, 0)
                    self.particles.append(
                        Particle(
                            PLAYER_X + 20,
                            GROUND_Y - 2,
                            vx,
                            vy,
                            (220, 200, 160),
                            random.uniform(2, 5),
                            random.randint(12, 20),
                        )
                    )
        else:
            self.dust_timer += 1
            if self.dust_timer >= 6:
                self.dust_timer = 0
                self.particles.append(
                    Particle(
                        PLAYER_X + 6,
                        GROUND_Y - 2,
                        random.uniform(-1.5, -0.5),
                        random.uniform(-0.5, 0),
                        (200, 190, 170),
                        random.uniform(2, 4),
                        random.randint(10, 18),
                    )
                )

        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if not p.is_dead()]

    def draw(self, surf, debug=False):
        for p in self.particles:
            p.draw(surf)

        img, target_w, target_h = self.get_current_image_and_size()

        # Evitar recálculos desnecessários de scale e rotação extrema que deixava horrível
        scaled_image = pygame.transform.scale(img, (max(1, target_w), max(1, target_h)))

        rect_drawn = scaled_image.get_rect()
        rect_drawn.midbottom = (PLAYER_X + target_w // 2, self.y_bottom)

        surf.blit(scaled_image, rect_drawn)

        if debug:
            # Sprite box (ciano)
            pygame.draw.rect(surf, (0, 229, 255), rect_drawn, 1)
            # Hitbox real (vermelho semitransparente com borda sólida)
            hb = self.hitbox
            hb_surf = pygame.Surface((hb.width, hb.height), pygame.SRCALPHA)
            hb_surf.fill((255, 50, 50, 90))
            surf.blit(hb_surf, (hb.x, hb.y))
            pygame.draw.rect(surf, (255, 50, 50), hb, 2)


class Obstacle:
    """Cactos aleatórios ou Meteoro."""

    CACTUS_FILES = [f"cacto_{i}.png" for i in range(1, 11)]

    def __init__(self, speed):
        self.speed_multiplier = 1.0
        if random.random() < 0.15:
            self.kind = "meteoro"
        else:
            self.kind = "cactus"

        self.trail_history = []
        self.sparks = []

        if self.kind == "cactus":
            c_file = random.choice(self.CACTUS_FILES)
            self.image = load_image(c_file)

            orig_w, orig_h = self.image.get_size()
            aspect = orig_w / max(1, orig_h)

            self.h = 65
            self.w = int(self.h * aspect)
            self.image = pygame.transform.scale(self.image, (self.w, self.h))

            self.x = WIDTH + 10
            self.y = GROUND_Y - self.h
            self.speed = speed

        elif self.kind == "meteoro":
            self.image = load_image("meteoro.png")
            orig_w, orig_h = self.image.get_size()
            aspect = orig_w / max(1, orig_h)

            self.h = 50
            self.w = int(self.h * aspect)
            self.image = pygame.transform.scale(self.image, (self.w, self.h))

            self.x = WIDTH + 10
            self.y = GROUND_Y - self.h - 15
            self.speed_multiplier = 1.15
            self.speed = speed * self.speed_multiplier
            self.spark_colors = [(255, 100, 50), (255, 200, 0), (200, 50, 20)]

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    @property
    def hitbox(self):
        r = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        # Mais perdoável: encolhe 50%
        return r.inflate(-int(self.w * 0.5), -int(self.h * 0.5))

    def update(self, world_speed=None):
        if world_speed is not None:
            self.speed = world_speed * self.speed_multiplier
        self.x -= self.speed

        if self.kind == "meteoro":
            self.trail_history.append((self.x, self.y))
            if len(self.trail_history) > 6:
                self.trail_history.pop(0)

            if random.random() < 0.6:
                p_col = random.choice(self.spark_colors)
                self.sparks.append(
                    Particle(
                        self.x + self.w - random.uniform(0, 10),
                        self.y + random.uniform(5, self.h - 5),
                        random.uniform(1, 4),
                        random.uniform(-1, 1),
                        p_col,
                        random.uniform(2.0, 5.0),
                        random.randint(15, 25),
                    )
                )

        for p in self.sparks:
            p.update()
        self.sparks = [p for p in self.sparks if not p.is_dead()]

    def offscreen(self):
        return self.x + self.w < 0

    def draw(self, surf, debug=False):
        r = self.rect
        if self.kind == "meteoro":
            for p in self.sparks:
                p.draw(surf)
            if len(self.trail_history) > 1:
                for idx, (tx, ty) in enumerate(self.trail_history[:-1]):
                    alpha = int(140 * (idx / len(self.trail_history)))
                    if alpha > 0:
                        scale_factor = 0.7 + 0.3 * (idx / len(self.trail_history))
                        tw = int(self.w * scale_factor)
                        th = int(self.h * scale_factor)
                        ghost_img = pygame.transform.scale(
                            self.image, (max(1, tw), max(1, th))
                        )
                        ghost_tint = pygame.Surface(
                            ghost_img.get_size(), pygame.SRCALPHA
                        )
                        ghost_tint.fill((255, 150, 50, alpha))
                        ghost_img.blit(
                            ghost_tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT
                        )
                        surf.blit(ghost_img, (int(tx + (self.w - tw)), int(ty)))

        surf.blit(self.image, (r.x, r.y))

        if debug:
            # Sprite box (ciano)
            pygame.draw.rect(surf, (0, 229, 255), r, 1)
            # Hitbox real (amarelo/laranja semitransparente com borda sólida)
            hb = self.hitbox
            hb_surf = pygame.Surface((hb.width, hb.height), pygame.SRCALPHA)
            hb_surf.fill((255, 215, 0, 90))
            surf.blit(hb_surf, (hb.x, hb.y))
            pygame.draw.rect(surf, (255, 215, 0), hb, 2)
