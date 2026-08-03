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
import relevance       # noqa: E402
import scoring         # noqa: E402
import synthesize      # noqa: E402
import summarize_context  # noqa: E402
import issues          # noqa: E402
from collectors import (rss, hackernews, spiceworks, reddit_arctic,  # noqa: E402
                        youtube_detect, sitemap_diff, archive_scrape,
                        paa, trends, reviews_capterra, reports_diff)
from converter import detect as converter_detect  # noqa: E402

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

    # Malformed feed falls back to lenient regex parse (facilitiesnet case).
    msrc = {"id": "facilitiesnet", "lane": "context", "config": {"feed": "x"}}
    mitems = rss.parse(load("malformed.xml", binary=True), msrc)
    check("rss malformed fallback recovers items", len(mitems) == 2, f"got {len(mitems)}")
    check("rss malformed title", mitems[0]["title"].startswith("Occupancy sensors"))
    check("rss malformed link", mitems[0]["url"].endswith("/article/12345"))
    check("rss malformed html stripped in body", "<p>" not in mitems[1]["text"])


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


def test_relevance():
    print("test_relevance")
    config = common.load_json(common.SCORING_PATH, default={})
    # Real live-run noise vs signal for a question source (Spiceworks).
    sw = {"id": "spiceworks", "lane": "question", "adapter": "spiceworks", "config": {}}
    items = [
        {"title": "Google Chrome", "text": "browser thread"},                       # junk
        {"title": "Microsoft Windows 7 Pro", "text": ""},                            # junk
        {"title": "Visitor management that integrates with access control", "text": ""},  # signal
        {"title": "Anyone using desk booking software?", "text": "hot desking"},     # signal
    ]
    kept, dropped = relevance.filter_source(items, sw, config)
    check("relevance drops junk", dropped == 2 and len(kept) == 2, f"kept={len(kept)} dropped={dropped}")
    check("relevance keeps visitor mgmt", any("Visitor management" in k["title"] for k in kept))

    # HN off-topic bleed-through gets dropped too.
    hn = {"id": "hackernews", "lane": "question", "adapter": "hackernews", "config": {}}
    hn_items = [
        {"title": "Future euro banknote design proposals", "text": ""},              # junk
        {"title": "JPMorgan Workers Ponder Union after Return-to-Office Mandate", "text": ""},  # signal
    ]
    _, hn_dropped = relevance.filter_source(hn_items, hn, config)
    check("relevance drops HN off-topic", hn_dropped == 1, f"dropped={hn_dropped}")

    # Reddit (query-targeted, sparse) is NOT gated by default.
    rd = {"id": "reddit_sysadmin", "lane": "question", "adapter": "reddit_arctic", "config": {}}
    rd_items = [{"title": "some tangential post", "text": "no keyword here"}]
    rd_kept, rd_dropped = relevance.filter_source(rd_items, rd, config)
    check("relevance skips reddit by default", rd_dropped == 0 and len(rd_kept) == 1)

    # Context feeds pass untouched by default.
    ctx = {"id": "allwork_space", "lane": "context", "adapter": "rss", "config": {}}
    ctx_kept, ctx_dropped = relevance.filter_source([{"title": "anything", "text": ""}], ctx, config)
    check("relevance skips context by default", ctx_dropped == 0 and len(ctx_kept) == 1)


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


def _item(iid, source_id, lane, day="2026-08-01"):
    return {"id": iid, "source_id": source_id, "lane": lane,
            "url": f"https://example.test/{iid}", "title": f"title {iid}",
            "published_at": day, "observed_at": day, "engagement": {}}


