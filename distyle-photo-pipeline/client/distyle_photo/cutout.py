"""Cutout client — calls AI server."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import httpx

from .config import Config


def process_cutout(
    config: Config,
    image_bytes: bytes,
    width: int | None = None,
    height: int | None = None,
    quality: int = 95,
) -> Tuple[bytes, Dict[str, Any]]:
    """Run cutout and return (webp bytes, validation meta)."""
    url = f"{config.ai_server_url}/cutout"
    headers = {"X-Api-Key": config.ai_server_api_key}
    params = {
        "width": width or config.output_width,
        "height": height or config.output_height,
        "quality": quality,
        "meta": "true",
    }
    files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

    with httpx.Client(timeout=300) as client:
        r = client.post(url, headers=headers, files=files, params=params)
        r.raise_for_status()
        data = r.json()
        import base64
        webp = base64.b64decode(data["webp_b64"])
        meta = data.get("meta", {})
        meta["valid"] = data.get("valid", meta.get("valid", False))
        return webp, meta
