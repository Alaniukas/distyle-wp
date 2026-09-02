"""CLI entry point for DiStyle photo pipeline."""

from __future__ import annotations

import json
import sys

import click

from .config import load_config
from .pipeline import run_pipeline, scan_products
from .vision import check_ai_server
from .woo import WooClient


@click.group()
def cli():
    """DiStyle photo pipeline — WooCommerce + Ollama + rembg."""
    pass


@cli.command()
def health():
    """Check WooCommerce API + AI server connectivity."""
    config = load_config()
    results = {}

    # WC
    try:
        woo = WooClient(config)
        results["woocommerce"] = woo.health()
    except Exception as e:
        results["woocommerce"] = {"wc_api": "error", "error": str(e)}

    # AI server
    try:
        results["ai_server"] = check_ai_server(config)
    except Exception as e:
        results["ai_server"] = {"status": "error", "error": str(e)}

    # WP upload auth
    try:
        woo = WooClient(config)
        results["wp_upload"] = woo.test_wp_auth()
    except Exception as e:
        results["wp_upload"] = {"wp_auth": "error", "error": str(e)}

    click.echo(json.dumps(results, indent=2))

    wc_ok = results.get("woocommerce", {}).get("wc_api") == "ok"
    ai_ok = results.get("ai_server", {}).get("status") == "ok"
    wp_ok = results.get("wp_upload", {}).get("wp_auth") == "ok"
    if not (wc_ok and ai_ok):
        sys.exit(1)
    if not wp_ok:
        click.echo("\nWARNING: WP upload auth neveikia — apply režimas nepavyks.", err=True)


@cli.command()
@click.option("--limit", default=10, help="Max products to show")
@click.option("--category", default=None, type=int, help="WC category ID")
def scan(limit, category):
    """List candidate products (no changes)."""
    config = load_config()
    cat = category if category is not None else config.category_id
    result = scan_products(limit=limit, category=cat, config=config)

    click.echo(f"\n=== Kandidatai (kategorija {cat}, limit {limit}) ===\n")
    for c in result["candidates"]:
        click.echo(f"  [{c['id']}] {c['name']} ({c['images']} nuotr.)")

    if result["skipped"]:
        click.echo(f"\n=== Praleista ({len(result['skipped'])}) ===")
        for s in result["skipped"][:10]:
            click.echo(f"  [{s['id']}] {s.get('name', '?')} — {s['skip_reason']}")
        if len(result["skipped"]) > 10:
            click.echo(f"  ... ir dar {len(result['skipped']) - 10}")

    click.echo(f"\nIš viso gauta: {result['total_fetched']}, kandidatų: {len(result['candidates'])}")


@cli.command()
@click.option("--apply", "apply_flag", is_flag=True, default=False, help="Tikras atnaujinimas svetainėje (default: dry-run)")
@click.option("--limit", default=10)
@click.option("--category", default=None, type=int, help="WC kategorija (default: CATEGORY_ID, sofoms=21)")
@click.option("--product-ids", default=None, help="Kableliais atskirti ID, pvz. 41617,41644")
@click.option("--random", "random_sample", is_flag=True, default=False, help="Atsitiktine tvarka is visos kategorijos")
@click.option("--skip-on-sale/--include-on-sale", default=True)
@click.option("--non-standard-only/--all", default=True)
@click.option("--skip-processed", is_flag=True, default=False)
def run(apply_flag, limit, category, product_ids, random_sample, skip_on_sale, non_standard_only, skip_processed):
    """Paleisti pipeline (dry-run arba apply). Tik sofos — naudok --category 21."""
    config = load_config()
    ids = None
    if product_ids:
        ids = [int(x.strip()) for x in product_ids.split(",") if x.strip()]

    is_apply = apply_flag
    is_dry = not is_apply

    if is_apply:
        if not config.wp_user or not config.wp_app_password:
            click.echo("ERROR: WP_USER ir WP_APP_PASSWORD reikalingi --apply režimui", err=True)
            sys.exit(1)
        click.echo("⚠️  APPLY režimas — keis distyle.lt produktų nuotraukas!")
    else:
        click.echo("DRY-RUN režimas — nieko nekeičia svetainėje.")

    result = run_pipeline(
        dry_run=is_dry,
        apply=is_apply,
        limit=limit,
        category=category,
        product_ids=ids,
        skip_on_sale=skip_on_sale,
        non_standard_only=non_standard_only,
        skip_processed=skip_processed,
        random_sample=random_sample,
        config=config,
    )

    _print_run_result(result)


