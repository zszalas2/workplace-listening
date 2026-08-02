#!/usr/bin/env python3
"""
Reddit collector via the Arctic Shift API (a public Pushshift-style mirror).
Endpoint: https://arctic-shift.photon-reddit.com/api/posts/search

Arctic Shift rate-limits aggressively, so full-text queries are bounded by a
date range (config.lookback_days) and spaced out with a short sleep. It returns
Reddit post objects under a top-level "data" key.

  parse(payload, source) -> list[raw_item]   pure (payload is a decoded dict/list)
  fetch(source)          -> list[dict]       one response per query (network)
  collect(source)        -> list[raw_item]
"""
import threading
import time
import urllib.parse
from datetime import date, timedelta

import common

API = "https://arctic-shift.photon-reddit.com/api/posts/search"

# Arctic Shift rate-limits aggressively and run.py collects sources concurrently,
# so all subreddit collectors would otherwise hit the API in parallel and get
# HTTP 429. This module-level lock + minimum spacing serializes every Arctic
# Shift request across threads, turning the fan-out into a polite single stream.
_LOCK = threading.Lock()
_last_request = [0.0]
_MIN_INTERVAL = 2.0  # seconds between any two Arctic Shift requests, globally


def _throttled_get_json(url):
    with _LOCK:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return common.get_json(url, retries=3)
        finally:
            _last_request[0] = time.monotonic()


def parse(payload, source):
    sid = source["id"]
    lane = source.get("lane", "question")
    cfg = source.get("config") or {}
    min_comments = cfg.get("min_comments", 0)
    subreddit = cfg.get("subreddit", "")
    # Response may be {"data": [...]} or a bare list.
    rows = payload.get("data") if isinstance(payload, dict) else payload
    items = []
    for p in rows or []:
        pid = p.get("id")
        if not pid:
            continue
        comments = p.get("num_comments") or 0
        if comments < min_comments:
            continue
        permalink = p.get("permalink") or ""
        url = ("https://www.reddit.com" + permalink) if permalink.startswith("/") else (p.get("url") or "")
        items.append({
            "source_id": sid,
            "lane": lane,
            "native_id": pid,
            "url": url,
            "title": p.get("title") or "",
            "text": common.strip_html(p.get("selftext") or ""),
            "published_at": common.iso_or_none(p.get("created_utc")),
            "author_role_hint": f"r/{subreddit}" if subreddit else None,
            "geo_hint": cfg.get("geo_hint"),
            "engagement": {"comments": comments, "score": p.get("score") or 0},
        })
    return items


def fetch(source):
    cfg = source.get("config") or {}
    subreddit = cfg.get("subreddit")
    queries = cfg.get("queries") or [""]
    limit = cfg.get("limit", 100)
    lookback = cfg.get("lookback_days", 60)
    after = (date.today() - timedelta(days=lookback)).isoformat()
    out = []
    for q in queries:
        params = {"subreddit": subreddit, "limit": limit, "after": after}
        if q:
            params["query"] = q
        url = f"{API}?{urllib.parse.urlencode(params)}"
        payload = _throttled_get_json(url)
        if payload is not None:
            out.append(payload)
    return out


def collect(source):
    seen = set()
    out = []
    for payload in fetch(source):
        for item in parse(payload, source):
            if item["native_id"] in seen:
                continue
            seen.add(item["native_id"])
            out.append(item)
    return out
