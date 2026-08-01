# Workplace Listening & Content Pipeline — Project Plan

**For:** Claude Code, executing in a new private repo `workplace-listening` plus the existing Croissant website repo
**Written:** 2026-07-31
**Status:** Ready to build. Read this whole file before writing code.

---

## 0. Style law for this project

The Croissant style law applies to all article content: **no em dashes anywhere in published posts.** This plan document follows the same rule so there is no ambiguity about what "matching the voice" means. Use commas, colons, parentheses, or a full stop instead.

---

## 1. What we are building

Two independent systems that share a repo but never share control flow.

**Track 1: the Converter.** Croissant's own YouTube videos become SEO blog posts. Deterministic, unconditional, one video in and one post out. This already runs as a scheduled Cowork task and is being migrated to Claude Code so posts land directly in the website repo instead of a Drive queue.

**Track 2: the Listener.** Roughly 27 external sources are polled on staggered cadences, normalized into an append-only event log, scored for theme velocity and market saturation, and rendered into a movers-only weekly digest that becomes a queue of blog topics.

### The hard boundary

These two tracks must not be merged, and specifically the Listener's novelty suppression must never gate the Converter.

Webinar posts exist for SEO, speaker relations, and partner reach. Skipping a webinar because a previous post covered similar ground is a bug, not deduplication. The Converter dedupes on `videoId` and nothing else. If you find yourself writing a code path where a theme registry can cause a video to be skipped, you have violated the boundary.

---

## 2. Reference implementation

`github.com/zszalas2/transition-watchlist` is the house pattern for this class of system, and the Listener should be recognizably its sibling. Read `collector.py` and the README there before designing anything. The conventions worth carrying over:

- A dependency-free collector that runs anywhere with outbound HTTPS, in GitHub Actions or on a laptop.
- `state.json` holding per-entity baselines and cursors, so every run is a diff against the last.
- An append-only `events.jsonl` as the single source of truth, with scores and digests treated as views over it rather than stored state.
- `scoring_config.json` for weights, decay windows, and thresholds, so tuning never requires a code change.
- A weekly GitHub Actions cron that commits its own output back to the repo.
- Digests that show **movers only**, not the full standing picture.
- A human feedback loop that writes labels back into the event log (`outcome_label` there, `became_post` here).

The movers-only principle is the single most important inheritance. Without it, every weekly digest rediscovers that people dislike managing desks in spreadsheets. With it, the digest surfaces only what is new or accelerating against a trailing baseline.

---

## 3. Repo layout

```
workplace-listening/                 (new, private)
├── README.md
├── PROJECT_PLAN.md                  this file
├── sources.yaml                     source registry: id, lane, cadence, adapter, config
├── scoring_config.json              weights, decay, thresholds
├── state.json                       per-source cursors, baselines, seen hashes
├── collectors/
│   ├── rss.py                       generic; serves ~12 sources
│   ├── reddit_arctic.py             Arctic Shift API
│   ├── spiceworks.py                Discourse JSON
│   ├── hackernews.py                Algolia API
│   ├── sitemap_diff.py              Envoy, OfficeSpace
│   ├── archive_scrape.py            The Assist
│   ├── reviews_capterra.py
│   ├── reviews_trustradius.py
│   ├── paa.py                       DataForSEO or AlsoAsked
│   ├── trends.py                    SerpApi
│   ├── podcast.py                   RSS plus enclosure fetch
│   ├── reports_diff.py              Gensler, JLL, CBRE, Gallup, Leesman
│   └── youtube_detect.py            RSS detection only, no transcripts
├── normalize.py                     any collector output → items.jsonl
├── summarize_context.py             Lane B long-form → structured summaries
├── synthesize.py                    items + context → themes.json
├── digest.py                        themes → markdown + GitHub Issues
├── converter/
│   ├── detect.py                    shared with youtube_detect.py
│   └── WRITING_GUIDE.md             the post spec, see section 8
├── data/
│   ├── items.jsonl                  append-only, normalized signal items
│   ├── context/<source>/<id>.json   per-episode and per-article summaries
│   ├── themes.json                  rolling theme registry with baselines
│   ├── video_queue.jsonl            converter handoff
│   └── digests/YYYY-Www.md
└── .github/workflows/
    ├── listen-weekly.yml
    ├── listen-monthly.yml
    └── yt-detect.yml
```

