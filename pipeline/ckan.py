"""Thin client for the CKAN API used by open.toronto.ca.

Two ways to get data out of CKAN:
  1. ``package_show`` -> find the resource -> download its ``url`` (static files).
  2. ``datastore_search`` -> page through rows (resources with ``datastore_active``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import requests

from pipeline.config import CKAN_BASE_URL

log = logging.getLogger(__name__)

PAGE_SIZE = 32_000  # CKAN caps datastore_search at 32k rows per call


class CkanClient:
    def __init__(self, base_url: str = CKAN_BASE_URL, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "toronto-open-data-pipeline/1.0"

    def _get(self, action: str, **params) -> dict:
        resp = self.session.get(
            f"{self.base_url}/{action}", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"CKAN {action} failed: {payload.get('error')}")
        return payload["result"]

    def package_show(self, package_id: str) -> dict:
        return self._get("package_show", id=package_id)

    def find_resource(self, package_id: str, resource_name: str) -> dict:
        pkg = self.package_show(package_id)
        for res in pkg["resources"]:
            if res["name"] == resource_name:
                return res
        names = [r["name"] for r in pkg["resources"]]
        raise KeyError(
            f"resource {resource_name!r} not in package {package_id!r}; have {names}"
        )

    def download(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s -> %s", url, dest)
        with self.session.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        log.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
        return dest

    def iter_datastore(
        self, resource_id: str, page_size: int = PAGE_SIZE
    ) -> Iterator[dict]:
        """Yield every record of a datastore resource, paging with offset."""
        offset = 0
        while True:
            result = self._get(
                "datastore_search",
                resource_id=resource_id,
                limit=page_size,
                offset=offset,
            )
            records = result["records"]
            if not records:
                return
            yield from records
            offset += len(records)
            log.info(
                "datastore %s: %d / %d rows",
                resource_id[:8],
                offset,
                result.get("total", -1),
            )
            if offset >= result.get("total", 0):
                return
