#!/usr/bin/env python3
"""
Generic RSS / Atom collector. Serves ~12 Lane B sources on its own (see
sources.yaml). Dependency-free: parses feeds with xml.etree from the stdlib.

Each collector exposes:
  parse(raw_bytes, source) -> list[raw_item]   pure, testable offline
  fetch(source)            -> list[raw_bytes]  network only
  collect(source)          -> list[raw_item]   fetch + parse

A raw_item is a dict in the intermediate shape that normalize.py turns into the
data/items.jsonl contract:
  {source_id, lane, native_id, url, title, text, published_at,
   author_role_hint, geo_hint, engagement}
"""
import re
import xml.etree.ElementTree as ET

import common

# Namespaces seen in the wild.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def _first(el, *tags):
    """Return the first matching child across plain and namespaced tags."""
    for tag in tags:
        found = el.find(tag, _NS) if ":" in tag else el.find(tag)
        if found is not None:
            return found
    return None


def _matches_keywords(title, text, keywords):
    if not keywords:
        return True
    hay = f"{title} {text}".lower()
    return any(k.lower() in hay for k in keywords)


def parse(raw, source):
    sid = source["id"]
    lane = source.get("lane", "context")
    cfg = source.get("config") or {}
    keywords = cfg.get("keywords")
    geo = cfg.get("geo_hint")
    items = []
    if not raw:
        return items
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        # Some feeds (e.g. facilitiesnet) ship malformed XML. Salvage what we can
        # with a lenient regex pass rather than losing the whole source.
        print(f"  ! {sid}: xml parse error ({e}); falling back to lenient parse")
        return _regex_items(raw, source)

    # RSS 2.0: <rss><channel><item>...  |  Atom: <feed><entry>...
    entries = root.findall(".//item")
    is_atom = False
    if not entries:
        entries = root.findall(".//atom:entry", _NS)
        is_atom = True

    for e in entries:
        title = _text(_first(e, "title", "atom:title"))
        if is_atom:
            link_el = e.find("atom:link", _NS)
            url = link_el.get("href") if link_el is not None else ""
            body = _text(_first(e, "atom:content", "atom:summary"))
            pub = _text(_first(e, "atom:published", "atom:updated"))
            native = _text(_first(e, "atom:id")) or url
        else:
            url = _text(_first(e, "link"))
            body = _text(_first(e, "content:encoded", "description"))
            pub = _text(_first(e, "pubDate", "dc:date"))
            guid = _first(e, "guid")
            native = _text(guid) or url or title
        text = common.strip_html(body)
        if not _matches_keywords(title, text, keywords):
            continue
        items.append({
            "source_id": sid,
            "lane": lane,
            "native_id": native,
            "url": url,
            "title": title,
            "text": text,
            "published_at": common.iso_or_none(pub),
            "author_role_hint": None,
            "geo_hint": geo,
            "engagement": {},
        })
    return items


def _tag(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S | re.I)
    if not m:
        return ""
    val = m.group(1).strip()
    cdata = re.match(r"^<!\[CDATA\[(.*)\]\]>$", val, re.S)
    return cdata.group(1).strip() if cdata else val


def _regex_items(raw, source):
    """Lenient fallback for malformed feeds: pull <item>/<entry> blocks by regex."""
    sid = source["id"]
    lane = source.get("lane", "context")
    cfg = source.get("config") or {}
    keywords = cfg.get("keywords")
    geo = cfg.get("geo_hint")
    try:
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    except Exception:  # noqa: BLE001
        return []
    items = []
    blocks = re.findall(r"<(?:item|entry)[^>]*>(.*?)</(?:item|entry)>", text, re.S | re.I)
    for b in blocks:
        title = common.strip_html(_tag(b, "title"))
        link = _tag(b, "link")
        if not link:  # atom style: <link href="..."/>
            m = re.search(r'<link[^>]*href="([^"]+)"', b, re.I)
            link = m.group(1) if m else ""
        body = _tag(b, "content:encoded") or _tag(b, "description") or _tag(b, "summary")
        body = common.strip_html(body)
        pub = _tag(b, "pubDate") or _tag(b, "published") or _tag(b, "updated") or _tag(b, "dc:date")
        native = _tag(b, "guid") or _tag(b, "id") or link or title
        if keywords and not _matches_keywords(title, body, keywords):
            continue
        if not (title or link):
            continue
        items.append({
            "source_id": sid,
            "lane": lane,
            "native_id": native,
            "url": link,
            "title": title,
            "text": body,
            "published_at": common.iso_or_none(pub),
            "author_role_hint": None,
            "geo_hint": geo,
            "engagement": {},
        })
    return items


def fetch(source):
    cfg = source.get("config") or {}
    feed = cfg.get("feed")
    if not feed:
        print(f"  ! {source['id']}: no feed url configured")
        return []
    raw = common.get(feed)
    return [raw] if raw else []


def collect(source):
    out = []
    for raw in fetch(source):
        out.extend(parse(raw, source))
    return out
