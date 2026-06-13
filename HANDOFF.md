# PCA Archive — Agent Handoff Document

**Last updated:** 2026-06-13
**Repo:** https://github.com/david78737/pca-archive
**Live site:** https://david78737.github.io/pca-archive/

This document is the single source of truth for any agent (Mac Claude, PC Claude,
iOS Claude, or a future instance) working on this repo. Read it before touching
anything. Update it when you make a significant change.

---

## What This Repo Is

A static GitHub Pages site that serves as the public-facing knowledge archive for
ProductCamp Austin. All 97 sessions from PCA28–PCA34 (2023–2026) are searchable
in one place — no server, no login, no API calls at runtime.

The site is designed to grow: new events add rows to `sessions.json`, one
`node build.js` regenerates the database, one `git push` publishes it.

---

## Repository Structure

```
pca-archive/
├── index.html        ← The entire front-end. Single-page app.
├── archive.db        ← SQLite database (binary). GENERATED — do not hand-edit.
├── sessions.json     ← Source of truth for session data. Edit this to add/change sessions.
├── build.js          ← Node script that generates archive.db from sessions.json.
├── pca28/index.html  ← Legacy per-event pages (kept for reference / direct links).
├── pca29/index.html
├── pca30/index.html
├── pca31/index.html
├── pca32/index.html
├── pca33/index.html
├── pca34/index.html
└── HANDOFF.md        ← This file.
```

---

## How It Works

### The Database Approach

Earlier versions embedded all session data as a JavaScript array in `index.html`.
That works at 97 sessions but becomes unwieldy as data grows, and `string.includes()`
search is crude.