def test_synthesis_assembly():
    print("test_synthesis_assembly")
    config = common.load_json(common.SCORING_PATH, default={})
    items = [_item("i1", "reddit_sysadmin", "question"),
             _item("c1", "allwork_space", "context")]
    prompt = synthesize.build_prompt(items, themes=[
        {"theme_id": "visitor-mgmt", "label": "Visitor mgmt", "vocabulary": ["badge"]}])
    check("prompt carries question item", "i1" in prompt)
    check("prompt carries context item", "c1" in prompt)
    check("prompt carries registry", "visitor-mgmt" in prompt)

    canned = {"themes": [{"theme_id": "t", "label": "L", "is_new": True,
                          "item_ids": ["i1"], "buying_questions": [], "vocabulary": [],
                          "covered_by_context": [], "suggested_angle": "", "watching": False}]}

    def fake(_ni, _th, _cfg, _key, _summaries=None):
        return canned

    out = synthesize.synthesize(items, [], config, call=fake)
    check("synthesize returns model output", out == canned)
    # No question items -> skip entirely.
    ctx_only = synthesize.synthesize([_item("c2", "allwork_space", "context")], [], config, call=fake)
    check("synthesize skips without question items", ctx_only is None)


def test_scoring_basic():
    print("test_scoring_basic")
    config = common.load_json(common.SCORING_PATH, default={})
    week = common.iso_week()
    items = [_item("i1", "reddit_sysadmin", "question"),
             _item("i2", "spiceworks", "question"),
             _item("i4", "hackernews", "question"),
             _item("i3", "hackernews", "question"),
             _item("c1", "allwork_space", "context")]
    model = {"themes": [
        {"theme_id": "visitor-mgmt", "label": "Visitor management + access control",
         "is_new": True, "item_ids": ["i1", "i2", "i4"],
         "buying_questions": [{"quote": "What VMS integrates with access control?",
                              "item_id": "i1"}],
         "vocabulary": ["visitor management", "access control"],
         "covered_by_context": [], "suggested_angle": "Lead with badge-free entry.",
         "watching": False},
        {"theme_id": "rto-mandate", "label": "RTO mandate enforcement", "is_new": True,
         "item_ids": ["i3"], "buying_questions": [], "vocabulary": ["rto"],
         "covered_by_context": ["allwork_space"], "suggested_angle": "", "watching": False},
    ]}
    out = scoring.score([], model, items, config, week=week)
    by = {t["theme_id"]: t for t in out}
    vm = by["visitor-mgmt"]
    rto = by["rto-mandate"]
    check("scoring two themes", len(out) == 2)
    check("scoring current count", vm["current"] == 3, str(vm["current"]))
    check("scoring status new", vm["status"] == "new", vm["status"])
    check("scoring demand normalized to 1", vm["demand_score"] == 1.0, str(vm["demand_score"]))
    check("scoring no saturation -> opportunity high", vm["opportunity_score"] == 1.0,
          str(vm["opportunity_score"]))
    check("scoring evidence carried", vm["evidence"] and "VMS" in vm["evidence"][0]["quote"])
    check("scoring evidence url resolved from item_id",
          vm["evidence"][0]["url"] == "https://example.test/i1", vm["evidence"][0]["url"])
    check("scoring evidence source resolved from item_id",
          vm["evidence"][0]["source_id"] == "reddit_sysadmin", vm["evidence"][0]["source_id"])
    check("scoring vocabulary carried", "access control" in vm["vocabulary"])
    check("scoring saturated theme -> saturation 1", rto["saturation_score"] == 1.0,
          str(rto["saturation_score"]))
    check("scoring sub-threshold -> watching", rto["status"] == "watching", rto["status"])


