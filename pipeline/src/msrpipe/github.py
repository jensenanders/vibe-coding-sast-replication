"""Minimal GitHub REST/GraphQL client (stdlib only) with rate-limit handling."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHub:
    def __init__(self, token=None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise SystemExit("GITHUB_TOKEN is not set (export it in the host shell).")
        self._last = {}

    def _pace(self, kind, min_interval):
        wait = self._last.get(kind, 0) + min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last[kind] = time.time()

    def _send(self, kind, url, min_interval, payload=None):
        """One request with retries. Returns (status, body); body is None for HTTP 422."""
        data = json.dumps(payload).encode() if payload is not None else None
        for attempt in range(1, 9):
            self._pace(kind, min_interval)
            req = urllib.request.Request(url, data=data, headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "msr-paper-pipeline",
            })
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.status, json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code == 422:          # e.g. page beyond the 1,000-result cap
                    return 422, None
                if e.code in (403, 429):   # rate limit: wait for reset or retry-after
                    retry_after = e.headers.get("Retry-After")
                    reset = e.headers.get("X-RateLimit-Reset")
                    if retry_after:
                        wait = int(retry_after) + 1
                    elif reset:
                        wait = max(int(reset) - time.time(), 0) + 2
                    else:
                        wait = 60 * attempt
                    print(f"    rate limit ({e.code}), waiting {int(wait)}s (attempt {attempt}/8)")
                    time.sleep(wait)
                    continue
                if e.code >= 500:
                    time.sleep(10 * attempt)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                time.sleep(10 * attempt)
        raise RuntimeError(f"giving up after 8 attempts: {kind} {url}")

    def search(self, kind, q, page, per_page, min_interval):
        """GET /search/<kind>. Returns (status, body); body is None for HTTP 422."""
        params = urllib.parse.urlencode({"q": q, "per_page": per_page, "page": page})
        return self._send(kind, f"{API}/search/{kind}?{params}", min_interval)

    def graphql(self, query, min_interval):
        """POST /graphql. Retries when GraphQL itself reports RATE_LIMITED (HTTP 200)."""
        for attempt in range(1, 9):
            status, body = self._send("graphql", f"{API}/graphql", min_interval, {"query": query})
            if not any(e.get("type") == "RATE_LIMITED" for e in (body or {}).get("errors", [])):
                return status, body
            print(f"    graphql RATE_LIMITED, waiting 60s (attempt {attempt}/8)")
            time.sleep(60)
        raise RuntimeError("giving up after 8 RATE_LIMITED responses from /graphql")
