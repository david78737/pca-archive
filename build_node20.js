#!/usr/bin/env node
// build_node20.js — generates archive.db from sessions.json
// Uses sql.js (pure JS) — works on Node 20+
// Run: node build_node20.js

const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');

const SESSIONS_FILE = path.join(__dirname, 'sessions.json');
const DB_FILE = path.join(__dirname, 'archive.db');

const sessions = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf8'));

initSqlJs().then(SQL => {
  const db = new SQL.Database();

  db.run(`
    CREATE TABLE sessions (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      event     TEXT NOT NULL,
      title     TEXT NOT NULL,
      presenter TEXT,
      level     TEXT,
      format    TEXT,
      synopsis  TEXT,
      takeaways TEXT,
      who       TEXT,
      brief     TEXT,
      youtube   TEXT,
      tags      TEXT,
      photo     TEXT,
      onda_url  TEXT
    );
  `);

  // FTS5 not supported in sql.js — search handled client-side in index.html

  const insert = db.prepare(`
    INSERT INTO sessions (event, title, presenter, level, format, synopsis, takeaways, who, brief, youtube, tags, photo, onda_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  let inserted = 0;
  for (const s of sessions) {
    const takeawaysJson = JSON.stringify(s.takeaways || []);
    const tagsJson      = JSON.stringify(s.tags || []);
    insert.run([
      s.event, s.title, s.presenter || '', s.level || '', s.format || '',
      s.synopsis || '', takeawaysJson, s.who || '', s.brief || '',
      s.youtube || null, tagsJson, s.photo || null, s.onda_url || null
    ]);
    inserted++;
  }
  insert.free();

  // FTS skipped — no fts5 in sql.js

  const count = db.exec('SELECT COUNT(*) FROM sessions')[0].values[0][0];
  const events = db.exec('SELECT event, COUNT(*) FROM sessions GROUP BY event ORDER BY event')[0];

  const data = db.export();
  fs.writeFileSync(DB_FILE, Buffer.from(data));

  const size = fs.statSync(DB_FILE).size;
  console.log(`\narchive.db built:`);
  console.log(`  Sessions : ${count}`);
  console.log(`  File size: ${(size / 1024).toFixed(1)} KB`);
  console.log(`  By event :`);
  events.values.forEach(([ev, n]) => console.log(`    ${ev}: ${n}`));
  console.log(`\nDone — commit sessions.json and archive.db\n`);
});