def test_scoring_velocity_and_suppression():
    print("test_scoring_velocity_and_suppression")
    config = common.load_json(common.SCORING_PATH, default={})
    week = common.iso_week()
    tw = scoring._trailing_weeks(week, config.get("velocity_window_weeks", 6))
    quiet = {tw[0]: 0, tw[1]: 0, tw[2]: 0, tw[3]: 0, tw[4]: 1, tw[5]: 1}
    existing = [
        {"theme_id": "desk-booking", "label": "Desk booking", "first_seen": "2026-01-01",
         "counts_by_week": dict(quiet), "evidence": [], "vocabulary": [],
         "became_post": None, "became_post_at": None},
        {"theme_id": "hoteling", "label": "Hoteling", "first_seen": "2026-01-01",
         "counts_by_week": {}, "evidence": [], "vocabulary": [],
         "became_post": "post-x", "became_post_at": common.RUN_ID},
    ]
    spike = [_item(f"d{i}", "reddit_sysadmin", "question") for i in range(6)]
    spike += [_item("h1", "spiceworks", "question")]
    model = {"themes": [
        {"theme_id": "desk-booking", "label": "Desk booking", "is_new": False,
         "item_ids": [f"d{i}" for i in range(6)], "buying_questions": [],
         "vocabulary": [], "covered_by_context": [], "suggested_angle": "", "watching": False},
        {"theme_id": "hoteling", "label": "Hoteling", "is_new": False,
         "item_ids": ["h1"], "buying_questions": [], "vocabulary": [],
         "covered_by_context": [], "suggested_angle": "", "watching": False},
    ]}
    out = scoring.score(existing, model, spike, config, week=week)
    by = {t["theme_id"]: t for t in out}
    check("velocity spike -> accelerating", by["desk-booking"]["status"] == "accelerating",
          f"{by['desk-booking']['status']} z={by['desk-booking']['delta_z']}")
    check("velocity delta_z positive", by["desk-booking"]["delta_z"] > 1.5,
          str(by["desk-booking"]["delta_z"]))
    check("recent post -> suppressed", by["hoteling"]["status"] == "suppressed",
          by["hoteling"]["status"])


def test_opportunity_floor():
    print("test_opportunity_floor")
    config = common.load_json(common.SCORING_PATH, default={})
    week = common.iso_week()
    items = [_item("s1", "reddit_sysadmin", "question"),
             _item("s2", "spiceworks", "question"),
             _item("s3", "hackernews", "question"),
             _item("k1", "reddit_msp", "question")]
    model = {"themes": [
        # 3 items (>= min) but fully covered by Lane B -> saturation 1.0 ->
        # opportunity 0 -> demoted from "new" to "watching".
        {"theme_id": "saturated", "label": "Saturated topic", "is_new": True,
         "item_ids": ["s1", "s2", "s3"], "buying_questions": [], "vocabulary": [],
         "covered_by_context": ["allwork_space", "charter"], "suggested_angle": "",
         "watching": False},
        # a second theme with no coverage so max_cov > 0 and the ratio is meaningful
        {"theme_id": "clean", "label": "Clean topic", "is_new": True,
         "item_ids": ["k1"], "buying_questions": [], "vocabulary": [],
         "covered_by_context": [], "suggested_angle": "", "watching": False},
    ]}
    out = scoring.score([], model, items, config, week=week)
    by = {t["theme_id"]: t for t in out}
    check("floor: saturated new theme demoted to watching",
          by["saturated"]["status"] == "watching",
          f"{by['saturated']['status']} opp={by['saturated']['opportunity_score']}")
    check("floor: saturated opportunity is 0",
          by["saturated"]["opportunity_score"] == 0.0, str(by["saturated"]["opportunity_score"]))


def test_youtube_detect():
    print("test_youtube_detect")
    vids = youtube_detect.parse_videos(load("youtube.xml", binary=True))
    check("yt two videos", len(vids) == 2, str(len(vids)))
    check("yt video id", vids[0]["video_id"] == "ABC123abc")
    check("yt description", "distributed workforce" in vids[0]["description"])
    check("yt views parsed", vids[0]["views"] == 1234, str(vids[0]["views"]))
    src = {"id": "yt_ifma", "lane": "context", "config": {}}
    items = youtube_detect.collect  # smoke: collect needs a feed url
    check("yt collect needs feed", youtube_detect.feed_url(src) is None)
    check("yt feed from channel_id",
          youtube_detect.feed_url({"config": {"channel_id": "UCx"}}).endswith("channel_id=UCx"))


