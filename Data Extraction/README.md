
# Floor plan extractor

To use it pick one or more floor plan PDFs or DXFs in a Tkinter window, choose an
output folder, and each file is run through PyMuPDF (fitz) for PDF or ezdxf for
DXF. For every page/layout you get:

    <name>-p<N>.svg    rendered floor plan for the React app   (PDF: one per page)
    <name>-p<N>.json   text labels + vector shapes with coordinates
    <name>.svg / .json (DXF: single modelspace layout, no page suffix)

Every JSON starts with the building it belongs to, looked up from the file
name (`<code>-<level>`, e.g. `AS101-01`) in the `BUILDINGS` table at the top
of `floorplan_extractor.py`:

    "building_code": "AS101", "ID": "ESH",
    "building_name": "Eugene Short Hall", "level": "01"

The table comes from UAA's official list at
http://fpgis.uaa.alaska.edu/FPTableANC.htm. Edit it there if a name changes
or a building is added. A code missing from the table still gets
`building_code` and `level`, with `ID` and `building_name` set to null.

Vector geometry is cleaned up before it's written: hatch/dash fragments below
`MIN_FEATURE_SIZE` are dropped, and connected line segments are merged into
polylines. That alone cuts typical output size by ~80% versus a raw 1:1 dump
of the source file's drawing commands, so JSON is written human-readable by
default -- indented like `json.dumps(indent=2)`, except coordinate pairs
(bbox, points, center) stay on one line each instead of one number per line,
so a shape with many points doesn't turn into hundreds of lines. Pass
`pretty=False` to `process_file`/`process_pdf`/`process_dxf` (or uncheck
"Human-readable JSON" in the GUI) for a smaller, single-line-per-file
compact JSON once you're done debugging and want to ship the output. Pass
`min_feature_size=0` to disable noise filtering entirely (the GUI has a
checkbox for this too).

For PDFs, only the building itself is kept. Everything else on the sheet is
removed: the title block (UAA Facilities logo, building name, dates, sheet
number), the sheet border, crop marks, the scale bar and the north arrow.
Check the original PDFs for those. The building is found as the largest
group of nearby shapes inside the sheet's frame, and the page is cropped to
it with a small margin. That means SVG and JSON coordinates start at the
top-left corner of the building, not the top-left of the sheet. `plan_area`
in the JSON gives the crop's position on the original sheet, so you can map
coordinates back if you need to. If a sheet has no frame, it's exported
uncropped and the log says so.

DXF entities already carry real layer names and typed geometry (LINE, ARC,
CIRCLE, LWPOLYLINE, TEXT, block INSERTs...), so a DXF source needs much less
cleanup than a PDF and generally produces a smaller, more semantic JSON.
HATCH fill boundaries are intentionally skipped (same reasoning as the PDF
noise filter) since they're fill-pattern detail, not wall/room geometry.

If a file's output already exists in the output folder, you're asked to
confirm before it's overwritten (a native Yes/No dialog in the GUI, a
`[y/N]` prompt on the command line). Answering no leaves the existing output
untouched and skips just that file; the rest of the batch still runs. This
only applies to the GUI and CLI -- calling `process_file`/`process_pdf`/
`process_dxf` directly from Python overwrites silently unless you pass your
own `confirm_overwrite(paths) -> bool` callback.

## Requirements

    pip install pymupdf ezdxf pillow

(`pillow` is only needed for DXF -> SVG preview rendering via ezdxf's drawing
add-on; DXF -> JSON extraction alone doesn't need it.)

## Usage

    If you want to select the file(s) in a window use:
    python floorplan_extractor.py

    Otherwise, use the command line with one or multiple files (PDF and DXF
    can be mixed) where -o indicates the folder you want to save the files to:
    python floorplan_extractor.py a.pdf b.dxf -o out/
