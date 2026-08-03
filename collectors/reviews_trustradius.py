#!/usr/bin/env python3
"""
reviews_trustradius.py: TrustRadius review collector (PLACEHOLDER, Wave 3).

Enterprise voice, 150-400 word reviews (PROJECT_PLAN.md 6). Same handling rules as
Capterra: private-repo scraping approved, never republish prose verbatim in a
public post. Clean no-op scaffold until Wave 3.

config: product_urls: [ ... ]     Cadence: monthly.
"""
import common  # noqa: F401  (used once fetch() is implemented)


def collect(source):
    # TODO(wave3): fetch product review pages; emit question-lane items from the
    # pros/cons and buying-context sections with firmographics in engagement.
    print(f"  - {source['id']}: TrustRadius reviews placeholder (Wave 3, not implemented)")
    return []