@cli.command("preview-batch")
@click.option("--limit", default=2, show_default=True)
def preview_batch(limit):
    """Etapas 1: atsitiktines sofos, generate tik lokaliai (be WP)."""
    config = load_config()
    click.echo("ETAPAS 1 — preview, distyle.lt nekeiciama")

    result = run_pipeline(
        dry_run=True,
        apply=False,
        limit=limit,
        category=21,
        skip_on_sale=True,
        non_standard_only=True,
        skip_processed=False,
        random_sample=True,
        preview_report=True,
        config=config,
    )
    _print_run_result(result, stage=1)


@cli.command("test-batch")
@click.option("--limit", default=10, show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-processed/--include-processed", default=True, show_default=True)
def test_batch(limit, dry_run, skip_processed):
    """Etapas 2: 10 atsitiktiniu sofu + apply i WP (po preview-batch)."""
    config = load_config()
    if not dry_run:
        if not config.wp_user or not config.wp_app_password:
            click.echo("ERROR: WP_USER ir WP_APP_PASSWORD reikalingi apply režimui", err=True)
            sys.exit(1)
        click.echo("ETAPAS 2 — 10 sofu, keis distyle.lt profilio nuotraukas!")
    else:
        click.echo("TEST-BATCH dry-run — nieko nekeicia WP.")

    result = run_pipeline(
        dry_run=dry_run,
        apply=not dry_run,
        limit=limit,
        category=21,
        skip_on_sale=True,
        non_standard_only=True,
        skip_processed=skip_processed,
        random_sample=True,
        config=config,
    )
    _print_run_result(result, stage=2 if not dry_run else None)


@cli.command("batch-all")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-processed/--include-processed", default=True, show_default=True)
def batch_all(dry_run, skip_processed):
    """Etapas 3: visos sofos (kategorija 21) + apply i WP (po test-batch)."""
    config = load_config()
    if not dry_run:
        if not config.wp_user or not config.wp_app_password:
            click.echo("ERROR: WP_USER ir WP_APP_PASSWORD reikalingi apply režimui", err=True)
            sys.exit(1)
        click.echo("ETAPAS 3 — visos sofos, keis distyle.lt!")
    else:
        click.echo("BATCH-ALL dry-run — nieko nekeicia WP.")

    result = run_pipeline(
        dry_run=dry_run,
        apply=not dry_run,
        limit=10_000,
        category=21,
        skip_on_sale=True,
        non_standard_only=True,
        skip_processed=skip_processed,
        random_sample=False,
        fetch_all=True,
        config=config,
    )
    _print_run_result(result, stage=3 if not dry_run else None)


def _print_run_result(result: dict, stage: int | None = None) -> None:
    click.echo(f"\n=== Rezultatai (run {result['run_id']}) ===\n")
    for r in result["results"]:
        status = r.get("status", "?")
        pid = r.get("product_id")
        name = r.get("name", "")
        score = r.get("vision_score", "-")
        out = r.get("output_file", "")
        jpg = r.get("preview_jpg", "")
        link = r.get("permalink", "")
        click.echo(f"  [{pid}] {name[:50]} — {status} (score={score}) {r.get('method', '')}")
        if link:
            click.echo(f"         puslapis: {link}")
        if jpg:
            click.echo(f"         perziurai: {jpg}")
        elif out:
            click.echo(f"         → {out}")
        if r.get("error"):
            click.echo(f"         ERROR: {r['error']}")

    click.echo(f"\nCSV: {result['csv']}")
    if result.get("preview_report"):
        click.echo(f"Preview ataskaita: {result['preview_report']}")
    click.echo(f"Apdorota: {result['processed']}, praleista filtru: {len(result['skipped_filter'])}")

    if stage == 1:
        click.echo("\n>>> Jei nuotraukos OK: python -m distyle_photo test-batch")
    elif stage == 2:
        click.echo("\n>>> Jei 10 sofu OK: python -m distyle_photo batch-all")
    elif stage == 3:
        click.echo("\n>>> Baigta. Galima Stop RunPod GPU.")


if __name__ == "__main__":
    cli()
