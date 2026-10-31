"""
NEON FLAP V2
Single-file Pygame game for Pydroid 3 (Android) and desktop.

Run:
    pip install pygame
    python neon_flap_v2.py

Controls:
    Android: tap to flap / tap menu buttons
    PC: SPACE, UP, or W to flap; ESC to quit; R to retry after game over
"""

import math
import json
import os
import random
import struct
import pygame

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

pygame.init()

AUDIO_ENABLED = True
try:
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
except (pygame.error, OSError):
    AUDIO_ENABLED = False

LOGICAL_W, LOGICAL_H = 480, 800
FPS = 60
GROUND_H = 95
GROUND_Y = LOGICAL_H - GROUND_H
BIRD_X = 145
PIPE_W = 76
PIPE_SPACING = 270

screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
pygame.display.set_caption("NEON FLAP V2")
SCREEN_W, SCREEN_H = screen.get_size()
clock = pygame.time.Clock()
logical = pygame.Surface((LOGICAL_W, LOGICAL_H))

scale = min(SCREEN_W / LOGICAL_W, SCREEN_H / LOGICAL_H)
scaled_size = (max(1, int(LOGICAL_W * scale)),
               max(1, int(LOGICAL_H * scale)))
offset_x = (SCREEN_W - scaled_size[0]) // 2
offset_y = (SCREEN_H - scaled_size[1]) // 2

# ---------------------------------------------------------------------------
# Colours, fonts and configuration
# ---------------------------------------------------------------------------

BG_TOP = (7, 12, 34)
BG_BOTTOM = (20, 18, 60)
CYAN = (56, 245, 255)
PINK = (255, 55, 190)
LIME = (130, 255, 100)
WHITE = (245, 250, 255)
GOLD = (255, 210, 75)
DARK_BLUE = (15, 25, 50)
PIPE_FILL = (8, 90, 102)
PIPE_EDGE = (22, 220, 190)

font_big = pygame.font.Font(None, 72)
font_med = pygame.font.Font(None, 38)
font_small = pygame.font.Font(None, 24)
font_tiny = pygame.font.Font(None, 20)

DIFFICULTIES = {
    # Gravity rises while flap strength stays the same, so HARD is
    # genuinely harder rather than compensating with a stronger jump.
    "EASY": {"gap": 220, "speed": 165.0, "gravity": 720.0,  "flap": -400.0},
    "MID":  {"gap": 185, "speed": 225.0, "gravity": 1000.0, "flap": -400.0},
    "HARD": {"gap": 150, "speed": 285.0, "gravity": 1320.0, "flap": -400.0},
}
current_diff = "MID"

SONG_NAMES = [
    "NEONWAVE", "RETRO CHIP", "LO-FI CHILL", "CYBERPUNK",
    "SUNSHINE", "STARDUST", "GROOVE"
]
SONG_NOTES = [
    [220, 277, 330, 440, 330, 277, 196, 247],
    [261, 329, 392, 523, 440, 392, 329, 294],
    [146, 196, 220, 261, 220, 196, 164, 146],
    [110, 130, 164, 196, 164, 130, 110, 220],
    [330, 392, 440, 523, 587, 523, 440, 392],
    [392, 493, 587, 659, 784, 659, 587, 493],
    [164, 220, 247, 294, 330, 294, 247, 220],
]
current_song_idx = 0
current_bgm = None

# Store the record in a writable user-home location.
SAVE_FILE = os.path.join(os.path.expanduser("~"), "neon_flap_best.json")
try:
    with open(SAVE_FILE, "r", encoding="utf-8") as file:
        BEST = max(0, int(json.load(file).get("best", 0)))
except (OSError, ValueError, TypeError, json.JSONDecodeError):
    BEST = 0


def save_best():
    """Save the best score without crashing if storage is unavailable."""
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as file:
            json.dump({"best": BEST}, file)
    except (OSError, TypeError):
        pass


