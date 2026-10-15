"""
Spider Sokoban: Người Nhện và Phi Vụ Giải Cứu Thế Giới
--------------------------------------------------------
Phiên bản đã tinh chỉnh theo yêu cầu:
- Bỏ màn menu, vào thẳng giao diện chơi.
- Sửa font để hiển thị tiếng Việt tốt hơn.
- Thêm nút BFS, DFS, UCS và nút Làm mới trên giao diện.
- Nút Làm mới tự sinh bản đồ với số block tường phụ tối đa 5 và yêu quái tối đa 3.
- Khi bấm BFS/DFS/UCS, game tự tìm và tự chạy lời giải đến khi hoàn thành.
- Giữ phong cách giao diện 2D arcade, bố cục lại panel chức năng gọn hơn.

Cài đặt:
    pip install pygame

Chạy:
    python spider_sokoban_rescue.py

Tùy chọn ảnh nhân vật:
    Đặt ảnh Người Nhện cùng thư mục với file này và đổi tên thành spider.png.

Điều khiển:
    Mũi tên / WASD  : di chuyển
    U               : hoàn tác
    R               : làm mới màn
    B / F / C       : tự giải bằng BFS / DFS / UCS
    Esc             : thoát
"""

from __future__ import annotations

import heapq
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pygame

# =========================
# Cấu hình chung
# =========================

SCREEN_W, SCREEN_H = 1152, 768
FPS = 120
TILE = 65
PANEL_W = 310
BOARD_PAD = 28

Vec = Tuple[int, int]
State = Tuple[Vec, Tuple[Vec, ...]]

DIRS: Dict[str, Vec] = {
    "U": (0, -1),
    "D": (0, 1),
    "L": (-1, 0),
    "R": (1, 0),
}

HERO_SCALE = 0.72
MONSTER_SCALE = 0.74
TARGET_SCALE = 0.52

# Bảng màu kiểu truyện tranh / arcade
COLORS = {
    "bg_top": (9, 14, 29),
    "bg_bottom": (26, 39, 73),
    "panel": (15, 24, 47),
    "panel_2": (20, 33, 64),
    "panel_light": (31, 49, 88),
    "grid": (46, 66, 112),
    "floor": (45, 64, 105),
    "floor_alt": (50, 71, 115),
    "wall": (13, 16, 28),
    "wall_edge": (88, 105, 161),
    "target": (68, 213, 255),
    "target_glow": (21, 103, 151),
    "box": (145, 44, 184),
    "box_dark": (76, 21, 115),
    "box_eye": (255, 240, 75),
    "hero_red": (237, 37, 54),
    "hero_blue": (35, 119, 205),
    "hero_black": (8, 9, 16),
    "white": (245, 248, 255),
    "muted": (165, 181, 219),
    "good": (78, 232, 156),
    "warn": (255, 194, 76),
    "danger": (255, 86, 100),
}

