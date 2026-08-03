#!/usr/bin/env python3
"""
podcast.py: collect podcast episodes as Lane B context (Wave 2).

Podcast feeds are RSS 2.0 with the episode show notes in <description> or
<content:encoded>, which the generic rss adapter already parses well. The
show notes name the guest (the ICP) and the topics, which is what the ingest
summarizer needs.

Transcript fetching is deliberately deferred: downloading enclosures or
transcript files at volume is IP-blocked from CI runners (PROJECT_PLAN.md
section 7), so Wave 2 summarizes the show notes rather than the audio. This
adapter therefore reuses rss parsing and just guarantees the context lane and a
podcast role hint. A dedicated transcript path can slot in later behind the same
interface without changing anything downstream.
"""
from . import rss


def collect(source):
    src = dict(source)
    src.setdefault("lane", "context")
    items = rss.collect(src)
    for it in items:
        it["lane"] = "context"
        it["author_role_hint"] = "podcast"
    return items
