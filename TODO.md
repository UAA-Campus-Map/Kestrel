# Campus Navigator — TODO

Hosting: navigator.cheeseverse.net · Frontend: plain HTML/JS first, React later

Last updated 2026-10-27. Oropendula pointer committed at `9db2b76`. New: routing-quality plan (section 11), floor JSON cleanup (section 12), places votes moved to an external form (section 10).

## Where things stand

- **Data extraction (us):** done for every public building. 156 floor JSONs (49 buildings) in `Data Extraction/Floor Data/`.
- **Georeferencing (us):** pilot on AS101-01 with `georef.py`. Holdout median 1.48 m. **On hold:** the app uses nothing georef produces, and its hand placement agrees with our fit within 0.6 m. We only use georef where buildings meet (section 1).
- **App (Oropendula, teammate):** rebuilt on our floor JSONs. It places floors by hand in `import.html` (saved in `buildings-config.json`), routes indoors/outdoors with skybridges and stairs/elevators (`navgraph.mjs`, `campus.mjs`), does PDR + GPS positioning, and has room search. Main UI is `app.html`, docs in `Oropendula/docs/` and `Oropendula/src/agents.md`, tests in `node smoke.mjs`.
- **Registered in the app (8 buildings):** ESH 01, SMH 01, BMH 01–02, RH 01–03, CUDY 01–02, AASC 01–03, SU 01–02, ECB 01–04.

## ⭐ Best next steps (in order)

1. **Agree on a data handoff with the teammate** (section 2). Floor JSONs are now copied by hand from `Floor Data/` into `Oropendula/src/`, so a re-extraction can silently go stale.
2. **Register the missing buildings and floors** (section 3). This is most of what's left before the app covers the whole campus, and it's data work that fits our side.
3. **Check the seams** while registering: skybridges, exits onto OSM paths, and the GPS → indoor hand-off. Fix a seam with `map-pick` corners only if it looks wrong there (section 1, Phase B).
4. **Field data for ESH** whenever someone is on campus (section 1, Phase A1). Low priority now.

To bump Oropendula later, run `/update-oropendula` in Claude Code (`.claude/skills/update-oropendula/`, local only since `.claude/` is gitignored).