# ---------------------------------------------------------------------------
# Procedural audio
# ---------------------------------------------------------------------------

def make_sound(freq_start, freq_end, duration, volume=0.35):
    if not AUDIO_ENABLED:
        return None
    try:
        sample_rate = 22050
        count = max(1, int(sample_rate * duration))
        data = bytearray()
        for i in range(count):
            progress = i / count
            t = i / sample_rate
            freq = freq_start + (freq_end - freq_start) * progress
            envelope = 1.0 - progress
            value = int(32767 * volume * envelope *
                        math.sin(2 * math.pi * freq * t))
            data.extend(struct.pack("<h", value))
        return pygame.mixer.Sound(buffer=bytes(data))
    except (pygame.error, ValueError, OverflowError):
        return None


def make_music(song_index):
    """Build a short seamless synthetic melody."""
    if not AUDIO_ENABLED:
        return None
    try:
        sample_rate = 22050
        duration = 4.0
        count = int(sample_rate * duration)
        notes = SONG_NOTES[song_index % len(SONG_NOTES)]
        note_duration = duration / len(notes)
        data = bytearray()

        for i in range(count):
            t = i / sample_rate
            note_index = min(len(notes) - 1, int(t / note_duration))
            freq = notes[note_index]
            local_t = (t % note_duration) / note_duration
            envelope = math.sin(math.pi * local_t)
            fundamental = math.sin(2 * math.pi * freq * t)
            harmonic_1 = 0.35 * math.sin(2 * math.pi * freq * 1.5 * t)
            harmonic_2 = 0.18 * math.sin(2 * math.pi * freq * 2 * t)
            sample = int(32767 * 0.085 * envelope *
                         (fundamental + harmonic_1 + harmonic_2))
            data.extend(struct.pack("<h", max(-32768, min(32767, sample))))

        return pygame.mixer.Sound(buffer=bytes(data))
    except (pygame.error, ValueError, OverflowError):
        return None


flap_sound = make_sound(300, 650, 0.10)
score_sound = make_sound(600, 950, 0.15)
hit_sound = make_sound(220, 80, 0.25)


def update_music():
    global current_bgm
    if not AUDIO_ENABLED:
        return
    try:
        if current_bgm:
            current_bgm.stop()
        current_bgm = make_music(current_song_idx)
        if current_bgm:
            current_bgm.set_volume(0.55)
            current_bgm.play(-1)
    except pygame.error:
        current_bgm = None


update_music()


def play_sound(sound):
    if sound is not None and AUDIO_ENABLED:
        try:
            sound.play()
        except pygame.error:
            pass


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_text(text, font, colour, center, shadow=True):
    rendered = font.render(str(text), True, colour)
    rect = rendered.get_rect(center=(int(center[0]), int(center[1])))
    if shadow:
        shade = font.render(str(text), True, (0, 0, 0))
        logical.blit(shade, (rect.x + 2, rect.y + 3))
    logical.blit(rendered, rect)


def draw_background(elapsed):
    # Smooth vertical gradient.
    for y in range(LOGICAL_H):
        ratio = y / LOGICAL_H
        colour = tuple(
            int(BG_TOP[i] * (1 - ratio) + BG_BOTTOM[i] * ratio)
            for i in range(3)
        )
        pygame.draw.line(logical, colour, (0, y), (LOGICAL_W, y))

    # Distant skyline.
    for i in range(14):
        x = i * 40 - 10
        height = 80 + (i * 43 % 140)
        top = GROUND_Y - height
        pygame.draw.rect(logical, (12, 18, 50), (x, top, 36, height))
        light = 45 + int(math.sin(elapsed * 2.0 + i) * 20)
        window_colour = (light, 90, 140)
        for wy in range(top + 10, GROUND_Y - 10, 18):
            pygame.draw.rect(logical, window_colour, (x + 8, wy, 5, 7))
            pygame.draw.rect(logical, window_colour, (x + 23, wy, 5, 7))

    # Twinkling stars.
    for i in range(60):
        x = (i * 79 + 13) % LOGICAL_W
        y = (i * 53 + 7) % (GROUND_Y - 130)
        radius = 1 + (i % 2)
        brightness = int(120 + 80 * math.sin(elapsed * 2.5 + i))
        pygame.draw.circle(logical, (brightness, brightness, 220),
                           (x, y), radius)