The current approach uses **SQLite running in the browser** via
[sql.js](https://github.com/sql-js/sql.js) (SQLite compiled to WebAssembly):

1. `sessions.json` is the human-editable data source.
2. `node build.js` reads it and produces `archive.db` — a real SQLite file.
3. `index.html` loads sql.js from CDN, fetches `archive.db` (~344 KB), and opens
   it as an in-memory database. All filtering and searching runs as SQL queries
   in the browser tab — no server involved.

**Why SQLite + FTS5?**
- Real full-text search with porter stemming: "strategy" matches "strategies",
  "build" matches "building", etc.
- BM25 relevance ranking: most relevant results surface first.
- Prefix matching: typing "road" returns sessions about roadmaps instantly.
- All filters compose cleanly as WHERE clauses.
- The `.db` file is a standard artifact any SQLite tool can inspect.

---

## Database Schema

```sql
-- Main table: one row per session
CREATE TABLE sessions (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  event     TEXT NOT NULL,   -- e.g. "PCA34"
  title     TEXT NOT NULL,
  presenter TEXT,
  level     TEXT,            -- "Essentials" | "Advanced" | "Entrepreneurs"
  format    TEXT,            -- "Workshop" | "Presentation" | "Case Study" | etc.
  synopsis  TEXT,
  takeaways TEXT,            -- JSON array: ["takeaway 1", "takeaway 2", ...]
  who       TEXT,            -- "Best for..." sentence
  brief     TEXT,            -- One-sentence call to action
  youtube   TEXT,            -- YouTube video ID (not full URL), or NULL
  tags      TEXT             -- JSON array: ["ai", "framework", ...] — auto-generated
);

-- FTS5 virtual table for full-text search
-- content= means it mirrors sessions; no storage duplication.
-- tokenize='porter ascii' enables stemming.
CREATE VIRTUAL TABLE sessions_fts USING fts5(
  title, presenter, synopsis, takeaways, who, brief, tags,
  content = sessions,
  content_rowid = id,
  tokenize = 'porter ascii'
);
```

`takeaways` and `tags` are stored as **JSON arrays serialized to TEXT**.
The front-end parses them with `JSON.parse()` before rendering.
The `tags` field is also indexed in FTS5 so tag words are searchable.

---

## Tags

Tags are a **starter set generated automatically** from word-frequency analysis
of each session's text (title + synopsis + takeaways + who + brief).

### How they are generated

`build.js` does NOT generate tags — that happens in the pre-processing step
when `sessions.json` is produced. The tag generation logic lives in the script
that was used to build `sessions.json` (documented below).

The tagging algorithm:
1. Concatenate title + synopsis + takeaways + who + brief for each session.
2. Lowercase, strip punctuation and contractions.
3. Boost "AI" and "API" (captured before lowercasing).
4. Remove stop words (English function words + ProductCamp-universal terms like
   "product", "manager", "team" — words that appear in nearly every session and
   carry no filter value).
5. Light plural normalization: "strategies" → "strategy", "customers" → "customer".
6. Take the top 8 words by frequency as tags for that session.

### Design philosophy

These are intentionally imperfect. They are a **starter set** — enough for basic
filtering to work. The long-term plan (Phase 2, not yet built) is a presenter
intake form where each presenter supplies their own tags. Presenter-supplied tags
will always be more accurate than frequency-derived ones.

**Do NOT use AI to assign "smart" tags.** Tags in ONDA always come from the person
closest to the content. The frequency approach is a mechanical proxy until presenters
can do it themselves.

### The Topics filter strip

The 24 tags shown in the Topics row are the most common tags across all sessions,
hardcoded in `index.html` as `TOP_TAGS`. If the session data changes significantly,
regenerate this list by running:

```bash
node -e "
const s = require('./sessions.json');
const c = {};
s.forEach(x => (x.tags||[]).forEach(t => c[t]=(c[t]||0)+1));
Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,30).forEach(([t,n])=>console.log(n,t));
"
```

Then update the `TOP_TAGS` array in `index.html` accordingly.

---

## How to Add or Update Sessions

### Adding a new event (e.g. PCA35)

1. Get session data from the per-event HTML file or Xano.
2. Add entries to `sessions.json` following the existing structure:

```json
{
  "event": "PCA35",
  "title": "Session Title",
  "presenter": "Presenter Name",
  "level": "Essentials",
  "format": "Presentation",
  "synopsis": "...",
  "takeaways": ["...", "...", "..."],
  "who": "...",
  "brief": "...",
  "youtube": "VIDEO_ID_OR_NULL",
  "tags": ["ai", "framework", "career"]
}
```

3. Generate tags for new sessions (use the tagging script or assign manually).
4. Run `node build.js` to regenerate `archive.db`.
5. Update the `TOP_TAGS` array in `index.html` if the tag landscape has shifted.
6. Update the `header .sub` line in `index.html` with the new session count.
7. Commit both `sessions.json` and `archive.db`. Push to main.

### Updating an existing session (e.g. adding a YouTube ID)

1. Find the session in `sessions.json` by title.
2. Update the `youtube` field (just the video ID, not the full URL).
3. Run `node build.js`.
4. Commit and push `sessions.json` and `archive.db`.

### Fixing a tag

1. Edit the `tags` array for that session in `sessions.json`.
2. Run `node build.js`.
3. Commit and push.

---

## How to Rebuild the Database

Requirements: **Node 24+** (uses the built-in `node:sqlite` module, no npm install needed).

```bash
cd pca-archive
node build.js
```

Output:
```
archive.db built:
  Sessions : 97 (FTS rows: 97)
  File size: 344.0 KB
  By event :
    PCA28: 19
    ...
```

Always commit `archive.db` after rebuilding. The browser fetches it directly.

---

## sql.js Dependency

- **Library:** sql.js 1.10.2
- **CDN:** `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.2/`
- **Files used:** `sql-wasm.js` (loader) + `sql-wasm.wasm` (the SQLite engine)
- **No npm install required** — loaded from CDN at page load.
- **Works on GitHub Pages** — does not require `SharedArrayBuffer` or special HTTP
  headers (unlike the official `@sqlite.org/sqlite-wasm` package).

To upgrade sql.js, update the version in both CDN URLs in `index.html` and
verify the DB still loads and queries correctly.

---

## What Each Filter Does (Technical)

| Filter | SQL generated |
|--------|---------------|
| Event chip | `WHERE s.event = 'PCA34'` |
| Level chip | `WHERE s.level = 'Essentials'` |
| Topic chip | `WHERE EXISTS (SELECT 1 FROM json_each(s.tags) WHERE value = 'ai')` |
| Search box | `JOIN sessions_fts ... WHERE sessions_fts MATCH 'roadmap*' ORDER BY rank` |

All filters compose — clicking multiple chips adds `AND` clauses to the same query.
Search and filters also compose: you can search "pricing" within PCA31 Advanced sessions.

---

## Known Gaps / Future Work

### Phase 2 — Presenter-supplied tags
Each presenter should get a unique URL to a form where they fill in their own
description and tags. That form POSTs to Xano and enriches the archive record.
This was designed but not built. See `LETTER_TO_PC_CLAUDE.md` for the full plan.

### YouTube IDs
Some sessions have `youtube: null` because the video hasn't been published or
the ID wasn't recovered after the miniMac crash that lost the compiled URL list.
These should be filled in as videos become available.

### Real transcripts
The current synopsis/takeaways/who/brief were generated by Claude from actual
session transcripts (for sessions where transcripts existed). Tags are derived
from those fields. When raw transcript text is added to sessions, re-running
the tag generator against the full transcript will produce significantly better tags.

### Speaker photos
`speaker_photo_url` exists in the Xano `session_archive` table but is not yet
in `sessions.json` or displayed on the archive page.

---

## Xano Backend (Separate from This Repo)

A Xano backend exists for the ONDA pipeline (transcription → Claude → structured
fields). The archive page does NOT use Xano at runtime — it's fully static.
Xano is used during the content generation pipeline only.

Endpoints (workspace `xrxm-29on-xlyt`, API group `gaCgk7Bm`):
- `POST /create` — accepts transcript + metadata, calls Claude API, writes synopsis/takeaways/who/brief
- `GET /sessions` — returns all archive records
- `PATCH /session/{id}` — updates individual fields (youtube, onda, status, etc.)
- `POST /import-request` — intake form submission from ondareplay.com/import

See `LETTER_TO_PC_CLAUDE.md` for full pipeline documentation.

---

## Agent Coordination Notes

This repo is worked on by multiple Claude instances across different machines:

| Agent | Machine | Role |
|-------|---------|------|
| PC Claude | Windows / VS Code | Session data curation, Xano pipeline, repo management |
| Mac Claude | miniMac | BlackHole capture pipeline, batch Whisper transcription, Xano POST |
| iOS Claude | miniMac (Claude Code iOS) | Flutter app (onda-replay repo), TestFlight builds |

**Before making changes:** `git pull` first. Multiple agents push to this repo.

**After making changes:** commit immediately. Do not hold uncommitted work across
sessions. The miniMac has crashed before and lost in-memory work.

**Commit-first protocol (from PC Claude, 2026-06-08):**
Any list, mapping, or dataset that required effort to compile must be committed
the moment it exists. Especially: YouTube URL lists, session-to-filename mappings,
any intermediate data file. These live in `docs/data/` in the onda-replay repo
(not this repo).

---

## Session Count Reference

| Event | Date | Sessions |
|-------|------|----------|
| PCA28 | April 2023 | 19 |
| PCA29 | October 2023 | 7 |
| PCA30 | April 2024 | 11 |
| PCA31 | October 2024 | 14 |
| PCA32 | April 2025 | 11 |
| PCA33 | October 2025 | 9 |
| PCA34 | April 2026 | 26 |
| **Total** | | **97** |