## 0. Data sources ✅
- [x] Building registry: `BUILDINGS` table in `floorplan_extractor.py` (from http://fpgis.uaa.alaska.edu/FPTableANC.htm). Every floor JSON gets `building_code`, `ID`, `building_name`, `level`
- [x] Run the extractor on all DXFs → `Floor Data/`
- [x] AS106 Lucy Cuddy Hall added and extracted (B1, 01, 02). B1 and 02 are small partial levels (mechanical/roof), 01 has the rooms
- [x] Remaining missing codes are maintenance-only, not public walking space (`maintainance.md`). Same for AS121 floor `04` and AS154 `Interstitial`
- [x] All 156 JSONs (49 buildings) have `ID` and `building_name` matching the UAA site

## 1. Georeferencing (CAD coordinates → lon/lat)

**YOU MAY WANT TO IGNORE THIS SECTION #1 ONLY USEFUL FOR FINDINGS**

Our approach: `georef.py` fits each floor from control points in a hand-editable `Data Extraction/georef/<code>-<level>.json` and reports the error. The app's approach: drag and rotate each floor in `import.html`, scale fixed at inches, upper floors aligned to the ground floor by `align.mjs` (elevators + outline). Both use 0.0254 m/unit, so the two transforms can be compared directly.

**Findings (2026-10-20):**
- **The app uses nothing georef produces.** It loads only `buildings-config.json` and the floor JSONs (its `AS101-01.json` is byte-identical to `Floor Data/`), and converts CAD → lon/lat itself in `geo.mjs` `makeToLL`. Nothing in `Oropendula/src` or `docs` references `georef`, control points, or any `.geojson`.
- **The two placements agree within 0.6 m.** For AS101-01, over 3,958 wall/door points: median 0.60 m, max 0.73 m apart. Rotation is 0.29° in the app vs -0.14° in ours. Both were tuned against the same prototype rooms (~1.6 m RMS), so neither is more accurate than that.
- **More precision isn't worth it campus-wide yet.** Routing, walls and the particle filter work in CAD coordinates, so a 1–2 m shift of a whole building changes nothing indoors, and phone GPS is off by 3–5 m anyway. Placement only matters where two coordinate systems meet: skybridges between buildings, exits onto OSM paths, and the GPS → indoor hand-off.
- Precision comes from better control points (`map-pick` 0.5–2 m, `field-gps`, `survey`), not from GeoJSON (see section 9).

**Phase A: AS101-01 accuracy test**
- [x] Georef JSON format, `georef.py init / fit / preview`, 6 pytest tests, procedure in `georef/README.md`
- [x] AS101-01 with the `esh` prototype rooms, scale locked to inches: **holdout median 1.48 m, 90th percentile 2.37 m**, rotation -0.14°
- [ ] **A1. Field data for ESH** (low priority): 1–2 tape-measured long distances (`checks`) to confirm the inch scale, and 3–4 building corners (`field-gps`), then refit
- [x] **A2. Compare against the app's placement:** measured once by hand (see Findings): 0.60 m median, 0.73 m max
- [x] **A3. Decision:** keep the app's hand placement. `georef.py` doesn't feed `buildings-config.json` for now
- [ ] `georef.py init --from-prototype` is broken since Oropendula `806fb9d`: the rewritten `src/index.html` no longer has the prototype building list, so it exits with `no prototype building 'esh' (have: )`. `fit`/`preview` and the existing `AS101-01.json` still work. Fix only if needed: save the old list from `git -C Oropendula show 49fe74e:src/index.html` into `georef/`, or start new floors from `map-pick` points instead. Then update `georef/README.md` line 33 (the `prototype` source row)

**Phase B: fix seams only where they look wrong**
- [ ] While registering buildings (section 3), check where skybridges connect, where exits meet OSM paths, and the GPS → indoor hand-off. If one building is visibly off from its neighbor or the paths, click 3–4 corners on satellite imagery (`map-pick`), run `fit`, and give the teammate the corrected origin and rotation
- [ ] Add `georef.py compare <floor>` (reads origin/offset from `buildings-config.json`, same math as `makeToLL`) only once this hand-off happens more than once or twice

**Phase C: scale out** (revised: the app already stacks floors and has a placement tool)
- ~~Stack AS101 B1 and 02 with shaft labels~~ → `import.html` "align to ground" (`align.mjs`) does this
- ~~Control-point picker admin page~~ → `import.html` covers manual placement
- ~~`georef.py compare` for every registered building~~ → only at seams (Phase B)
- ~~`georef.py report` for every floor~~ → not needed while georef is on hold

## 2. Data pipeline: extractor → app
The app reads the extractor's floor JSONs directly and converts them to lon/lat at runtime. No GeoJSON step is needed (section 9).
- [ ] **Single source for floor JSONs:** the app keeps its own copies in `Oropendula/src/AS*.json`. Agree with the teammate on one of: a copy script from `Floor Data/`, or the app loading from a shared `/data/` path on the server
- [ ] After any re-extraction, the app needs `node gen-portals.mjs` (refreshes the portal cache in `buildings-config.json`) and the changed JSONs uploaded
- [ ] Optional later: room polygons (Shapely `polygonize` of walls + doors, paired with labels). The app currently routes to the room's nearest door, so this is only for highlighting rooms or area-based search

## 3. Campus coverage in the app (register via `import.html`)
Process per building: import the floor JSON in `import.html`, place it, align upper floors, check exterior doors and skybridges, download `buildings-config.json` (+ `osm-paths.json` if the campus area grew), run `node smoke.mjs`, deploy.
- [ ] **Missing floors of registered buildings:** ESH 02 (JSON already in `src/`), and the B1 floors (ESH, SMH, BMH, CUDY) if they hold public space
- [ ] **JSONs already copied but not registered:** WWA (AS112), SSB (AS123), LIB (AS124), CPISB (AS154), East/West/North Hall housing (AS142–144). Several have no `01` level in `src/`, so check which floors are missing
- [ ] **Not in the app yet:** the remaining public buildings from `Floor Data/` (AS104, AS110, AS111, AS114, and others; get the list by comparing `Floor Data/` with `buildings-config.json`)
- [ ] AS121 floor `04` is registered, but our notes say it's a maintenance space. Tell the teammate
- [ ] Skybridges: check that AS107 West Bridge (2nd floor, no DXF), AS164 Parrish Bridge (3rd floor) and AS120 Arcade are modeled as `skybridges` in the config. The 3D view needs each bridge as its own floor JSON: AS120 (B1, 01, 02) and AS164-03 are already in `Floor Data/`, AS107 still needs extracting from `AS107-01.pdf`
- [ ] **Central Parking Garage bridge** (the curved one in front of the garage, NSB ↔ CPG ↔ CPG's elevator tower by SSB). Found 2026-10-27:
  - `AS150-03.dxf` draws it with **solid walls and windows**, so it's walkable on CPG floor `03`. It already lands in `Floor Data/AS150-03.json` and needs no cleanup. Register AS150-03 and mark skybridge portals at both ends
  - `AS150-02.dxf` only shows it dashed (`HIDDEN` layer = overhead, the floor above), so don't turn those lines into walls on floor 02
  - `AS122-02.dxf` (NSB) draws the NSB end on its dashed `HIDDEN` layer (double walls, posts, mullions). The extractor now drops it (section 12). NSB floor `02` meets CPG floor `03` (grade change), so the skybridge pair joins different floor numbers
  - No other DXF contains this bridge
- [ ] Exterior doors: AS105 has fewer exits than the drawing suggests, and AS103 lost one (known issues the teammate deferred)

## 4. Hosting (navigator.cheeseverse.net)
- [x] Site and data served from the same nginx host. Deploy is `scp` of changed files only (see "Deployment" in `agents.md`)
- [ ] Serve JSON compressed (gzip/brotli). The floor JSONs are large and loaded at boot
- [ ] Short cache time for `buildings-config.json` and `osm-paths.json`; long for floor JSONs and `scak.pmtiles`

## 5. Frontend (Oropendula)
- [x] Split into ES modules (`geo`, `navgraph`, `campus`, `osm`, `motion`, `locate`, `arbiter`, ...), no build step
- [x] Buildings load from `buildings-config.json` instead of a hardcoded array
- [x] Floor switcher, 2D/3D view, room labels as a symbol layer
- [x] Authoring tools moved to `import.html`
- [x] Room search by UAA ID (`ESH 114A`, `CUDY ...`) or registration code, routes to the room's door
- [x] Compass permission handled per platform (`motion.mjs`)
- [x] How to run locally: `python -m http.server` in `src/` (documented in `docs/apps.md`)
- [ ] Pin one MapLibre version: `app.html` still loads CSS from unpkg 6.9.0 and JS from the local `.mjs`
- [ ] Clean up legacy files: `pathfinder.js`, `index_v1.html`, `index_v2.html`, `index2.html`, `index3.html`, and decide whether `index.html` stays alongside `app.html`

## 6. Navigation ✅ (teammate)
- [x] Per-floor walkable graph generated from walls (`navgraph.mjs`), no hand clicking
- [x] Tiered router: indoor → stairs/elevator → skybridge → outdoor OSM paths, outdoor penalized for cold weather (`campus.mjs`)
- [x] Stairs, elevators and exits extracted from DXF layers. Exits and skybridges can be placed by hand in `import.html`
- [x] Old `pathfinder.js` bugs: replaced, no longer used
- [x] Route drawn per floor, with leg-by-leg instructions in `app.html`
- [ ] Accessibility option: elevator-only routes (no stairs) — check with the teammate whether it exists

## 7. Positioning ✅ (teammate, new)
- [x] Step detection, compass heading, step-length calibration, particle filter constrained by walls, GPS/PDR fusion
- [ ] Field testing on campus. Placement error (~1–2 m) is below phone GPS error, so watch for jumps at building seams rather than overall offset (section 1, Phase B)

## 8. React migration (later)
- [ ] Port the UI to React with `react-map-gl` + MapLibre. The core `.mjs` modules have no DOM code, so they carry over as is

## 9. GeoJSON — not needed, parked
**Not part of the current pipeline.** The app loads the floor JSONs directly and converts CAD → lon/lat itself (`geo.mjs`). The only GeoJSON we make is `georef.py preview`, a view-only file for checking a georef fit on https://geojson.io. It adds no precision and nothing loads it.

**Cleanup**
- [ ] `Oropendula/src/AS101-01.geojson` was committed upstream and nothing loads it. It's byte-identical to our `georef/preview/AS101-01.geojson`. Ask the teammate whether it can be removed
- ~~GeoJSON export with IMDF schema, layer→category config, arcs to segments, label points~~ → superseded by runtime loading in the app

**What it could be used for later** (only if one of these comes up)
- **Sharing campus data outside the app:** a standard format other tools read directly (QGIS, geojson.io, ArcGIS, OpenStreetMap editors), for example to hand floor plans to UAA Facilities or GIS staff
- **IMDF export:** Apple's indoor-map format is GeoJSON-based. Needed only to publish UAA indoor maps to Apple Maps
- **Room polygons** (section 2, optional): if rooms become polygons, GeoJSON is the natural way to store and inspect them
- **Faster loading:** pre-converted, simplified GeoJSON (or vector tiles) instead of converting the full floor JSONs on the phone at boot, if load time becomes a problem
- **Visual QA:** dropping a floor on satellite imagery to check placement or stacking (section 1, Phase B, and the stair overlap check)

## 10. Places of interest (nicknames in search) — built locally in Oropendula, not yet sent to the teammate
Default list in `Oropendula/src/places.json` (edited in `places.html`), student favorites in each phone's localStorage, and votes through an external form (students sign in with their UAA email) linked by `PLACE_VOTE_FORM_URL` in `app.html`. Admins read the responses and add accepted names in `places.html`. No backend, no `/api/`. Details: `Oropendula/docs/places.md`.
- [x] `places.mjs` (shared room lookup + nickname search), search dropdown and ☆ Save in `app.html`, `places.html`, `node smoke.mjs places`
- [x] Removed the SQLite vote server (`server/`) and every `/api/` call (2026-10-27)
- [ ] Build the vote form and paste its link into `PLACE_VOTE_FORM_URL` (optional `{name}` / `{place}` placeholders fill a Google Forms pre-filled link)
- [x] Seeded `places.json` with names drawn on registered plans only (SU Subway / Enrollment, AASC Pool / Ice Rink, SMH Student Lounge / Sim Suite / CNA Lab)
- [ ] Hand the Oropendula changes to the teammate (PR upstream), then `/update-oropendula`
- [ ] Fill in the real nicknames students use (clubs, labs, offices). EIB (AS162, e.g. "AI & Robotics Lab" = EIB 303) only resolves after it's registered (section 3)
- [ ] Server: nginx basic auth on `places.html` (config in `docs/places.md`)

## 11. Routing quality: impossible paths and closed rooms (planned 2026-10-27, not started)
**Problem:** routes sometimes go where no person can, or through rooms students can't use. The router (`navgraph.mjs`) treats only `WALLS`/`WINDOWS` lines as obstacles, everything else as open floor, and every door as always open. Three causes, found across all 153 floors:
1. **Missing wall layers.** `isWallLayer` (`Oropendula/src/campus.mjs:133`) accepts only `wall(s)` / `window(s)`. CPISB (AS154) uses `fp-2$0$wall-i`, `fp-2$0$wall-i-l`, `fp-2$0$wind-i`, so most of its walls are invisible. Columns, `ELEVATOR` shafts, `Air-shaft` and `CONCRETE` are ignored everywhere
2. **Non-walkable areas count as floor.** 100 "OPEN TO BELOW" / "OTB" atrium voids, plus "ROOF", "DECK", "ATTIC SPACE", "CAT WALKS", "UNEXCAVATED"
3. **Every room is a hallway.** Doors are always open, so the shortest path cuts through offices, labs and mechanical rooms

**Key finding:** UAA room numbers encode the space type. `<floor>00<letter><n>` is shared space, and the letter says which (confirmed by the room names in CPISB's DXF attributes):

| Letter | Meaning | Count | Rule |
|---|---|---|---|
| C | Corridor (and bridges) | 371 | walkable |
| L | Lobby | 74 | walkable |
| V | Vestibule | 110 | walkable |
| S | Stair | 354 | walkable |
| E | Elevator | 109 | walkable |
| M / W / T | Men's / women's / all-gender restroom | 72 / 73 / 29 | destination only |
| A | Shaft | 162 | blocked |
| D | IDF (network) | 41 | blocked |
| U | Electrical / utility | 434 | blocked |
| J | Janitor | 93 | blocked |
| K | Kitchen | 14 | blocked |
| P | unconfirmed (probably plumbing/pipe chase) | 180 | blocked, check PDFs |
| plain number (`114A`, `301`) | classroom, office, lab | most | destination only |

"Destination only" = a route may start or end inside, never pass through.

**Plan** (pilot on AS101 ESH + AS124 Library for the atrium, then scale):
- [ ] **1. Complete the wall set.** Add the CPISB `fp-2$0$wall-*` / `wind-*` layers, `COLUMNS`, `ELEVATOR` shafts, `Air-shaft`. Add a smoke check that flags floors with suspiciously few wall segments (catches the next odd layer name)
- [ ] **2. Block non-walkable areas.** Flood-fill the region around each "OPEN TO BELOW" / "OTB" / "ROOF" / "DECK" / "ATTIC" / "CATWALK" / "UNEXCAVATED" label and each blocked-letter room (doors sealed, same trick as exit detection) and add it as an obstacle. Change goes in `navgraph-source.mjs` (wall inputs); `navgraph.mjs` stays frozen. Regenerate the `.nvg.gz` bundles from `import.html`
- [ ] **3. No cutting through rooms.** Find each destination-only room's doors the same way; the router treats them as closed unless the route starts or ends in that room. A new layer on top of the router, not a pathfinder change
- [ ] **4. Hand-editable overrides** (`access.json` per building): open a lounge, close a lab, add a blocked area the labels missed. Team-correctable without code
- [ ] **5. Pilot, then scale:** verify on AS101 + AS124, then every registered building
- [ ] **Field check: closed rooms with no door** (2026-10-27). Some rooms have walls all around and no door in the DXF or the PDF, e.g. **AS154 room 103** (CPISB floor 1, in the 102/104 hallway). Shafts are drawn with an X (AS118 `100A1`); others have no X, so it's unclear whether they're empty, inaccessible, or missing a door. Check on campus and record the answer in the overrides file (step 4). **Full list: `closed-rooms.txt`** (43 rooms to check, 176 closed as expected, 116 labels off the plan; Alaska Airlines Center labels need fixing first)
- [ ] **Open questions:** access policy (restrooms and all assigned rooms destination only? which plain-number lounges stay open?), the meaning of `P`, and 1–2 real bad routes (start, destination, floor) to use as test cases

## 12. Floor JSON cleanup: fewer shapes (planned 2026-10-27)
Some floor JSONs carry thousands of shapes that are drawing aids, not building geometry. They bloat downloads and the 3D view, and slow the app's graph build.
- [x] **Drop dashed-linetype lines in the extractor** (2026-10-27). Dashed = a drafting convention (overhead/`HIDDEN`, neighboring buildings, ceiling and column grids, centerlines, fences), never a wall on that floor. `DROP_DASHED_LINES` in `floorplan_extractor.py`; door, stair and elevator layers are exempt so portal detection is unchanged. Each JSON now has `shapes_dashed_dropped`
  - All 153 DXFs re-extracted: **312,278 → 294,019 shapes (−5.8%)**. Biggest: AS123-04 −86%, AS154-Interstitial −69%, AS119-01 −62%, ECB floors −45–52%. AS122-02 964 → 790 (its `HIDDEN` CPG-bridge drawing is gone; the bridge itself is solid in AS150-03)
  - Verified: with the rule off the extractor reproduces every shipped JSON exactly; with it on it only removes shapes
  - Also a routing fix: 17 dashed lines sat on wall layers and reached the app as solid walls, e.g. AS121-03's 3 alcove edges (sealed alcoves off). Gone now
  - Not done on purpose: matching neighbor outlines across DXFs. Each DXF has its own coordinate frame, and the linetype already marks those outlines. The "pre-cut dashes" were false alarms: AS122-02's `HIDDEN` lines are a full bridge drawing, and AS155's short wall pieces are real wall details
- [x] **Hand the new JSONs to the app** (2026-10-27, not deployed): copied all 83 `Oropendula/src/AS*-*.json`, regenerated `AS105/AS121/AS150.nvg.gz` with `gen-navgraphs.mjs`. `node smoke.mjs`: 670 pass, 1 fail that already failed before (no route to/from AS154 and AS118, same 90 pairs with the old JSONs). Original note: Checked against `buildings-config.json`: every registered floor keeps the same portal cache. Only **AS105-02, AS121-03, AS150-02** change walls, so re-copy those three and regenerate the AS105, AS121, AS150 `.nvg.gz` bundles in `import.html`, then `node smoke.mjs`. The other copies only shrink (no app-visible change)
- [ ] Optional: drop continuous drawing-only layers too (`STRIPING`, `Parking Stripes`, `FURNITURE`, `PLUMBING&KIT`, `Fixtures`). The app ignores them, so this only shrinks downloads. Agree on it with the teammate first, since other tools may use them
