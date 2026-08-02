#!/usr/bin/env python3
"""
Shared helpers for the workplace-listening collectors.

House rules inherited from the transition-watchlist reference implementation:
  - Dependency-free. Everything here uses the Python standard library only, so a
    collector runs on a bare GitHub Actions runner or a laptop with no pip install.
  - state.json holds per-source cursors and seen ids, so every run is a diff.
  - Append-only jsonl is the single source of truth; digests are views over it.

PyYAML is used when present (it is more correct), otherwise a small parser that
understands the exact subset used by sources.yaml keeps this dependency-free.
"""
import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_ID = date.today().isoformat()
UA = {"User-Agent": "Mozilla/5.0 (workplace-listening-collector)"}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def path(*parts):
    return os.path.join(HERE, *parts)


DATA = path("data")
ITEMS_PATH = path("data", "items.jsonl")
THEMES_PATH = path("data", "themes.json")
STATE_PATH = path("state.json")
SOURCES_PATH = path("sources.yaml")
SCORING_PATH = path("scoring_config.json")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def get(url, timeout=15, headers=None, retries=2):
    """GET a URL, returning bytes or None. Never raises: a dead source must not
    fail the whole run (see the risk notes in PROJECT_PLAN.md section 13)."""
    h = dict(UA)
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:  # noqa: PERF203
            last = e
            if attempt < retries:
                # Honor Retry-After on 429/503, else exponential backoff.
                wait = 2 ** attempt
                if e.code in (429, 503):
                    ra = e.headers.get("Retry-After") if e.headers else None
                    try:
                        wait = max(wait, int(ra)) if ra else max(wait, 5)
                    except (TypeError, ValueError):
                        wait = max(wait, 5)
                time.sleep(wait)
        except Exception as e:  # noqa: BLE001 - best effort by design
            last = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    print(f"  ! fetch failed {url}: {last}")
    return None


def get_json(url, timeout=15, headers=None, retries=2):
    b = get(url, timeout=timeout, headers=headers, retries=retries)
    if b is None:
        return None
    try:
        return json.loads(b)
    except Exception as e:  # noqa: BLE001
        print(f"  ! json parse failed {url}: {e}")
        return None


# --------------------------------------------------------------------------- #
# JSON / JSONL io
# --------------------------------------------------------------------------- #
def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def append_jsonl(p, records):
    if not records:
        return 0
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


def read_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# --------------------------------------------------------------------------- #
# Identity / dates
# --------------------------------------------------------------------------- #
def sha1(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def item_id(source_id, native_id):
    return sha1(f"{source_id}:{native_id}")


def iso_week(d=None):
    """ISO week label like 2026-W31, matching counts_by_week keys in themes.json."""
    if d is None:
        d = date.today()
    if isinstance(d, str):
        d = parse_date(d) or date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def parse_date(s):
    """Best-effort date parse -> datetime.date. Handles RFC822, ISO, epoch."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, tz=timezone.utc).date()
    s = str(s).strip()
    if re.fullmatch(r"-?\d{9,}", s):  # epoch seconds
        return datetime.fromtimestamp(int(s), tz=timezone.utc).date()
    # ISO 8601, including fractional seconds and trailing Z (e.g. ...:00.000Z)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    # ISO 8601 explicit fallbacks
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # RFC 822 (RSS pubDate): "Mon, 20 Oct 2025 14:03:00 +0000"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.date()
    except Exception:  # noqa: BLE001
        pass
    return None


def iso_or_none(s):
    d = parse_date(s)
    return d.isoformat() if d else None


# --------------------------------------------------------------------------- #
# HTML -> text
# --------------------------------------------------------------------------- #
class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(s, limit=8000):
    if not s:
        return ""
    p = _Stripper()
    try:
        p.feed(s)
        text = "".join(p.parts)
    except Exception:  # noqa: BLE001
        text = re.sub(r"<[^>]+>", " ", s)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# --------------------------------------------------------------------------- #
# YAML (subset) loader
# --------------------------------------------------------------------------- #
def load_yaml(p):
    text = open(p).read()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(text)


def _scalar(v):
    v = v.strip()
    if v == "" or v == "~" or v.lower() == "null":
        return None if v != "" else ""
    if v[0] in "[{":
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return v
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    return v


def _split_kv(line):
    k, _, v = line.partition(":")
    return k.strip(), v.strip()


def _mini_yaml(text):
    """Parse the specific shape of sources.yaml: a top-level list of maps, each
    with scalar fields plus a nested `config:` map whose values are scalars or
    inline JSON lists. Deliberately small; not a general YAML implementation."""
    items = []
    cur = None
    sub = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if line.startswith("- "):
            cur = {}
            items.append(cur)
            sub = None
            k, v = _split_kv(line[2:])
            cur[k] = _scalar(v)
        elif indent <= 2:  # top-level key of the current list item
            k, v = _split_kv(line)
            if v == "":
                sub = {}
                cur[k] = sub
            else:
                cur[k] = _scalar(v)
                sub = None
        else:  # nested under the most recent map (config:)
            k, v = _split_kv(line)
            if sub is not None:
                sub[k] = _scalar(v)
    return items
