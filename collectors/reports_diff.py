#!/usr/bin/env python3
"""
reports_diff.py: research-report page-diff collector (PLACEHOLDER, Wave 3).

Gensler, JLL, CBRE, Gallup, and Leesman publish findings on pages with no RSS.
The plan collects them by diffing the page over time and surfacing new stats as
Lane B context (PROJECT_PLAN.md 6). Clean no-op scaffold until Wave 3; the diff
baseline will live in state.json alongside the other per-source cursors.

config: url: <report/insights page>     Cadence: monthly.
"""
import common  # noqa: F401  (used once fetch() is implemented)


def collect(source):
    # TODO(wave3): fetch the page, compare against the stored hash/snapshot in
    # state, and emit a context item when the content changes, carrying the new
    # stats as claims. Best-effort.
    print(f"  - {source['id']}: reports diff placeholder (Wave 3, not implemented)")
    return []
