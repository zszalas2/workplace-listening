#!/usr/bin/env python3
"""
youtube_detect.py: detect new videos on a YouTube channel via its RSS feed.

Detection only, no transcripts: YouTube blocks caption/transcript requests from
datacenter IPs, so CI never touches transcripts (PROJECT_PLAN.md section 7). The
channel feed carries titles, ids, publish dates, and descriptions, which is all
Lane B needs as context signal.

Used two ways:
  1. As a Lane B collector for external channels (yt_ifma, yt_worktech, ...),
     emitting context items from each video's title + description.
  2. As the parser the Track 1 Converter detector reuses (converter/detect.py) to
     find new Croissant videos.

config:
  channel_id: UCxxxx        (preferred)
  feed: <full feed url>     (optional override)
"""
import re
import xml.etree.ElementTree as ET

import common

FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def feed_url(source):
    cfg = source.get("config") or {}
    if cfg.get("feed"):
        return cfg["feed"]
    if cfg.get("channel_id"):
        return FEED.format(cfg["channel_id"])
    return None


def parse_videos(raw):
    """Return [{video_id, title, url, published, description, views}] from a
    channel feed. Tolerant: falls back to regex if XML parsing fails."""
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return _regex_videos(raw)
    out = []
    for e in root.findall("atom:entry", _NS):
        vid = e.findtext("yt:videoId", default="", namespaces=_NS)
        title = e.findtext("atom:title", default="", namespaces=_NS)
        link_el = e.find("atom:link", _NS)
        url = link_el.get("href") if link_el is not None else (
            f"https://www.youtube.com/watch?v={vid}" if vid else "")
        published = e.findtext("atom:published", default="", namespaces=_NS)
        grp = e.find("media:group", _NS)
        desc = ""
        views = 0
        if grp is not None:
            desc = grp.findtext("media:description", default="", namespaces=_NS) or ""
            stats = grp.find("media:community/media:statistics", _NS)
            if stats is not None:
                try:
                    views = int(stats.get("views", "0"))
                except (TypeError, ValueError):
                    views = 0
        if vid:
            out.append({"video_id": vid, "title": title.strip(), "url": url,
                        "published": published, "description": desc.strip(),
                        "views": views})
    return out


def _regex_videos(raw):
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    out = []
    for block in re.findall(r"<entry>(.*?)</entry>", text, re.S | re.I):
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", block)
        title = re.search(r"<title>(.*?)</title>", block, re.S)
        if not vid:
            continue
        v = vid.group(1).strip()
        out.append({
            "video_id": v,
            "title": common.strip_html(title.group(1)) if title else "",
            "url": f"https://www.youtube.com/watch?v={v}",
            "published": "",
            "description": "",
            "views": 0,
        })
    return out


def collect(source):
    url = feed_url(source)
    if not url:
        print(f"  ! {source['id']}: channel_id or feed required")
        return []
    raw = common.get(url)
    if raw is None:
        return []
    items = []
    for v in parse_videos(raw):
        items.append({
            "source_id": source["id"],
            "lane": source.get("lane", "context"),
            "native_id": v["video_id"],
            "url": v["url"],
            "title": v["title"],
            "text": v["description"],
            "published_at": common.iso_or_none(v["published"]),
            "author_role_hint": "youtube",
            "geo_hint": (source.get("config") or {}).get("geo_hint"),
            "engagement": {"views": v["views"]},
        })
    return items