Raw scraped text stays in this repo because it is private indefinitely. If that ever changes, `data/` is the directory to scrub. Do not put review prose or Reddit usernames anywhere that syncs to the website repo.

---

## 4. Data contracts

Define these first and do not let collectors invent their own shapes.

### 4.1 `data/items.jsonl` — normalized signal item

```json
{
  "id": "sha1(source_id + ':' + native_id)",
  "source_id": "reddit_sysadmin",
  "lane": "question",
  "native_id": "1oepsxb",
  "url": "https://reddit.com/r/sysadmin/comments/1oepsxb/...",
  "title": "What visitor management system are you guys using?",
  "text": "full body, comments concatenated where cheap to get",
  "published_at": "2025-10-20",
  "observed_at": "2026-07-31",
  "author_role_hint": "IT admin",
  "geo_hint": "US",
  "engagement": { "comments": 20, "score": 45 },
  "run_id": "2026-07-31"
}
```

`lane` is either `question` or `context`, and it determines everything downstream. Question sources are short, high volume, and literal. Context sources are long form. Never let them into the same synthesis prompt raw.

### 4.2 `data/context/<source>/<id>.json` — Lane B summary

Long-form sources get summarized at ingest, not at synthesis time. A single podcast transcript runs past 8,000 words, and twenty Reddit threads lose to two episodes on token mass alone. Summarizing at ingest fixes the imbalance and keeps weekly synthesis cost flat.

```json
{
  "id": "...", "source_id": "podcast_workplace_innovator",
  "url": "...", "published_at": "2026-07-28",
  "summary": "≤300 words, structured",
  "claims": [
    { "claim": "Seat allocation is now over-provisioned", "stat": "111% ratio", "attribution": "CBRE 2026" }
  ],
  "vocabulary": ["structured hybrid", "seat allocation ratio", "neighborhood model"],
  "topics_covered": ["desk-booking-utilization", "rto-mandate-enforcement"]
}
```

`topics_covered` is what powers saturation scoring. It must use the same theme vocabulary as `themes.json`, so the summarizer receives the current theme list as part of its prompt.

### 4.3 `data/themes.json` — the movers engine

```json
{
  "theme_id": "visitor-mgmt-access-control-integration",
  "label": "Visitor management that actually integrates with access control",
  "first_seen": "2026-06-01",
  "counts_by_week": { "2026-W24": 3, "2026-W25": 2, "2026-W31": 9 },
  "trailing_mean": 2.4,
  "current": 9,
  "delta_z": 2.8,
  "status": "accelerating",
  "demand_score": 0.81,
  "saturation_score": 0.10,
  "opportunity_score": 0.73,
  "evidence": [{ "url": "...", "quote": "...", "source_id": "reddit_sysadmin" }],
  "became_post": null,
  "became_post_at": null
}
```

### 4.4 `scoring_config.json`

```json
{
  "decay_half_life_days": 45,
  "velocity_window_weeks": 6,
  "lane_weights": { "question": 1.0, "context": 0.35 },
  "source_weights": {
    "paa": 1.3, "capterra_cons": 1.2, "reddit_sysadmin": 1.0,
    "spiceworks": 1.0, "trustradius_cons": 1.1, "hackernews": 0.6
  },
  "saturation_sources": ["trade_press", "competitor_blogs", "podcasts"],
  "thresholds": {
    "accelerating_z": 1.5,
    "new_theme_min_items": 3,
    "digest_max_themes": 8,
    "gap_play_max_saturation": 0.2
  },
  "suppress_if_became_post_within_days": 120
}
```

