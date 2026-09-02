"""Image selection heuristics — strict front/3-4 eye-level sofa only."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Tuple

from PIL import Image


def score_image_heuristics(image_bytes: bytes) -> Dict[str, Any]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    if w < 400 or h < 400:
        return {"heuristic_score": 0, "reason": "too_small", "width": w, "height": h, "reject": True}

    aspect = w / h
    score = 40.0
    reasons: List[str] = []
    reject = False

    if 0.92 <= aspect <= 1.12:
        score += 18
        reasons.append("square_studio")
    elif 1.12 < aspect <= 1.55:
        score += 10
        reasons.append("landscape_ok")
    elif aspect < 0.88:
        score -= 40
        reasons.append("portrait_profile")
        reject = True

    fill, centroid_y = _subject_stats(img)
    reasons.append(f"fill={fill:.0f}")
    reasons.append(f"centroid_y={centroid_y:.2f}")

    # Front eye-level: sofa mass sits in middle-lower band
    if centroid_y < 0.42:
        score -= 45
        reasons.append("subject_too_high")
        reject = True
    elif 0.48 <= centroid_y <= 0.65:
        score += 20
        reasons.append("good_vertical_position")
    elif centroid_y > 0.75:
        score -= 15
        reasons.append("subject_too_low")

    top_span, mid_span, bot_span = _horizontal_spans(img)
    reasons.append(f"span_top={top_span:.2f}")
    reasons.append(f"span_bot={bot_span:.2f}")
    front_perspective = top_span > 0 and bot_span > 0 and bot_span >= top_span * 1.08

    overhead = _looks_overhead(img)
    if overhead and centroid_y < 0.50 and not front_perspective:
        score -= 50
        reasons.append("overhead_camera")
        reject = True
    elif overhead:
        reasons.append("wide_modular_front")

    clutter = _has_side_clutter(img)
    if clutter:
        score -= 25
        reasons.append("side_clutter_lamp_table")
        # Penalty only — cutout blob cleanup removes isolated lamp/table artifacts

    clusters = _count_subject_clusters(img)
    if clusters >= 3:
        score -= 30
        reasons.append(f"multi_subject_{clusters}")
        reject = True
    elif clusters == 2:
        score -= 10
        reasons.append("multi_subject_2")

    if fill > 78 and top_span > 0 and bot_span > 0 and (bot_span / top_span) < 1.12:
        score -= 45
        reasons.append("overhead_uniform_fill")
        reject = True
    elif top_span > 0 and bot_span > 0:
        if front_perspective:
            score += 15
            reasons.append("front_perspective_ok")
        elif top_span >= bot_span * 0.98 and centroid_y < 0.46:
            score -= 25
            reasons.append("flat_overhead_spread")
            reject = True

    return {
        "heuristic_score": max(0, min(100, round(score))),
        "reasons": reasons,
        "width": w,
        "height": h,
        "aspect": round(aspect, 2),
        "centroid_y": round(centroid_y, 2),
        "reject": reject,
    }


def _is_foreground(r: int, g: int, b: int) -> bool:
    brightness = (r + g + b) / 3
    saturation = max(r, g, b) - min(r, g, b)
    return not (brightness > 205 and saturation < 50)


def _subject_stats(img: Image.Image) -> Tuple[float, float]:
    small = img.resize((96, 96), Image.LANCZOS)
    fg_y: List[float] = []
    fg_count = 0
    for idx, px in enumerate(list(small.getdata())):
        if not _is_foreground(*px):
            continue
        fg_count += 1
        fg_y.append((idx // 96) / 96.0)
    fill = (fg_count / (96 * 96)) * 100
    return fill, (sum(fg_y) / len(fg_y) if fg_y else 0.5)


def _horizontal_spans(img: Image.Image) -> Tuple[float, float, float]:
    return (
        _band_span(img, 0, 0.33),
        _band_span(img, 0.33, 0.66),
        _band_span(img, 0.66, 1.0),
    )


def _looks_overhead(img: Image.Image) -> bool:
    """Overhead = uniform width across vertical bands OR top wider than bottom."""
    top, mid, bot = _horizontal_spans(img)
    if top <= 0 or bot <= 0:
        return False
    if min(top, mid, bot) / max(top, mid, bot, 0.01) > 0.88:
        return True
    if top >= bot * 1.05 and mid >= bot * 0.95:
        return True
    return False


def _band_span(img: Image.Image, y_frac_start: float, y_frac_end: float) -> float:
    w, h = img.size
    small = img.resize((64, 64), Image.LANCZOS)
    y0 = int(64 * y_frac_start)
    y1 = int(64 * y_frac_end)
    xs = []
    for y in range(y0, y1):
        for x in range(64):
            if _is_foreground(*small.getpixel((x, y))):
                xs.append(x)
    return (max(xs) - min(xs)) / 64.0 if len(xs) >= 3 else 0.0


def _has_side_clutter(img: Image.Image) -> bool:
    """Detect lamp/table/pouf in side zones (e.g. upper-right)."""
    w, h = img.size
    small = img.resize((48, 48), Image.LANCZOS)

    zones = {
        "ur": (24, 48, 0, 24),   # upper-right
        "ul": (24, 48, 24, 48),  # upper-left
        "lr": (0, 24, 0, 24),    # lower-right
    }
    center_mass = 0
    corner_mass = 0
    for y in range(48):
        for x in range(48):
            if not _is_foreground(*small.getpixel((x, y))):
                continue
            cy, cx = y / 48, x / 48
            if 0.25 <= cy <= 0.75 and 0.2 <= cx <= 0.8:
                center_mass += 1
            else:
                if cy < 0.45 and (cx < 0.2 or cx > 0.8):
                    corner_mass += 3  # weight upper corners heavily
                elif cx < 0.15 or cx > 0.85:
                    corner_mass += 1

    total = center_mass + corner_mass
    if total < 20:
        return False
    return corner_mass > total * 0.18 and corner_mass > 14


def _count_subject_clusters(img: Image.Image) -> int:
    grid = img.resize((32, 32), Image.LANCZOS)
    mask = [
        [1 if _is_foreground(*grid.getpixel((x, y))) else 0 for x in range(32)]
        for y in range(32)
    ]
    visited = [[False] * 32 for _ in range(32)]
    clusters = 0

    def dfs(sy: int, sx: int) -> None:
        stack = [(sy, sx)]
        while stack:
            cy, cx = stack.pop()
            if cy < 0 or cy >= 32 or cx < 0 or cx >= 32 or visited[cy][cx] or mask[cy][cx] == 0:
                continue
            visited[cy][cx] = True
            stack.extend([(cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)])

    for y in range(32):
        for x in range(32):
            if mask[y][x] and not visited[y][x]:
                dfs(y, x)
                clusters += 1
    return clusters
