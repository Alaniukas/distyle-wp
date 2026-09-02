"""Studio background cutout using rembg + mask cleanup + soft shadow."""

from __future__ import annotations

import io
import os
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image

try:
    from rembg import remove
    from scipy import ndimage
except ImportError:
    remove = None  # type: ignore
    ndimage = None  # type: ignore

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore


def _bg_color() -> Tuple[int, int, int]:
    return (
        int(os.getenv("BG_COLOR_R", "237")),
        int(os.getenv("BG_COLOR_G", "236")),
        int(os.getenv("BG_COLOR_B", "232")),
    )


def _clean_alpha_mask(
    alpha: np.ndarray,
    min_area_ratio: float = 0.015,
    strip_side_artifacts: bool = True,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Keep the main sofa blob; remove floating shelves/poufs/disconnected artifacts.
    Prefer large components whose centroid sits in the lower 75% of the frame.
    """
    meta: Dict[str, Any] = {"blob_count": 0, "removed_blobs": 0}
    if ndimage is None:
        return alpha, meta

    binary = alpha > 48
    labeled, num = ndimage.label(binary)
    meta["blob_count"] = int(num)
    if num <= 1:
        return alpha, meta

    h, w = alpha.shape
    min_area = h * w * min_area_ratio
    best_label = 0
    best_score = -1.0

    for label in range(1, num + 1):
        mask = labeled == label
        area = float(mask.sum())
        if area < min_area:
            continue
        ys, xs = np.where(mask)
        cy = ys.mean() / h
        cx = xs.mean() / w
        score = area * (0.55 + cy * 0.9)
        if cy < 0.25 and area < min_area * 4:
            score *= 0.15
        # Upper-right/left corner blobs = lamp, side table
        if cy < h * 0.42 and (cx < w * 0.18 or cx > w * 0.72):
            score *= 0.05
        if score > best_score:
            best_score = score
            best_label = label

    if best_label == 0:
        sizes = ndimage.sum(binary, labeled, range(1, num + 1))
        best_label = int(np.argmax(sizes)) + 1

    cleaned = np.where(labeled == best_label, alpha, 0).astype(np.uint8)
    meta["removed_blobs"] = max(0, num - 1)

    if strip_side_artifacts:
        cleaned = _strip_upper_side_artifacts(cleaned)
    return cleaned, meta


def _strip_upper_side_artifacts(alpha: np.ndarray) -> np.ndarray:
    """Remove lamp/table blobs in upper-right and upper-left corners."""
    h, w = alpha.shape
    out = alpha.copy()
    zones = (
        (slice(0, int(h * 0.42)), slice(int(w * 0.68), w)),   # upper-right
        (slice(0, int(h * 0.38)), slice(0, int(w * 0.12))),    # upper-left shelf zone
    )
    for ys, xs in zones:
        zone = out[ys, xs]
        if (zone > 48).sum() > 0:
            out[ys, xs] = 0
    return out


def _corner_patches(rgb: np.ndarray) -> Tuple[np.ndarray, ...]:
    h, w, _ = rgb.shape
    s = max(6, min(h, w) // 40)
    return (
        rgb[:s, :s],
        rgb[:s, -s:],
        rgb[-s:, :s],
        rgb[-s:, -s:],
    )


def _is_white_studio(rgb: np.ndarray) -> bool:
    return all(
        float(c.mean()) > 248 and float(c.std()) < 12 for c in _corner_patches(rgb)
    )


def _is_neutral_studio(rgb: np.ndarray) -> bool:
    """True for already-composited #edece8 (or near) catalog shots — not a bright room."""
    bg = np.array(_bg_color(), dtype=np.float32)
    for c in _corner_patches(rgb):
        mean = c.reshape(-1, 3).mean(axis=0)
        if float(np.abs(mean - bg).max()) > 22:
            return False
        if float(c.std()) > 22:
            return False
    return True


def _strip_bright_edge_drapery(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Drop white/sheer curtains at left/right frame edges without eating beige fabric."""
    h, w = alpha.shape
    lum = rgb.mean(axis=2)
    chroma = rgb.std(axis=2)
    out = alpha.copy()
    left = max(1, int(w * 0.18))
    right = min(w - 1, int(w * 0.90))
    sheer = (lum > 225) & (chroma < 14)
    out[:, :left][sheer[:, :left]] = 0
    out[:, right:][sheer[:, right:]] = 0
    return out


def _inpaint_rgb_alpha(rgb: np.ndarray, alpha: np.ndarray, gap: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Inpaint gap using sofa colors, not rembg's black transparent RGB."""
    sofa = alpha > 48
    seed = rgb.copy()
    if sofa.any():
        seed[~sofa] = np.median(rgb[sofa], axis=0)
    repaired = cv2.inpaint(seed, (gap.astype(np.uint8) * 255), 10, cv2.INPAINT_TELEA)
    out_rgb = rgb.copy()
    out_rgb[gap] = repaired[gap]
    out_alpha = alpha.copy()
    out_alpha[gap] = 255
    return out_rgb, out_alpha


def _repair_drapery_bites(
    rgba: Image.Image,
    drapery_lost: np.ndarray,
) -> Tuple[Image.Image, Dict[str, Any]]:
    """Inpaint curtain pixels that still touch the sofa. Ignore leftover rembg speckles."""
    meta: Dict[str, Any] = {"inpainted": False, "needs_generate": False, "gap_ratio": 0.0}
    alpha = np.array(rgba.split()[3])
    sofa = alpha > 48
    blob = float(sofa.sum())
    if blob < 100 or ndimage is None or cv2 is None:
        return rgba, meta

    near_sofa = ndimage.binary_dilation(sofa, iterations=10)
    gap = drapery_lost & near_sofa
    ratio = float(gap.sum()) / blob
    meta["gap_ratio"] = round(ratio, 4)
    if ratio <= 0.0005:
        return rgba, meta
    if ratio > 0.12:
        meta["needs_generate"] = True
        return rgba, meta

    rgb = np.array(rgba.convert("RGB"))
    out_rgb, new_alpha = _inpaint_rgb_alpha(rgb, alpha, gap)
    out = Image.fromarray(out_rgb, mode="RGB").convert("RGBA")
    out.putalpha(Image.fromarray(new_alpha, mode="L"))
    meta["inpainted"] = True
    return out, meta


def _fill_boxy_corner_bites(rgba: Image.Image) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Boxy arm + curtain: lower outer corner inset vs a stable vertical edge.
    Skip if the outer edge is already a smooth curve (studio 3-seater arms).
    """
    meta: Dict[str, Any] = {"corner_inpainted": False, "needs_generate": False, "corner_ratio": 0.0}
    if cv2 is None:
        return rgba, meta
    alpha = np.array(rgba.split()[3])
    sofa = alpha > 48
    bbox = Image.fromarray(alpha, mode="L").getbbox()
    if not bbox:
        return rgba, meta
    x0, y0, x1, y1 = bbox
    h_box = y1 - y0
    blob = float(sofa.sum())
    if h_box < 20 or blob < 100:
        return rgba, meta

    gap = np.zeros_like(sofa)

    for from_left in (True, False):
        ys = []
        xs = []
        for y in range(y0, y1):
            row = np.where(sofa[y, x0:x1])[0]
            if row.size:
                ys.append(y)
                xs.append(int(row[0] if from_left else row[-1]))
        if len(xs) < 12:
            continue
        y_arr = np.array(ys, dtype=np.float32)
        x_arr = np.array(xs, dtype=np.float32)
        fit = np.polyfit(y_arr, x_arr, 2)
        resid = float(np.std(x_arr - np.polyval(fit, y_arr)))
        if resid < 5.0:
            continue  # smooth studio silhouette
        outer = int(np.percentile(x_arr, 8 if from_left else 92))
        for y, x in zip(ys, xs):
            if from_left and x > outer + 4:
                gap[y, x0 + outer : x0 + x] = True
            elif (not from_left) and x < outer - 4:
                gap[y, x0 + x + 1 : x0 + outer + 1] = True

    ratio = float(gap.sum()) / blob
    meta["corner_ratio"] = round(ratio, 4)
    if ratio <= 0.0008:
        return rgba, meta
    if ratio > 0.04:
        meta["needs_generate"] = True
        return rgba, meta

    rgb = np.array(rgba.convert("RGB"))
    out_rgb, new_alpha = _inpaint_rgb_alpha(rgb, alpha, gap)
    out = Image.fromarray(out_rgb, mode="RGB").convert("RGBA")
    out.putalpha(Image.fromarray(new_alpha, mode="L"))
    meta["corner_inpainted"] = True
    return out, meta


def validate_cutout_rgba(
    rgba: Image.Image,
    orig_rgb: np.ndarray | None = None,
) -> Dict[str, Any]:
    """Validate cutout quality before accepting."""
    alpha = np.array(rgba.split()[3])
    binary = alpha > 48
    h, w = alpha.shape

    if ndimage is not None:
        labeled, num = ndimage.label(binary)
    else:
        num = 1

    bbox = _opaque_bbox(rgba) or rgba.getbbox()
    if not bbox:
        return {"valid": False, "reason": "empty_mask"}

    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    fill = (bw * bh) / (w * h)

    cy = (bbox[1] + bbox[3]) / 2 / h
    aspect_bbox = bw / max(bh, 1)
    isolated = bbox[0] > w * 0.015 and bbox[2] < w * 0.985
    white_src = bool(
        orig_rgb is not None
        and (_is_white_studio(orig_rgb) or _is_neutral_studio(orig_rgb))
    )

    if fill < 0.22:
        if not (white_src and isolated and fill >= 0.08):
            return {"valid": False, "reason": "subject_too_small", "fill": round(fill, 2)}
    if cy < 0.58 and not white_src:
        return {"valid": False, "reason": "subject_too_high", "centroid_y": round(cy, 2)}
    if num > 3:
        return {"valid": False, "reason": "multiple_blobs", "blob_count": num}
    if 0.85 < aspect_bbox < 1.45 and cy < 0.52 and fill > 0.35 and not white_src:
        return {"valid": False, "reason": "overhead_layout", "aspect": round(aspect_bbox, 2)}

    top_zone = alpha[: int(h * 0.2), :]
    if (not white_src) and (top_zone > 48).sum() > (w * h * 0.02) and bbox[1] > h * 0.15:
        return {"valid": False, "reason": "top_artifacts"}

    # Side clutter: upper-right alpha after cleanup = lamp/table survived blob filter
    ur = alpha[: int(h * 0.42), int(w * 0.68):]
    if (ur > 48).sum() > (w * h * 0.008) and not white_src:
        return {"valid": False, "reason": "side_clutter"}

    return {"valid": True, "fill": round(fill, 2), "centroid_y": round(cy, 2), "blob_count": num}


def _defringe_rgba(rgba: Image.Image) -> Image.Image:
    """Remove light-bg fringe on the silhouette; fill leftover transparent RGB."""
    arr = np.array(rgba)
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3].astype(np.float32)
    interior = alpha > 220
    if interior.sum() < 80:
        interior = alpha > 160
    if not interior.any():
        return rgba
    med = np.median(rgb[interior], axis=0)
    med_lum = float(med.mean())
    lum = rgb.mean(axis=2)
    if ndimage is not None:
        core = ndimage.binary_erosion(alpha > 48, iterations=2)
        rim = (alpha > 48) & ~core
        bg_lum = float(np.mean(_bg_color()))
        too_bright = rim & (lum > max(med_lum + 14, bg_lum + 3))
        alpha[too_bright] = 0
        rgb[too_bright] = med
    rgb[alpha < 96] = med
    alpha = np.where(alpha < 24, 0, alpha)
    rgb[alpha < 8] = med
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha, 0, 255)]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _choke_smooth_alpha(rgba: Image.Image, choke: int = 2, sigma: float = 1.05) -> Image.Image:
    """Pull the mask inward to drop white fringe, then anti-alias only the contour."""
    if ndimage is None:
        return rgba
    alpha = np.array(rgba.split()[3])
    binary = alpha > 48
    if choke > 0:
        binary = ndimage.binary_erosion(binary, iterations=choke)
    binary = ndimage.binary_closing(binary, iterations=1)
    smooth = ndimage.gaussian_filter(binary.astype(np.float32) * 255.0, sigma=sigma)
    rgba.putalpha(Image.fromarray(np.clip(smooth, 0, 255).astype(np.uint8), mode="L"))
    return rgba


def _unify_studio_bg(
    rgb: np.ndarray,
    bg: Tuple[int, int, int],
    sofa_alpha: np.ndarray,
) -> np.ndarray:
    """Force leftover gen/catalog plates (Qubik rectangle, white floor) to exact #edece8."""
    bg_arr = np.array(bg, dtype=np.uint8)
    dist = np.abs(rgb.astype(np.int16) - bg_arr.astype(np.int16)).sum(axis=2)
    lum = rgb.mean(axis=2)
    chroma = rgb.std(axis=2)
    bg_lum = float(np.mean(bg))
    outside = sofa_alpha < 36
    snap = outside & (
        (dist < 28)
        | (lum > 242)
        | ((np.abs(lum - bg_lum) < 16) & (chroma < 7))
    )
    if ndimage is not None:
        near = dist < 22
        seed = np.zeros(dist.shape, dtype=bool)
        seed[:4, :] = True
        seed[-4:, :] = True
        seed[:, :4] = True
        seed[:, -4:] = True
        seed &= near
        flooded = ndimage.binary_propagation(seed, mask=near)
        snap = snap | flooded
    out = rgb.copy()
    out[snap] = bg_arr
    return out


def _strip_bottom_white_halo(rgba: Image.Image) -> Image.Image:
    """Drop catalog/gen white fringe at the feet so it cannot composite as a glow."""
    arr = np.array(rgba)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3].copy()
    h, _w = alpha.shape
    lum = rgb.mean(axis=2)
    chroma = rgb.std(axis=2)
    sofa = alpha > 40
    if ndimage is None or not sofa.any():
        return rgba
    flipped = sofa[::-1]
    bottom = h - 1 - np.argmax(flipped, axis=0)
    has = sofa.any(axis=0)
    bottom = np.where(has, bottom, -1)
    yy = np.arange(h)[:, None]
    dist_up = bottom[None, :] - yy
    near = sofa & has[None, :] & (dist_up >= 0) & (dist_up < 18)
    bg_lum = float(np.mean(_bg_color()))
    whiteish = (lum >= 243) | ((lum >= bg_lum + 7) & (chroma < 16))
    alpha[near & whiteish] = 0
    dil = ndimage.binary_dilation(sofa, iterations=5)
    glow = dil & (alpha < 40) & (lum > bg_lum + 3) & (chroma < 14)
    alpha[glow] = 0
    arr[:, :, 3] = alpha
    return Image.fromarray(arr, mode="RGBA")


def _heal_white_on_fabric(rgba: Image.Image) -> Image.Image:
    """Inpaint blown-out white noise sitting on top of sofa fabric (Hero chaise)."""
    if cv2 is None or ndimage is None:
        return rgba
    arr = np.array(rgba)
    rgb = arr[:, :, :3].copy()
    alpha = arr[:, :, 3]
    sofa = alpha > 120
    if sofa.sum() < 200:
        return rgba
    lum = rgb.mean(axis=2)
    chroma = rgb.std(axis=2)
    fabric = sofa & (lum < 232) & (lum > 120) & (chroma > 3)
    if fabric.sum() < 80:
        return rgba
    fab_med = float(np.median(lum[fabric]))
    blown = sofa & ((lum >= 248) | ((lum > max(fab_med + 26, 240)) & (chroma < 10)))
    if blown.sum() < 40:
        return rgba
    seed = rgb.copy()
    keep = sofa & ~blown
    if keep.any():
        seed[blown] = np.median(rgb[keep], axis=0)
    repaired = cv2.inpaint(seed, (blown.astype(np.uint8) * 255), 9, cv2.INPAINT_TELEA)
    rgb[blown] = repaired[blown]
    return Image.fromarray(np.dstack([rgb, alpha]), mode="RGBA")


def _kill_false_plate(rgb: np.ndarray, bg: Tuple[int, int, int], sofa_alpha: np.ndarray) -> np.ndarray:
    """Snap leftover cool-gray floor strips under the sofa — never beige fabric."""
    bg_arr = np.array(bg, dtype=np.uint8)
    h, w = sofa_alpha.shape
    ys, xs = np.where(sofa_alpha > 40)
    if xs.size == 0:
        return rgb
    y1 = int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y_from = max(0, y1 - 28)
    y_to = min(h, y1 + 36)
    r, g, b = rgb[:, :, 0].astype(np.int16), rgb[:, :, 1].astype(np.int16), rgb[:, :, 2].astype(np.int16)
    cool_gray = (np.abs(r - g) < 4) & (np.abs(g - b) < 5)
    lum = rgb.mean(axis=2)
    dist = np.abs(rgb.astype(np.int16) - bg_arr.astype(np.int16)).sum(axis=2)
    region = np.zeros((h, w), dtype=bool)
    region[y_from:y_to, x0:x1] = True
    plate = region & cool_gray & (lum > 200) & (dist > 3) & (sofa_alpha < 30)
    out = rgb.copy()
    out[plate] = bg_arr
    return out


def _under_contact_shadow_on_bg(
    canvas_rgb: np.ndarray,
    sofa_alpha: np.ndarray,
    bg: Tuple[int, int, int],
) -> np.ndarray:
    """Soft contact shade of the same #edece8 hue, following the feet — not a plate rectangle."""
    if ndimage is None:
        return canvas_rgb
    h, w = sofa_alpha.shape
    cover = sofa_alpha > 40
    if not cover.any():
        return canvas_rgb
    flipped = cover[::-1]
    bottom_y = h - 1 - np.argmax(flipped, axis=0)
    bottom_y = np.where(cover.any(axis=0), bottom_y, -10_000)
    yy = np.arange(h, dtype=np.float32)[:, None]
    dy = yy - bottom_y.astype(np.float32)[None, :]
    # Peak a few px below the silhouette, fade out — no hard horizontal lip.
    fall = np.exp(-0.5 * ((dy - 5.0) / 11.0) ** 2)
    fall = np.where(bottom_y[None, :] > 0, fall, 0.0)
    fall = ndimage.gaussian_filter(fall.astype(np.float32), sigma=3.5)
    k = np.clip(fall * 0.22 * (1.0 - sofa_alpha.astype(np.float32) / 255.0 * 0.95), 0.0, 0.20)
    bg_arr = np.array(bg, dtype=np.float32)
    darker = bg_arr * 0.82
    base = canvas_rgb.astype(np.float32)
    out = base * (1.0 - k[..., None]) + darker * k[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def _opaque_bbox(rgba: Image.Image, threshold: int = 48) -> Tuple[int, int, int, int] | None:
    alpha = np.array(rgba.split()[3])
    ys, xs = np.where(alpha > threshold)
    if xs.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _fit_to_canvas(rgba: Image.Image, width: int, height: int, bg: Tuple[int, int, int]) -> Image.Image:
    """Scale sofa to fill frame; place it in the optical center of the square (catalog studio)."""
    padding_x = int(width * 0.07)
    padding_y = int(height * 0.08)
    max_w = width - 2 * padding_x
    max_h = height - 2 * padding_y

    alpha = np.array(rgba.split()[3]).astype(np.float32) / 255.0
    rgba.putalpha(Image.fromarray((alpha * 255).astype(np.uint8), mode="L"))

    bbox = _opaque_bbox(rgba, threshold=28)
    if not bbox:
        return Image.new("RGB", (width, height), bg)

    x0, y0, x1, y1 = bbox
    pad = 6
    cropped = rgba.crop(
        (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(rgba.width, x1 + pad),
            min(rgba.height, y1 + pad),
        )
    )
    cw, ch = cropped.size
    scale = min(max_w / cw, max_h / ch)
    new_w = max(1, int(cw * scale))
    new_h = max(1, int(ch * scale))
    resized = cropped.resize((new_w, new_h), Image.BICUBIC)
    resized = _choke_smooth_alpha(resized, choke=3, sigma=1.2)

    x = (width - new_w) // 2
    spare = height - new_h
    y = int(spare * 0.55)
    y = max(int(height * 0.10), min(y, height - new_h - int(height * 0.12)))

    a_full = np.zeros((height, width), dtype=np.uint8)
    a_full[y : y + new_h, x : x + new_w] = np.array(resized.split()[3])

    canvas = np.full((height, width, 3), bg, dtype=np.uint8)
    canvas = _under_contact_shadow_on_bg(canvas, a_full, bg)
    canvas = _kill_false_plate(canvas, bg, a_full)

    base = Image.fromarray(canvas, mode="RGB").convert("RGBA")
    sofa_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sofa_layer.paste(resized, (x, y))
    composed = np.array(Image.alpha_composite(base, sofa_layer).convert("RGB"))
    # LANCZOS/BICUBIC ringing reads as a white overlay on ribbed cream fabric.
    lum = composed.mean(axis=2)
    if ndimage is not None:
        local = ndimage.median_filter(lum.astype(np.float32), size=9)
        over = lum > (local + 12)
        if over.any():
            gain = np.clip((local + 8) / np.maximum(lum, 1.0), 0.75, 1.0)
            composed = composed.astype(np.float32)
            composed[over] *= gain[over, None]
            composed = np.clip(composed, 0, 255).astype(np.uint8)
    lum = composed.mean(axis=2)
    chroma = composed.std(axis=2)
    bg_lum = float(np.mean(bg))
    glow = (lum > bg_lum + 3) & (chroma < 14) & (a_full < 90)
    hot = (lum >= 244) & (chroma < 14)
    if ndimage is not None and (a_full > 40).any():
        near_feet = ndimage.binary_dilation(a_full > 40, iterations=10)
        ys, xs = np.where(a_full > 40)
        y1 = int(ys.max()) + 1
        foot_band = np.zeros(a_full.shape, dtype=bool)
        foot_band[max(0, y1 - 22) : min(a_full.shape[0], y1 + 6), :] = True
        glow = (glow | (hot & foot_band)) & near_feet
    composed[glow] = np.array(bg, dtype=np.uint8)
    composed = _unify_studio_bg(composed, bg, a_full)
    composed = _under_contact_shadow_on_bg(composed, a_full, bg)
    composed = _kill_false_plate(composed, bg, a_full)
    composed = _unify_studio_bg(composed, bg, a_full)
    return Image.fromarray(composed, mode="RGB")


def _rgba_from_flat_studio(rgb: np.ndarray) -> Image.Image:
    """Alpha from a flat catalog plate (white or #edece8) without rembg.

    rembg on cream fabric vs beige studio eats arms/chaise and draws a stroke.
    """
    plate = np.median(np.concatenate([c.reshape(-1, 3) for c in _corner_patches(rgb)]), axis=0)
    lum = rgb.mean(axis=2)
    chroma = rgb.std(axis=2)
    dist = np.abs(rgb.astype(np.int16) - plate.astype(np.int16)).sum(axis=2)
    plate_like = dist < 16
    white_spill = (lum > 246) & (chroma < 10)
    sofa = ~plate_like & ~white_spill
    if ndimage is not None:
        labeled, num = ndimage.label(sofa)
        if num > 1:
            sizes = ndimage.sum(sofa, labeled, range(1, num + 1))
            sofa = labeled == (int(np.argmax(sizes)) + 1)
        # Drop only a thin cool-gray floor strip under the blob, not beige upholstery.
        ys, xs = np.where(sofa)
        if ys.size:
            y1 = int(ys.max()) + 1
            r, g, bch = rgb[:, :, 0].astype(np.int16), rgb[:, :, 1].astype(np.int16), rgb[:, :, 2].astype(np.int16)
            cool = (np.abs(r - g) < 4) & (np.abs(g - bch) < 5)
            strip = np.zeros_like(sofa)
            strip[max(0, y1 - 18) : min(sofa.shape[0], y1 + 8), :] = True
            sofa = sofa & ~(strip & cool & (lum > 200))
    alpha = (sofa.astype(np.uint8) * 255)
    out = Image.fromarray(rgb, mode="RGB").convert("RGBA")
    out.putalpha(Image.fromarray(alpha, mode="L"))
    return out


def process_cutout(
    image_bytes: bytes,
    width: int = 1920,
    height: int = 1920,
    quality: int = 95,
) -> Tuple[bytes, Dict[str, Any]]:
    """Remove background, clean mask, apply studio BG. Returns (webp bytes, meta)."""
    bg = _bg_color()
    input_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_rgb = np.array(input_img)
    studio_src = _is_white_studio(orig_rgb) or _is_neutral_studio(orig_rgb)

    if studio_src:
        rgba = _rgba_from_flat_studio(orig_rgb)
    else:
        if remove is None:
            raise RuntimeError("rembg not installed")
        buf_in = io.BytesIO()
        input_img.save(buf_in, format="PNG")
        output_bytes = remove(buf_in.getvalue())
        rgba = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

    alpha = np.array(rgba.split()[3])
    if studio_src:
        stripped = alpha
        drapery_lost = np.zeros_like(alpha, dtype=bool)
        skip_corner = True
    else:
        stripped = _strip_bright_edge_drapery(orig_rgb, alpha)
        drapery_lost = (alpha > 48) & (stripped <= 48)
        skip_corner = False
    cleaned_alpha, clean_meta = _clean_alpha_mask(
        stripped, strip_side_artifacts=not studio_src
    )
    rgba.putalpha(Image.fromarray(cleaned_alpha, mode="L"))
    rgba, repair_meta = _repair_drapery_bites(rgba, drapery_lost)
    if skip_corner:
        corner_meta = {"corner_inpainted": False, "needs_generate": False, "corner_ratio": 0.0}
    else:
        rgba, corner_meta = _fill_boxy_corner_bites(rgba)
    repair_meta = {**repair_meta, **corner_meta}
    repair_meta["needs_generate"] = bool(
        repair_meta.get("needs_generate") or corner_meta.get("needs_generate")
    )

    validation = validate_cutout_rgba(rgba, orig_rgb=orig_rgb)
    if repair_meta.get("needs_generate"):
        validation["valid"] = False
        validation["reason"] = "truncated_needs_generate"
    rgba = _defringe_rgba(rgba)
    rgba = _strip_bottom_white_halo(rgba)
    rgba = _heal_white_on_fabric(rgba)
    result = _fit_to_canvas(rgba, width, height, bg)

    buf_out = io.BytesIO()
    result.save(buf_out, format="WEBP", lossless=True, method=6)
    meta = {**clean_meta, **repair_meta, **validation}
    return buf_out.getvalue(), meta
