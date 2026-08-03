#!/usr/bin/env python3
"""
detect.py: Track 1 Converter detection (CI half only).

Detects new Croissant videos worth turning into a blog post, appends them to
data/video_queue.jsonl, and opens a GitHub Issue per video. It does NOT write
posts: transcript extraction and drafting run locally against the website repo,
because YouTube blocks transcripts from datacenter IPs (PROJECT_PLAN.md 7, 8).

The hard boundary (PROJECT_PLAN.md 1): this path dedupes on videoId ONLY. The
Listener's theme suppression must never gate it, so nothing here imports the
theme registry.

Duration (needed for the <10 min filter) is not in the RSS feed. If
YOUTUBE_API_KEY is set we resolve it via the Data API; otherwise the video is
queued with duration unknown and the Issue asks a human to judge, rather than
silently dropping it.

Run: python3 converter/detect.py   (wired in .github/workflows/yt-detect.yml)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import common          # noqa: E402
import issues          # noqa: E402
from collectors import youtube_detect  # noqa: E402

CHANNEL_ID = "UCfyBWT0jp_WGJrMVG9rnFhw"  # Croissant Workspace
MIN_DURATION_SECONDS = 600               # ~10 min; shorts/recaps below this
QUEUE_PATH = common.path("data", "video_queue.jsonl")

# Already processed / deliberately skipped (PROJECT_PLAN.md section 8).
SKIP_IDS = {
    "g2qEjH8SwhI", "CIahBVLQD0Q", "VYiwsMs90Bw", "Jn3aIEJqd0s", "vOJTUoYM02M",
    "rVC_Y67-qnQ", "hjZ7gvppE0Q", "6KpRfDy1WII", "YgacXHn0Bbc", "okWXpFu5oIU",
}


def _queued_ids():
    return {r.get("video_id") for r in common.read_jsonl(QUEUE_PATH)}


def _iso8601_seconds(s):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def _duration_seconds(video_id):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None
    url = ("https://www.googleapis.com/youtube/v3/videos"
           f"?part=contentDetails&id={video_id}&key={key}")
    data = common.get_json(url)
    try:
        iso = data["items"][0]["contentDetails"]["duration"]
    except (TypeError, KeyError, IndexError):
        return None
    return _iso8601_seconds(iso)


def _qualifies(duration):
    """Return (include, reason). Unknown duration is included for human judgment."""
    if duration is None:
        return True, "duration unknown (no YOUTUBE_API_KEY); human to confirm length"
    if duration >= MIN_DURATION_SECONDS:
        return True, f"{duration // 60}m {duration % 60}s"
    return False, f"under 10 min ({duration // 60}m {duration % 60}s); skipped unless a customer story"


def _issue_body(v, duration, reason):
    return "\n".join([
        f"**Video:** [{v['title']}]({v['url']})",
        f"**Video ID:** `{v['video_id']}`",
        f"**Published:** {v.get('published', 'unknown')}",
        f"**Duration:** {reason}",
        "",
        "Detected by the Converter (Track 1). Transcript extraction and post "
        "drafting happen locally in the website repo, not here. When the post "
        "ships, close this Issue.",
        "",
        "Reminder: skip videos under ~10 minutes unless it is a customer story.",
    ])


def detect(open_issues=True):
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    raw = common.get(youtube_detect.FEED.format(CHANNEL_ID))
    videos = youtube_detect.parse_videos(raw)
    processed = SKIP_IDS | _queued_ids()

    new_rows = []
    for v in videos:
        vid = v["video_id"]
        if vid in processed:
            continue
        duration = _duration_seconds(vid)
        include, reason = _qualifies(duration)
        if not include:
            print(f"  - skip {vid}: {reason}")
            continue
        row = {
            "video_id": vid,
            "url": v["url"],
            "title": v["title"],
            "published": v.get("published", ""),
            "duration_seconds": duration,
            "reason": reason,
            "detected_at": common.RUN_ID,
        }
        new_rows.append(row)
        if open_issues and repo and token:
            issues.open_issue(repo, token, f"New video ready: {v['title']}",
                              _issue_body(v, duration, reason), labels=["converter"])
        print(f"  + queued {vid}: {v['title']}")

    common.append_jsonl(QUEUE_PATH, new_rows)
    print(f"detect: {len(new_rows)} new video(s) queued")
    return new_rows


if __name__ == "__main__":
    detect()