---

## 5. The scoring model

This is where the two lanes pay off, and it is the part worth getting right.

**Demand** comes from Lane A: weighted item frequency for the theme, with exponential recency decay, plus velocity measured as a z-score against the trailing six-week mean. PAA carries the highest source weight because it is literal, measurable search demand rather than inferred interest.

**Saturation** comes from Lane B: how many trade press articles, competitor blog posts, and podcast episodes in the window already cover this theme, normalized against the busiest theme in the window.

**Opportunity = demand × (1 − saturation).**

A theme enters the digest if any of these is true:

1. `delta_z > accelerating_z` (it is moving)
2. `first_seen` is inside the current window and `item_count >= new_theme_min_items` (it is new)
3. `saturation_score < gap_play_max_saturation` and demand is at least moderate (the gap play: real questions, nobody answering them)

A theme is suppressed if `became_post_at` is within `suppress_if_became_post_within_days`. That is the feedback loop, and it is the reason the digest stays readable in month six.

Cap the digest at eight themes. A digest that lists everything is the standing picture again, which is the failure mode we are designing against.

---

## 6. Source registry

`sources.yaml`, one entry per source. Structure:

```yaml
- id: reddit_sysadmin
  lane: question
  adapter: reddit_arctic
  cadence: weekly
  config:
    subreddit: sysadmin
    queries: ["visitor management", "desk booking", "room booking", "hoteling", "space management"]
    min_comments: 3
```

### Lane A, question sources

| id | adapter | cadence | notes |
|---|---|---|---|
| `reddit_sysadmin` | reddit_arctic | weekly | highest yield; 978k members, recurring RFP threads |
| `reddit_k12sysadmin` | reddit_arctic | weekly | visitor management as school security |
| `reddit_msp`, `reddit_itmanagers` | reddit_arctic | weekly | specifiers and buyers |
| `reddit_facilitymanagement` | reddit_arctic | weekly | small (4.8k) but high precision |
| `reddit_executiveassistants`, `reddit_adminassistant` | reddit_arctic | weekly | room booking and visitor logistics daily |
| `reddit_humanresources`, `reddit_humanresourcesuk` | reddit_arctic | weekly | HR flank, UK coverage |
| `spiceworks` | spiceworks | weekly | open Discourse JSON, `/search.json?q=` verified working |
| `hackernews` | hackernews | weekly | free Algolia API, RTO and hybrid discourse |
| `paa_seed_keywords` | paa | monthly | highest source weight; seed list in section 6.1 |
| `capterra_reviews` | reviews_capterra | monthly | backfill once, then deltas; Cons + "Switched from" |
| `trustradius_reviews` | reviews_trustradius | monthly | enterprise voice, 150-400 word reviews |

Do not attempt IWFM's member forum or IFMA Engage programmatically. Both are behind login and are human-monitored, not collected.

### Lane B, context sources

