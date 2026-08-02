#!/usr/bin/env python3
"""
relevance.py: a cheap keyword gate that drops off-topic items before they reach
items.jsonl and synthesis.

The first live run showed question sources returning noise: Spiceworks Discourse
search surfaces product-catalog threads ("Google Chrome", "Microsoft Windows 7
Pro"), and HN Algolia ranks loosely enough to admit euro banknote design. Both
are fetched by query but the query term need not actually appear in the result,
so we re-check that at least one workplace-vocabulary keyword is present in the
title or text.

Applied to question-lane items by default. Context (Lane B) feeds are already
topical, so they pass untouched unless a source opts in with `relevance: true`.
A source can force the gate off with `relevance: false` (e.g. Reddit, already
query-targeted). Keywords live in scoring_config.json so tuning needs no code
change.
"""


def is_relevant(item, keywords):
    hay = f"{item.get('title', '')} {item.get('text', '')}".lower()
    return any(k in hay for k in keywords)


def filter_source(raw_items, source, config):
    """Return (kept_items, dropped_count)."""
    rel = (config or {}).get("relevance") or {}
    if not rel.get("enabled", True):
        return raw_items, 0
    keywords = [k.lower() for k in rel.get("keywords", [])]
    if not keywords:
        return raw_items, 0

    mode = (source.get("config") or {}).get("relevance")  # True | False | None
    lane = source.get("lane", "question")
    # Reddit is fetched per subreddit+query, so results are already on-topic and
    # the source is sparse; do not risk dropping real signal there by default.
    already_targeted = source.get("adapter") in ("reddit_arctic",)
    default_on = lane == "question" and not already_targeted
    apply_gate = (mode is True) or (mode is None and default_on)
    if not apply_gate:
        return raw_items, 0

    kept = [it for it in raw_items if is_relevant(it, keywords)]
    return kept, len(raw_items) - len(kept)
