#!/usr/bin/env node
// Count place-nickname votes from the Google Form CSV export.
//
//   node count_votes.mjs                 newest CSV in responses/
//   node count_votes.mjs path/to.csv     a specific export
//   options: --min N        distinct voters needed to make the shortlist (default 5)
//            --all          also list names already in places.json
//            --feedback     print the free-text feedback answers
//            --any-email    accept non-@alaska.edu emails (testing only)
//
// Form columns used (matched by header text, so small renames are fine):
//   Email                    one vote per distinct UAA email per nickname
//   Name Suggestion          the nickname students search for ("Subway")
//   Location name            what the place is, shown next to the nickname
//   Campus Site              only Anchorage votes can reach the map; other
//                            campuses (Mat-Su, ...) are listed separately
//   Location Abbreviation    building code (EIB, ECB, RH), checked against
//                            the extractor's BUILDINGS table and the app
//   Location Floor Number    floor ("3" -> "03", "basement" -> "B1")
//   Room Number              pre-fills the draft's room when most voters agree
//   ...feedback...           printed with --feedback
// "Name" (the voter) and "Column 6" (leftover) are ignored.
//
// Names are matched with the app's own normName (places.mjs), so
// "AI & Robotics Lab" = "ai robotics lab". Writes shortlist.json (no emails)
// next to this script: the names at or over the threshold, with a draft
// places.json entry. An admin still fills in the room label as drawn, picks a
// category, and adds the accepted names in places.html.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..');
const SRC = path.join(ROOT, 'Oropendula', 'src');
const { normName, parseTarget } = await import(pathToFileURL(path.join(SRC, 'places.mjs')).href);

// ---------- options ----------
const args = process.argv.slice(2);
const flag = (f) => { const i = args.indexOf(f); if (i < 0) return false; args.splice(i, 1); return true; };
const opt = (f, def) => { const i = args.indexOf(f); if (i < 0) return def; const v = args[i + 1]; args.splice(i, 2); return v; };
const MIN = Number(opt('--min', 5));
const SHOW_ALL = flag('--all');
const SHOW_FEEDBACK = flag('--feedback');
const ANY_EMAIL = flag('--any-email');
const EMAIL_OK = /@alaska\.edu$/i;
const ANCHORAGE = /anchorage|main campus|^uaa$/i;   // empty campus answer also counts as Anchorage

function newestCsv() {
  const dir = path.join(HERE, 'responses');
  const files = fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => f.toLowerCase().endsWith('.csv')) : [];
  if (!files.length) throw new Error(`no .csv in ${dir}`);
  return files.map((f) => path.join(dir, f)).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
}
const csvPath = args[0] ?? newestCsv();

// ---------- CSV (quotes, embedded commas/newlines, BOM) ----------
function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  text = text.replace(/^﻿/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') q = false;
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); rows.push(row); row = []; cell = '';
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((x) => x.trim()));
}

const [header, ...data] = parseCsv(fs.readFileSync(csvPath, 'utf8'));
if (!header) throw new Error(`${csvPath} is empty`);