def draw_pipe(x, gap_y, gap):
    x = int(x)
    top_bottom = int(gap_y - gap / 2)
    bottom_top = int(gap_y + gap / 2)

    top_rect = pygame.Rect(x, 0, PIPE_W, max(0, top_bottom))
    bottom_rect = pygame.Rect(
        x, bottom_top, PIPE_W, max(0, GROUND_Y - bottom_top)
    )

    for rect in (top_rect, bottom_rect):
        if rect.height > 0:
            pygame.draw.rect(logical, PIPE_FILL, rect, border_radius=8)
            pygame.draw.rect(logical, PIPE_EDGE, rect, 3, border_radius=8)
            pygame.draw.line(
                logical, (120, 255, 240),
                (rect.x + 12, rect.y + 6),
                (rect.x + 12, max(rect.y + 6, rect.bottom - 6)), 2
            )

    cap_h = 24
    caps = [
        pygame.Rect(x - 6, top_bottom - cap_h, PIPE_W + 12, cap_h),
        pygame.Rect(x - 6, bottom_top, PIPE_W + 12, cap_h),
    ]
    for cap in caps:
        pygame.draw.rect(logical, (20, 185, 165), cap, border_radius=6)
        pygame.draw.rect(logical, CYAN, cap, 2, border_radius=6)


def draw_bird(x, y, elapsed):
    x, y = int(x), int(y)
    # Glow is drawn on a separate surface so alpha works consistently.
    glow = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(glow, (20, 70, 110, 65), (40, 40), 37)
    pygame.draw.circle(glow, (15, 125, 150, 75), (40, 40), 28)
    logical.blit(glow, (x - 40, y - 40))

    pygame.draw.ellipse(logical, GOLD, (x - 22, y - 16, 44, 34))
    pygame.draw.ellipse(logical, (255, 245, 155), (x - 15, y - 12, 24, 12))

    wing_y = int(y + math.sin(elapsed * 12) * 6)
    pygame.draw.ellipse(logical, (255, 145, 50),
                        (x - 14, wing_y - 3, 23, 15))
    pygame.draw.circle(logical, WHITE, (x + 10, y - 6), 7)
    pygame.draw.circle(logical, (20, 25, 45), (x + 12, y - 6), 3)
    pygame.draw.polygon(logical, PINK, [
        (x + 19, y), (x + 35, y + 4), (x + 19, y + 9)
    ])
    pygame.draw.polygon(logical, GOLD, [
        (x - 19, y), (x - 30, y - 8), (x - 28, y + 6)
    ])


def draw_ground(scroll):
    pygame.draw.rect(logical, (10, 20, 52),
                     (0, GROUND_Y, LOGICAL_W, GROUND_H))
    pygame.draw.line(logical, PINK, (0, GROUND_Y),
                     (LOGICAL_W, GROUND_Y), 3)
    tile = 40
    offset = int(scroll) % tile
    for x in range(-tile, LOGICAL_W + tile, tile):
        xx = x - offset
        pygame.draw.line(logical, (28, 105, 130),
                         (xx, GROUND_Y), (xx + 25, LOGICAL_H), 2)
    for y in range(GROUND_Y + 25, LOGICAL_H, 24):
        pygame.draw.line(logical, (20, 65, 100),
                         (0, y), (LOGICAL_W, y), 1)


def draw_button(rect, label, colour, selected=False, text_colour=WHITE):
    background = colour if selected else DARK_BLUE
    foreground = BG_TOP if selected else text_colour
    pygame.draw.rect(logical, background, rect, border_radius=8)
    pygame.draw.rect(logical, colour, rect, 2, border_radius=8)
    draw_text(label, font_small, foreground, rect.center, shadow=not selected)


