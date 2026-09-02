"""Product filtering: skip sales, already standardized, small galleries."""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

STANDARD_BG = (237, 236, 232)
STANDARD_BG_HEX = "#edece8"
STANDARD_URL_MARKERS = ("DitreItalia_Sofas", "ditreitalia", "studio_sofa")


def is_on_sale(product: Dict[str, Any]) -> bool:
    if product.get("on_sale"):
        return True
    sale = product.get("sale_price")
    return bool(sale and str(sale).strip())


def is_already_standardized(product: Dict[str, Any]) -> bool:
    """Check if profile image already has Ditre Italia studio style."""
    images = product.get("images", [])
    if not images:
        return False

    featured = images[0]
    src = featured.get("src", "")
    alt = (featured.get("alt") or "").lower()
    name = (featured.get("name") or "").lower()

    for marker in STANDARD_URL_MARKERS:
        if marker.lower() in src.lower() or marker.lower() in alt or marker.lower() in name:
            return True

    # Check corner pixels for studio BG color (optional, requires download)
    return False


def check_bg_color_from_bytes(image_bytes: bytes, tolerance: int = 15) -> bool:
    """Sample corners — if all ≈ #edece8, image is likely already standardized."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        corners = [
            img.getpixel((2, 2)),
            img.getpixel((w - 3, 2)),
            img.getpixel((2, h - 3)),
            img.getpixel((w - 3, h - 3)),
        ]
        for r, g, b in corners:
            if (
                abs(r - STANDARD_BG[0]) > tolerance
                or abs(g - STANDARD_BG[1]) > tolerance
                or abs(b - STANDARD_BG[2]) > tolerance
            ):
                return False
        return True
    except Exception:
        return False


def gallery_too_small(product: Dict[str, Any], min_images: int = 2) -> bool:
    return len(product.get("images", [])) < min_images


def filter_product(
    product: Dict[str, Any],
    *,
    skip_on_sale: bool = True,
    non_standard_only: bool = True,
) -> Tuple[bool, Optional[str]]:
    """
    Returns (include, skip_reason).
    include=True means product is a candidate.
    """
    if skip_on_sale and is_on_sale(product):
        return False, "on_sale"

    if non_standard_only and is_already_standardized(product):
        return False, "already_standardized"

    if gallery_too_small(product):
        return False, "gallery_too_small"

    return True, None


def filter_products(
    products: List[Dict[str, Any]],
    *,
    skip_on_sale: bool = True,
    non_standard_only: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split into (candidates, skipped_with_reason)."""
    candidates = []
    skipped = []
    for p in products:
        ok, reason = filter_product(p, skip_on_sale=skip_on_sale, non_standard_only=non_standard_only)
        if ok:
            candidates.append(p)
        else:
            skipped.append({"id": p.get("id"), "name": p.get("name"), "skip_reason": reason})
    return candidates, skipped