| id | adapter | cadence | notes |
|---|---|---|---|
| `allwork_space` | rss | weekly | `allwork.space/feed/` |
| `workplace_insight` | rss | weekly | `workplaceinsight.net/feed/`, UK/EU |
| `worktech_academy` | rss | weekly | `worktechacademy.com/feed/` |
| `charter` | rss | weekly | `charterworks.com/feed`, Work Tech reviews |
| `work_design_mag` | rss | weekly | `workdesign.com/feed/` |
| `fmlink` | rss | weekly | `fmlink.com/feed/` |
| `facilitiesnet` | rss | weekly | per-segment feeds at `facilitiesnet.com/rss/` |
| `worklife_news` | rss | weekly | `worklife.news/feed/` |
| `raconteur` | rss | weekly | keyword-filtered |
| `facility_executive` | rss | weekly | direct feed returns 403 Cloudflare; use Google News RSS proxy |
| `hr_brew` | rss | weekly | no public RSS; Google News proxy or sitemap |
| `the_assist` | archive_scrape | weekly | no RSS; paginated public archive |
| `competitor_robin` | rss | weekly | `robinpowered.com/blog/rss.xml` |
| `competitor_envoy`, `competitor_officespace` | sitemap_diff | weekly | no RSS; poll sitemap, fetch new URLs |
| `podcast_workplace_innovator` | podcast | weekly | `workplaceinnovator.libsyn.com/rss`, guests are the ICP |
| `podcast_workplace_geeks` | podcast | weekly | `feeds.buzzsprout.com/1933353.rss` |
| `podcast_dwg_impact` | podcast | weekly | `feeds.acast.com/public/shows/5f5b6f3c39b79b4f9afc8812`, transcripts in feed |
| `podcast_connected_fm` | podcast | weekly | IFMA World Workplace sessions released free |
| `yt_ifma`, `yt_worktech`, `yt_running_remote` | rss + local transcript | weekly detect | see section 7 on the IP problem |
| `trends_seed_keywords` | trends | monthly | SerpApi |
| `reports_gensler`, `reports_jll`, `reports_cbre`, `reports_gallup`, `reports_leesman` | reports_diff | monthly | page diffing, no RSS available |

### 6.1 Seed keywords for PAA and Trends

Start here and let the theme registry expand it: desk booking software, hot desking software, room booking system, meeting room scheduling, visitor management system, visitor sign in app, office occupancy sensors, workplace analytics software, hybrid work policy, return to office policy, office attendance tracking, workspace management software, flex office software, coworking access for employees, workspace spend management.

That last one is Croissant positioning. Track it deliberately so you can see whether the category language is being adopted.

---

## 7. Workflows and the datacenter IP problem

Three crons.

**`yt-detect.yml`** runs twice weekly. RSS only, no transcript work. Reads `https://www.youtube.com/feeds/videos.xml?channel_id=UCfyBWT0jp_WGJrMVG9rnFhw`, resolves duration via oEmbed or the Data API (RSS does not carry duration), applies the filters in section 8, appends qualifying videos to `data/video_queue.jsonl`, and opens a GitHub Issue titled `New video ready: <title>`.

**`listen-weekly.yml`** runs Mondays 11:00 UTC, matching the transition-watchlist convention so both digests are ready before the workweek. Runs all weekly-cadence collectors, normalizes, summarizes new Lane B items, runs synthesis, writes `data/digests/YYYY-Www.md`, and opens or updates GitHub Issues for digest themes.

**`listen-monthly.yml`** runs on the 1st. Reviews, PAA, Trends, and research report diffs, then triggers synthesis.

### The constraint that shapes the design

YouTube aggressively blocks caption and transcript requests from datacenter IPs. Both `yt-dlp` and `youtube-transcript-api` fail from Actions runners. Do not design as though the first cron run will prove otherwise, and do not spend a day debugging it as a bug.

The split is therefore: **detection in CI, transcript extraction and post writing locally.** The cron flags a new video and opens an Issue; Z runs Claude Code on his machine, which pulls the transcript from a residential IP and writes the post. If this becomes a bottleneck later, a residential proxy in CI is the upgrade path, but build the local path first because it is the one that works today.

The same caution applies to podcast enclosure downloads at volume, though those have been less aggressively blocked.

### Secrets

`ANTHROPIC_API_KEY`, plus `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` (or `ALSOASKED_API_KEY`), and `SERPAPI_KEY`. Budget is approved at 50 to 100 USD per month across the paid data APIs.

---

## 8. Track 1: the Converter

### Detection

Channel: Croissant Workspace, ID `UCfyBWT0jp_WGJrMVG9rnFhw`. The RSS feed is reliable and needs no browser. It carries titles, IDs, publish dates, full descriptions, and view counts, but not duration, so fetch duration separately before deciding whether to process.

Dedupe on `videoId` against `videoUrl` in existing post frontmatter plus the processed list below.

### Filters

