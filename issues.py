#!/usr/bin/env python3
"""
issues.py: mirror digest movers into GitHub Issues (PROJECT_PLAN.md section 9).

Each mover theme opens or updates one Issue labeled `theme`, a `status:*` label,
and `wave1`. Issues are the editorial queue: when a post ships, a human closes
the Issue and writes became_post/became_post_at back into themes.json, which
activates suppression on the next run.

Best-effort and non-fatal by design. It runs only in CI where GITHUB_TOKEN and
GITHUB_REPOSITORY are set; locally (or on any failure) it no-ops. Dependency-free
raw HTTPS, consistent with the rest of the project.
"""
import json
import os
import urllib.error
import urllib.request

API = "https://api.github.com"
MARKER = "<!-- workplace-listening:theme_id={} -->"
_MOVER_STATUSES = ("new", "accelerating", "gap")


def _movers(themes, config):
    thr = config.get("thresholds", {})
    cap = thr.get("digest_max_themes", 8)
    movers = [t for t in themes if t.get("status") in _MOVER_STATUSES]
    movers.sort(key=lambda t: t.get("opportunity_score", 0), reverse=True)
    return movers[:cap]


def issue_body(theme):
    """Markdown body for a theme's Issue. Pure; unit-tested without network."""
    lines = [MARKER.format(theme.get("theme_id", "")), ""]
    lines.append(f"**Status:** {theme.get('status', 'n/a')}  |  "
                 f"**Opportunity:** {theme.get('opportunity_score', 0):.2f} "
                 f"(demand {theme.get('demand_score', 0):.2f}, "
                 f"saturation {theme.get('saturation_score', 0):.2f})")
    angle = (theme.get("suggested_angle") or "").strip()
    if angle:
        lines += ["", f"**Suggested angle:** {angle}"]
    ev = theme.get("evidence") or []
    if ev:
        lines += ["", "**Verbatim buying questions:**"]
        for e in ev[:3]:
            lines.append(f"- \"{(e.get('quote') or '').strip()}\" "
                         f"([{e.get('source_id', '')}]({e.get('url', '')}))")
    covered = theme.get("covered_by_context") or []
    lines += ["", f"**Saturation read:** "
              + ("already covered by " + ", ".join(covered) if covered
                 else "no Lane B coverage found (open field)")]
    vocab = theme.get("vocabulary") or []
    if vocab:
        lines += ["", "**Buyer vocabulary:** " + ", ".join(vocab[:12])]
    lines += ["", "_Close this Issue when a post ships, then set became_post / "
              "became_post_at in themes.json to activate suppression._"]
    return "\n".join(lines)


def issue_labels(theme):
    return ["theme", f"status:{theme.get('status', 'steady')}", "wave1"]


def _req(method, url, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "workplace-listening",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "null")


def _existing(repo, token):
    """Map theme_id -> issue number for issues we previously opened."""
    out = {}
    try:
        items = _req("GET", f"{API}/repos/{repo}/issues?state=all&labels=theme&per_page=100",
                     token) or []
    except Exception as e:  # noqa: BLE001
        print(f"  ! issues: list failed: {e}")
        return out
    for it in items:
        body = it.get("body") or ""
        marker = MARKER.format("")
        head = marker.split("=", 1)[0]  # "<!-- workplace-listening:theme_id"
        if head in body:
            frag = body.split(head + "=", 1)[1]
            tid = frag.split(" ", 1)[0].replace("-->", "").strip()
            if tid:
                out[tid] = it["number"]
    return out


def sync(themes, config, repo=None, token=None):
    """Open/update one Issue per mover theme. No-ops without credentials."""
    token = token or os.environ.get("GITHUB_TOKEN")
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("  - issues sync skipped (no GITHUB_TOKEN/GITHUB_REPOSITORY)")
        return 0
    existing = _existing(repo, token)
    n = 0
    for t in _movers(themes, config):
        tid = t.get("theme_id")
        title = f"[theme] {t.get('label', tid)}"
        payload = {"title": title, "body": issue_body(t), "labels": issue_labels(t)}
        try:
            if tid in existing:
                _req("PATCH", f"{API}/repos/{repo}/issues/{existing[tid]}", token,
                     {**payload, "state": "open"})
            else:
                _req("POST", f"{API}/repos/{repo}/issues", token, payload)
            n += 1
        except Exception as e:  # noqa: BLE001 - never fatal
            print(f"  ! issues: sync failed for {tid}: {e}")
    print(f"  issues: synced {n} theme(s)")
    return n
