"""Main pipeline: scan → review gallery → generate studio shot → dry-run/apply."""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from .config import Config, load_config
from .generate import process_generate
from .image_urls import gallery_urls
from .selectors import filter_products
from .vision import score_image
from .woo import WooClient

_SKIP_REF_URL = ("armchair", "fotel", "easy-chair", "easychair")
_SOFA_SKIP_NAME = ("fotel", "armchair", "pufas", "pouf", "ottoman", "chair", "kėdė")


def _processed_marker(backup_dir: Path, product_id: int) -> Path:
    return backup_dir / f"product_{product_id}_processed.json"


def is_already_processed(backup_dir: Path, product_id: int) -> bool:
    return _processed_marker(backup_dir, product_id).exists()


def mark_processed(backup_dir: Path, product_id: int, meta: Dict[str, Any]) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = _processed_marker(backup_dir, product_id)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _is_sofa_product(product: Dict[str, Any]) -> bool:
    """Extra guard: category 21 + name must look like a sofa, not pouf/chair."""
    name = (product.get("name") or "").lower()
    if "sofa" in name or "sofą" in name or "sofa-" in name.replace(" ", "-"):
        return True
    return not any(x in name for x in _SOFA_SKIP_NAME)


def _skip_ref_url(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _SKIP_REF_URL)


def _save_studio_outputs(output_dir: Path, pid: int, studio_bytes: bytes) -> Dict[str, str]:
    """Write WebP + JPEG preview for easy review."""
    webp_path = output_dir / f"product_{pid}_studio.webp"
    jpg_path = output_dir / f"product_{pid}_studio.jpg"
    webp_path.write_bytes(studio_bytes)
    img = Image.open(BytesIO(studio_bytes)).convert("RGB")
    img.save(jpg_path, "JPEG", quality=95)
    return {"webp": str(webp_path), "jpg": str(jpg_path)}


