"""Extract highest-resolution image URL from WooCommerce src/srcset."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def best_image_url(image: Dict[str, Any]) -> str:
    """Pick largest resolution URL from WC image object."""
    src = image.get("src", "")
    srcset = image.get("srcset", "")

    if srcset:
        candidates = _parse_srcset(srcset)
        if candidates:
            return max(candidates, key=lambda x: x[0])[1]

    return src


def _parse_srcset(srcset: str) -> List[tuple[int, str]]:
    """Parse srcset string into (width, url) pairs."""
    results = []
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2:
            url = tokens[0]
            w_match = re.search(r"(\d+)w", tokens[1])
            if w_match:
                results.append((int(w_match.group(1)), url))
            else:
                results.append((0, url))
        elif len(tokens) == 1:
            results.append((0, tokens[0]))
    return results


def gallery_urls(product: Dict[str, Any], include_featured: bool = False) -> List[str]:
    """Return gallery image URLs (excluding featured unless requested)."""
    urls = []
    seen = set()

    if include_featured and product.get("images"):
        for img in product["images"][:1]:
            url = best_image_url(img)
            if url and url not in seen:
                urls.append(url)
                seen.add(url)

    # Gallery = all images except first (featured/profile)
    images = product.get("images", [])
    for img in images[1:] if len(images) > 1 else images:
        url = best_image_url(img)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    return urls
