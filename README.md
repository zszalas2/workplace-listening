# workplace-listening

Two independent systems that share a repo but never share control flow.

- **Track 1, the Converter:** Croissant's own YouTube videos become SEO blog
  posts. Deterministic, one video in and one post out. Dedupes on `videoId` and
  nothing else.
- **Track 2, the Listener:** ~27 external sources are polled on staggered
  cadences, normalized into an append-only event log, scored for theme velocity
  and market saturation, and rendered into a movers-only weekly digest that
  becomes a queue of blog topics.

This is the recognizable sibling of
[`transition-watchlist`](https://github.com/zszalas2/transition-watchlist):
dependency-free collectors, `state.json` baselines and cursors, an append-only
JSONL as the single source of truth, `scoring_config.json` for tuning without
code changes, a weekly cron that commits its own output, and digests that show
**movers only**.

> The hard boundary: the Listener's novelty suppression must never gate the
> Converter. The Converter dedupes on `videoId` only. See `PROJECT_PLAN.md`
> section 1.

## Status

This repo currently implements **Track 2, Wave 0** plus the dependency-free
**Lane A** question collectors. The loop runs end to end: collect -> normalize
-> dedup -> append -> counts digest.

| Piece | State |
| --- | --- |
| Data contracts (items, context, themes, scoring) | defined (`PROJECT_PLAN.md` 4.x) |
| `collectors/rss.py` (serves ~12 Lane B sources) | built + tested |
| `collectors/hackernews.py` | built + tested |
| `collectors/spiceworks.py` | built + tested |
| `collectors/reddit_arctic.py` | built + tested |
| `normalize.py`, `digest.py` (counts-only), `run.py` | built + tested |
| Weekly / monthly workflows | written (see location note) |
| `synthesize.py` (themes, scoring, Issues) | **Wave 1, not built** |
| `summarize_context.py`, podcasts, YouTube detect, saturation | **Wave 2** |
| Reviews, PAA, Trends, report diffs | **Wave 3** |
| Track 1 Converter | **not built** (writes to the website repo; see below) |

Per the build sequence (`PROJECT_PLAN.md` section 10): stop after Wave 1's first
real digest and read the output before building more. Wave 0 exists to prove the
loop before adding intelligence.

## Location note

The plan calls for a standalone private repo named `workplace-listening`. This
directory is that project, staged inside `transition-watchlist` because the
current working session is scoped to that repo. It is self-contained and ready
to be extracted with `git subtree split` (or a plain copy) into its own repo.
Until then, the GitHub Actions workflows under `.github/workflows/` will not
fire, because GitHub only reads workflows at the repository root. Everything
runs locally via `python3 run.py` in the meantime.

## Running

No dependencies required (PyYAML is used if present, otherwise a small built-in
parser reads `sources.yaml`).

```bash
python3 run.py                      # weekly cadence (default)
python3 run.py --cadence monthly
python3 run.py --cadence all
python3 run.py --only reddit_sysadmin,hackernews
python3 run.py --limit 5            # cap sources (smoke test)
python3 run.py --dry-run            # do not write items.jsonl / state.json
python3 tests/test_pipeline.py      # offline parser + pipeline tests
```

A run collects each selected source, appends new normalized items to
`data/items.jsonl`, updates per-source cursors in `state.json`, and writes
`data/digests/YYYY-Www.md`. A dead or blocked source is logged and skipped,
never fatal.

### Network

Collectors need outbound HTTPS to the live feeds (Reddit via Arctic Shift, HN
Algolia, Spiceworks Discourse, and the RSS hosts). They are designed to run from
a GitHub Actions runner or a laptop. In a restricted sandbox those hosts may be
blocked by egress policy; the run still completes and writes a (zero-item)
digest, which is why the offline tests parse recorded fixtures instead of the
live network.

## Data contracts

The shapes in `PROJECT_PLAN.md` sections 4.1 to 4.4 are authoritative.
Collectors must not invent their own shapes.

- `data/items.jsonl` - append-only normalized signal items (Lane A + Lane B).
- `data/context/<source>/<id>.json` - Lane B summaries (Wave 2).
- `data/themes.json` - the movers engine, per-theme baselines (Wave 1).
- `scoring_config.json` - weights, decay, thresholds. Tune here, not in code.

Raw scraped text stays in `data/` because this repo is private indefinitely.
Never sync review prose or Reddit usernames to the website repo.

## Track 1 (Converter) and the datacenter IP problem

YouTube blocks caption/transcript requests from datacenter IPs, so the design is
**detection in CI, transcript extraction and post writing locally**. A cron
flags a new video and opens a GitHub Issue; a local Claude Code run pulls the
transcript from a residential IP and writes the post into the website repo's
content collection. The Converter is not built here yet, and it writes to the
website repo (out of scope for this session). See `PROJECT_PLAN.md` section 8.

## Secrets (for CI, Waves 1 and 3)

`ANTHROPIC_API_KEY` (synthesis), `DATAFORSEO_LOGIN` + `DATAFORSEO_PASSWORD` (or
`ALSOASKED_API_KEY`) for PAA, and `SERPAPI_KEY` for Trends. Paid-API budget is
approved at 50 to 100 USD per month.
