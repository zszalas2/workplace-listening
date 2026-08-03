#!/usr/bin/env python3
"""
archive_scrape.py: collect posts from a paginated public archive with no RSS.

The Assist publishes a public archive but no feed. Fetch the archive page(s),
pull article links matching a configured pattern, and turn each into a Lane B
item (title from the anchor text, body from the linked page's title + meta
description). Dedup is downstream in normalize (native_id is the URL).

Best-effort and bounded (`max_urls`, default 20). Anti-bot or markup changes make
this fragile by nature (PROJECT_PLAN.md section 13), so a failure yields nothing
and never fails the run. The link_pattern usually needs tuning against the live
markup once the site is observed.

config:
  archive_url: https://theassistmedia.com/archive/   (required)
  link_pattern: 'href="(https://theassistmedia\\.com/[^"]+)"'  (regex, group 1 = url)
  max_urls: 20
"""
import re
import urllib.parse

import common

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.S | re.I)


def _links(html, pattern):
    seen, out = set(), []
    for m in re.finditer(pattern, html, re.I):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _page_item(url, source):
    raw = common.get(url)
    if raw is None:
        return None
    html = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    tm = _TITLE.search(html)
    title = common.strip_html(tm.group(1)) if tm else url
    dm = _META_DESC.search(html)
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
    archive = cfg.get("archive_url") or cfg.get("archive")
    if not archive:
        print(f"  ! {source['id']}: archive_url (or archive) required")
        return []
    pattern = cfg.get("link_pattern")
    if not pattern:
        # Default: same-host links under a path, which for a blog archive is a
        # reasonable first cut. Tune link_pattern in sources.yaml once observed.
        host = urllib.parse.urlparse(archive).netloc
        pattern = r'href=["\'](https?://' + re.escape(host) + r'/[^"\'#?]+)["\']'
    raw = common.get(archive)
    if raw is None:
        return []
    html = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    base = archive.rstrip("/")
    urls = [u for u in _links(html, pattern) if u.rstrip("/") != base]
    urls = urls[:cfg.get("max_urls", 20)]
    out = []
    for url in urls:
        item = _page_item(url, source)
        if item:
            out.append(item)
    return out
