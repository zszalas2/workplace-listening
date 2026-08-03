#!/usr/bin/env python3
"""
trends.py: search-trends collector (PLACEHOLDER).

Tracks rising/steady search interest for the seed keywords, including the
Croissant category language ("workspace spend management") so we can see whether
it is being adopted (PROJECT_PLAN.md 6.1). Needs SerpApi, so this stays a clean
no-op until the credential is added.

Required secret (repo Actions secret, then listen-monthly.yml env):
  SERPAPI_KEY

Cadence: monthly.
"""
import os

import common  # noqa: F401  (used once fetch() is implemented)


def collect(source):
    if not os.environ.get("SERPAPI_KEY"):
        print(f"  - {source['id']}: Trends placeholder (awaiting SERPAPI_KEY secret)")
        return []
    # TODO(premium): query SerpApi Google Trends for config.queries; emit a
    # question-lane item per keyword carrying its interest delta in engagement,
    # so scoring can weight rising terms.
    print(f"  - {source['id']}: SERPAPI_KEY present but fetch() not implemented yet")
    return []
