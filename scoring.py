#!/usr/bin/env python3
"""
scoring.py: deterministic scoring over the model's structured synthesis output
(PROJECT_PLAN.md section 5). The model assigns items to themes; the arithmetic
lives here so the numbers are reproducible and never depend on model sampling.

  demand      = normalized weighted item frequency for the theme, where each item
                is weighted by lane, source, and exponential recency decay.
  velocity    = z-score of this week's raw count against the trailing mean.
  saturation  = how many Lane B sources already cover the theme, normalized to the
                busiest theme this window.
  opportunity = demand * (1 - saturation).

A theme enters the digest (is a "mover") if it is accelerating, new, or a gap
play; digest.py applies those rules. A theme whose became_post_at is within
suppress_if_became_post_within_days is marked suppressed and drops out. That is
the feedback loop that keeps the digest readable in month six.
"""
import math
import statistics
from datetime import date

import common

_EVIDENCE_CAP = 5
_VOCAB_CAP = 20


def _item_weight(item, config, today):
    lane_w = (config.get("lane_weights") or {}).get(item.get("lane", "question"), 1.0)
    src_w = (config.get("source_weights") or {}).get(item.get("source_id"), 1.0)
    half = config.get("decay_half_life_days", 45) or 45
    d = common.parse_date(item.get("published_at")) or common.parse_date(item.get("observed_at"))
    if d is None:
        decay = 1.0
    else:
        age = max(0, (today - d).days)
        decay = 0.5 ** (age / half)
    return lane_w * src_w * decay


def _trailing_weeks(week, n):
    """Return the n ISO-week labels immediately before `week`."""
    y, w = int(week[:4]), int(week.split("W")[1])
    out = []
    for _ in range(n):
        w -= 1
        if w < 1:
            y -= 1
            # 52 or 53 weeks; date.fromisocalendar validates, fall back to 52.
            try:
                date.fromisocalendar(y, 53, 1)
                w = 53
            except ValueError:
                w = 52
        out.append(f"{y}-W{w:02d}")
    return out


def _status(theme, demand, saturation, delta_z, week, config, model_watching):
    thr = config.get("thresholds", {})
    acc_z = thr.get("accelerating_z", 1.5)
    min_items = thr.get("new_theme_min_items", 3)
    gap_max = thr.get("gap_play_max_saturation", 0.2)
    suppress_days = config.get("suppress_if_became_post_within_days", 120)

    bp = theme.get("became_post_at")
    if bp:
        d = common.parse_date(bp)
        if d and (date.today() - d).days <= suppress_days:
            return "suppressed"

    current = theme.get("current", 0)
    if model_watching or (theme.get("first_seen", "") and
                          common.iso_week(theme["first_seen"]) == week and current < min_items):
        return "watching"
    if delta_z > acc_z:
        return "accelerating"
    if theme.get("first_seen", "") and common.iso_week(theme["first_seen"]) == week \
            and current >= min_items:
        return "new"
    if saturation < gap_max and demand >= 0.4:
        return "gap"
    return "steady"


def score(themes, model_output, new_items, config, week=None):
    """Return the updated themes registry (list). Pure over its inputs except for
    reading today's date via common."""
    week = week or common.iso_week()
    today = date.today()
    item_map = {it["id"]: it for it in new_items}
    by_id = {t.get("theme_id"): t for t in themes}

    touched = {}   # theme_id -> {"weighted": float, "cov": int, "watching": bool}

    for m in (model_output or {}).get("themes", []):
        tid = m.get("theme_id")
        if not tid:
            continue
        t = by_id.get(tid)
        if t is None:
            t = {
                "theme_id": tid,
                "label": m.get("label", tid),
                "first_seen": today.isoformat(),
                "counts_by_week": {},
                "evidence": [],
                "vocabulary": [],
                "became_post": None,
                "became_post_at": None,
            }
            by_id[tid] = t
            themes.append(t)
        t["label"] = m.get("label", t.get("label", tid))
        t.setdefault("first_seen", today.isoformat())
        t.setdefault("counts_by_week", {})

        assigned = [item_map[i] for i in m.get("item_ids", []) if i in item_map]
        raw = len(assigned)
        t["counts_by_week"][week] = t["counts_by_week"].get(week, 0) + raw
        weighted = sum(_item_weight(it, config, today) for it in assigned)

        # Evidence (verbatim buying questions) and vocabulary.
        ev = [{"quote": q.get("quote", ""), "url": q.get("url", ""),
               "source_id": q.get("source_id", "")}
              for q in (m.get("buying_questions") or []) if q.get("quote")]
        if ev:
            t["evidence"] = ev[:_EVIDENCE_CAP]
        vocab = list(dict.fromkeys((t.get("vocabulary") or []) + (m.get("vocabulary") or [])))
        t["vocabulary"] = vocab[:_VOCAB_CAP]
        t["covered_by_context"] = sorted(set(m.get("covered_by_context") or []))
        t["suggested_angle"] = m.get("suggested_angle", t.get("suggested_angle", ""))

        touched[tid] = {"weighted": weighted, "cov": len(t["covered_by_context"]),
                        "watching": bool(m.get("watching"))}

    # Every theme gets this week's count recorded (0 if untouched) so stale
    # movers naturally fall out of the digest.
    for t in themes:
        t.setdefault("counts_by_week", {})
        t["counts_by_week"].setdefault(week, 0)
        t["current"] = t["counts_by_week"][week]

    # Normalize demand and saturation across themes active this window.
    max_weighted = max([v["weighted"] for v in touched.values()], default=0.0)
    max_cov = max([v["cov"] for v in touched.values()], default=0)
    window_weeks = config.get("velocity_window_weeks", 6)

    for t in themes:
        tid = t.get("theme_id")
        info = touched.get(tid)
        weighted = info["weighted"] if info else 0.0
        cov = info["cov"] if info else 0
        watching = info["watching"] if info else False

        demand = (weighted / max_weighted) if max_weighted > 0 else 0.0
        saturation = (cov / max_cov) if max_cov > 0 else 0.0

        trailing = [t["counts_by_week"].get(w, 0) for w in _trailing_weeks(week, window_weeks)]
        if len([x for x in trailing]) >= 2 and statistics.pstdev(trailing) > 0:
            delta_z = (t["current"] - statistics.mean(trailing)) / statistics.pstdev(trailing)
        else:
            delta_z = 0.0

        t["trailing_mean"] = round(statistics.mean(trailing), 3) if trailing else 0.0
        t["delta_z"] = round(delta_z, 3)
        t["demand_score"] = round(demand, 3)
        t["saturation_score"] = round(saturation, 3)
        t["opportunity_score"] = round(demand * (1 - saturation), 3)
        t["status"] = _status(t, demand, saturation, delta_z, week, config, watching)

    return themes
