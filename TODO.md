# Campus Navigator — TODO

Hosting: navigator.cheeseverse.net · Frontend: plain HTML/JS first, React later

## 0. Data sources
- [x] Building registry: `BUILDINGS` table in `floorplan_extractor.py` (from http://fpgis.uaa.alaska.edu/FPTableANC.htm). Every floor JSON gets `building_code`, `ID`, `building_name`, `level`
- [x] Run the extractor on all DXFs → `Floor Data/`
- [x] Get DXFs for main-campus buildings that are missing them. AS106 Lucy Cuddy Hall added and extracted (B1, 01, 02 → `Floor Data/AS106-*`). B1 and 02 are small partial levels (mechanical/roof), 01 has the rooms
- [x] Compare the remaining missing codes against the UAA site: they're maintenance-only, not public walking space, so no DXF is needed. Notes in `maintainance.md`. AS107 West Bridge is tracked under Navigation
- [x] Check DXF floors the UAA site doesn't list: AS121 floor `04` and AS154 `Interstitial` are maintenance spaces, not public walking space (see `maintainance.md`)
- [x] Verify every floor JSON has its UAA identifier: all 156 JSONs (49 buildings) have `ID` and `building_name`, and every `ID` matches the UAA Identifier column on the UAA site

**Next step:** Data sources are done for every public building, so start Georeferencing with AS101 (section 1).

## 1. Georeferencing (CAD coordinates → lon/lat)
Approach: start with one building (AS101-01), measure its accuracy, write down the procedure, then repeat it for the others. Each floor has a hand-editable `Data Extraction/georef/<code>-<level>.json` (control points with a `source`, plus field `checks`), and `georef.py` refits from it, so the team can correct coordinates with data collected on campus.

Notes: CAD units are inches (door arcs are 36), but the `$INSUNITS` header is unreliable, so the fit checks the scale (≈0.0254 m/unit). The north arrow was stripped and each floor has its own CAD origin, so there's one transform per floor and rotation comes from the fit.

**Phase A: AS101-01 accuracy test**
- [x] Define the georef JSON format (plus optional `scale_m_per_unit` to lock the scale): `control_points` (`name`, `cad`, `lonlat`, `source`: prototype / map-pick / field-gps / survey, `note`, `use`), `checks` (two CAD points + a tape-measured distance), and a generated `fit` block
- [x] `georef.py init <floor> --from-prototype <name>`: seed control points by matching prototype room names to the floor's `text_lines`, and list the names that don't match
- [x] `georef.py fit <floor>`: least-squares similarity fit (numpy, local east/north plane in meters). Report the residual per point, RMS, scale vs 0.0254, and each check. Flag points over 3× the median residual instead of dropping them
- [x] `georef.py preview <floor>`: write walls, doors and labels in lon/lat as GeoJSON to look at on a map
- [x] pytest (`test_georef.py`, 6 tests): a synthetic transform is recovered, a locked scale still recovers the rotation, an outlier gets flagged, and lon/lat → plane → lon/lat round-trips
- [x] Run on AS101-01 with the `esh` prototype rooms (61 used; one of the prototype's two `100U3` rooms was 15.7 m off). A free fit gives a scale 6% too large, but the OSM footprint confirms inches, so the scale is locked at 0.0254. Walls land within 0.1–1.2 m of the OSM outline on three sides
- [x] Holdout test: **median 1.48 m, 90th percentile 2.37 m** with the scale locked. This is limited by the prototype points
- [ ] **Next: field data for ESH.** 1–2 tape-measured long distances (a corridor or exterior wall, as `checks`) to confirm the inch scale, and 3–4 building corners (`field-gps`), then refit and compare against the numbers above

**Phase B: repeatable process**
- [x] `Data Extraction/georef/README.md`: the procedure for one floor (init → fit → review flagged points → preview → add field data → refit), how to collect field points and what accuracy to expect from each `source`, with AS101-01 results as the reference

**Phase C: scale out (after Phase A looks good)**
- [ ] AS101 B1 and 02: stack them onto 01 using shaft labels that repeat across floors (`100S1`/`200S1`, `100V1`/`200V1`), falling back to manual points
- [ ] Seed the other 10 prototype buildings (bmh, lch→AS106, rh, aasc, su, ecb, esc, smh, ahs, nsb) and stack their floors
- [ ] Control-point picker admin page for buildings with no prototype data, writing the same JSON with `source: "map-pick"`
- [ ] `georef.py report`: status, point count, RMS and scale for every floor

## 2. GeoJSON export (`Data Extraction/geo_export.py`)
- [ ] Output schema modeled on IMDF: properties `building`, `level` (B1=-1, 01=1, ...), `category`
- [ ] Per-building config mapping CAD layers to categories (WALLS, DOORS, WINDOW, STAIR, ELEVATOR, ROOM_NO, ...)
- [ ] Convert arcs, circles and ellipses into line segments
- [ ] Turn room label text into label points
- [ ] Build room polygons with Shapely `polygonize` (walls + door openings), pair each with its label, and log rooms that can't be matched
- [ ] Handle special levels (`Interstitial`)
- [ ] Generate `data/campus.json` from the building fields in the exported floor JSONs
- [ ] Batch mode: process every DXF, skipping floors without a georef file and reporting them
- [ ] pytest tests for the transform and the level parsing

## 3. Hosting (navigator.cheeseverse.net)
- [ ] Folder layout `/data/<version>/campus.json` and `/data/<version>/buildings/<code>/<level>.geojson`
- [ ] Serve GeoJSON compressed (gzip/brotli), and keep the cache time short for `campus.json`
- [ ] Serve the site and data from the same domain to avoid CORS issues

## 4. Frontend refactor (plain JS, ready for React)
- [ ] Split `Oropendula/src/index.html` into ES modules: `map.js`, `data.js`, `indoor-layers.js`, `level-control.js`, `search.js`, `location.js`
- [ ] Keep core logic (data loading, search index, level selection) free of DOM code so React can reuse it
- [ ] Pin one MapLibre version; the CSS (unpkg 6.9.0) and JS (local `.mjs`) currently come from different places
- [ ] Load buildings from `campus.json` instead of the hardcoded `buildings` array
- [ ] One GeoJSON source per building with data-driven layers, replacing the hundreds of random-ID layers
- [ ] Floor switcher (filter by `level`), with indoor detail from about zoom 17
- [ ] Room labels as a symbol layer instead of DOM markers
- [ ] Keep PNG overlays as a fallback for buildings without vector data
- [ ] Move the authoring tools (Add Rooms, Define Walkable, Upload Floor Plan) to a separate admin page

## 5. Prototype bugs to fix
- [ ] Room search crashes on unknown or malformed input; also support searching by UAA building ID (e.g. `ESH`, `CUDY`)
- [ ] Compass: `DeviceOrientationEvent.requestPermission()` only exists on iOS, so on Android and desktop it throws and the compass listener is never attached
- [ ] `index.html` uses absolute paths (`/pathfinder.js`), so it needs a web server; document how to run it locally

## 6. Navigation (next phase)
- [ ] Reserve a `nav` layer in the data format: nodes and edges with `level`, plus connectors (stairs, elevators, entrances)
- [ ] Generate the walkable graph from doors and room polygons instead of clicking it by hand
- [ ] Model enclosed bridges as connector edges between buildings, so routes can stay indoors. No floor plan needed: record the two doors each bridge links, the floors they're on, and its length
  - AS107 West Bridge: 2nd-floor connection, no DXF (not needed for display)
  - AS164 Parrish Bridge: 3rd floor, DXF available
  - AS120 Arcade and Bridge Lounge: check whether it links buildings
- [ ] Snap segment endpoints so the graph is connected (hand-drawn `bmhroutes`/`smhroutes` segments don't share endpoints)
- [ ] Replace `pathfinder.js`:
  - `nodes` is never declared (`// nodes = [];`)
  - `pathFind()` reads `path.path`, but the function returns an array
  - the distance formula treats longitude as latitude and divides by 60
  - Dijkstra is O(n²); use A* with a priority queue or `ngraph.path`
- [ ] Draw the route in one source/layer, with instructions for each floor

## 7. React migration (later)
- [ ] Port UI modules to React components; use `react-map-gl` with MapLibre so the layer definitions carry over unchanged
