"""Ollama moondream — strict front-view sofa selection."""

from __future__ import annotations

import base64
import io
import os
import re
from typing import Any, Dict, Optional

import httpx
from PIL import Image

HARD_REJECT_KEYWORDS = (
    "overhead", "top-down", "top down", "from above", "looking down",
    "aerial", "bird", "high angle", "elevated",
    "lamp", "table", "chair", "stool", "pouf", "ottoman",
    "door", "shelf", "shelves", "cabinet",
    "profile", "side view", "close-up", "closeup",
)


def _ollama_config() -> tuple[str, str]:
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llava")
    return url, model


def check_ollama() -> Dict[str, Any]:
    url, model = _ollama_config()
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{url}/api/tags")
            r.raise_for_status()
            models = [m.get("name", "").split(":")[0] for m in r.json().get("models", [])]
            ok = any(model in m for m in models)
            return {"status": "ok" if ok else "model_missing", "model": model, "available": models}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def score_with_ollama(image_bytes: bytes) -> Dict[str, Any]:
    url, model = _ollama_config()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = (
        "Rate this furniture photo as a reference for generating a new catalog sofa shot.\n"
        "SCORE 100: one sofa, straight front view at eye level, full piece visible.\n"
        "SCORE 50: sofa visible but 3/4 angle or busy room.\n"
        "SCORE 0: overhead/top-down, armchair only, or no sofa.\n"
        "Reply exactly: SCORE: <number 0-100>. REASON: <one short sentence>."
    )

    payload = {"model": model, "prompt": prompt, "stream": False, "images": [b64]}

    try:
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{url}/api/generate", json=payload)
            r.raise_for_status()
            text = r.json().get("response", "").strip()
            score = _parse_score(text)
            low = text.lower()
            overhead = any(k in low for k in ("overhead", "above", "looking down", "top-down", "aerial", "from above"))
            clutter = _detect_clutter(low)
            reject = _should_reject(score, low, overhead, clutter)
            return {
                "ollama_score": score,
                "ollama_raw": text,
                "overhead": overhead,
                "clutter": clutter,
                "reject": reject,
            }
    except Exception as e:
        return {"ollama_score": None, "ollama_error": str(e), "reject": False}


def _parse_score(text: str) -> Optional[int]:
    low = text.lower()
    # Skip template echoes like "0-100"
    if re.search(r"0\s*[-–]\s*100", low) and not re.search(r"\b[1-9]\d?\b", text):
        return None
    # Prefer explicit SCORE: NN pattern from llava
    explicit = re.search(r"score\s*:\s*(\d{1,3})", low)
    if explicit:
        return max(0, min(100, int(explicit.group(1))))
    match = re.search(r"(?<![\d.])(\d{1,2}|100)(?![\d.])", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    return None


def _detect_clutter(low: str) -> bool:
    """Detect separate furniture clutter — ignore generic mentions at high scores."""
    phrases = (
        "side table", "coffee table", "floor lamp", "table lamp", "bedside lamp",
        "with a lamp", "with a table", "visible lamp", "visible table",
        "lamp visible", "table visible", "lamp on the", "table on the",
        "separate lamp", "separate table", "next to the sofa",
    )
    return any(p in low for p in phrases)


def _should_reject(
    score: Optional[int],
    low: str,
    overhead: bool,
    clutter: bool,
) -> bool:
    if score is not None and score >= 75:
        return False
    not_eye_level = any(
        p in low for p in ("not eye level", "not at eye level", "high angle", "looking down", "from above")
    )
    if not_eye_level and (score is None or score < 90):
        return True
    if clutter and (score is None or score < 65):
        return True
    if score is not None and score >= 70 and not overhead:
        return False
    if overhead and (score is None or score < 60):
        return True
    if score is not None and score < 45:
        return True
    if score is None:
        return any(kw in low for kw in HARD_REJECT_KEYWORDS)
    return False


def combined_score(
    heuristic: int,
    ollama: Optional[int],
    *,
    heuristic_reject: bool = False,
    ollama_weight: float = 0.45,
) -> int:
    if heuristic_reject:
        return 0
    if ollama is None:
        return heuristic
    combined = heuristic * (1 - ollama_weight) + ollama * ollama_weight
    return max(0, min(100, round(combined)))
