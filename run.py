#!/usr/bin/env python3
"""
run.py: the Listener orchestrator. One entry point for the weekly and monthly
crons and for local runs.

  1. Load sources.yaml, scoring_config.json, state.json.
  2. Select sources by cadence.
  3. Collect each source concurrently (network bound). A dead source is logged
     and skipped, never fatal (PROJECT_PLAN.md section 13).
  4. Normalize + dedup sequentially, append new items to data/items.jsonl.
  5. Render the digest to data/digests/YYYY-Www.md.
  6. Update and save state.json.

Synthesis (Wave 1) will slot in between steps 4 and 5; for now the digest is
counts-only.

Usage:
  python3 run.py                      # weekly cadence (default)
  python3 run.py --cadence monthly
  python3 run.py --cadence all
  python3 run.py --only reddit_sysadmin,hackernews
  python3 run.py --limit 5           # cap number of sources (smoke test)
  python3 run.py --dry-run           # do not write items.jsonl / state.json
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import collectors
import common
import digest
import normalize
import relevance
import scoring
import summarize_context
import synthesize
try:
    import issues
except ImportError:  # issues module is optional
    issues = None


def select_sources(sources, cadence, only, limit):
    if only:
        wanted = set(only.split(","))
        sel = [s for s in sources if s["id"] in wanted]
    elif cadence == "all":
        sel = list(sources)
    else:
        sel = [s for s in sources if (s.get("cadence", "weekly") == cadence)]
    if limit:
        sel = sel[:limit]
    return sel


def collect_one(source):
    """Run one adapter. Returns (source, raw_items, error_str_or_None)."""
    adapter = collectors.get(source.get("adapter"))
    if adapter is None:
        return source, None, "skip:adapter-not-built"
    try:
        return source, adapter.collect(source), None
    except Exception as e:  # noqa: BLE001 - one source must not fail the run
        return source, None, f"error:{type(e).__name__}:{e}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cadence", default="weekly", choices=["weekly", "monthly", "all"])
    ap.add_argument("--only", default=None, help="comma-separated source ids")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    sources = common.load_yaml(common.SOURCES_PATH)
    config = common.load_json(common.SCORING_PATH, default={})
    state = common.load_json(common.STATE_PATH, default={"sources": {}, "runs": []})
    themes = common.load_json(common.THEMES_PATH, default=[])

    selected = select_sources(sources, args.cadence, args.only, args.limit)
    print(f"run {common.RUN_ID}: {len(selected)} sources ({args.cadence})")

    # Step 3: collect concurrently.
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(collect_one, selected))

    # Step 4: normalize + dedup sequentially (mutates state).
    all_new = []
    summary_rows = []
    ok = err = skipped = 0
    for source, raw_items, error in results:
        sid = source["id"]
        if error and error.startswith("skip:"):
            skipped += 1
            summary_rows.append({"id": sid, "new": 0, "note": "adapter not built"})
            print(f"  - {sid}: skipped ({error})")
            continue
        if error:
            err += 1
            summary_rows.append({"id": sid, "new": 0, "note": error[:60]})
            print(f"  ! {sid}: {error}")
            continue
        ok += 1
        fetched = len(raw_items or [])
        kept, off_topic = relevance.filter_source(raw_items or [], source, config)
        new_items, dup = normalize.normalize(kept, sid, state)
        all_new.extend(new_items)
        note = "ok"
        extra = []
        if dup:
            extra.append(f"{dup} dup")
        if off_topic:
            extra.append(f"{off_topic} off-topic")
        if extra:
            note = "ok (" + ", ".join(extra) + ")"
        summary_rows.append({"id": sid, "new": len(new_items), "note": note})
        print(f"  + {sid}: {len(new_items)} new ({dup} dup, {off_topic} off-topic, {fetched} fetched)")

    run_summary = {
        "run_id": common.RUN_ID,
        "cadence": args.cadence,
        "sources": summary_rows,
        "sources_ok": ok,
        "sources_error": err,
        "sources_skipped": skipped,
        "new_items": len(all_new),
    }

    # Step 4.5: summarize new Lane B items (Wave 2), then synthesis + scoring
    # (Wave 1). All best-effort: skipped without ANTHROPIC_API_KEY, in which case
    # the digest falls back to the counts-only view.
    context_summaries = summarize_context.summarize_items(all_new, themes, config)
    summaries_arg = context_summaries if context_summaries else None
    model_output = synthesize.synthesize(all_new, themes, config,
                                         context_summaries=summaries_arg)
    if model_output is not None:
        themes = scoring.score(themes, model_output, all_new, config,
                               context_summaries=summaries_arg)
        run_summary["themes_total"] = len(themes)
        run_summary["movers"] = sum(
            1 for t in themes if t.get("status") in ("new", "accelerating", "gap"))
        print(f"  synthesis: {len(themes)} themes, {run_summary['movers']} movers")

    if args.dry_run:
        print(f"\n[dry-run] would append {len(all_new)} items; not writing items.jsonl/state.json/themes.json")
    else:
        common.append_jsonl(common.ITEMS_PATH, all_new)
        state.setdefault("runs", []).append(run_summary)
        common.save_json(common.STATE_PATH, state)
        if model_output is not None:
            common.save_json(common.THEMES_PATH, themes)

    # Step 5: digest (always written so the loop is visible even on dry runs).
    out = digest.write(run_summary, all_new, themes, config)
    print(f"\ndigest: {out}")
    if issues is not None and model_output is not None and not args.dry_run:
        issues.sync(themes, config)
    print(f"done: {len(all_new)} new items, {ok} ok / {err} err / {skipped} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
