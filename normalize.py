#!/usr/bin/env python3
"""
normalize.py: any collector output -> the data/items.jsonl contract.

Collectors emit "raw items" in a shared intermediate shape. normalize() stamps
the identity fields (id, observed_at, run_id), fills contract defaults, and drops
items already seen (per-source seen ids live in state.json). Deduping here, not
in each collector, keeps the boundary in one place.

items.jsonl contract (PROJECT_PLAN.md 4.1):
  id, source_id, lane, native_id, url, title, text, published_at,
  observed_at, author_role_hint, geo_hint, engagement, run_id
"""
import common

_SEEN_CAP = 5000  # cap seen-id history per source so state.json stays bounded


def _contract(raw, run_id):
    sid = raw["source_id"]
    native = str(raw.get("native_id", ""))
    return {
        "id": common.item_id(sid, native),
        "source_id": sid,
        "lane": raw.get("lane", "question"),
        "native_id": native,
        "url": raw.get("url", ""),
        "title": raw.get("title", ""),
        "text": raw.get("text", ""),
        "published_at": raw.get("published_at"),
        "observed_at": run_id,
        "author_role_hint": raw.get("author_role_hint"),
        "geo_hint": raw.get("geo_hint"),
        "engagement": raw.get("engagement") or {},
        "run_id": run_id,
    }


def normalize(raw_items, source_id, state, run_id=None):
    """Return (new_items, n_seen_skipped). Mutates state's per-source seen list."""
    run_id = run_id or common.RUN_ID
    src_state = state.setdefault("sources", {}).setdefault(source_id, {})
    seen = set(src_state.get("seen", []))
    new_items = []
    skipped = 0
    batch_seen = set()
    for raw in raw_items:
        item = _contract(raw, run_id)
        iid = item["id"]
        if iid in seen or iid in batch_seen:
            skipped += 1
            continue
        batch_seen.add(iid)
        new_items.append(item)
    # Update seen history, newest last, capped.
    combined = src_state.get("seen", []) + [i["id"] for i in new_items]
    src_state["seen"] = combined[-_SEEN_CAP:]
    return new_items, skipped