Skip videos under roughly ten minutes (shorts, event recaps) **unless** the video is a customer story. "We Have Employees in 20+ States" was processed at 2:31 because it is a customer story.

Croissant-hosted webinars are the core material. Partner-channel videos are processed ad hoc only when Z asks.

### Already processed, skip these videoIds

`g2qEjH8SwhI`, `CIahBVLQD0Q`, `VYiwsMs90Bw`, `Jn3aIEJqd0s`, `vOJTUoYM02M`, `rVC_Y67-qnQ`, `hjZ7gvppE0Q`, `6KpRfDy1WII`, `YgacXHn0Bbc`, and `okWXpFu5oIU` (deliberately skipped, 1:09 event recap).

Two packages exist in the Cowork folder but were never staged to the site: `reverse-tech-remote-team-europe` and `timely-office-in-20-states`. Decide during migration whether to publish them.

### Transcript

Use `youtube-transcript-api` or `yt-dlp` auto-captions. Auto-captions garble proper nouns predictably: Croissant becomes Quasant, Quason, or Katan; WorkFlex becomes Wordflex; Zoltan becomes Zultan, Sultan, or Zolan. Fix these silently in the post and keep the raw text in any saved transcript.

Keep the transcript for fact-checking. **Never publish or commit it to the site.**

### Writing

Synthesize, do not dump. Structure is a hook intro naming speakers and context, thematic H2 sections, and a closing CTA. Target 1,100 to 1,400 words, a 7 to 8 minute read.

SEO block: `metaTitle` at 60 characters or fewer, `metaDescription` at 155 or fewer, slug, primary keyword, secondary keywords.

Verbatim quotes only where genuinely strong, verified against the transcript, lightly cleaned of ASR garble. Attribute by first name (Zoltan, Brock, Tiago).

**No em dashes anywhere in article content.** Match the voice of existing posts at getcroissant.com/resources.

Positioning: use Workspace Spend Management framing where it fits naturally. The buyer is HR-led, so lead with outcomes language (retention, fairness, employer brand) for HR audiences and governance, visibility, and usage-data language for finance-adjacent points.

Check titles against the brand law Z set on 2026-07-29 regarding benefit framing and operating-model titles. Those details live with Z or in the website repo session, not in this document.

### Output

Write directly into the website repo's content collection. Copy the frontmatter shape from existing posts in `resources/events/`. **The repo is the source of truth for the schema; do not invent fields.** Fields in use today: `slug`, `category` ("events" for webinars), `title`, `metaTitle`, `metaDescription`, `primaryKeyword`, `secondaryKeywords[]`, `author`, `tag` ("Webinar"), `videoUrl`, `videoTitle`, `guests[]`, `publishDate`, `readTime`, hero image note, `status`. Default author is Fernanda Grace Lins.

Production hides future-dated posts, so set `publishDate` deliberately.

Commit or PR per Z's preference. The most recent post was committed straight to main at his request.

Once this runs end to end in Claude Code, the Drive queue (`croissant-publish-queue`, ID `1LJC3nwfJqEQzJb3w_4Ag4uwLyFakpLXX`) and the `/stage-post` handoff are retired. **Tell Z when it is live so the Cowork weekly task can be disabled**, otherwise both pipelines will process the same videos.

---

## 9. Track 2: the Listener, synthesis stage

`synthesize.py` calls the Claude API with a prompt built from: the current `themes.json`, all Lane A items added since the last run, and all Lane B context summaries since the last run. It returns an updated theme registry.

The prompt should instruct the model to:

1. Assign each new Lane A item to an existing theme or propose a new one. Prefer assignment; a registry that grows unboundedly is a failed registry.
2. Extract the literal buying question where present, quoted verbatim with its source URL. This is the highest-value output, and it is what makes a digest actionable rather than merely interesting.
3. Note the vocabulary buyers actually use, especially where it differs from vendor language.
4. Mark, for each theme, which Lane B sources have already covered it, feeding `saturation_score`.
5. Flag emerging themes with fewer than the minimum item count as `watching` rather than promoting them.

