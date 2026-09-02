"""Generate client — calls AI server /generate."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import Config


def process_generate(
    config: Config,
    image_bytes: bytes,
    extra_refs: Optional[List[bytes]] = None,
    width: int | None = None,
    height: int | None = None,
    quality: int = 95,
    product_id: int | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    url = f"{config.ai_server_url}/generate"
    headers = {"X-Api-Key": config.ai_server_api_key}
    params = {
        "width": width or config.output_width,
        "height": height or config.output_height,
        "quality": quality,
    }
    if product_id:
        params["product_id"] = product_id
    files = [("file", ("image.jpg", image_bytes, "image/jpeg"))]
    for i, ref in enumerate((extra_refs or [])[:2]):
        files.append(("refs", (f"ref_{i}.jpg", ref, "image/jpeg")))

    with httpx.Client(timeout=300) as client:
        r = client.post(url, headers=headers, files=files, params=params)
        r.raise_for_status()
        data = r.json()
        webp = base64.b64decode(data["webp_b64"])
        meta = data.get("meta", {})
        meta["valid"] = data.get("valid", True)
        meta["method"] = "generate"
        return webp, meta
