#!/usr/bin/env node
// build.js — generates archive.db from sessions.json
//
// Run:  node build.js
// Requires: Node 24+ (uses built-in node:sqlite)
// Output:   archive.db  (commit this file to the repo)
//
// Schema overview:
//   sessions     — one row per session, all structured fields
//   sessions_fts — FTS5 virtual table for full-text search across all text fields
//
// To add or update sessions:
//   1. Edit sessions.json (or regenerate it from the per-event HTML files)
//   2. Run:  node build.js
//   3. Commit both sessions.json and archive.db

const { DatabaseSync } = require('node:sqlite');
const fs = require('fs');
const path = require('path');

const SESSIONS_FILE = path.join(__dirname, 'sessions.json');
const DB_FILE = path.join(__dirname, 'archive.db');

const sessions = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf8'));

// Remove existing DB so we always build fresh
if (fs.existsSync(DB_FILE)) fs.unlinkSync(DB_FILE);

const db = new DatabaseSync(DB_FILE);

// ── Schema ────────────────────────────────────────────────────────────────────

db.exec(`
  CREATE TABLE sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event     TEXT NOT NULL,
    title     TEXT NOT NULL,
    presenter TEXT,
    level     TEXT,
    format    TEXT,
    synopsis  TEXT,
    takeaways TEXT,   -- JSON array: ["takeaway 1", "takeaway 2", ...]
    who       TEXT,
    brief     TEXT,
    youtube   TEXT,
    tags      TEXT    -- JSON array: ["ai", "framework", ...]
  );
`);

// FTS5 virtual table — content= mirrors the sessions table so we don't
// duplicate storage. The tokenizer uses porter stemming for better recall
// ("strategies" matches "strategy", "building" matches "build", etc.).
db.exec(`
  CREATE VIRTUAL TABLE sessions_fts USING fts5(
    title,
    presenter,
    synopsis,
    takeaways,
    who,
    brief,
    tags,
    content = sessions,
    content_rowid = id,
    tokenize = 'porter ascii'
  );
`);

// ── Insert ────────────────────────────────────────────────────────────────────

const insert = db.prepare(`
  INSERT INTO sessions (event, title, presenter, level, format, synopsis, takeaways, who, brief, youtube, tags)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

const insertFts = db.prepare(`
  INSERT INTO sessions_fts (rowid, title, presenter, synopsis, takeaways, who, brief, tags)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?)
`);

let inserted = 0;
for (const s of sessions) {
  const takeawaysJson = JSON.stringify(s.takeaways || []);
  const tagsJson      = JSON.stringify(s.tags || []);
  // Flatten arrays to plain text for FTS indexing
  const takeawaysText = (s.takeaways || []).join(' ');
  const tagsText      = (s.tags || []).join(' ');

  const result = insert.run(
    s.event, s.title, s.presenter || '', s.level || '', s.format || '',
    s.synopsis || '', takeawaysJson, s.who || '', s.brief || '',
    s.youtube || null, tagsJson
  );

  insertFts.run(
    result.lastInsertRowid,
    s.title, s.presenter || '', s.synopsis || '',
    takeawaysText, s.who || '', s.brief || '', tagsText
  );

  inserted++;
}

// ── Verify ────────────────────────────────────────────────────────────────────

const count     = db.prepare('SELECT COUNT(*) AS n FROM sessions').get().n;
const ftsCount  = db.prepare('SELECT COUNT(*) AS n FROM sessions_fts').get().n;
const events    = db.prepare('SELECT event, COUNT(*) AS n FROM sessions GROUP BY event ORDER BY event').all();

db.close();

const size = fs.statSync(DB_FILE).size;
console.log(`\narchive.db built:`);
console.log(`  Sessions : ${count} (FTS rows: ${ftsCount})`);
console.log(`  File size: ${(size / 1024).toFixed(1)} KB`);
console.log(`  By event :`);
events.forEach(e => console.log(`    ${e.event}: ${e.n}`));
console.log(`\nDone — commit sessions.json and archive.db\n`);
