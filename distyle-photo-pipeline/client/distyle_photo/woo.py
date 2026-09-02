"""WooCommerce REST API + WordPress media upload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import Config

USER_AGENT = "DiStyle-PhotoPipeline/1.0 (distyle.lt; +https://distyle.lt)"


class WooClient:
    def __init__(self, config: Config):
        self.config = config
        self.base = f"{config.wc_url}/wp-json/wc/v3"
        self.auth = (config.wc_consumer_key, config.wc_consumer_secret)
        self.headers = {"User-Agent": USER_AGENT}

    def _client(self, timeout: float = 60) -> httpx.Client:
        return httpx.Client(timeout=timeout, headers=self.headers, auth=self.auth)

    def health(self) -> Dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{self.base}/products", params={"per_page": 1})
            r.raise_for_status()
            return {"wc_api": "ok", "status": r.status_code}

    def test_wp_auth(self) -> Dict[str, Any]:
        """Verify WordPress Application Password works for media upload."""
        if not self.config.wp_user or not self.config.wp_app_password:
            return {
                "wp_auth": "missing",
                "hint": "Nustatyk WP_USER ir WP_APP_PASSWORD .env faile",
            }

        auth = (self.config.wp_user, self.config.wp_app_password)

        # Try media endpoint (what apply actually uses)
        media_url = f"{self.config.wc_url}/wp-json/wp/v2/media?per_page=1"
        try:
            with httpx.Client(timeout=30, headers=self.headers, auth=auth) as c:
                r = c.get(media_url)
                if r.status_code == 401:
                    return {
                        "wp_auth": "failed",
                        "status": 401,
                        "hint": (
                            "401 — WP_APP_PASSWORD neteisingas. "
                            "Sukurk Application Password: WP Admin -> Users -> Alanas -> "
                            "Application Passwords -> Add New. Irasyk i .env (be tarpu)."
                        ),
                    }
                if r.status_code == 403:
                    return {
                        "wp_auth": "blocked",
                        "status": 403,
                        "hint": (
                            "403 — REST API uzdraustas security pluginu arba vartotojas neturi teises. "
                            "Patikrink: Wordfence/iThemes/Interneto vizija REST API nustatymai. "
                            "Arba bandyk sukurti nauja Application Password."
                        ),
                    }
                if r.status_code == 200:
                    return {"wp_auth": "ok", "status": 200, "hint": None}
                return {"wp_auth": "unknown", "status": r.status_code, "body": r.text[:200]}
        except Exception as e:
            return {"wp_auth": "error", "error": str(e)}

    def get_products(
        self,
        *,
        category: Optional[int] = None,
        limit: int = 10,
        product_ids: Optional[List[int]] = None,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"per_page": min(limit, 100), "page": page, "status": "publish"}
        if category:
            params["category"] = category
        if product_ids:
            params["include"] = ",".join(str(i) for i in product_ids)
            params["per_page"] = len(product_ids)

        with self._client() as c:
            r = c.get(f"{self.base}/products", params=params)
            r.raise_for_status()
            return r.json()

    def get_products_in_category(
        self,
        category: int,
        *,
        max_pages: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch all published products in a WC category (paginated)."""
        all_products: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            batch = self.get_products(category=category, limit=100, page=page)
            if not batch:
                break
            all_products.extend(batch)
            if len(batch) < 100:
                break
        return all_products

    def get_product(self, product_id: int) -> Dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{self.base}/products/{product_id}")
            r.raise_for_status()
            return r.json()

    def download_image(self, url: str) -> bytes:
        with httpx.Client(timeout=60, headers=self.headers, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.content

    def upload_media(self, image_bytes: bytes, filename: str, mime: str = "image/webp") -> Dict[str, Any]:
        if not self.config.wp_user or not self.config.wp_app_password:
            raise ValueError(
                "WP_USER ir WP_APP_PASSWORD privalomi. "
                "WP_APP_PASSWORD = Application Password is WP Admin (ne login slaptazodis)."
            )

        url = f"{self.config.wc_url}/wp-json/wp/v2/media"
        auth = (self.config.wp_user, self.config.wp_app_password)
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime,
        }
        with httpx.Client(timeout=120, headers=headers, auth=auth) as c:
            r = c.post(url, content=image_bytes)
            if r.status_code == 401:
                raise PermissionError(
                    "401 Unauthorized — WP media upload nepavyko. "
                    "Sukurk Application Password: WP Admin -> Users -> Alanas -> Application Passwords -> Add New. "
                    "Irasyk i .env kaip WP_APP_PASSWORD (be tarpu)."
                )
            r.raise_for_status()
            return r.json()

    def update_product_images(self, product_id: int, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        with self._client() as c:
            r = c.put(f"{self.base}/products/{product_id}", json={"images": images})
            r.raise_for_status()
            return r.json()

    def backup_images(self, product: Dict[str, Any], backup_dir: Path) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        pid = product["id"]
        path = backup_dir / f"product_{pid}_images.json"
        data = {
            "id": pid,
            "name": product.get("name"),
            "images": product.get("images", []),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def build_new_images_list(
        self,
        product: Dict[str, Any],
        new_media: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        new_entry = {"id": new_media["id"], "src": new_media["source_url"]}
        existing = product.get("images", [])
        rest = [img for img in existing if img.get("id") != new_media["id"]]
        return [new_entry] + rest