# ---------------------------------------------------------------------------
# Game state and gameplay
# ---------------------------------------------------------------------------

easy_btn = pygame.Rect(40, 350, 120, 44)
mid_btn = pygame.Rect(180, 350, 120, 44)
hard_btn = pygame.Rect(320, 350, 120, 44)
song_btn = pygame.Rect(90, 412, 300, 44)
reset_btn = pygame.Rect(90, 472, 300, 42)

retry_btn = pygame.Rect(140, 440, 200, 46)
home_btn = pygame.Rect(140, 502, 200, 46)
confirm_yes_btn = pygame.Rect(90, 510, 135, 42)
confirm_no_btn = pygame.Rect(255, 510, 135, 42)

reset_confirm = False
reset_confirm_until = 0.0


def new_pipe(x, gap):
    # Keep the opening away from the ceiling and floor.
    margin = int(gap / 2) + 75
    low = margin
    high = GROUND_Y - margin
    if high <= low:
        gap_y = LOGICAL_H // 2
    else:
        gap_y = random.randint(low, high)
    return {"x": float(x), "gap_y": float(gap_y), "scored": False}


def reset_game(started=False):
    gap = DIFFICULTIES[current_diff]["gap"]
    return {
        "bird_y": LOGICAL_H * 0.42,
        "bird_v": 0.0,
        "pipes": [
            new_pipe(LOGICAL_W + 100, gap),
            new_pipe(LOGICAL_W + 100 + PIPE_SPACING, gap),
        ],
        "score": 0,
        "scroll": 0.0,
        "particles": [],
        "started": started,
        "dead": False,
        "elapsed": 0.0,
        "death_sound_played": False,
    }


game = reset_game()
running = True
menu_cooldown = 0.0
last_finger_time = -1.0


def add_particles(x, y, amount, palette, speed=150):
    for _ in range(amount):
        angle = random.uniform(0, math.tau)
        velocity = random.uniform(speed * 0.25, speed)
        game["particles"].append({
            "x": float(x),
            "y": float(y),
            "vx": math.cos(angle) * velocity,
            "vy": math.sin(angle) * velocity,
            "radius": random.uniform(2.0, 6.0),
            "life": random.uniform(0.25, 0.55),
            "colour": random.choice(palette),
        })


def flap_bird():
    if game["dead"]:
        return
    config = DIFFICULTIES[current_diff]
    game["bird_v"] = config["flap"]
    play_sound(flap_sound)
    add_particles(BIRD_X - 12, game["bird_y"], 7, [CYAN, PINK, GOLD], 100)


def start_game():
    global game, menu_cooldown
    game = reset_game(started=True)
    flap_bird()
    menu_cooldown = 0.12


def screen_to_logical(position):
    px, py = position
    if scale <= 0:
        return None
    lx = (px - offset_x) / scale
    ly = (py - offset_y) / scale
    if 0 <= lx <= LOGICAL_W and 0 <= ly <= LOGICAL_H:
        return (lx, ly)
    return None


def handle_tap(position):
    global current_diff, current_song_idx, BEST, game
    global reset_confirm, reset_confirm_until, menu_cooldown

    if menu_cooldown > 0:
        return
    logical_pos = screen_to_logical(position)
    if logical_pos is None:
        return
    lx, ly = logical_pos

    if not game["started"]:
        if reset_confirm:
            if confirm_yes_btn.collidepoint(lx, ly):
                BEST = 0
                save_best()
                reset_confirm = False
            elif confirm_no_btn.collidepoint(lx, ly):
                reset_confirm = False
            return

        if easy_btn.collidepoint(lx, ly):
            current_diff = "EASY"
        elif mid_btn.collidepoint(lx, ly):
            current_diff = "MID"
        elif hard_btn.collidepoint(lx, ly):
            current_diff = "HARD"
        elif song_btn.collidepoint(lx, ly):
            current_song_idx = (current_song_idx + 1) % len(SONG_NAMES)
            update_music()
        elif reset_btn.collidepoint(lx, ly):
            reset_confirm = True
            reset_confirm_until = game["elapsed"] + 5.0
        else:
            start_game()

    elif game["dead"]:
        if retry_btn.collidepoint(lx, ly):
            start_game()
        elif home_btn.collidepoint(lx, ly):
            game = reset_game()
            menu_cooldown = 0.18
    else:
        flap_bird()


