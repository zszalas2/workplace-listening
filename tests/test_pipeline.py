#!/usr/bin/env python3
"""
Offline pipeline tests. The egress policy blocks the live feeds from CI/sandbox,
so these exercise each collector's pure parse() against recorded fixtures, plus
the normalize -> digest loop end to end. Run: python3 tests/test_pipeline.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIX = os.path.join(ROOT, "tests", "fixtures")

import common          # noqa: E402
import normalize       # noqa: E402
import digest          # noqa: E402
from collectors import rss, hackernews, spiceworks, reddit_arctic  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def load(fn, binary=False):
    with open(os.path.join(FIX, fn), "rb" if binary else "r") as f:
        return f.read()


# --------------------------------------------------------------------------- #
def test_rss():
    print("test_rss")
    src = {"id": "allwork_space", "lane": "context", "config": {"feed": "x"}}
    items = rss.parse(load("rss.xml", binary=True), src)
    check("rss two items", len(items) == 2, f"got {len(items)}")
    it = items[0]
    check("rss title", it["title"].startswith("The hybrid office"))
    check("rss content:encoded used", "neighborhood model" in it["text"])
    check("rss html stripped", "<" not in it["text"])
    check("rss rfc822 date", it["published_at"] == "2026-07-28", it["published_at"])
    check("rss native id from guid", it["native_id"] == "https://allwork.space/?p=12345")
    check("rss lane", it["lane"] == "context")

    # Atom branch.
    asrc = {"id": "worktech_academy", "lane": "context", "config": {}}
    aitems = rss.parse(load("atom.xml", binary=True), asrc)
    check("atom one entry", len(aitems) == 1, f"got {len(aitems)}")
    check("atom link href", aitems[0]["url"].endswith("/seat-allocation/"))
    check("atom iso date", aitems[0]["published_at"] == "2026-07-29")
    check("atom content stripped", "seat allocation ratio" in aitems[0]["text"])

    # Keyword filter.
    ksrc = {"id": "raconteur", "lane": "context",
            "config": {"feed": "x", "keywords": ["return to office"]}}
    kitems = rss.parse(load("rss.xml", binary=True), ksrc)
    check("rss keyword filter", len(kitems) == 1 and "Return to office" in kitems[0]["title"],
          f"got {len(kitems)}")


def test_hn():
    print("test_hn")
    src = {"id": "hackernews", "lane": "question", "config": {"min_points": 5}}
    items = hackernews.parse(json.loads(load("hn.json")), src)
    check("hn min_points filter", len(items) == 1, f"got {len(items)}")
    it = items[0]
    check("hn title", "return-to-office" in it["title"].lower())
    check("hn url fallback to item", it["url"].endswith("id=40123456"))
    check("hn engagement", it["engagement"]["score"] == 142 and it["engagement"]["comments"] == 210)
    check("hn date", it["published_at"] == "2026-07-30", it["published_at"])


def test_spiceworks():
    print("test_spiceworks")
    src = {"id": "spiceworks", "lane": "question", "config": {"base": "https://community.spiceworks.com"}}
    items = spiceworks.parse(json.loads(load("discourse.json")), src)
    check("spiceworks one post", len(items) == 1, f"got {len(items)}")
    it = items[0]
    check("spiceworks title from topic", "access control" in it["title"])
    check("spiceworks url built", it["url"].endswith("/t/visitor-management-access-control/90001"))
    check("spiceworks blurb text", "badge access" in it["text"])


def test_reddit():
    print("test_reddit")
    src = {"id": "reddit_sysadmin", "lane": "question",
           "config": {"subreddit": "sysadmin", "min_comments": 3}}
    items = reddit_arctic.parse(json.loads(load("reddit.json")), src)
    check("reddit min_comments filter", len(items) == 1, f"got {len(items)}")
    it = items[0]
    check("reddit title", it["title"].startswith("What visitor management"))
    check("reddit url from permalink", it["url"].endswith("/what_visitor_management_system/"))
    check("reddit epoch date", it["published_at"] == "2025-10-09", it["published_at"])
    check("reddit engagement", it["engagement"]["comments"] == 20)


def test_normalize_and_dedup():
    print("test_normalize_and_dedup")
    src = {"id": "reddit_sysadmin", "lane": "question",
           "config": {"subreddit": "sysadmin", "min_comments": 3}}
    raw = reddit_arctic.parse(json.loads(load("reddit.json")), src)
    state = {"sources": {}, "runs": []}
    new1, dup1 = normalize.normalize(raw, "reddit_sysadmin", state, run_id="2026-07-31")
    check("normalize first pass new", len(new1) == 1 and dup1 == 0)
    it = new1[0]
    check("normalize id is sha1(source:native)",
          it["id"] == common.item_id("reddit_sysadmin", "1oepsxb"))
    check("normalize contract fields",
          all(k in it for k in ("id", "source_id", "lane", "native_id", "url", "title",
                                "text", "published_at", "observed_at", "author_role_hint",
                                "geo_hint", "engagement", "run_id")))
    check("normalize observed_at/run_id", it["observed_at"] == "2026-07-31" and it["run_id"] == "2026-07-31")
    # Second pass: same items should all dedup.
    new2, dup2 = normalize.normalize(raw, "reddit_sysadmin", state, run_id="2026-08-07")
    check("normalize dedup on second pass", len(new2) == 0 and dup2 == 1, f"new={len(new2)} dup={dup2}")


def test_digest():
    print("test_digest")
    config = common.load_json(common.SCORING_PATH, default={})
    # Assemble a small run from multiple parsers.
    items = []
    items += normalize.normalize(
        reddit_arctic.parse(json.loads(load("reddit.json")),
                            {"id": "reddit_sysadmin", "lane": "question",
                             "config": {"subreddit": "sysadmin", "min_comments": 3}}),
        "reddit_sysadmin", {"sources": {}}, run_id="2026-07-31")[0]
    items += normalize.normalize(
        rss.parse(load("rss.xml", binary=True),
                  {"id": "allwork_space", "lane": "context", "config": {"feed": "x"}}),
        "allwork_space", {"sources": {}}, run_id="2026-07-31")[0]
    run_summary = {
        "run_id": "2026-07-31",
        "sources": [{"id": "reddit_sysadmin", "new": 1, "note": "ok"},
                    {"id": "allwork_space", "new": 2, "note": "ok"},
                    {"id": "paa_seed_keywords", "new": 0, "note": "adapter not built"}],
        "sources_ok": 2, "sources_error": 0, "sources_skipped": 1,
    }
    md = digest.build(run_summary, items, themes=[], config=config)
    check("digest has movers section", "## Movers" in md)
    check("digest has counts", "## Run counts" in md)
    check("digest total items", "Total new items: **3**" in md, md.split("\n")[0])
    check("digest lists question", "What visitor management" in md)
    check("digest shows skipped note", "adapter not built" in md)
    check("digest NO em dashes (style law)", "—" not in md)
    check("digest wave0 movers placeholder", "counts-only Wave 0 digest" in md)


def main():
    for t in (test_rss, test_hn, test_spiceworks, test_reddit,
              test_normalize_and_dedup, test_digest):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