def _write_preview_report(output_dir: Path, run_id: str, results: List[Dict[str, Any]]) -> Path:
    path = output_dir / f"preview_{run_id}.md"
    lines = [
        f"# Preview batch {run_id}",
        "",
        "Perziurek sugeneruotus JPG. Jei OK — paleisk **etapa 2**: `python -m distyle_photo test-batch`",
        "",
    ]
    for r in results:
        if r.get("status") not in ("dry_run", "applied"):
            continue
        lines.extend(
            [
                f"## [{r.get('product_id')}] {r.get('name', '')}",
                "",
                f"- Puslapis: {r.get('permalink', '')}",
                f"- Reference: {r.get('selected_url', '')}",
                f"- Studio JPG: `{r.get('preview_jpg', r.get('output_file', ''))}`",
                f"- Studio WebP: `{r.get('output_file', '')}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def select_best_gallery_image(
    woo: WooClient,
    config: Config,
    product: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Review every gallery photo, then generate one new studio catalog frame.
    Never rembg / crop — cutout eats seams, piping, and light fabric.
    """
    urls = gallery_urls(product, include_featured=True)
    downloaded: List[Dict[str, Any]] = []
    for url in urls:
        if _skip_ref_url(url):
            continue
        try:
            data = woo.download_image(url)
        except Exception:
            continue
        downloaded.append({"url": url, "image_bytes": data})

    if not downloaded:
        return None

    for entry in downloaded:
        try:
            scored = score_image(config, entry["image_bytes"])
            entry["score"] = 0 if scored.get("reject") else int(scored.get("score") or 0)
        except Exception:
            entry["score"] = 40

    downloaded.sort(key=lambda e: (e["score"], len(e["image_bytes"])), reverse=True)
    if downloaded[0]["score"] <= 0:
        downloaded.sort(key=lambda e: len(e["image_bytes"]), reverse=True)

    ref = downloaded[0]
    extras = [e["image_bytes"] for e in downloaded[1:3]]
    webp_bytes, gen_meta = process_generate(
        config,
        ref["image_bytes"],
        extra_refs=extras,
        product_id=int(product["id"]),
    )
    return {
        "url": ref["url"],
        "score": ref["score"],
        "details": {"path": "generate"},
        "image_bytes": ref["image_bytes"],
        "studio_bytes": webp_bytes,
        "cutout_meta": gen_meta,
    }


def run_pipeline(
    *,
    dry_run: bool = True,
    apply: bool = False,
    limit: int = 10,
    category: Optional[int] = None,
    product_ids: Optional[List[int]] = None,
    skip_on_sale: bool = True,
    non_standard_only: bool = True,
    skip_processed: bool = False,
    random_sample: bool = False,
    preview_report: bool = False,
    fetch_all: bool = False,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    config = config or load_config()
    woo = WooClient(config)

    output_dir = config.output_dir
    backup_dir = config.backup_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    category = category if category is not None else config.category_id

    if product_ids:
        products = woo.get_products(product_ids=product_ids)
    elif fetch_all or random_sample:
        products = woo.get_products_in_category(category)
    else:
        fetch_limit = max(limit * 10, 100)
        products = woo.get_products(category=category, limit=fetch_limit)

    candidates, skipped = filter_products(
        products, skip_on_sale=skip_on_sale, non_standard_only=non_standard_only
    )
    candidates = [p for p in candidates if _is_sofa_product(p)]

    if skip_processed:
        candidates = [p for p in candidates if not is_already_processed(backup_dir, p["id"])]

    if random_sample:
        random.shuffle(candidates)

    candidates = candidates[:limit]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"run_{run_id}.csv"
    results: List[Dict[str, Any]] = []

    for product in candidates:
        pid = product["id"]
        name = product.get("name", "")
        row: Dict[str, Any] = {
            "product_id": pid,
            "name": name,
            "permalink": product.get("permalink", ""),
            "status": "pending",
        }

        try:
            best = select_best_gallery_image(woo, config, product)
            if not best:
                row["status"] = "no_suitable_image"
                results.append(row)
                continue

            row["selected_url"] = best["url"]
            row["vision_score"] = best["score"]
            if best.get("cutout_meta"):
                row["cutout_valid"] = best["cutout_meta"].get("valid")
                row["cutout_reason"] = best["cutout_meta"].get("reason", "")
                row["method"] = best["cutout_meta"].get("method", "")

            studio_bytes = best.get("studio_bytes")
            if not studio_bytes:
                raise RuntimeError("generate returned no studio_bytes")

            paths = _save_studio_outputs(output_dir, pid, studio_bytes)
            row["output_file"] = paths["webp"]
            row["preview_jpg"] = paths["jpg"]

            if apply and not dry_run:
                woo.backup_images(product, backup_dir)
                media = woo.upload_media(studio_bytes, f"product_{pid}_studio.webp")
                new_images = woo.build_new_images_list(product, media)
                woo.update_product_images(pid, new_images)
                mark_processed(backup_dir, pid, {
                    "product_id": pid,
                    "media_id": media["id"],
                    "applied_at": run_id,
                })
                row["status"] = "applied"
                row["media_id"] = media["id"]
            else:
                row["status"] = "dry_run"

        except Exception as e:
            row["status"] = "error"
            row["error"] = str(e)

        results.append(row)

    if results:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sorted({k for r in results for k in r.keys()}))
            writer.writeheader()
            writer.writerows(results)

    report_path: Optional[Path] = None
    if preview_report and results:
        report_path = _write_preview_report(output_dir, run_id, results)

    return {
        "run_id": run_id,
        "csv": str(csv_path),
        "preview_report": str(report_path) if report_path else None,
        "processed": len(results),
        "skipped_filter": skipped,
        "results": results,
    }


def scan_products(
    *,
    limit: int = 10,
    category: Optional[int] = None,
    skip_on_sale: bool = True,
    non_standard_only: bool = True,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    config = config or load_config()
    woo = WooClient(config)
    category = category if category is not None else config.category_id

    products = woo.get_products(category=category, limit=limit * 3)
    candidates, skipped = filter_products(
        products, skip_on_sale=skip_on_sale, non_standard_only=non_standard_only
    )
    return {
        "candidates": [{"id": p["id"], "name": p.get("name"), "images": len(p.get("images", []))} for p in candidates[:limit]],
        "skipped": skipped,
        "total_fetched": len(products),
    }
