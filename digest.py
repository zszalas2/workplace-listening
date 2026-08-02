#!/usr/bin/env python3
"""
digest.py: render a weekly digest markdown file from a run.

Wave 0 renders a counts-only digest: items collected per source, lane
breakdown, and a taste of new titles. This proves the loop end to end before
synthesis exists (PROJECT_PLAN.md section 10, Wave 0). Once themes.json is
populated by synthesize.py (Wave 1), the movers section fills in above the
counts. The digest deliberately shows movers only, capped at digest_max_themes.

Style law: no em dashes anywhere in rendered content.
"""
import common


def _fmt_movers(themes, config):
    """Render the movers section. Empty until synthesis (Wave 1) exists."""
    if not themes:
        return ("_No theme synthesis yet. This is a counts-only Wave 0 digest; "
                "movers appear once synthesize.py is populating themes.json._\n")
    thr = config.get("thresholds", {})
    cap = thr.get("digest_max_themes", 8)
    acc_z = thr.get("accelerating_z", 1.5)
    gap_max = thr.get("gap_play_max_saturation", 0.2)
    min_items = thr.get("new_theme_min_items", 3)
    window = common.iso_week()

    def is_mover(t):
        if (t.get("delta_z") or 0) > acc_z:
            return True
        if t.get("first_seen", "") and common.iso_week(t.get("first_seen")) == window \
                and t.get("current", 0) >= min_items:
            return True
        if (t.get("saturation_score") or 1.0) < gap_max and (t.get("demand_score") or 0) >= 0.4:
            return True
        return False

    movers = [t for t in themes if is_mover(t) and t.get("status") != "watching"]
    movers.sort(key=lambda t: t.get("opportunity_score", 0), reverse=True)
    movers = movers[:cap]
    if not movers:
        return "_No movers this window._\n"

    lines = []
    for t in movers:
        lines.append(f"### {t.get('label', t.get('theme_id'))}")
        lines.append(f"- status: **{t.get('status', 'n/a')}** | "
                     f"opportunity {t.get('opportunity_score', 0):.2f} "
                     f"(demand {t.get('demand_score', 0):.2f}, "
                     f"saturation {t.get('saturation_score', 0):.2f})")
        for ev in (t.get("evidence") or [])[:3]:
            q = (ev.get("quote") or "").strip()
            lines.append(f"  - \"{q}\" [{ev.get('source_id', '')}]({ev.get('url', '')})")
        covered = t.get("covered_by_context") or []
        if covered:
            lines.append(f"- saturation read: already covered by {', '.join(covered)}")
        else:
            lines.append("- saturation read: no Lane B coverage found (open field)")
        angle = (t.get("suggested_angle") or "").strip()
        if angle:
            lines.append(f"- suggested angle: {angle}")
        lines.append("")
    return "\n".join(lines)


def _fmt_watching(themes):
    """One-line list of sub-threshold themes being watched."""
    watching = [t for t in themes if t.get("status") == "watching"]
    if not watching:
        return ""
    watching.sort(key=lambda t: t.get("current", 0), reverse=True)
    parts = [f"{t.get('label', t.get('theme_id'))} ({t.get('current', 0)})" for t in watching[:12]]
    return "_Watching: " + "; ".join(parts) + "._\n"


def build(run_summary, items_this_run, themes, config):
    week = common.iso_week()
    lines = [f"# Workplace listening digest {week}", ""]

    # Movers (empty in Wave 0).
    lines.append("## Movers")
    lines.append(_fmt_movers(themes, config))

    watching = _fmt_watching(themes)
    if watching:
        lines.append(watching)

    # Counts view.
    lines.append("## Run counts")
    lines.append("")
    by_source = {}
    by_lane = {"question": 0, "context": 0}
    for it in items_this_run:
        by_source[it["source_id"]] = by_source.get(it["source_id"], 0) + 1
        by_lane[it.get("lane", "question")] = by_lane.get(it.get("lane", "question"), 0) + 1

    lines.append(f"Total new items: **{len(items_this_run)}** "
                 f"(question {by_lane.get('question', 0)}, context {by_lane.get('context', 0)})")
    lines.append("")
    lines.append("| source | new items | status |")
    lines.append("| --- | ---: | --- |")
    for s in run_summary.get("sources", []):
        note = s.get("note", "ok")
        lines.append(f"| {s['id']} | {s.get('new', 0)} | {note} |")
    lines.append("")

    # Taste of new titles (question lane, most engaged first).
    lines.append("## New questions this run")
    lines.append("")
    q_items = [it for it in items_this_run if it.get("lane") == "question"]
    q_items.sort(key=lambda it: (it.get("engagement") or {}).get("comments", 0), reverse=True)
    if not q_items:
        lines.append("_None this run._")
    for it in q_items[:15]:
        eng = it.get("engagement") or {}
        c = eng.get("comments", 0)
        title = it.get("title", "").strip()
        lines.append(f"- [{title}]({it.get('url', '')}) ({it['source_id']}, {c} comments)")
    lines.append("")

    # Run summary line.
    r = run_summary
    lines.append("---")
    lines.append(f"_Run {r.get('run_id')}: {len(items_this_run)} new items across "
                 f"{r.get('sources_ok', 0)} sources, {r.get('sources_error', 0)} errors, "
                 f"{r.get('sources_skipped', 0)} skipped (adapter not built)._")
    return "\n".join(lines) + "\n"


def write(run_summary, items_this_run, themes, config):
    md = build(run_summary, items_this_run, themes, config)
    out = common.path("data", "digests", f"{common.iso_week()}.md")
    common.os.makedirs(common.os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(md)
    return out
