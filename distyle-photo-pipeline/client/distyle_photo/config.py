"""Configuration loaded from .env (project root or client dir)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load from project root .env first, then client/.env
_ROOT = Path(__file__).resolve().parents[2]  # distyle-photo-pipeline/
_CLIENT = Path(__file__).resolve().parents[1]  # client/
for p in [_ROOT / ".env", _CLIENT / ".env", _ROOT.parent / ".env"]:
    if p.exists():
        load_dotenv(p)


@dataclass
class Config:
    wc_url: str
    wc_consumer_key: str
    wc_consumer_secret: str
    wp_user: str
    wp_app_password: str
    ai_server_url: str
    ai_server_api_key: str
    vision_score_threshold: int
    category_id: int
    output_dir: Path
    backup_dir: Path
    output_width: int
    output_height: int
    bg_color: tuple[int, int, int]


def load_config() -> Config:
    return Config(
        wc_url=os.getenv("WC_URL", "https://distyle.lt").rstrip("/"),
        wc_consumer_key=os.getenv("WC_CONSUMER_KEY", ""),
        wc_consumer_secret=os.getenv("WC_CONSUMER_SECRET", ""),
        wp_user=os.getenv("WP_USER", ""),
        wp_app_password=os.getenv("WP_APP_PASSWORD", "").replace(" ", ""),
        ai_server_url=os.getenv("AI_SERVER_URL", "http://127.0.0.1:8765").rstrip("/"),
        ai_server_api_key=os.getenv("AI_SERVER_API_KEY", "local-test-key"),
        vision_score_threshold=int(os.getenv("VISION_SCORE_THRESHOLD", "70")),
        category_id=int(os.getenv("CATEGORY_ID", "21")),
        output_dir=Path(os.getenv("OUTPUT_DIR", "./output")),
        backup_dir=Path(os.getenv("BACKUP_DIR", "./backups")),
        output_width=int(os.getenv("OUTPUT_WIDTH", "1920")),
        output_height=int(os.getenv("OUTPUT_HEIGHT", "1920")),
        bg_color=(
            int(os.getenv("BG_COLOR_R", "237")),
            int(os.getenv("BG_COLOR_G", "236")),
            int(os.getenv("BG_COLOR_B", "232")),
        ),
    )