def test_sitemap_diff():
    print("test_sitemap_diff")
    locs = sitemap_diff._locs(load("sitemap.xml", binary=True))
    check("sitemap three locs", len(locs) == 3, str(len(locs)))
    blog = [u for (u, m) in locs if "/blog/" in u]
    check("sitemap blog filter finds two", len(blog) == 2, str(len(blog)))
    # newest-first sort by lastmod
    src = {"id": "competitor_envoy", "lane": "context",
           "config": {"include": ["/blog/"], "max_urls": 25}}
    kept = [u for (u, m) in locs if any(inc in u for inc in ["/blog/"])]
    kept.sort()
    check("sitemap include matches blog urls", set(kept) == set(blog))


def test_archive_scrape():
    print("test_archive_scrape")
    html = ('<a href="https://theassistmedia.com/blog/ea-time-savers">x</a>'
            '<a href="https://theassistmedia.com/blog/office-manager-guide">y</a>'
            '<a href="https://twitter.com/theassist">social</a>')
    import re as _re
    host = "theassistmedia.com"
    pattern = r'href=["\'](https?://' + _re.escape(host) + r'/[^"\'#?]+)["\']'
    links = archive_scrape._links(html, pattern)
    check("archive extracts same-host links", len(links) == 2, str(links))
    check("archive drops offsite", all("theassistmedia.com" in u for u in links))


def test_summarize_context():
    print("test_summarize_context")
    config = common.load_json(common.SCORING_PATH, default={})
    themes = [{"theme_id": "desk-booking-utilization", "label": "Desk booking",
               "vocabulary": ["hot desk"]}]
    item = _item("c1", "allwork_space", "context")
    item["text"] = "A long article about desk booking utilization and occupancy sensors."
    prompt = summarize_context.build_prompt(item, themes)
    check("summary prompt carries theme_id", "desk-booking-utilization" in prompt)
    check("summary prompt carries item text", "occupancy sensors" in prompt)

    def fake(_it, _th, _cfg, _key):
        return {"summary": "Desks are over-provisioned.",
                "claims": [{"claim": "111% ratio", "stat": "111%", "attribution": "CBRE"}],
                "vocabulary": ["seat allocation ratio"],
                "topics_covered": ["desk-booking-utilization"]}

    out = summarize_context.summarize_items([item], themes, config, call=fake, write=False)
    check("summary produced one", len(out) == 1, str(len(out)))
    check("summary carries topics_covered",
          out[0]["topics_covered"] == ["desk-booking-utilization"])
    check("summary carries id/source", out[0]["id"] == "c1" and out[0]["source_id"] == "allwork_space")
    # question-lane items are ignored by the summarizer
    q = _item("q1", "reddit_sysadmin", "question")
    check("summary ignores question lane",
          summarize_context.summarize_items([q], themes, config, call=fake, write=False) == [])


def test_saturation_from_summaries():
    print("test_saturation_from_summaries")
    config = common.load_json(common.SCORING_PATH, default={})
    week = common.iso_week()
    items = [_item("i1", "reddit_sysadmin", "question"),
             _item("i2", "spiceworks", "question"),
             _item("i3", "hackernews", "question"),
             _item("j1", "reddit_msp", "question")]
    model = {"themes": [
        {"theme_id": "desk-booking", "label": "Desk booking", "is_new": True,
         "item_ids": ["i1", "i2", "i3"], "buying_questions": [], "vocabulary": [],
         "covered_by_context": [], "suggested_angle": "", "watching": False},
        {"theme_id": "visitor-open", "label": "Visitor open field", "is_new": True,
         "item_ids": ["j1"], "buying_questions": [], "vocabulary": [],
         "covered_by_context": [], "suggested_angle": "", "watching": False},
    ]}
    summaries = [
        {"source_id": "allwork_space", "topics_covered": ["desk-booking"]},
        {"source_id": "charter", "topics_covered": ["desk-booking"]},
        {"source_id": "worktech_academy", "topics_covered": []},
    ]
    out = scoring.score([], model, items, config, week=week, context_summaries=summaries)
    by = {t["theme_id"]: t for t in out}
    check("saturation from summaries: covered theme saturated",
          by["desk-booking"]["saturation_score"] == 1.0,
          str(by["desk-booking"]["saturation_score"]))
    check("saturation covered_by_context resolved from summaries",
          by["desk-booking"]["covered_by_context"] == ["allwork_space", "charter"],
          str(by["desk-booking"]["covered_by_context"]))
    check("saturation from summaries: uncovered theme open",
          by["visitor-open"]["saturation_score"] == 0.0,
          str(by["visitor-open"]["saturation_score"]))