Scoring is deterministic Python over the model's structured output, not something the model is asked to compute. Keep the arithmetic out of the prompt.

### Digest format

`data/digests/YYYY-Www.md`, movers only, capped at eight themes. Per theme: label, status (new, accelerating, gap play), opportunity score, two or three verbatim buying questions with links, the saturation read (who has already covered this), and a suggested angle. Close with a "watching" list of sub-threshold themes and a one-line run summary (items collected per source, new themes, suppressed themes).

Each digest theme opens or updates a GitHub Issue in this repo, labeled `theme`, `status:new` or `status:accelerating` or `status:gap`, and `wave`. Issues are the editorial queue. When a post ships, close the Issue and Claude Code writes `became_post` and `became_post_at` back into `themes.json`, which activates suppression.

---

## 10. Build sequence

Track 1 and Track 2 are independent and can proceed in parallel. Track 1 is the faster win and unblocks retiring the Cowork task.

**Track 1, roughly a day.** Detection from RSS with duration resolution and filters, then local transcript plus post writing against `resources/events/` conventions, then migrate the two unstaged packages and tell Z to disable the Cowork task.

**Track 2, Wave 0.** Repo skeleton, the four data contracts, `state.json`, and the generic RSS collector, which alone serves about twelve sources. Digest renders with no synthesis, just counts. The point is to prove the loop end to end before adding intelligence.

**Track 2, Wave 1.** Remaining Lane A collectors (Arctic Shift, Spiceworks, HN, PAA), then synthesis, themes, scoring, digest, and Issues. This produces the first real digest. Stop here and read the output before building more. Wave 1 output tells you which parsers deserve care and which sources are noise.

**Track 2, Wave 2.** Lane B depth: podcast collectors, the ingest summarizer, YouTube detection for external channels, and saturation scoring. This is when `opportunity_score` becomes meaningful, because before Lane B exists, saturation is always zero.

**Track 2, Wave 3.** Reviews (Capterra backfill then monthly deltas, TrustRadius), Trends, and research report diffing.

The success test for the whole Listener: does one weekly digest reliably produce two or three post-worthy topics that would not have occurred to us otherwise. If Wave 1 does not clear that bar, the fix is source weighting and prompt work, not more sources.

---

## 11. Decisions already made

- Repo is private indefinitely, so raw scraped text can live in `data/`.
- Full review scraping (Capterra, TrustRadius) is approved for a private repo. Never republish review prose verbatim in a public post; quote buying questions and paraphrase complaints, and cite structured facts like ratings and firmographics freely.
- Paid data APIs approved at 50 to 100 USD per month.
- Separate repo from the website, with digest Issues as the handoff contract.
- Synthesis runs on the Claude API inside the weekly cron; post drafting stays manual in Claude Code where the brand bible lives.

## 12. Open questions for Z

1. Digest destination: this plan writes markdown plus GitHub Issues in the listening repo. transition-watchlist puts digests in Drive where a salesperson reads them. Mirror to Drive as well, or is repo-native enough now that the Drive handoff is being retired?
2. Publish the two unstaged packages (`reverse-tech-remote-team-europe`, `timely-office-in-20-states`) as part of migration, or leave them?
3. Should the website repo get a `CLAUDE.md` section covering how to write a listening-derived post, so the drafting step is repeatable rather than re-prompted each time? Recommended.
4. Do you want a residential proxy provisioned now so transcript work can eventually move into CI, or is the local step acceptable indefinitely?

## 13. Known risks

The Actions IP block on transcripts is the main operational one and is already designed around. Beyond it: review-site anti-bot may change without notice, so treat those collectors as best-effort and never let one failure fail the whole run. Arctic Shift rate-limits aggressively, so bound date ranges on full-text queries. The theme registry will drift toward too many narrow themes if the synthesis prompt does not push hard toward assignment over creation, and that is the most likely quality failure in month two.
