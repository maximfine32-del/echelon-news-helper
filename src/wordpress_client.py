from __future__ import annotations

import base64
import mimetypes
from typing import Any

import httpx

from .config import WordPressSiteConfig


class WordPressClient:
    """Helper that wraps the WordPress REST API."""

    def __init__(self, site: WordPressSiteConfig):
        self.site = site
        auth_bytes = f"{site.username}:{site.application_password}".encode()
        self._auth_header = base64.b64encode(auth_bytes).decode()
        self._client = httpx.AsyncClient(base_url=site.base_url, timeout=15.0)

    async def __aenter__(self) -> "WordPressClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def upload_media(self, filename: str, data: bytes) -> int:
        """Upload an attachment and return the media ID."""
        mime_type, _ = mimetypes.guess_type(filename)
        headers = {
            "Authorization": f"Basic {self._auth_header}",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type or "image/jpeg",
        }
        response = await self._client.post(
            "/wp-json/wp/v2/media",
            headers=headers,
            content=data,
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return int(payload["id"])

    async def create_post(
        self,
        title: str,
        excerpt: str,
        content: str,
        featured_media: int | None = None,
    ) -> dict[str, Any]:
        """Create the post in the 'Новости' rubric."""
        headers = {"Authorization": f"Basic {self._auth_header}"}
        payload = {
            "title": title,
            "excerpt": excerpt,
            "content": content,
            "status": "publish",
            "categories": [self.site.news_category_id],
        }
        if featured_media:
            payload["featured_media"] = featured_media

        response = await self._client.post("/wp-json/wp/v2/posts", headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()

