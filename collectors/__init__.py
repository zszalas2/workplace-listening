"""Adapter registry. Maps the `adapter` field in sources.yaml to a module that
exposes collect(source) -> list[raw_item].

Only Wave 0/1 adapters are wired up. Adapters named in sources.yaml but not yet
implemented (paa, reviews_capterra, podcast, sitemap_diff, ...) resolve to None
so run.py can skip them with a log line instead of crashing."""
from . import rss, hackernews, spiceworks, reddit_arctic

ADAPTERS = {
    "rss": rss,
    "hackernews": hackernews,
    "spiceworks": spiceworks,
    "reddit_arctic": reddit_arctic,
}


def get(name):
    return ADAPTERS.get(name)
