"""Vision scoring client — calls AI server."""

from __future__ import annotations

from typing import Any, Dict

import httpx

from .config import Config


def score_image(config: Config, image_bytes: bytes) -> Dict[str, Any]:
    url = f"{config.ai_server_url}/vision/score"
    headers = {"X-Api-Key": config.ai_server_api_key}
    files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

    with httpx.Client(timeout=180) as client:
        r = client.post(url, headers=headers, files=files)
        r.raise_for_status()
        return r.json()


def check_ai_server(config: Config) -> Dict[str, Any]:
    url = f"{config.ai_server_url}/health"
    with httpx.Client(timeout=10) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
