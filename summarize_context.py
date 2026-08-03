#!/usr/bin/env python3
"""
summarize_context.py: summarize Lane B (context) items at ingest (Wave 2).

Long-form sources (trade press, competitor blogs, podcast show notes) are
summarized once, when first seen, into data/context/<source>/<id>.json. This
fixes the token-mass imbalance the plan warns about (PROJECT_PLAN.md 4.2): twenty
Reddit threads lose to two podcast episodes on raw token count, so synthesis
would drown in context. Summarizing at ingest keeps weekly synthesis cost flat
and gives saturation something structured to score against.

Each summary carries topics_covered, drawn from the current theme registry, which
is what powers deterministic saturation in scoring.py. The summarizer therefore
receives the live theme list so its topic tags line up with themes.json.

Best-effort: needs ANTHROPIC_API_KEY; skipped otherwise. Idempotent: an item
whose summary file already exists is not re-summarized, so steady-state weekly
runs only pay for genuinely new context. Bulk volume is bounded per run.

Dependency-free raw-HTTPS call. Model is configurable via scoring_config.json
("context_summary_model"), defaulting to claude-opus-5; for high-volume weeks a
cheaper model (e.g. claude-sonnet-5) is a reasonable override.
"""
import json
import os

import common

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-opus-5"
TEXT_SNIPPET = 6000  # chars of item body sent to the summarizer

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "stat": {"type": "string"},
                    "attribution": {"type": "string"},
                },
                "required": ["claim", "stat", "attribution"],
                "additionalProperties": False,
            },
        },
        "vocabulary": {"type": "array", "items": {"type": "string"}},
        "topics_covered": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "claims", "vocabulary", "topics_covered"],
    "additionalProperties": False,
}

SYSTEM = (
    "You summarize long-form workplace-technology content (trade press, competitor "
    "blogs, podcast show notes) for a B2B listening pipeline covering visitor "
    "management, desk and room booking, hybrid/RTO policy, workplace analytics, and "
    "facilities. For each item:\n"
    "1. summary: a structured summary of 300 words or fewer.\n"
    "2. claims: notable factual claims, each with its stat (empty string if none) "
    "and attribution (who said it; empty string if unclear).\n"
    "3. vocabulary: the terms the piece uses, especially category or vendor language.\n"
    "4. topics_covered: which of the provided theme_ids this item covers. Use ONLY "
    "the given theme_ids; return an empty array if none apply. This drives "
    "saturation scoring, so be strict.\n"
    "Never use em dashes."
)


def _context_dir(source_id):
    return common.path("data", "context", source_id)


def summary_path(source_id, iid):
    return os.path.join(_context_dir(source_id), f"{iid}.json")


def already_summarized(item):
    return os.path.exists(summary_path(item["source_id"], item["id"]))


def build_prompt(item, themes):
    registry = [{"theme_id": t.get("theme_id"), "label": t.get("label"),
                 "vocabulary": (t.get("vocabulary") or [])[:8]} for t in themes]
    payload = {
        "theme_ids": [t.get("theme_id") for t in themes],
        "themes": registry,
        "item": {
            "source_id": item["source_id"],
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "text": (item.get("text") or "")[:TEXT_SNIPPET],
        },
    }
    return ("Summarize this item and tag it against the theme registry. Registry "
            "and item follow as JSON.\n\n" + json.dumps(payload, ensure_ascii=False))


def _extract_json(response):
    for block in response.get("content", []):
        if block.get("type") == "text" and block.get("text", "").strip():
            return json.loads(block["text"])
    raise ValueError("no text block in summary response")


def call_model(item, themes, config, api_key):
    model = config.get("context_summary_model", DEFAULT_MODEL)
    body = {
        "model": model,
        "max_tokens": config.get("context_summary_max_tokens", 4000),
        "system": SYSTEM,
        "output_config": {
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": config.get("context_summary_effort", "low"),
        },
        "messages": [{"role": "user", "content": build_prompt(item, themes)}],
    }
    try:
        resp = common.post_json(API_URL, body, {
            "x-api-key": api_key, "anthropic-version": "2023-06-01"})
    except Exception as e:  # noqa: BLE001 - never fatal
        print(f"  ! summary call failed for {item['id']}: {e}")
        return None
    if resp.get("stop_reason") == "refusal":
        return None
    try:
        return _extract_json(resp)
    except Exception as e:  # noqa: BLE001
        print(f"  ! summary parse failed for {item['id']}: {e}")
        return None


def summarize_items(context_items, themes, config, api_key=None, call=None, write=True):
    """Summarize new Lane B items. Returns the list of summary dicts produced this
    run (data contract 4.2). Idempotent and bounded per run."""
    if call is None:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  - context summaries skipped (no ANTHROPIC_API_KEY)")
            return []
        call = call_model

    todo = [it for it in context_items
            if it.get("lane") == "context" and not already_summarized(it)]
    cap = config.get("max_context_summaries_per_run", 40)
    dropped = 0
    if len(todo) > cap:
        dropped = len(todo) - cap
        todo = todo[:cap]

    out = []
    for it in todo:
        res = call(it, themes, config, api_key)
        if not res:
            continue
        summary = {
            "id": it["id"],
            "source_id": it["source_id"],
            "url": it.get("url", ""),
            "published_at": it.get("published_at"),
            "observed_at": it.get("observed_at") or common.RUN_ID,
            "summary": res.get("summary", ""),
            "claims": res.get("claims", []),
            "vocabulary": res.get("vocabulary", []),
            "topics_covered": res.get("topics_covered", []),
        }
        if write:
            common.save_json(summary_path(it["source_id"], it["id"]), summary)
        out.append(summary)

    if dropped:
        print(f"  ! context summaries capped: {dropped} item(s) not summarized this run")
    print(f"  summarized {len(out)} context item(s)")
    return out
