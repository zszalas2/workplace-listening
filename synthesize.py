#!/usr/bin/env python3
"""
synthesize.py: turn a run's new signal into an updated theme registry (Wave 1).

One Claude API call does the judgment the plan reserves for the model
(PROJECT_PLAN.md section 9):

  1. Assign each new Lane A (question) item to an existing theme or propose a new
     one. Assignment is strongly preferred; an unbounded registry is a failed
     registry.
  2. Extract the literal buying question, quoted verbatim with its source URL.
  3. Note the vocabulary buyers actually use.
  4. Mark, per theme, which Lane B (context) sources already cover it (saturation).
  5. Flag sub-threshold themes as `watching` rather than promoting them.

The model returns structured JSON only. All scoring arithmetic is deterministic
Python in scoring.py, never asked of the model, so the numbers are reproducible.

Dependency-free house style: the project runs on a bare runner with no pip
install and the CI job is `python3 run.py`, so the Anthropic call goes over raw
HTTPS via urllib rather than the SDK. Model id is configurable in
scoring_config.json ("synthesis_model"), defaulting to claude-opus-5.
"""
import json
import os
import urllib.error
import urllib.request

import common

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-opus-5"
CONTEXT_SNIPPET = 400   # chars of Lane B text shown to the model per item
QUESTION_SNIPPET = 600  # chars of Lane A text shown to the model per item

# Structured-output schema: the model must return exactly this shape. Scoring
# consumes it; the model is never asked to compute a score.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme_id": {"type": "string"},
                    "label": {"type": "string"},
                    "is_new": {"type": "boolean"},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "buying_questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string"},
                                "item_id": {"type": "string"},
                            },
                            "required": ["quote", "item_id"],
                            "additionalProperties": False,
                        },
                    },
                    "vocabulary": {"type": "array", "items": {"type": "string"}},
                    "covered_by_context": {"type": "array", "items": {"type": "string"}},
                    "suggested_angle": {"type": "string"},
                    "watching": {"type": "boolean"},
                },
                "required": ["theme_id", "label", "is_new", "item_ids",
                             "buying_questions", "vocabulary", "covered_by_context",
                             "suggested_angle", "watching"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["themes"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are the synthesis stage of a B2B workplace-technology listening pipeline. "
    "The buyer space is visitor management, desk and room booking, hybrid/RTO "
    "policy, workplace analytics, and facilities. You receive the current theme "
    "registry plus this run's new items in two lanes: question (short, literal "
    "buyer questions) and context (long-form trade press, competitor blogs). "
    "Your job:\n"
    "1. Assign every question item to an existing theme when one fits; only "
    "propose a new theme when nothing fits. Strongly prefer assignment. Reuse the "
    "exact theme_id of an existing theme you assign to.\n"
    "2. For each theme, extract up to three literal buying questions, quoted "
    "verbatim from the item text or title. Cite each one with the item_id of the "
    "exact item it came from (the id field of that item). Do not invent or "
    "cross-reference ids; the url and source are resolved from the item_id.\n"
    "3. List the vocabulary buyers actually use, especially where it differs from "
    "vendor language.\n"
    "4. In covered_by_context, list the source_ids of context items that already "
    "cover the theme (this feeds saturation).\n"
    "5. Set watching=true for a genuinely emerging theme with too little signal to "
    "promote yet.\n"
    "6. suggested_angle: one sentence on the content angle for Croissant "
    "(workspace spend management, HR-led buyer).\n"
    "Return every theme that has new items this run. Do not compute scores. "
    "Never use em dashes in any text you write."
)


def _slug(raw_items):
    return {it["id"]: it for it in raw_items}


def _lane_block(items, lane, snippet):
    rows = []
    for it in items:
        if it.get("lane") != lane:
            continue
        text = (it.get("text") or "").strip()[:snippet]
        rows.append({
            "id": it["id"],
            "source_id": it["source_id"],
            "url": it.get("url", ""),
            "title": it.get("title", ""),
            "text": text,
            "engagement": it.get("engagement") or {},
        })
    return rows


def build_prompt(new_items, themes):
    """Assemble the user message payload the model synthesizes over."""
    registry = [
        {"theme_id": t.get("theme_id"), "label": t.get("label"),
         "vocabulary": (t.get("vocabulary") or [])[:12]}
        for t in themes
    ]
    payload = {
        "current_themes": registry,
        "new_question_items": _lane_block(new_items, "question", QUESTION_SNIPPET),
        "new_context_items": _lane_block(new_items, "context", CONTEXT_SNIPPET),
    }
    return (
        "Current theme registry and this run's new items follow as JSON. Assign "
        "the question items, extract verbatim buying questions, note vocabulary and "
        "context coverage, and flag emerging themes as watching.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _post(body, api_key, timeout=120):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _extract_json(response):
    """Pull the JSON text block out of a Messages API response. With thinking on,
    content may lead with a thinking block, so scan for the text block."""
    for block in response.get("content", []):
        if block.get("type") == "text" and block.get("text", "").strip():
            return json.loads(block["text"])
    raise ValueError("no text block in model response")


def call_model(new_items, themes, config, api_key):
    """Real Anthropic call. Returns the parsed {"themes": [...]} dict, or None on
    any failure (synthesis is best-effort; the digest falls back to counts-only)."""
    model = config.get("synthesis_model", DEFAULT_MODEL)
    body = {
        "model": model,
        "max_tokens": config.get("synthesis_max_tokens", 20000),
        "system": SYSTEM,
        "output_config": {
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            "effort": config.get("synthesis_effort", "medium"),
        },
        "messages": [{"role": "user", "content": build_prompt(new_items, themes)}],
    }
    try:
        resp = _post(body, api_key)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300] if hasattr(e, "read") else ""
        print(f"  ! synthesis HTTP {e.code}: {detail}")
        return None
    except Exception as e:  # noqa: BLE001 - never fatal
        print(f"  ! synthesis call failed: {e}")
        return None
    if resp.get("stop_reason") == "refusal":
        print("  ! synthesis refused by safety classifier; skipping")
        return None
    try:
        return _extract_json(resp)
    except Exception as e:  # noqa: BLE001
        print(f"  ! synthesis parse failed: {e}")
        return None


def synthesize(new_items, themes, config, api_key=None, call=None):
    """Return the model's {"themes": [...]} assignment, or None to skip synthesis.

    `call` is injectable so tests exercise the assembly and downstream scoring
    without a network call. In production it defaults to the live Anthropic call
    and requires ANTHROPIC_API_KEY.
    """
    if call is None:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  - synthesis skipped (no ANTHROPIC_API_KEY)")
            return None
        call = call_model
    question_items = [it for it in new_items if it.get("lane") == "question"]
    if not question_items:
        print("  - synthesis skipped (no new question items)")
        return None
    return call(new_items, themes, config, api_key)
