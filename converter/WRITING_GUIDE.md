# Converter writing guide

The post spec for Track 1. This is the deterministic path: one Croissant video
in, one SEO blog post out, written locally (transcript extraction fails from
datacenter IPs). Dedupe on `videoId` only. The Listener's theme suppression must
never gate this path.

Style law: **no em dashes anywhere in article content.** Use commas, colons,
parentheses, or a full stop.

## Detection

- Channel: Croissant Workspace, ID `UCfyBWT0jp_WGJrMVG9rnFhw`.
- Read `https://www.youtube.com/feeds/videos.xml?channel_id=UCfyBWT0jp_WGJrMVG9rnFhw`.
- RSS carries title, id, publish date, description, view count, but not
  duration. Resolve duration separately (oEmbed or the Data API) before deciding.
- Dedupe on `videoId` against `videoUrl` in existing post frontmatter plus the
  processed list in `PROJECT_PLAN.md` section 8.

## Filters

- Skip videos under roughly 10 minutes (shorts, event recaps) **unless** the
  video is a customer story (example: "We Have Employees in 20+ States" at 2:31).
- Croissant-hosted webinars are the core material. Partner-channel videos only
  when Z asks.

## Transcript

- Pull with `youtube-transcript-api` or `yt-dlp` auto-captions, from a
  residential IP.
- Fix predictable ASR garble silently in the post: Croissant (not Quasant,
  Quason, Katan); WorkFlex (not Wordflex); Zoltan (not Zultan, Sultan, Zolan).
- Keep the transcript for fact-checking. **Never publish or commit it to the
  site.**

## Writing

- Synthesize, do not dump. Hook intro naming speakers and context, thematic H2
  sections, closing CTA.
- Target 1,100 to 1,400 words (7 to 8 minute read).
- Verbatim quotes only where genuinely strong and verified against the
  transcript, lightly cleaned of ASR garble. Attribute by first name (Zoltan,
  Brock, Tiago).
- Positioning: use Workspace Spend Management framing where it fits. Buyer is
  HR-led: lead with outcomes (retention, fairness, employer brand) for HR
  audiences, and governance, visibility, usage-data language for finance points.
- Check titles against the brand law Z set on 2026-07-29 (benefit framing and
  operating-model titles). Those details live with Z or the website repo.

## SEO block

`metaTitle` <= 60 chars, `metaDescription` <= 155 chars, plus slug, primary
keyword, secondary keywords.

## Output

Write into the website repo's content collection. Copy the frontmatter shape
from existing posts in `resources/events/`. **The repo is the source of truth
for the schema; do not invent fields.** Fields in use today: `slug`, `category`
("events"), `title`, `metaTitle`, `metaDescription`, `primaryKeyword`,
`secondaryKeywords[]`, `author`, `tag` ("Webinar"), `videoUrl`, `videoTitle`,
`guests[]`, `publishDate`, `readTime`, hero image note, `status`. Default author
is Fernanda Grace Lins. Production hides future-dated posts, so set `publishDate`
deliberately.

When this runs end to end, tell Z so the Cowork weekly task and the Drive queue
handoff can be retired, otherwise both pipelines process the same videos.
