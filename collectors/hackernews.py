#!/usr/bin/env python3
"""
Hacker News collector via the free Algolia search API. RTO / hybrid discourse.
No key required. Docs: https://hn.algolia.com/api

  parse(payload, source) -> list[raw_item]   pure (payload is a decoded dict)
  fetch(source)          -> list[dict]       one Algolia response per query
  collect(source)        -> list[raw_item]
"""
import urllib.parse

import common

API = "https://hn.algolia.com/api/v1/search_by_date"


def parse(payload, source):
    sid = source["id"]
    lane = source.get("lane", "question")
    min_points = (source.get("config") or {}).get("min_points", 0)
    items = []
    for h in (payload or {}).get("hits", []):
        points = h.get("points") or 0
        if points < min_points:
            continue
        oid = h.get("objectID")
        if not oid:
            continue
        title = h.get("title") or h.get("story_title") or ""
        url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
        items.append({
            "source_id": sid,
            "lane": lane,
            "native_id": oid,
            "url": url,
            "title": title,
            "text": common.strip_html(h.get("story_text") or h.get("comment_text") or ""),
            "published_at": common.iso_or_none(h.get("created_at") or h.get("created_at_i")),
            "author_role_hint": None,
            "geo_hint": None,
            "engagement": {"score": points, "comments": h.get("num_comments") or 0},
        })
    return items


def fetch(source):
    cfg = source.get("config") or {}
    queries = cfg.get("queries") or []
    hits_per = cfg.get("hits_per_page", 50)
    out = []
    for q in queries:
        params = urllib.parse.urlencode({
            "query": q, "tags": "story", "hitsPerPage": hits_per,
        })
        payload = common.get_json(f"{API}?{params}")
        if payload:
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
