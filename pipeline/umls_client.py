"""UMLS REST API client with disk-cached responses and exponential-backoff retries."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


BASE = "https://uts-ws.nlm.nih.gov/rest"


class _RateLimiter:
    """Token-bucket style limiter — caps requests per second."""

    def __init__(self, max_per_sec: float = 15.0) -> None:
        self.min_interval = 1.0 / max_per_sec
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


class UMLSClient:
    """Thin wrapper over the UMLS REST API with on-disk caching."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: str | Path = "cache",
        max_per_sec: float = 15.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("UMLS_API_KEY")
        if not self.api_key:
            raise RuntimeError("UMLS_API_KEY not set")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "verisim-vdb/0.1"})
        self.limiter = _RateLimiter(max_per_sec)
        self.cache_hits = 0
        self.api_calls = 0

    # ---------- internals ----------

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h[:2]}" / f"{h}.json"

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((requests.RequestException, ValueError)),
        reraise=True,
    )
    def _fetch(self, url: str) -> Any:
        self.limiter.wait()
        resp = self.session.get(url, timeout=90)
        if resp.status_code == 404:
            return None  # not found is a stable outcome — cache it
        if resp.status_code in (429, 500, 502, 503, 504):
            raise requests.RequestException(f"transient {resp.status_code}")
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as e:
            raise ValueError(f"non-json from {url}: {resp.text[:200]}") from e

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        params = dict(params or {})
        params["apiKey"] = self.api_key
        # ensure deterministic url for caching
        qs = urlencode(sorted(params.items()), doseq=True)
        full = f"{BASE}{path}?{qs}"
        cache_path = self._cache_path(full)
        if cache_path.exists():
            self.cache_hits += 1
            try:
                with open(cache_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                cache_path.unlink(missing_ok=True)
        data = self._fetch(full)
        self.api_calls += 1
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f)
        tmp.rename(cache_path)
        return data

    # ---------- public ----------

    def search(
        self,
        query: str,
        sabs: Optional[Iterable[str]] = None,
        semantic_types: Optional[Iterable[str]] = None,
        return_id_type: str = "concept",
        search_type: str = "words",
        page_size: int = 25,
        page_number: int = 1,
    ) -> dict:
        params: dict = {
            "string": query,
            "returnIdType": return_id_type,
            "searchType": search_type,
            "pageSize": page_size,
            "pageNumber": page_number,
        }
        if sabs:
            params["sabs"] = ",".join(sabs)
        if semantic_types:
            params["semanticTypes"] = ",".join(semantic_types)
        data = self._get("/search/current", params)
        return data or {}

    def _paginate(self, path: str, params: dict, max_pages: int) -> list[dict]:
        """Generic paginator. The UMLS `pageCount` field is unreliable on
        /descendants (returns 1 even when more pages exist), so we ignore it
        and break only when a page returns empty results or we hit max_pages.
        Exceptions on a single page (timeouts, 5xx after retry) abort the
        loop but the previously-collected results are returned — partial
        progress beats losing everything."""
        results: list[dict] = []
        page = 1
        last_len: int | None = None
        while page <= max_pages:
            p = dict(params)
            p["pageNumber"] = page
            try:
                data = self._get(path, p)
            except Exception:
                # log via caller — return what we have so caller can continue
                break
            if not data:
                break
            page_results = data.get("result") or []
            if not page_results:
                break
            results.extend(page_results)
            if last_len is not None and len(page_results) < last_len:
                break
            last_len = len(page_results)
            page += 1
        return results

    def get_atoms(
        self,
        cui: str,
        sabs: Optional[Iterable[str]] = None,
        ttys: Optional[Iterable[str]] = None,
        language: str = "ENG",
        page_size: int = 100,
        max_pages: int = 6,
    ) -> list[dict]:
        params: dict = {"language": language, "pageSize": page_size}
        if sabs:
            params["sabs"] = ",".join(sabs)
        if ttys:
            params["ttys"] = ",".join(ttys)
        return self._paginate(f"/content/current/CUI/{cui}/atoms", params, max_pages)

    def get_relations(
        self,
        cui: str,
        sabs: Optional[Iterable[str]] = None,
        include_rela: Optional[Iterable[str]] = None,
        page_size: int = 100,
        max_pages: int = 3,
    ) -> list[dict]:
        """Relations endpoint caps pageSize ~20 server-side; max_pages caps total
        relations pulled (we only need representative RELA buckets, not all)."""
        params: dict = {"pageSize": page_size}
        if sabs:
            params["sabs"] = ",".join(sabs)
        if include_rela:
            params["includeRelationLabels"] = ",".join(include_rela)
        return self._paginate(f"/content/current/CUI/{cui}/relations", params, max_pages)

    def get_definitions(self, cui: str) -> list[dict]:
        data = self._get(f"/content/current/CUI/{cui}/definitions", {})
        if not data:
            return []
        return data.get("result") or []

    def get_source_attributes(self, sab: str, code: str) -> list[dict]:
        data = self._get(f"/content/current/source/{sab}/{code}/attributes", {})
        if not data:
            return []
        return data.get("result") or []

    def get_source_atoms(
        self,
        sab: str,
        code: str,
        page_size: int = 50,
        max_pages: int = 1,
        language: str = "ENG",
    ) -> list[dict]:
        """Atoms for a source-vocab code. Each result includes a `concept` URL
        whose last path segment is the CUI — useful for code→CUI lookups."""
        params = {"language": language, "pageSize": page_size}
        return self._paginate(f"/content/current/source/{sab}/{code}/atoms", params, max_pages)

    def get_source_children(
        self,
        sab: str,
        code: str,
        page_size: int = 100,
        max_pages: int = 3,
    ) -> list[dict]:
        params = {"pageSize": page_size}
        return self._paginate(f"/content/current/source/{sab}/{code}/children", params, max_pages)

    def get_source_descendants(
        self,
        sab: str,
        code: str,
        page_size: int = 100,
        max_pages: int = 30,
    ) -> list[dict]:
        params = {"pageSize": page_size}
        return self._paginate(f"/content/current/source/{sab}/{code}/descendants", params, max_pages)

    def crosswalk(self, sab: str, code: str, target_sab: str) -> list[dict]:
        params = {"targetSource": target_sab}
        data = self._get(f"/crosswalk/current/source/{sab}/{code}", params)
        if not data:
            return []
        return data.get("result") or []

    def stats(self) -> dict:
        return {"api_calls": self.api_calls, "cache_hits": self.cache_hits}