def end_game():
    global BEST
    if game["dead"]:
        return
    game["dead"] = True
    if not game["death_sound_played"]:
        play_sound(hit_sound)
        game["death_sound_played"] = True
    if game["score"] > BEST:
        BEST = game["score"]
        save_best()


def update_game(dt):
    if not game["started"] or game["dead"]:
        return

    config = DIFFICULTIES[current_diff]
    game["bird_v"] = min(
        game["bird_v"] + config["gravity"] * dt, 650.0
    )
    game["bird_y"] += game["bird_v"] * dt
    speed = config["speed"] * dt
    game["scroll"] += speed

    for pipe in game["pipes"]:
        pipe["x"] -= speed

        if not pipe["scored"] and pipe["x"] + PIPE_W < BIRD_X:
            pipe["scored"] = True
            game["score"] += 1
            play_sound(score_sound)
            add_particles(BIRD_X, game["bird_y"], 14,
                          [CYAN, PINK, GOLD], 170)

    # Recycle pipes while preserving consistent spacing.
    while game["pipes"] and game["pipes"][0]["x"] < -PIPE_W - 20:
        game["pipes"].pop(0)
        last_x = game["pipes"][-1]["x"] if game["pipes"] else LOGICAL_W
        game["pipes"].append(new_pipe(last_x + PIPE_SPACING, config["gap"]))

    # Collision rectangle is deliberately close to the visible bird body.
    bird_rect = pygame.Rect(
        BIRD_X - 18, int(game["bird_y"]) - 14, 36, 28
    )

    if bird_rect.top < 0 or bird_rect.bottom >= GROUND_Y:
        end_game()
        return

    for pipe in game["pipes"]:
        pipe_x = int(pipe["x"])
        pipe_rect = pygame.Rect(pipe_x, 0, PIPE_W, LOGICAL_H)
        if bird_rect.colliderect(pipe_rect):
            gap_top = pipe["gap_y"] - config["gap"] / 2
            gap_bottom = pipe["gap_y"] + config["gap"] / 2
            if bird_rect.top < gap_top or bird_rect.bottom > gap_bottom:
                end_game()
                return


def update_particles(dt):
    alive = []
    for particle in game["particles"]:
        particle["life"] -= dt
        particle["x"] += particle["vx"] * dt
        particle["y"] += particle["vy"] * dt
        particle["vy"] += 100 * dt
        particle["radius"] *= max(0.0, 1.0 - 1.5 * dt)
        if particle["life"] > 0 and particle["radius"] > 0.7:
            alive.append(particle)
    game["particles"] = alive


