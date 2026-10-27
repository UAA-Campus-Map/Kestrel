# Georeferencing floor plans

The floor JSONs in `Floor Data/` use raw CAD coordinates in inches, and each
floor has its own origin. Each file in this folder ties one floor to the real
world. `georef.py` fits a transform from that file:

    lon/lat = rotate + scale + shift (CAD x, y)

The fitted transform is written back into the same file, so later steps
(GeoJSON export, the map) only need to read it.

The files are meant to be edited by hand. When a point is wrong, or the team
collects better data on campus, edit the file and run `fit` again.

## File format: `<code>-<level>.json`

See [`EXAMPLE.jsonc`](EXAMPLE.jsonc) for a commented example of each edit:
adding a field point, adding a tape-measured check, and turning a point off.

| Field | Who writes it | What it is |
|---|---|---|
| `building_code`, `ID`, `building_name`, `level` | `init` | Same as the floor JSON |
| `scale_m_per_unit` | you, optional | Lock the scale (`0.0254` = inches) and fit only rotation and offset. Leave it out to fit the scale too |
| `scale_note` | you, optional | Why the scale is locked |
| `control_points` | `init`, then you | One per line: `name`, `cad` [x, y], `lonlat` [lon, lat], `source`, `note`, `use` |
| `checks` | you | Distances measured on campus: `what`, `cad_a`, `cad_b`, `measured_m`, `source` |
| `fit` | `fit` | Generated, so don't edit it: the transform, RMS, a residual per point (worst first), and the check results |

**`source` values**, from least to most trusted:

| source | Typical error | Where it comes from |
|---|---|---|
| `prototype` | 1–3 m, and the scale can be off | Rooms hand-placed in the prototype (`Oropendula/src/index.html`), on PNGs stretched to fit a lon/lat box |
| `map-pick` | 0.5–2 m | A building corner clicked on satellite imagery or the OSM footprint |
| `field-gps` | 3–5 m (phone), <1 m (averaged / RTK) | Standing at a point with a GPS app |
| `survey` | centimeters | Survey-grade equipment or official campus GIS |

To turn a point off without deleting it, set `"use": false` and say why in
`note`.

## Procedure for one floor

Run `georef.py` and its tests from this folder (`Data Extraction/georef/`). It finds `floorplan_extractor.py` and `Floor Data/` one folder up on its own.

1. **Extract** the floor if it isn't done yet, from `Data Extraction/`: `python floorplan_extractor.py "Floor Plans/DXFs/AS101-01.dxf" -o "Floor Data"`
2. **Init** the georef file:
   - `python georef.py init AS101-01 --from-prototype esh` if the prototype has rooms for this building. The prototype's building names are `bmh`, `lch` (AS106), `rh`, `aasc`, `su`, `ecb`, `esc`, `smh`, `esh`, `ahs`, `nsb`.
   - `python georef.py init AS101-01` otherwise, then add at least 3 points by hand. Building corners spread far apart work best.

   `init` lists prototype rooms whose label isn't on the floor, or appears on it more than once. You can add those by hand.
3. **Fit**: `python georef.py fit AS101-01 --holdout`
   - **RMS** is how far the points are from the fit. **Holdout** is the error on points left out of the fit, so it's the accuracy to report.
   - **scale vs inches** should be close to 0%. If a free fit gives several percent, the control points are stretched (prototype points are), so check against an independent source and lock the scale with `"scale_m_per_unit": 0.0254`.
   - **FLAGGED** points are more than 3× the median error (and over 1 m). Find out why, then fix the point or set `"use": false`. Don't just delete them.
4. **Preview**: `python georef.py preview AS101-01`, then drag `preview/AS101-01.geojson` onto https://geojson.io (satellite view). The walls should sit on the building with the right orientation. Green dots are control points, red are flagged ones, gray are turned off.
5. **Add field data** when you can, then refit:
   - **Distances (`checks`):** tape- or laser-measure a long straight distance, like a corridor or an exterior wall. Use the room labels or wall corners in `../Floor Data/<floor>.json` to get the two CAD points. These test the scale without any GPS.
   - **Points (`control_points`):** stand at a building corner and record its lon/lat (average a few readings). Give it `source: "field-gps"` and the accuracy in `note`. Find the same corner's CAD x, y in the floor JSON or the SVG.
6. Commit the georef JSON. The preview folder is generated and isn't tracked.

## Reference result: AS101-01 (Eugene Short Hall, floor 1), 2026-10-06

- **Points:** 62 prototype points matched (`100U13` is `U13` in the CAD, and `114A` appears 3 times). The prototype had two rooms named `100U3`; the one near 100V2 was 15.7 m off and is turned off.
- **Fitting the scale freely:** RMS 1.29 m, holdout median 1.16 m / 90th percentile 1.98 m. But the scale comes out **6% larger than inches**.
- **Independent check:** the OSM footprint (way 211383054) is 53.3 m east to west. The CAD walls are 54.6 m at inches and 57.9 m at +6%. So the CAD scale is right and the prototype overlays are stretched.
- **Locked to inches (current):** rotation -0.14°, RMS 1.60 m, holdout median 1.48 m / 90th percentile 2.37 m. The fitted walls are within 0.1 m of the OSM outline on the west edge, 0.4 m on the north and 1.2 m on the east. The OSM outline is 3 m deeper north to south than the CAD walls.

Most of the remaining error is in the prototype points themselves. Field points
should bring it under 1 m. Also, the label coordinate is the text's insert
point (the start of the label), not the room center. That's about 0.5 m of
known bias, which is smaller than the prototype's own error.

**Still to do:** a tape-measured `checks` entry to confirm the inch scale, plus a few `field-gps` corners.
