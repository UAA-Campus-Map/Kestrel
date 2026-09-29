# Campus Navigator — TODO

Hosting: navigator.cheeseverse.net · Frontend: plain HTML/JS first, React later

## 0. Data sources
- [x] Building registry: `BUILDINGS` table in `floorplan_extractor.py` (from http://fpgis.uaa.alaska.edu/FPTableANC.htm). Every floor JSON gets `building_code`, `ID`, `building_name`, `level`
- [x] Run the extractor on all DXFs → `Floor Data/`
- [ ] Get DXFs for main-campus buildings that are missing them, starting with AS106 Lucy Cuddy Hall (LCH, in the prototype). Also missing: AS107, AS108, AS109, AS115, AS116, AS126, AS145–AS149, AS159, AS165, AS166
- [ ] Check DXF floors the UAA site doesn't list: AS121 floor `04`, AS154 `Interstitial`
- [ ] Add aliases to the `BUILDINGS` table for common nicknames (e.g. "Eugene Short", "Library")

## 1. Georeferencing (CAD coordinates → lon/lat)
- [ ] Define the `georef/<code>-<level>.json` format: ≥3 control points (CAD x,y ↔ lon,lat)
- [ ] Fit a similarity/affine transform by least squares in UTM 6N (EPSG:32606) using `pyproj`, and report RMS error in meters
- [ ] Georeference AS101 (Eugene Short Hall), floors B1, 01 and 02. Each floor has its own CAD origin, so align upper floors using the stair and elevator shafts
- [ ] Validate AS101 against the 63 hand-placed `esh` rooms in the prototype (distance in meters for each room)
- [ ] Build a control-point picker tool on an admin page (reuse the prototype's drag-corner idea)

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
- [ ] Room search crashes on unknown or malformed input; also support building IDs and aliases
- [ ] Compass: `DeviceOrientationEvent.requestPermission()` only exists on iOS, so on Android and desktop it throws and the compass listener is never attached
- [ ] `index.html` uses absolute paths (`/pathfinder.js`), so it needs a web server; document how to run it locally

## 6. Navigation (next phase)
- [ ] Reserve a `nav` layer in the data format: nodes and edges with `level`, plus connectors (stairs, elevators, entrances)
- [ ] Generate the walkable graph from doors and room polygons instead of clicking it by hand
- [ ] Snap segment endpoints so the graph is connected (hand-drawn `bmhroutes`/`smhroutes` segments don't share endpoints)
- [ ] Replace `pathfinder.js`:
  - `nodes` is never declared (`// nodes = [];`)
  - `pathFind()` reads `path.path`, but the function returns an array
  - the distance formula treats longitude as latitude and divides by 60
  - Dijkstra is O(n²); use A* with a priority queue or `ngraph.path`
- [ ] Draw the route in one source/layer, with instructions for each floor

## 7. React migration (later)
- [ ] Port UI modules to React components; use `react-map-gl` with MapLibre so the layer definitions carry over unchanged