# =========================
# Tiện ích giao diện
# =========================


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def make_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Chọn font ưu tiên hỗ trợ tiếng Việt để tránh lỗi mất dấu trong Pygame."""
    candidates = [
        "Segoe UI",
        "Tahoma",
        "Arial Unicode MS",
        "Noto Sans",
        "DejaVu Sans",
        "Verdana",
        "Arial",
    ]
    path = pygame.font.match_font(candidates, bold=bold)
    if path:
        font = pygame.font.Font(path, size)
        font.set_bold(bold)
        return font
    return pygame.font.SysFont("arial", size, bold=bold)


def draw_vertical_gradient(surface: pygame.Surface, top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> None:
    h = surface.get_height()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        pygame.draw.line(surface, color, (0, y), (surface.get_width(), y))


def draw_text(
    surf: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Tuple[int, int, int],
    pos: Tuple[int, int],
    center: bool = False,
) -> pygame.Rect:
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surf.blit(img, rect)
    return rect


def rounded_rect(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color: Tuple[int, int, int],
    radius: int = 18,
    border: int = 0,
    border_color: Optional[Tuple[int, int, int]] = None,
) -> None:
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surface, border_color or COLORS["white"], rect, border, border_radius=radius)


class Button:
    def __init__(self, rect: pygame.Rect, label: str, action: str, hotkey: str = ""):
        self.rect = rect
        self.label = label
        self.action = action
        self.hotkey = hotkey

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, mouse: Tuple[int, int], active: bool = True) -> None:
        hover = self.rect.collidepoint(mouse) and active
        base = COLORS["panel_light"] if hover else COLORS["panel_2"]
        edge = COLORS["target"] if hover else COLORS["grid"]
        if not active:
            base = (22, 27, 43)
            edge = (55, 61, 84)
        rounded_rect(surf, self.rect, base, 14, 2, edge)
        color = COLORS["white"] if active else (120, 132, 158)
        draw_text(surf, self.label, font, color, self.rect.center, True)

# =========================
# Dữ liệu màn chơi
# =========================

@dataclass
class Level:
    raw: List[str]
    walls: Set[Vec]
    targets: Set[Vec]
    boxes: Set[Vec]
    player: Vec
    width: int
    height: int

    @staticmethod
    def parse(raw: Sequence[str]) -> "Level":
        walls: Set[Vec] = set()
        targets: Set[Vec] = set()
        boxes: Set[Vec] = set()
        player = (0, 0)
        width = max(len(row) for row in raw)
        height = len(raw)
        for y, row in enumerate(raw):
            for x, ch in enumerate(row):
                p = (x, y)
                if ch == "#":
                    walls.add(p)
                elif ch == ".":
                    targets.add(p)
                elif ch == "$":
                    boxes.add(p)
                elif ch == "@":
                    player = p
                elif ch == "*":
                    boxes.add(p)
                    targets.add(p)
                elif ch == "+":
                    player = p
                    targets.add(p)
        return Level(list(raw), walls, targets, boxes, player, width, height)

# =========================
# Sinh màn chơi tự động
# =========================

class LevelGenerator:
    """
    Sinh màn Sokoban nhỏ, đảm bảo có lời giải bằng cách tạo từ trạng thái hoàn thành,
    sau đó kéo ngược các yêu quái ra khỏi cổng phong ấn.
    """

    def __init__(self, width: int = 9, height: int = 7):
        self.width = width
        self.height = height

    def inside(self, p: Vec) -> bool:
        x, y = p
        return 1 <= x < self.width - 1 and 1 <= y < self.height - 1

    def build_border_walls(self) -> Set[Vec]:
        walls: Set[Vec] = set()
        for x in range(self.width):
            walls.add((x, 0))
            walls.add((x, self.height - 1))
        for y in range(self.height):
            walls.add((0, y))
            walls.add((self.width - 1, y))
        return walls

    def generate(self, max_blocks: int = 5, max_monsters: int = 3) -> Level:
        for _ in range(400):
            block_count = random.randint(0, max_blocks)
            monster_count = random.randint(1, max_monsters)
            level = self._attempt(block_count, monster_count)
            if level:
                solver = SokobanSolver(level)
                result = solver.bfs(max_nodes=80_000)
                if result:
                    return level
        # Màn dự phòng đơn giản nếu máy sinh quá nhiều lần chưa ra.
        return Level.parse([
            "#########",
            "#   .   #",
            "#   $   #",
            "#  @    #",
            "#   $   #",
            "#   .   #",
            "#########",
        ])

    def _attempt(self, block_count: int, monster_count: int) -> Optional[Level]:
        walls = self.build_border_walls()
        cells = [(x, y) for y in range(1, self.height - 1) for x in range(1, self.width - 1)]

        # Tường phụ không đặt quá sát để tránh chia cắt bản đồ quá nặng.
        random.shuffle(cells)
        extra: Set[Vec] = set()
        for p in cells:
            if len(extra) >= block_count:
                break
            if p[0] in (1, self.width - 2) and p[1] in (1, self.height - 2):
                continue
            extra.add(p)
        walls |= extra

        free = [p for p in cells if p not in walls]
        if len(free) < monster_count * 2 + 1:
            return None

        targets = set(random.sample(free, monster_count))
        boxes = set(targets)
        player = random.choice([p for p in free if p not in targets])

        # Kéo ngược thùng khỏi đích để chắc chắn tồn tại chuỗi đẩy xuôi.
        for _ in range(16 + monster_count * 8):
            box = random.choice(tuple(boxes))
            dirs = list(DIRS.values())
            random.shuffle(dirs)
            for dx, dy in dirs:
                old_box = box
                new_box = (box[0] - dx, box[1] - dy)
                player_needed = (box[0] + dx, box[1] + dy)
                if (
                        self.inside(new_box)
                        and self.inside(player_needed)
                        and new_box not in walls
                        and player_needed not in walls
                        and new_box not in boxes
                        and player_needed not in boxes
                        and new_box not in targets
                ):
                    boxes.remove(old_box)
                    boxes.add(new_box)
                    player = player_needed
                    break

        # Đảm bảo số yêu quái bằng số điểm đích
        if len(boxes) != len(targets):
            return None

        # Không cho yêu quái nằm trùng điểm đích khi sinh màn mới
        if boxes & targets:
            return None

        if boxes == targets:
            return None
        raw: List[str] = []
        for y in range(self.height):
            row = ""
            for x in range(self.width):
                p = (x, y)
                if p in walls:
                    row += "#"
                elif p == player and p in targets:
                    row += "+"
                elif p == player:
                    row += "@"
                elif p in boxes and p in targets:
                    row += "*"
                elif p in boxes:
                    row += "$"
                elif p in targets:
                    row += "."
                else:
                    row += " "
            raw.append(row)
        return Level.parse(raw)

# =========================
# Bộ giải Sokoban: BFS, DFS, UCS
# =========================

class SokobanSolver:
    def __init__(self, level: Level):
        self.level = level
        self.walls = level.walls
        self.targets = level.targets
        self.expanded = 0
        self.max_frontier = 0
        self.elapsed = 0.0

    def initial_state(self) -> State:
        return self.level.player, tuple(sorted(self.level.boxes))

    def is_goal(self, state: State) -> bool:
        _, boxes = state
        return set(boxes) == self.targets

    def deadlock(self, boxes: Set[Vec]) -> bool:
        """Cắt tỉa đơn giản: yêu quái kẹt góc mà không nằm trên cổng phong ấn."""
        for x, y in boxes:
            if (x, y) in self.targets:
                continue
            wall_left = (x - 1, y) in self.walls
            wall_right = (x + 1, y) in self.walls
            wall_up = (x, y - 1) in self.walls
            wall_down = (x, y + 1) in self.walls
            if (wall_left or wall_right) and (wall_up or wall_down):
                return True
        return False

    def neighbors(self, state: State) -> Iterable[Tuple[State, str, int]]:
        player, boxes_tuple = state
        boxes = set(boxes_tuple)
        px, py = player
        for move, (dx, dy) in DIRS.items():
            np = (px + dx, py + dy)
            if np in self.walls:
                continue
            new_boxes = set(boxes)
            cost = 1
            if np in boxes:
                bp = (np[0] + dx, np[1] + dy)
                if bp in self.walls or bp in boxes:
                    continue
                new_boxes.remove(np)
                new_boxes.add(bp)
                cost = 2
                if self.deadlock(new_boxes):
                    continue
            yield (np, tuple(sorted(new_boxes))), move, cost

    def reconstruct(self, parents: Dict[State, Tuple[Optional[State], str]], goal: State) -> List[str]:
        moves: List[str] = []
        cur = goal
        while parents[cur][0] is not None:
            prev, mv = parents[cur]
            moves.append(mv)
            assert prev is not None
            cur = prev
        moves.reverse()
        return moves

    def bfs(self, max_nodes: int = 250_000) -> Optional[List[str]]:
        start_time = time.perf_counter()
        start = self.initial_state()
        frontier = deque([start])
        parents: Dict[State, Tuple[Optional[State], str]] = {start: (None, "")}
        self.expanded = 0
        self.max_frontier = 1

        while frontier and self.expanded < max_nodes:
            state = frontier.popleft()
            self.expanded += 1
            if self.is_goal(state):
                self.elapsed = time.perf_counter() - start_time
                return self.reconstruct(parents, state)
            for nxt, mv, _ in self.neighbors(state):
                if nxt not in parents:
                    parents[nxt] = (state, mv)
                    frontier.append(nxt)
            self.max_frontier = max(self.max_frontier, len(frontier))
        self.elapsed = time.perf_counter() - start_time
        return None

    def dfs(self, max_nodes: int = 250_000, depth_limit: int = 180) -> Optional[List[str]]:
        start_time = time.perf_counter()
        start = self.initial_state()
        stack: List[Tuple[State, int]] = [(start, 0)]
        parents: Dict[State, Tuple[Optional[State], str]] = {start: (None, "")}
        self.expanded = 0
        self.max_frontier = 1

        while stack and self.expanded < max_nodes:
            state, depth = stack.pop()
            self.expanded += 1
            if self.is_goal(state):
                self.elapsed = time.perf_counter() - start_time
                return self.reconstruct(parents, state)
            if depth >= depth_limit:
                continue
            for nxt, mv, _ in reversed(list(self.neighbors(state))):
                if nxt not in parents:
                    parents[nxt] = (state, mv)
                    stack.append((nxt, depth + 1))
            self.max_frontier = max(self.max_frontier, len(stack))
        self.elapsed = time.perf_counter() - start_time
        return None

    def ucs(self, max_nodes: int = 250_000) -> Optional[List[str]]:
        start_time = time.perf_counter()
        start = self.initial_state()
        frontier: List[Tuple[int, int, State]] = [(0, 0, start)]
        counter = 1
        parents: Dict[State, Tuple[Optional[State], str]] = {start: (None, "")}
        best_cost: Dict[State, int] = {start: 0}
        self.expanded = 0
        self.max_frontier = 1

        while frontier and self.expanded < max_nodes:
            cost, _, state = heapq.heappop(frontier)
            if cost != best_cost.get(state, 10**9):
                continue
            self.expanded += 1
            if self.is_goal(state):
                self.elapsed = time.perf_counter() - start_time
                return self.reconstruct(parents, state)
            for nxt, mv, step_cost in self.neighbors(state):
                nc = cost + step_cost
                if nc < best_cost.get(nxt, 10**9):
                    best_cost[nxt] = nc
                    parents[nxt] = (state, mv)
                    heapq.heappush(frontier, (nc, counter, nxt))
                    counter += 1
            self.max_frontier = max(self.max_frontier, len(frontier))
        self.elapsed = time.perf_counter() - start_time
        return None

# =========================
# Game chính
# =========================

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Spider Sokoban - Người Nhện và Phi Vụ Giải Cứu Thế Giới")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()

        self.font_title = make_font(44, bold=True)
        self.font_big = make_font(27, bold=True)
        self.font_btn = make_font(21, bold=True)
        self.font = make_font(20)
        self.font_small = make_font(16)

        self.generator = LevelGenerator(width=9, height=7)
        self.level_no = 1
        self.level = self.generator.generate(max_blocks=5, max_monsters=3)
        self.player = self.level.player
        self.boxes = set(self.level.boxes)
        self.history: List[Tuple[Vec, Set[Vec], int]] = []
        self.moves = 0
        self.pushes = 0
        self.message = "Sẵn sàng! Chọn BFS, DFS hoặc UCS để Người Nhện tự giải cứu thế giới."
        self.solution: List[str] = []
        self.solution_name = ""
        self.solution_i = 0
        self.autoplay = False
        self.autoplay_timer = 0.0
        self.last_solver_stats = "Chưa chạy thuật toán."
        self.hero_img = self.load_hero_image()
        self.buttons = self.build_buttons()

    def load_hero_image(self) -> Optional[pygame.Surface]:
        for name in ("spider.png", "spiderman.png", "hero.png"):
            if os.path.exists(name):
                try:
                    img = pygame.image.load(name).convert_alpha()
                    size = int(TILE * HERO_SCALE)
                    return pygame.transform.smoothscale(img, (size, size))
                except pygame.error:
                    pass
        return None

    def build_buttons(self) -> List[Button]:
        x = SCREEN_W - PANEL_W + 34
        y = 322
        w = PANEL_W - 68
        gap = 12
        return [
            Button(pygame.Rect(x, y, w, 48), "BFS", "BFS", "B"),
            Button(pygame.Rect(x, y + 48 + gap, w, 48), "DFS", "DFS", "F"),
            Button(pygame.Rect(x, y + (48 + gap) * 2, w, 48), "UCS", "UCS", "C"),
            Button(pygame.Rect(x, y + (48 + gap) * 3 + 12, w, 50), "Làm mới", "refresh", "R"),
        ]

    def new_random_level(self) -> None:
        self.level_no += 1
        self.level = self.generator.generate(max_blocks=5, max_monsters=3)
        self.player = self.level.player
        self.boxes = set(self.level.boxes)
        self.history.clear()
        self.moves = 0
        self.pushes = 0
        self.solution.clear()
        self.solution_i = 0
        self.autoplay = False
        block_count = max(0, len(self.level.walls) - (self.level.width * 2 + self.level.height * 2 - 4))
        monster_count = len(self.boxes)
        self.message = f"Đã sinh màn mới: {block_count} block, {monster_count} yêu quái."
        self.last_solver_stats = "Chưa chạy thuật toán."

    def board_origin(self) -> Vec:
        board_w = self.level.width * TILE
        board_h = self.level.height * TILE
        usable_w = SCREEN_W - PANEL_W
        x = (usable_w - board_w) // 2
        y = 192
        return x, y

    def move(self, key: str, record: bool = True) -> bool:
        dx, dy = DIRS[key]
        px, py = self.player
        np = (px + dx, py + dy)
        if np in self.level.walls:
            return False
        old_boxes = set(self.boxes)
        pushed = 0
        if np in self.boxes:
            bp = (np[0] + dx, np[1] + dy)
            if bp in self.level.walls or bp in self.boxes:
                return False
            self.boxes.remove(np)
            self.boxes.add(bp)
            pushed = 1
        if record:
            self.history.append((self.player, old_boxes, self.pushes))
        self.player = np
        self.moves += 1
        self.pushes += pushed
        if self.is_win():
            self.message = "Hoàn thành! Người Nhện đã phong ấn toàn bộ yêu quái."
            self.autoplay = False
        return True

    def undo(self) -> None:
        if not self.history or self.autoplay:
            return
        self.player, self.boxes, old_pushes = self.history.pop()
        self.moves = max(0, self.moves - 1)
        self.pushes = old_pushes
        self.message = "Đã hoàn tác một bước."

    def is_win(self) -> bool:
        return self.boxes == self.level.targets

    def solve_and_autoplay(self, algorithm: str) -> None:
        if self.autoplay:
            return
        solver_level = Level(
            raw=self.level.raw,
            walls=set(self.level.walls),
            targets=set(self.level.targets),
            boxes=set(self.boxes),
            player=self.player,
            width=self.level.width,
            height=self.level.height,
        )
        solver = SokobanSolver(solver_level)
        self.message = f"Đang chạy {algorithm} để tìm đường giải cứu..."
        self.draw_game()
        pygame.display.flip()

        if algorithm == "BFS":
            result = solver.bfs()
        elif algorithm == "DFS":
            result = solver.dfs()
        else:
            result = solver.ucs()

        self.last_solver_stats = (
            f"{algorithm}: mở rộng {solver.expanded:,} trạng thái | "
            f"frontier {solver.max_frontier:,} | {solver.elapsed:.3f}s"
        )
        if result is None:
            self.solution = []
            self.solution_i = 0
            self.autoplay = False
            self.message = f"{algorithm}: chưa tìm thấy lời giải trong giới hạn. Hãy bấm Làm mới."
            return

        self.solution = result
        self.solution_i = 0
        self.solution_name = algorithm
        self.autoplay = True
        self.autoplay_timer = 0.0
        self.message = f"{algorithm}: tìm thấy {len(result)} bước. Đang tự động thực hiện lời giải."

    # =========================
    # Vẽ đồ họa
    # =========================

    def draw_background(self) -> None:
        draw_vertical_gradient(self.screen, COLORS["bg_top"], COLORS["bg_bottom"])
        for x in range(0, SCREEN_W, 48):
            pygame.draw.line(self.screen, (30, 43, 78), (x, 0), (x, SCREEN_H), 1)
        for y in range(0, SCREEN_H, 48):
            pygame.draw.line(self.screen, (30, 43, 78), (0, y), (SCREEN_W, y), 1)
        for i in range(5):
            sx = 90 + i * 210
            pygame.draw.line(self.screen, (55, 74, 118), (sx, 0), (sx + 220, 210), 1)
            pygame.draw.line(self.screen, (55, 74, 118), (sx + 80, 0), (sx - 80, 190), 1)

    def draw_wall(self, rect: pygame.Rect) -> None:
        rounded_rect(self.screen, rect.inflate(-2, -2), COLORS["wall"], 10)
        pygame.draw.rect(self.screen, COLORS["wall_edge"], rect.inflate(-2, -2), 2, border_radius=10)
        pygame.draw.line(self.screen, (102, 119, 172), rect.topleft, rect.topright, 2)

    def draw_target(self, cx: int, cy: int) -> None:
        base = int(TILE * TARGET_SCALE)

        for r, alpha in [(base, 50), (int(base * 0.72), 78), (int(base * 0.46), 128)]:
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*COLORS["target"], alpha), (r, r), r)
            self.screen.blit(s, (cx - r, cy - r))

        pygame.draw.circle(self.screen, COLORS["target"], (cx, cy), int(base * 0.55), 2)
        pygame.draw.line(self.screen, COLORS["target"], (cx - int(base * 0.8), cy), (cx + int(base * 0.8), cy), 2)
        pygame.draw.line(self.screen, COLORS["target"], (cx, cy - int(base * 0.8)), (cx, cy + int(base * 0.8)), 2)

    def draw_monster_box(self, rect: pygame.Rect, sealed: bool) -> None:
        size = int(TILE * MONSTER_SCALE)
        box_rect = pygame.Rect(0, 0, size, size)
        box_rect.center = rect.center

        color = COLORS["good"] if sealed else COLORS["box"]
        dark = (26, 120, 85) if sealed else COLORS["box_dark"]

        rounded_rect(self.screen, box_rect, color, 12, 3, dark)

        inner = box_rect.inflate(-16, -16)
        pygame.draw.arc(self.screen, dark, inner.move(-8, -2), 0.2, 2.9, 3)
        pygame.draw.arc(self.screen, dark, inner.move(8, -2), 0.2, 2.9, 3)

        eye_y = box_rect.y + int(size * 0.34)

        pygame.draw.ellipse(self.screen, COLORS["box_eye"],
                            (box_rect.x + int(size * 0.18), eye_y, int(size * 0.20), int(size * 0.13)))
        pygame.draw.ellipse(self.screen, COLORS["box_eye"],
                            (box_rect.x + int(size * 0.52), eye_y, int(size * 0.20), int(size * 0.13)))

        pygame.draw.circle(self.screen, COLORS["hero_black"], (box_rect.x + int(size * 0.28), eye_y + int(size * 0.06)),
                           2)
        pygame.draw.circle(self.screen, COLORS["hero_black"], (box_rect.x + int(size * 0.62), eye_y + int(size * 0.06)),
                           2)

        mouth_y = box_rect.y + int(size * 0.70)
        pygame.draw.line(
            self.screen,
            COLORS["hero_black"],
            (box_rect.x + int(size * 0.22), mouth_y),
            (box_rect.x + int(size * 0.78), mouth_y),
            2,
        )

        for i in range(4):
            x = box_rect.x + int(size * 0.24) + i * int(size * 0.12)
            pygame.draw.polygon(
                self.screen,
                COLORS["white"],
                [(x, mouth_y), (x + 3, mouth_y + 7), (x + 6, mouth_y)],
            )

    def draw_hero(self, rect: pygame.Rect) -> None:
        size = int(TILE * HERO_SCALE)
        icon_rect = pygame.Rect(0, 0, size, size)
        icon_rect.center = rect.center

        if self.hero_img:
            img = pygame.transform.smoothscale(self.hero_img, (size, size))
            self.screen.blit(img, icon_rect)
            return

        body = icon_rect.inflate(-4, -4)
        pygame.draw.ellipse(self.screen, COLORS["hero_red"], body)
        pygame.draw.ellipse(self.screen, COLORS["hero_black"], body, 3)

        pygame.draw.polygon(
            self.screen,
            COLORS["hero_blue"],
            [
                (icon_rect.centerx, icon_rect.bottom - 5),
                (icon_rect.x + 8, icon_rect.centery + 4),
                (icon_rect.right - 8, icon_rect.centery + 4),
            ],
        )

        pygame.draw.ellipse(self.screen, COLORS["white"], (icon_rect.x + 10, icon_rect.y + 14, 12, 16))
        pygame.draw.ellipse(self.screen, COLORS["white"], (icon_rect.x + 24, icon_rect.y + 14, 12, 16))
        pygame.draw.ellipse(self.screen, COLORS["hero_black"], (icon_rect.x + 10, icon_rect.y + 14, 12, 16), 2)
        pygame.draw.ellipse(self.screen, COLORS["hero_black"], (icon_rect.x + 24, icon_rect.y + 14, 12, 16), 2)

        for ox in (-12, 0, 12):
            pygame.draw.line(
                self.screen,
                COLORS["hero_black"],
                icon_rect.center,
                (icon_rect.centerx + ox, icon_rect.y + 4),
                2,
            )

        pygame.draw.arc(self.screen, COLORS["hero_black"], icon_rect.inflate(-12, -10), 3.5, 5.9, 2)
        pygame.draw.arc(self.screen, COLORS["hero_black"], icon_rect.inflate(-20, -18), 3.5, 5.9, 2)

    def draw_board(self) -> None:
        ox, oy = self.board_origin()
        board_rect = pygame.Rect(ox - 18, oy - 18, self.level.width * TILE + 36, self.level.height * TILE + 36)
        rounded_rect(self.screen, board_rect, (9, 14, 28), 24, 2, COLORS["grid"])
        for y in range(self.level.height):
            for x in range(self.level.width):
                p = (x, y)
                rect = pygame.Rect(ox + x * TILE, oy + y * TILE, TILE, TILE)
                if p in self.level.walls:
                    self.draw_wall(rect)
                else:
                    c = COLORS["floor"] if (x + y) % 2 == 0 else COLORS["floor_alt"]
                    rounded_rect(self.screen, rect.inflate(-3, -3), c, 8)
                    pygame.draw.rect(self.screen, (58, 77, 123), rect.inflate(-3, -3), 1, border_radius=8)
                if p in self.level.targets:
                    self.draw_target(rect.centerx, rect.centery)
        for b in sorted(self.boxes):
            rect = pygame.Rect(ox + b[0] * TILE, oy + b[1] * TILE, TILE, TILE)
            self.draw_monster_box(rect, b in self.level.targets)
        pr = pygame.Rect(ox + self.player[0] * TILE, oy + self.player[1] * TILE, TILE, TILE)
        self.draw_hero(pr)

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        cur = ""
        for w in words:
            test = w if not cur else cur + " " + w
            if font.size(test)[0] <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def draw_panel(self) -> None:
        panel = pygame.Rect(SCREEN_W - PANEL_W + 18, 46, PANEL_W - 36, SCREEN_H - 92)
        rounded_rect(self.screen, panel, COLORS["panel"], 26, 2, COLORS["grid"])
        x = panel.x + 22
        y = panel.y + 24

        draw_text(self.screen, "CHỨC NĂNG", self.font_big, COLORS["white"], (x, y))
        y += 42
        block_count = max(0, len(self.level.walls) - (self.level.width * 2 + self.level.height * 2 - 4))
        lines = [
            f"Màn sinh: {self.level_no}",
            f"Block: {block_count}/5",
            f"Yêu quái: {len(self.boxes)}/3",
            f"Bước đi: {self.moves}",
            f"Lượt đẩy: {self.pushes}",
        ]
        for line in lines:
            draw_text(self.screen, line, self.font, COLORS["muted"], (x, y))
            y += 28

        y += 8
        draw_text(self.screen, "Tự động giải", self.font_big, COLORS["white"], (x, y))
        for b in self.buttons:
            b.draw(self.screen, self.font_btn, pygame.mouse.get_pos(), active=not self.autoplay or b.action == "refresh")

        msg_rect = pygame.Rect(x - 8, 585, panel.width - 28, 82)
        rounded_rect(self.screen, msg_rect, (24, 38, 69), 16, 1, COLORS["grid"])
        yy = msg_rect.y + 10
        for line in self.wrap_text(self.message, self.font_small, msg_rect.width - 18)[:3]:
            draw_text(self.screen, line, self.font_small, COLORS["white"], (msg_rect.x + 9, yy))
            yy += 21

        stat_y = 680
        for line in self.wrap_text(self.last_solver_stats, self.font_small, panel.width - 42)[:2]:
            draw_text(self.screen, line, self.font_small, COLORS["warn"], (x, stat_y))
            stat_y += 21

    def draw_top_info(self) -> None:
        draw_text(self.screen, "SPIDER SOKOBAN", self.font_title, COLORS["white"], (36, 28))
        draw_text(self.screen, "Người Nhện và Phi Vụ Giải Cứu Thế Giới", self.font, COLORS["target"], (40, 84))
        info = "BFS/DFS/UCS: bấm nút để tự chạy lời giải  •  R: làm mới  •  U: hoàn tác  •  Esc: thoát"
        draw_text(self.screen, info, self.font_small, COLORS["muted"], (40, 120))

    def draw_game(self) -> None:
        self.draw_background()
        self.draw_top_info()
        self.draw_board()
        self.draw_panel()

    # =========================
    # Vòng lặp
    # =========================

    def handle_game_key(self, event: pygame.event.Event) -> None:
        keymap = {
            pygame.K_UP: "U", pygame.K_w: "U",
            pygame.K_DOWN: "D", pygame.K_s: "D",
            pygame.K_LEFT: "L", pygame.K_a: "L",
            pygame.K_RIGHT: "R", pygame.K_d: "R",
        }
        if event.key in keymap and not self.autoplay:
            self.move(keymap[event.key])
        elif event.key == pygame.K_u:
            self.undo()
        elif event.key == pygame.K_r:
            self.new_random_level()
        elif event.key == pygame.K_b:
            self.solve_and_autoplay("BFS")
        elif event.key == pygame.K_f:
            self.solve_and_autoplay("DFS")
        elif event.key == pygame.K_c:
            self.solve_and_autoplay("UCS")
        elif event.key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit()

    def handle_button_click(self, pos: Vec) -> None:
        for b in self.buttons:
            if b.rect.collidepoint(pos):
                if b.action == "refresh":
                    self.new_random_level()
                elif not self.autoplay:
                    self.solve_and_autoplay(b.action)
                return

    def update_autoplay(self, dt: float) -> None:
        if not self.autoplay or not self.solution:
            return
        self.autoplay_timer += dt
        if self.autoplay_timer >= 0.13:
            self.autoplay_timer = 0.0
            if self.solution_i < len(self.solution):
                moved = self.move(self.solution[self.solution_i], record=True)
                if moved:
                    self.solution_i += 1
            else:
                self.autoplay = False
                self.message = f"Đã chạy xong lời giải {self.solution_name}."

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_game_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_button_click(event.pos)

            self.update_autoplay(dt)
            self.draw_game()
            pygame.display.flip()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