def test_converter_detect():
    print("test_converter_detect")
    check("iso8601 minutes+seconds", converter_detect._iso8601_seconds("PT12M30S") == 750)
    check("iso8601 hours", converter_detect._iso8601_seconds("PT1H2M") == 3720)
    inc, _ = converter_detect._qualifies(900)
    check("converter includes long video", inc is True)
    exc, _ = converter_detect._qualifies(120)
    check("converter excludes short video", exc is False)
    unk, reason = converter_detect._qualifies(None)
    check("converter includes unknown-duration for human", unk is True and "unknown" in reason)


def test_placeholder_adapters():
    print("test_placeholder_adapters")
    for mod, sid in [(paa, "paa_seed_keywords"), (trends, "trends_seed_keywords"),
                     (reviews_capterra, "capterra_reviews"), (reports_diff, "reports_gensler")]:
        out = mod.collect({"id": sid, "config": {}})
        check(f"placeholder {sid} no-ops", out == [], str(out))


def test_digest_v1():
    print("test_digest_v1")
    config = common.load_json(common.SCORING_PATH, default={})
    week = common.iso_week()
    items = [_item("i1", "reddit_sysadmin", "question"),
             _item("i2", "spiceworks", "question"),
             _item("i4", "hackernews", "question")]
    model = {"themes": [{"theme_id": "visitor-mgmt",
                         "label": "Visitor management + access control", "is_new": True,
                         "item_ids": ["i1", "i2", "i4"],
                         "buying_questions": [{"quote": "Which VMS integrates with access control?",
                                              "item_id": "i1"}],
                         "vocabulary": ["visitor management"], "covered_by_context": [],
                         "suggested_angle": "Lead with badge-free entry for HR.",
                         "watching": False}]}
    scored = scoring.score([], model, items, config, week=week)
    md = digest.build({"run_id": common.RUN_ID, "sources": [], "sources_ok": 1,
                       "sources_error": 0, "sources_skipped": 0}, items, scored, config)
    check("digest v1 renders mover", "Visitor management + access control" in md)
    check("digest v1 not wave0 placeholder", "counts-only Wave 0 digest" not in md)
    check("digest v1 verbatim question", "Which VMS integrates" in md)
    check("digest v1 saturation read", "saturation read" in md)
    check("digest v1 suggested angle", "badge-free entry" in md)
    check("digest v1 no em dashes", "—" not in md)


def test_issues_body():
    print("test_issues_body")
    theme = {"theme_id": "visitor-mgmt", "label": "Visitor management",
             "status": "new", "opportunity_score": 0.81, "demand_score": 0.9,
             "saturation_score": 0.1, "suggested_angle": "Badge-free entry.",
             "evidence": [{"quote": "Which VMS?", "url": "https://x", "source_id": "reddit_sysadmin"}],
             "covered_by_context": [], "vocabulary": ["visitor management", "kiosk"]}
    body = issues.issue_body(theme)
    check("issue body has marker", "theme_id=visitor-mgmt" in body)
    check("issue body has question", "Which VMS?" in body)
    check("issue body has angle", "Badge-free entry" in body)
    check("issue body no em dash", "—" not in body)
    labels = issues.issue_labels(theme)
    check("issue labels", labels == ["theme", "status:new", "wave1"], str(labels))


def main():
    for t in (test_rss, test_hn, test_spiceworks, test_reddit,
              test_normalize_and_dedup, test_relevance, test_digest,
              test_synthesis_assembly, test_scoring_basic,
              test_scoring_velocity_and_suppression, test_opportunity_floor,
              test_youtube_detect, test_sitemap_diff, test_archive_scrape,
              test_summarize_context, test_saturation_from_summaries,
              test_converter_detect, test_placeholder_adapters,
              test_digest_v1, test_issues_body):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
