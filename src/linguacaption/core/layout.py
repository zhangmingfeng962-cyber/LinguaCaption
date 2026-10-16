"""Geometry is independent of Qt; coordinates are logical pixels."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def intersects(self, other: Rect) -> bool:
        return (self.x < other.right and self.right > other.x
                and self.y < other.bottom and self.bottom > other.y)

    def contains(self, other: Rect) -> bool:
        return (self.x <= other.x and self.y <= other.y
                and self.right >= other.right and self.bottom >= other.bottom)

    def padded(self, gap: float) -> Rect:
        return Rect(self.x - gap, self.y - gap, self.w + 2 * gap, self.h + 2 * gap)


def place_subtitle(
    bounds: Rect, size: tuple[float, float], preferred: tuple[float, float],
    forbidden: list[Rect], gap: float = 12,
) -> Rect | None:
    """Find the nearest collision-free rectangle; hide if none fits.

    All critical obstacle edges participate, so narrow free corridors are not
    missed by a coarse grid. Preferred is the desired top-left coordinate.
    """
    w, h = size
    if w <= 0 or h <= 0 or w > bounds.w or h > bounds.h:
        return None
    blocks = [r.padded(gap) for r in forbidden]
    px = min(max(preferred[0], bounds.x), bounds.right - w)
    py = min(max(preferred[1], bounds.y), bounds.bottom - h)
    xs = {bounds.x, bounds.right - w, px}
    ys = {bounds.y, bounds.bottom - h, py}
    for block in blocks:
        xs.update((block.x - w, block.right))
        ys.update((block.y - h, block.bottom))
    candidates = [Rect(x, y, w, h) for x in xs for y in ys]
    valid = [r for r in candidates if bounds.contains(r) and not any(r.intersects(b) for b in blocks)]
    return min(valid, key=lambda r: ((r.x - px) ** 2 + (r.y - py) ** 2, r.y, r.x), default=None)


def preferred_position(bounds: Rect, size: tuple[float, float], preset: str,
                       custom: tuple[float, float] = (0.5, 0.83)) -> tuple[float, float]:
    w, h = size
    middle = bounds.x + (bounds.w - w) / 2
    if preset == "top":
        return middle, bounds.y + 32
    if preset == "left":
        return bounds.x + 24, bounds.y + (bounds.h - h) / 2
    if preset == "right":
        return bounds.right - w - 24, bounds.y + (bounds.h - h) / 2
    if preset == "custom":
        return bounds.x + bounds.w * custom[0] - w / 2, bounds.y + bounds.h * custom[1] - h / 2
    return middle, bounds.bottom - h - 64