// First header matching any of the patterns, in order of preference.
const col = (...res) => {
  for (const re of res) { const i = header.findIndex((h) => re.test(h.trim())); if (i >= 0) return i; }
  return -1;
};
const C = {
  time: col(/^timestamp$/i),
  email: col(/e-?mail/i),
  nick: col(/name suggestion/i, /place of interest|nickname|what do you call/i),
  desc: col(/^location name$/i, /^name of location$/i),
  campus: col(/campus/i),
  code: col(/abbreviation/i),
  floor: col(/floor/i),
  room: col(/room\s*(number|#|no)/i, /room/i),
  target: col(/filled in by the app/i),   // optional app-prefilled {place} key
  feedback: col(/feedback/i),
};
if (C.email < 0 || C.nick < 0) {
  throw new Error(`need an email column and a nickname column; headers are:\n  ${header.join('\n  ')}`);
}

// ---------- buildings: extractor registry + what the app has registered ----------
// code/name -> {as, code, name}
const buildingsByKey = new Map();
const extractor = fs.readFileSync(path.join(ROOT, 'Data Extraction', 'floorplan_extractor.py'), 'utf8');
for (const m of extractor.matchAll(/"(AS\d+)":\s*\("([^"]*)",\s*"([^"]*)"\)/g)) {
  const b = { as: m[1], code: m[2], name: m[3] };
  for (const k of [b.as, b.code, b.name]) if (k) buildingsByKey.set(normName(k), b);
}
const registered = new Set(JSON.parse(fs.readFileSync(path.join(SRC, 'buildings-config.json'), 'utf8')).map((b) => b.id));
const lookupBuilding = (s) => (s ? buildingsByKey.get(normName(s)) ?? null : null);

function normFloor(s) {
  s = String(s ?? '').trim().toLowerCase();
  if (!s) return '';
  if (/^(b|basement|b1|lower|-1)/.test(s)) return 'B1';
  if (/ground|main/.test(s)) return '01';
  const words = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth'];
  const w = words.findIndex((x) => s.includes(x));
  if (w >= 0) return String(w + 1).padStart(2, '0');
  const n = /\d+/.exec(s)?.[0];
  return n ? n.padStart(2, '0') : s;
}

// "EIB 303", "Room 303", "rm. 303" -> "303". Keeps labels like "Student Lounge".
function cleanRoom(s) {
  let words = String(s ?? '').trim().split(/\s+/).filter(Boolean);
  if (words.length > 1 && lookupBuilding(words[0])) words = words.slice(1);
  if (words.length > 1 && /^(room|rm\.?|#)$/i.test(words[0])) words = words.slice(1);
  return words.join(' ').replace(/^#/, '').toUpperCase();
}

// ---------- names already in the app ----------
const known = new Map();   // normName -> place id
for (const p of JSON.parse(fs.readFileSync(path.join(SRC, 'places.json'), 'utf8'))) {
  for (const n of p.names ?? []) known.set(normName(n), p.id);
}

// ---------- count ----------
const tally = (m, k) => k && m.set(k, (m.get(k) ?? 0) + 1);
const groups = new Map();   // normName -> group
const other = new Map();    // campus -> Map(nickname -> votes)
const rejected = { noName: 0, badEmail: 0, duplicate: 0 };
const feedback = [];
const seen = new Set();     // email|normName

for (const r of data) {
  const get = (i) => (i >= 0 ? (r[i] ?? '').trim().replace(/\s+/g, ' ') : '');
  const fb = (C.feedback >= 0 ? r[C.feedback] ?? '' : '').trim();
  if (fb) feedback.push(fb);

  const email = get(C.email).toLowerCase();
  const raw = get(C.nick) || get(C.desc);
  const key = normName(raw);
  if (!key) { rejected.noName++; continue; }
  if (!email || (!ANY_EMAIL && !EMAIL_OK.test(email))) { rejected.badEmail++; continue; }
  if (seen.has(`${email}|${key}`)) { rejected.duplicate++; continue; }
  seen.add(`${email}|${key}`);

  const campus = get(C.campus);
  if (campus && !ANCHORAGE.test(campus)) {
    if (!other.has(campus)) other.set(campus, new Map());
    tally(other.get(campus), raw);
    continue;
  }

  let g = groups.get(key);
  if (!g) groups.set(key, g = { rooms: new Map(), names: new Map(), descs: new Map(), voters: new Set(), where: new Map(), targets: new Map(), first: '', last: '' });
  tally(g.names, raw);
  tally(g.descs, get(C.desc) !== raw ? get(C.desc) : '');
  g.voters.add(email);

  const codeRaw = get(C.code);
  const b = lookupBuilding(codeRaw);
  const floor = normFloor(get(C.floor));
  const bLabel = b ? b.code || b.as : codeRaw.toUpperCase();
  tally(g.where, [bLabel, floor && `floor ${floor}`].filter(Boolean).join(' '));
  tally(g.targets, get(C.target));
  tally(g.rooms, cleanRoom(get(C.room)));

  const t = get(C.time);
  if (t) { if (!g.first) g.first = t; g.last = t; }
}

const top = (m) => [...m].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
const results = [...groups].map(([key, g]) => {
  const where = top(g.where);                       // e.g. "EIB floor 03"
  const b = lookupBuilding(where.split(' floor ')[0]);
  return {
    key,
    name: top(g.names),                             // most common spelling
    spellings: [...g.names.keys()],
    descriptions: [...g.descs.keys()],
    votes: g.voters.size,
    where, locations: Object.fromEntries(g.where),
    building: b, floor: /floor (\S+)$/.exec(where)?.[1] ?? '',
    onMap: b ? registered.has(b.as) : null,
    target: top(g.targets),
    room: top(g.rooms), rooms: Object.fromEntries(g.rooms),
    first: g.first, last: g.last,
    alreadyIn: known.get(key) ?? null,
  };
}).sort((a, b) => b.votes - a.votes || a.name.localeCompare(b.name));

// ---------- report ----------
const otherVotes = [...other.values()].reduce((s, m) => s + [...m.values()].reduce((a, n) => a + n, 0), 0);
console.log(`${path.basename(csvPath)}: ${data.length} responses, ${seen.size - otherVotes} Anchorage votes, ${groups.size} distinct names`);
console.log(`skipped: ${rejected.noName} no nickname, ${rejected.badEmail} non-UAA email, ${rejected.duplicate} repeat vote, ${otherVotes} other campus`);
console.log(`threshold: ${MIN} distinct voters\n`);

const shown = results.filter((r) => SHOW_ALL || !r.alreadyIn);
if (!shown.length) console.log('(no votes to show)');
for (const r of shown) {
  const mark = r.alreadyIn ? `  [in places.json: ${r.alreadyIn}]` : r.votes >= MIN ? '  ← SHORTLIST' : '';
  console.log(`${String(r.votes).padStart(4)}  ${r.name}${mark}`);
  if (r.spellings.length > 1) console.log(`        also written: ${r.spellings.filter((s) => s !== r.name).join(' | ')}`);
  if (r.descriptions.length) console.log(`        described as: ${r.descriptions.join(' | ')}`);
  if (r.where) {
    const status = r.building ? (r.onMap ? `${r.building.as} ${r.building.name}, on the map`
      : `${r.building.as} ${r.building.name}, not registered in the app yet`) : 'unknown building code';
    console.log(`        where: ${Object.entries(r.locations).map(([l, n]) => `${l} (${n})`).join(', ')}  [${status}]`);
  } else console.log('        where: (no building given)');
}

if (other.size) {
  console.log('\nother campuses (not on the Anchorage map):');
  for (const [campus, m] of other) {
    console.log(`  ${campus}: ${[...m].sort((a, b) => b[1] - a[1]).map(([n, c]) => `${n} (${c})`).join(', ')}`);
  }
}

if (SHOW_FEEDBACK) {
  console.log(`\nfeedback (${feedback.length}):`);
  for (const f of feedback) console.log(`  - ${f.replace(/\s+/g, ' ')}`);
} else if (feedback.length) {
  console.log(`\n${feedback.length} feedback answers (run with --feedback to read them)`);
}

// ---------- shortlist.json (no emails) ----------
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const shortlist = results.filter((r) => !r.alreadyIn && r.votes >= MIN).map((r) => {
  const t = r.target ? parseTarget(r.target) : null;
  const loc = t?.ll ? { ll: t.ll, floor: t.floor }
    : t ? { building: t.building, room: t.room }
    : { building: r.building ? r.building.code || r.building.as : '', room: r.room };
  return {
    votes: r.votes, name: r.name, spellings: r.spellings, descriptions: r.descriptions,
    locations: r.locations, floor: r.floor, rooms: r.rooms,
    building: r.building && { ...r.building, on_map: r.onMap },
    first_vote: r.first, last_vote: r.last,
    // Draft entry for places.json. Fill `room` with the label exactly as drawn
    // on that floor (check it in places.html) and pick a category.
    draft: { id: slug(`${loc.building ?? ''} ${r.name}`), names: [r.name], category: '', ...loc },
  };
});
const out = path.join(HERE, 'shortlist.json');
fs.writeFileSync(out, JSON.stringify({ source: path.basename(csvPath), threshold: MIN, generated: new Date().toISOString(), shortlist }, null, 2) + '\n');
console.log(`\nwrote ${path.relative(process.cwd(), out) || out}: ${shortlist.length} name(s) at or over ${MIN} votes`);
