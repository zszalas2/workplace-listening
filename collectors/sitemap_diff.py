#!/usr/bin/env python3
"""
sitemap_diff.py: collect new pages from sites with no usable RSS (Wave 2).

For competitor blogs like Envoy and OfficeSpace that publish no feed, poll the
sitemap, take the most recently modified URLs, and fetch each for a title and
description. Dedup happens downstream in normalize (native_id is the URL), so an
already-seen page is dropped even though it is re-listed.

Bounded by config `max_urls` (default 25) so a large sitemap never fans out into
hundreds of page fetches. Best-effort: a dead sitemap or page returns nothing and
never fails the run.

config:
  sitemap: https://example.com/sitemap.xml   (required)
  url_contains: /blog/                        (optional substring filter on <loc>)
  max_urls: 25                                (optional)
"""
import re
import xml.etree.ElementTree as ET

import common

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.S | re.I)
_OG_DESC = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', re.S | re.I)


def _locs(raw):
    """Return [(url, lastmod)] from a sitemap, tolerant of namespaces."""
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # Namespace-free regex fallback.
        for m in re.finditer(r"<loc>(.*?)</loc>", raw.decode("utf-8", "replace"), re.S | re.I):
            out.append((m.group(1).strip(), ""))
        return out
    for url_el in root.iter():
        if not url_el.tag.endswith("url"):
            continue
        loc = lastmod = ""
        for child in url_el:
            if child.tag.endswith("loc"):
                loc = (child.text or "").strip()
            elif child.tag.endswith("lastmod"):
                lastmod = (child.text or "").strip()
        if loc:
            out.append((loc, lastmod))
    return out


def _page_item(url, source):
    raw = common.get(url)
    if raw is None:
        return None
    html = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    tm = _TITLE.search(html)
    title = common.strip_html(tm.group(1)) if tm else url
    dm = _META_DESC.search(html) or _OG_DESC.search(html)
    desc = common.strip_html(dm.group(1)) if dm else ""
    return {
        "source_id": source["id"],
        "lane": source.get("lane", "context"),
        "native_id": url,
        "url": url,
        "title": title,
        "text": (title + ". " + desc).strip(". ").strip(),
        "published_at": None,
        "author_role_hint": None,
        "geo_hint": (source.get("config") or {}).get("geo_hint"),
        "engagement": {},
    }


def collect(source):
    cfg = source.get("config") or {}
    sitemap = cfg.get("sitemap")
    if not sitemap:
        print(f"  ! {source['id']}: no sitemap url configured")
        return []
    raw = common.get(sitemap)
    if raw is None:
        return []
    locs = _locs(raw)
    # `include` (list of substrings, match any) or `url_contains` (single string).
    includes = cfg.get("include") or ([cfg["url_contains"]] if cfg.get("url_contains") else [])
    if includes:
        locs = [(u, m) for (u, m) in locs if any(inc in u for inc in includes)]
    # Newest first by lastmod (blank lastmod sorts last).
    locs.sort(key=lambda um: um[1] or "", reverse=True)
    locs = locs[:cfg.get("max_urls", 25)]
    out = []
    for url, _ in locs:
        item = _page_item(url, source)
        if item:
            out.append(item)
    return out