def draw_scene():
    config = DIFFICULTIES[current_diff]
    draw_background(game["elapsed"])

    for pipe in game["pipes"]:
        draw_pipe(pipe["x"], pipe["gap_y"], config["gap"])

    draw_ground(game["scroll"])

    for particle in game["particles"]:
        pygame.draw.circle(
            logical, particle["colour"],
            (int(particle["x"]), int(particle["y"])),
            max(1, int(particle["radius"]))
        )

    bird_y = game["bird_y"]
    if not game["started"]:
        # Keep the decorative bird clear of the difficulty buttons.
        bird_y = 305 + math.sin(game["elapsed"] * 3.5) * 7
        draw_bird(240, bird_y, game["elapsed"])
    else:
        draw_bird(BIRD_X, bird_y, game["elapsed"])

    draw_text(game["score"], font_big, WHITE, (LOGICAL_W // 2, 65))
    draw_text("BEST RECORD  " + str(BEST), font_small, CYAN,
              (LOGICAL_W // 2, 112))

    if not game["started"]:
        draw_text("NEON FLAP", font_big, CYAN, (LOGICAL_W // 2, 140))
        draw_text("Select Difficulty:", font_med, WHITE,
                  (LOGICAL_W // 2, 245))

        draw_button(easy_btn, "EASY", LIME, current_diff == "EASY")
        draw_button(mid_btn, "MID", GOLD, current_diff == "MID")
        draw_button(hard_btn, "HARD", PINK, current_diff == "HARD")

        pygame.draw.rect(logical, DARK_BLUE, song_btn, border_radius=8)
        pygame.draw.rect(logical, CYAN, song_btn, 2, border_radius=8)
        draw_text("SONG: " + SONG_NAMES[current_song_idx],
                  font_small, CYAN, song_btn.center)

        if reset_confirm:
            draw_text("RESET BEST SCORE?", font_small, GOLD,
                      (LOGICAL_W // 2, 480))
            draw_button(confirm_yes_btn, "YES", PINK)
            draw_button(confirm_no_btn, "CANCEL", CYAN)
        else:
            pygame.draw.rect(logical, (50, 20, 30), reset_btn,
                             border_radius=8)
            pygame.draw.rect(logical, PINK, reset_btn, 2,
                             border_radius=8)
            draw_text("RESET BEST SCORE", font_small, WHITE,
                      reset_btn.center)

        if not reset_confirm:
            draw_text("Tap / Click to start", font_small, GOLD,
                      (LOGICAL_W // 2, 570))
            draw_text("SPACE / UP / W on PC", font_tiny, WHITE,
                      (LOGICAL_W // 2, 600), shadow=False)

    elif game["dead"]:
        overlay = pygame.Surface((LOGICAL_W, LOGICAL_H), pygame.SRCALPHA)
        overlay.fill((3, 5, 20, 185))
        logical.blit(overlay, (0, 0))

        draw_text("GAME OVER", font_big, PINK, (LOGICAL_W // 2, 220))
        draw_text("SCORE: " + str(game["score"]), font_med, WHITE,
                  (LOGICAL_W // 2, 300))
        draw_text("BEST: " + str(BEST), font_med, GOLD,
                  (LOGICAL_W // 2, 350))
        draw_button(retry_btn, "RETRY", LIME)
        draw_button(home_btn, "HOME", CYAN)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

try:
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.04)
        game["elapsed"] += dt
        menu_cooldown = max(0.0, menu_cooldown - dt)

        if reset_confirm and game["elapsed"] > reset_confirm_until:
            reset_confirm = False

        tap_position = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                    if menu_cooldown <= 0:
                        if not game["started"] or game["dead"]:
                            start_game()
                        else:
                            flap_bird()
                elif event.key == pygame.K_r and game["dead"]:
                    start_game()

            elif event.type == pygame.FINGERDOWN:
                tap_position = (event.x * SCREEN_W, event.y * SCREEN_H)
                last_finger_time = pygame.time.get_ticks() / 1000.0

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Some Android Pygame builds emit a mouse event after touch.
                now = pygame.time.get_ticks() / 1000.0
                if now - last_finger_time > 0.25 and tap_position is None:
                    tap_position = event.pos

        if tap_position is not None:
            handle_tap(tap_position)

        update_game(dt)
        update_particles(dt)
        draw_scene()

        screen.fill((5, 8, 22))
        scaled = pygame.transform.smoothscale(logical, scaled_size)
        screen.blit(scaled, (offset_x, offset_y))
        pygame.display.flip()

finally:
    if current_bgm:
        try:
            current_bgm.stop()
        except pygame.error:
            pass
    pygame.quit()
