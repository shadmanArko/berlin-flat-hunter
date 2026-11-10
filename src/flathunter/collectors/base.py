"""Collector contract (SPEC §7): idempotent, time-bounded, raises typed errors, never
silently returns empty when items are expected."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Collection
from typing import ClassVar

import httpx

from flathunter.core.schema import FetchError, RawListing

USER_AGENT = "flathunter-personal/0.1 (private household flat search; polite, rate-limited)"


class Collector:
    source_id: ClassVar[str]
    name: ClassVar[str]
    tier: ClassVar[int] = 1
    #: True when one fetch() covers the full listing set (enables gone-detection).
    complete_crawl: ClassVar[bool] = False
    min_delay_s: ClassVar[float] = 2.0

    def __init__(self, client: httpx.AsyncClient | None = None, *, max_pages: int | None = None) -> None:
        self._own_client = client is None
        self.client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"},
            timeout=20.0,
            follow_redirects=True,
            http2=False,
        )
        self.max_pages = max_pages
        self.http_status: int | None = None
        self.requests = 0

    async def get(self, url: str, *, params: dict[str, str] | None = None) -> str:
        if self.requests:
            await asyncio.sleep(self.min_delay_s * random.uniform(0.8, 1.2))
        self.requests += 1
        try:
            resp = await self.client.get(url, params=params)
        except httpx.HTTPError as e:
            raise FetchError(f"{self.source_id}: {type(e).__name__} fetching {url}: {e}") from e
        self.http_status = resp.status_code
        if resp.status_code != 200:
            raise FetchError(f"{self.source_id}: HTTP {resp.status_code} for {url}")
        return resp.text

    async def fetch(self, known_ids: Collection[str] = ()) -> list[RawListing]:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None:
        if self._own_client:
            await self.client.aclose()
