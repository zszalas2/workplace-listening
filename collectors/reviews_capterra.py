#!/usr/bin/env python3
"""
reviews_capterra.py: Capterra review collector (PLACEHOLDER, Wave 3).

Approved for the private repo: scrape competitor review pages, backfill once, then
collect deltas. The Cons section and "Switched from" lines are the highest-signal
question-lane material (PROJECT_PLAN.md 6, 11). No paid API, but anti-bot makes it
fragile, so it is scoped to Wave 3 and left as a clean no-op scaffold here.

Never republish review prose verbatim in a public post; quote buying questions and
paraphrase complaints only (PROJECT_PLAN.md 11).

config: product_urls: [ ... ]     Cadence: monthly.
"""
import common  # noqa: F401  (used once fetch() is implemented)


def collect(source):
    # TODO(wave3): fetch each product's review pages, extract Cons + "Switched
    # from" as question-lane items with firmographics in engagement. Best-effort;
    # never let anti-bot failure fail the run.
    print(f"  - {source['id']}: Capterra reviews placeholder (Wave 3, not implemented)")
    return []
