"""Adapter registry. Maps the `adapter` field in sources.yaml to a module that
exposes collect(source) -> list[raw_item].

Wave 0/1 adapters plus Wave 2 coverage (podcast, sitemap_diff, archive_scrape,
youtube_detect) are fully implemented. Premium/Wave 3 adapters (paa, trends,
reviews_*, reports_diff) are registered as clean no-op placeholders so their
sources run in the monthly cron without crashing and light up once their secrets
or scrapers are added."""
from . import (rss, hackernews, spiceworks, reddit_arctic, podcast,
               sitemap_diff, archive_scrape, youtube_detect,
               paa, trends, reviews_capterra, reviews_trustradius, reports_diff)

ADAPTERS = {
    "rss": rss,
    "hackernews": hackernews,
    "spiceworks": spiceworks,
    "reddit_arctic": reddit_arctic,
    "podcast": podcast,
    "sitemap_diff": sitemap_diff,
    "archive_scrape": archive_scrape,
    "youtube_detect": youtube_detect,
    # Premium / Wave 3 placeholders (no-op until wired):
    "paa": paa,
    "trends": trends,
    "reviews_capterra": reviews_capterra,
    "reviews_trustradius": reviews_trustradius,
    "reports_diff": reports_diff,
}


def get(name):
    return ADAPTERS.get(name)
