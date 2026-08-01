#!/usr/bin/env python3
"""
Spiceworks Community collector. The community runs Discourse, whose public
search endpoint returns JSON at /search.json?q=<term>. We join returned posts to
their topics so each item carries a title, url, and a blurb of body text.

  parse(payload, source) -> list[raw_item]   pure (payload is a decoded dict)
  fetch(source)          -> list[dict]       one search response per query
  collect(source)        -> list[raw_item]
"""
import urllib.parse

import common


def parse(payload, source):
    sid = source["id"]
    lane = source.get("lane", "question")
    base = (source.get("config") or {}).get("base", "https://community.spiceworks.com").rstrip("/")
    payload = payload or {}
    topics = {t.get("id"): t for t in payload.get("topics", []) if t.get("id") is not None}
    items = []
    posts = payload.get("posts", [])
    # If the endpoint returns only topics (no post bodies), fall back to topics.
    rows = posts if posts else list(topics.values())
    for row in rows:
        if posts:
            tid = row.get("topic_id")
            topic = topics.get(tid, {})
            native = f"post-{row.get('id')}"
            title = topic.get("title") or topic.get("fancy_title") or ""
            slug = topic.get("slug")
            url = f"{base}/t/{slug}/{tid}" if slug and tid else base
            text = common.strip_html(row.get("blurb") or row.get("cooked") or "")
            comments = topic.get("posts_count") or topic.get("reply_count") or 0
        else:
            tid = row.get("id")
            native = f"topic-{tid}"
            title = row.get("title") or row.get("fancy_title") or ""
            slug = row.get("slug")
            url = f"{base}/t/{slug}/{tid}" if slug and tid else base
            text = ""
            comments = row.get("posts_count") or row.get("reply_count") or 0
        if not title:
            continue
        items.append({
            "source_id": sid,
            "lane": lane,
            "native_id": native,
            "url": url,
            "title": title,
            "text": text,
            "published_at": common.iso_or_none(row.get("created_at")),
            "author_role_hint": "IT admin",
            "geo_hint": None,
            "engagement": {"comments": comments},
        })
    return items


def fetch(source):
    cfg = source.get("config") or {}
    base = cfg.get("base", "https://community.spiceworks.com").rstrip("/")
    queries = cfg.get("queries") or []
    out = []
    for q in queries:
        url = f"{base}/search.json?q={urllib.parse.quote(q)}"
        payload = common.get_json(url)
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
