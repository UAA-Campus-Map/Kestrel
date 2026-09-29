import json
import sys
import threading
import queue
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF 1.24+
except ImportError:
    import fitz

try:
    import ezdxf
    from ezdxf import bbox as dxf_bbox
    from ezdxf import colors as dxf_colors
except ImportError:
    ezdxf = None


# Shapes below this size (bbox diagonal, in the source file's own units --
# points for PDF, drawing units for DXF) are dropped as noise: hatch ticks,
# dash-pattern fragments, texture marks. These make up the bulk of a raw
# architectural export and add nothing usable for room/wall geometry.
# Set to 0 to disable filtering and keep every primitive.
MIN_FEATURE_SIZE = 0.75

SUPPORTED_SUFFIXES = {".pdf", ".dxf"}

# Anchored to the script's own location rather than the current working
# directory, so output always lands in Floor Data/ next to Floor Plans/
# regardless of where you launch the script from.
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "Floor Data"

# UAA facility code -> (ID, building name), from the official Anchorage
# floor plan list at http://fpgis.uaa.alaska.edu/FPTableANC.htm. Source files
# are named <code>-<level> (AS101-01.dxf is Eugene Short Hall, floor 1), so
# every JSON gets its building's name and ID from this table. Codes marked
# "No Longer Used" on that page are left out.
BUILDINGS = {
    # Main Campus Buildings
    "AS101": ("ESH", "Eugene Short Hall"),
    "AS102": ("SMH", "Sally Monserud Hall"),
    "AS103": ("BMH", "Beatrice McDonald Hall"),
    "AS104": ("GHH", "Gordon Hartlieb Hall"),
    "AS105": ("RH", "Edward & Cathryn Rasmuson Hall"),
    "AS106": ("CUDY", "Lucy Cuddy Hall"),
    "AS107": ("WB", "West Bridge"),
    "AS108": ("GRN", "Greenhouse"),
    "AS109": ("GRS", "Greenhouse Storage"),
    "AS110": ("ADT", "Auto/Diesel Technology Building"),
    "AS111": ("PSB", "Professional Studies Building"),
    "AS112": ("WWA", "Wendy Williamson Auditorium"),
    "AS114": ("AHS", "Allied Health Sciences Building"),
    "AS115": ("EM1", "Total Energy Module #1"),
    "AS116": ("EM2", "Total Energy Module #2"),
    "AS117": ("AASC", "Avis Alaska Sports Complex"),
    "AS118": ("ESC", "Enrollment Service Center"),
    "AS119": ("SU", "Student Union"),
    "AS120": ("ABL", "Arcade and Bridge Lounge"),
    "AS121": ("ECB", "Engineering & Computation Building"),
    "AS122": ("NSB", "Natural Sciences Building"),
    "AS123": ("SSB", "Social Sciences Building"),
    "AS124": ("LIB", "Consortium Library"),
    "AS125": ("ADM", "Administration/Humanities Building"),
    "AS126": ("ADU", "Administration Utility Building"),
    "AS127": ("ART", "Fine Arts Building"),
    "AS128": ("SH1", "Student Housing Building #1"),
    "AS129": ("SH2", "Student Housing Building #2"),
    "AS130": ("SH3", "Student Housing Building #3"),
    "AS131": ("SH4", "Student Housing Building #4"),
    "AS132": ("SH5", "Student Housing Building #5"),
    "AS133": ("SH6", "Student Housing Building #6"),
    "AS135": ("TWA", "Temple Wood Building A"),
    "AS136": ("TWB", "Temple Wood Building B"),
    "AS137": ("TWC", "Temple Wood Building C"),
    "AS138": ("TWD", "Temple Wood Building D"),
    "AS139": ("TWE", "Temple Wood Building E"),
    "AS140": ("TWF", "Temple Wood Building F"),
    "AS141": ("CMMNS", "Commons"),
    "AS142": ("EASTH", "East Hall Student Housing"),
    "AS143": ("WESTH", "West Hall Student Housing"),
    "AS144": ("NORTHH", "North Hall Student Housing"),
    "AS145": ("GAO", "Grounds Administration Office"),
    "AS146": ("GSO", "Grounds Staff Office"),
    "AS147": ("GES", "Grounds Equipment Shed"),
    "AS148": ("GIE", "Grounds Irrigation Equipment Shed"),
    "AS149": ("CSS", "Custodial Storage Shed"),
    "AS150": ("CPG", "Central Parking Garage"),
    "AS151": ("EBL", "Ecosystem-Biomedical Health Laboratory"),
    "AS153": ("ANSEP", "Alaska Native Science and Engineering Programs Building"),
    "AS154": ("CPISB", "ConocoPhillips Integrated Science Building"),
    "AS155": ("EPG", "East Parking Garage"),
    "AS156": ("HSB", "Health Sciences Building"),
    "AS157": ("AAC", "Alaska Airlines Center"),
    "AS158": ("AAB", "ANSEP Academy Building"),
    "AS159": ("HMB", "EBL Hazardous Material Storage"),
    "AS160": ("ETB1", "Engineering Temporary Building #1"),
    "AS161": ("ETB2", "Engineering Temporary Building #2"),
    "AS162": ("EIB", "Engineering & Industry Building"),
    "AS163": ("ENPG", "Engineering Parking Garage"),
    "AS164": ("PB", "Parrish Bridge"),
    "AS165": ("IP1", "Ice Plant 1"),
    "AS166": ("WMB", "Winter Maintenance Building"),
    # Off-Campus Buildings
    "AO101": ("AVC", "Aviation Technology Complex"),
    "AO102": ("AVS", "Aviation Storage Building"),
    "AO106": ("ULB", "University Lake Building"),
    "AO107": ("ULA", "University Lake Annex"),
    "AO108": ("UC", "University Center"),
    "AO109": ("TRB", "Transportation Research Building"),
    "AO110": (None, "State Fairgrounds Cabin"),
    "AO111": ("BOC3", "1901 Bragaw Office Complex #3"),
    "AO112": ("GLT", "Goose Lake Townhomes"),
    "AO113": ("KBAY", "Kachemak Bay National Estuarine Research Center"),
    "AO114": ("TBA", "TBA"),
    "AO115": ("WCC", "Widgeon Court Condominiums"),
    # Anchorage Lease Space
    "AL121": (None, "SBDC - Matsu"),
    "AL124": (None, "Gambell Professional Building"),
    "AL127": (None, "SBDC - Soldotna"),
    "AL129": (None, "UC Warehouse"),
    "AL139": (None, "SBDC - Fairbanks"),
    "AL143": (None, "SBDC - Ketchikan"),
    "AL144": (None, "SBDC - Juneau"),
    # Others
    "SW914": ("BOC1", "1815 Bragaw Office Complex #1"),
}


def building_info(stem):
    """Return the building fields for a source file stem like 'AS101-01'.
    Unknown codes still get building_code/level, with ID and name None."""
    code, _, level = stem.partition("-")
    code = code.upper()
    building_id, name = BUILDINGS.get(code, (None, None))
    return {"building_code": code, "ID": building_id, "building_name": name, "level": level or None}


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _pt(x, y):
    return [round(x, 2), round(y, 2)]


def _bbox_diag(bbox):
    if not bbox:
        return 0.0
    x0, y0, x1, y1 = bbox
    return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5


def _is_scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


def _pretty_json(value, indent=0, step=2):
    """Like json.dumps(indent=2), except a list made up entirely of scalars
    (e.g. a bbox) or entirely of scalar-lists (e.g. polyline points) is kept
    one row per element instead of one line per number -- plain indent=2
    would spread a single [x, y] pair across 4 lines, which makes anything
    with real coordinate data unreadable rather than more readable."""
    pad, pad_in = " " * indent, " " * (indent + step)

    if isinstance(value, dict):
        if not value:
            return "{}"
        rows = [f'{pad_in}{json.dumps(k)}: {_pretty_json(v, indent + step, step)}' for k, v in value.items()]
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"

    if isinstance(value, list):
        if not value:
            return "[]"
        if all(_is_scalar(v) for v in value):
            return json.dumps(value)
        if all(isinstance(v, list) and all(_is_scalar(x) for x in v) for v in value):
            rows = [f"{pad_in}{json.dumps(v)}" for v in value]
            return "[\n" + ",\n".join(rows) + "\n" + pad + "]"
        rows = [f"{pad_in}{_pretty_json(v, indent + step, step)}" for v in value]
        return "[\n" + ",\n".join(rows) + "\n" + pad + "]"

    return json.dumps(value)


def _dump(data, pretty=True):
    if pretty:
        return _pretty_json(data)
    # Compact separators: for a file with tens of thousands of coordinate
    # pairs, indent=2 pretty-printing multiplies the byte size several times
    # over with pure whitespace. Use pretty=False for shipping into the app
    # once you're done debugging a given extraction.
    return json.dumps(data, separators=(",", ":"))


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _serialize_path_item(item):
    """Turn one PyMuPDF drawing command into plain JSON."""
    op = item[0]
    if op == "l":   # line: p1, p2
        return {"op": "line", "points": [_pt(item[1].x, item[1].y), _pt(item[2].x, item[2].y)]}
    if op == "c":   # cubic bezier: p1, ctrl1, ctrl2, p2
        return {"op": "curve", "points": [_pt(p.x, p.y) for p in item[1:5]]}
    if op == "re":  # rectangle
        r = item[1]
        return {"op": "rect", "rect": [round(v, 2) for v in (r.x0, r.y0, r.x1, r.y1)]}
    if op == "qu":  # quad
        q = item[1]
        return {"op": "quad", "points": [_pt(q.ul.x, q.ul.y), _pt(q.ur.x, q.ur.y), _pt(q.lr.x, q.lr.y), _pt(q.ll.x, q.ll.y)]}
    return {"op": op}


def _merge_path_items(items):
    """Collapse chains of connected line segments into single polylines and
    drop zero-length lines. Architectural PDFs draw hatching and dash
    patterns as hundreds of tiny 'l' commands; this cuts that down to one
    entry per continuous stroke without losing any geometry."""
    merged = []
    poly = None
    for item in items:
        op = item[0]
        if op == "l":
            p1, p2 = item[1], item[2]
            if p1 == p2:
                continue
            a, b = _pt(p1.x, p1.y), _pt(p2.x, p2.y)
            if poly and poly[-1] == a:
                poly.append(b)
            else:
                if poly:
                    merged.append({"op": "polyline", "points": poly})
                poly = [a, b]
            continue
        if poly:
            merged.append({"op": "polyline", "points": poly})
            poly = None
        merged.append(_serialize_path_item(item))
    if poly:
        merged.append({"op": "polyline", "points": poly})
    return merged


def _color(c):
    return [round(v, 3) for v in c] if c else None


# Shapes closer than this (in points) are treated as part of the same
# drawing when separating the building from the sheet's other annotations.
_GROUP_GAP = 10
# Whitespace kept around the building when cropping to it.
_PLAN_MARGIN = 6


def _find_sheet_frame(page, drawings):
    """UAA sheets draw everything except the title block inside a thin
    stroked frame: the smallest stroked rectangle covering most of the page.
    If a sheet puts its title block inside the frame instead, it's split off
    by a full-width horizontal rule in the lower part -- cut there. Returns
    None if the sheet has no frame."""
    pr = page.rect
    frames = [
        d["rect"] for d in drawings
        if d.get("color") is not None
        and d["rect"].width >= pr.width * 0.7
        and d["rect"].height >= pr.height * 0.5
        and any(item[0] in ("re", "qu") for item in d["items"])
    ]
    if not frames:
        return None
    frame = fitz.Rect(min(frames, key=lambda r: r.width * r.height))

    rules = [
        d["rect"] for d in drawings
        if d["rect"].width >= frame.width * 0.9
        and d["rect"].height <= 4
        and frame.y0 + frame.height * 0.6 <= d["rect"].y0 < frame.y1 - 5
    ]
    if rules:
        frame.y1 = min(r.y0 for r in rules)
    return frame


def _largest_group(rects, gap=_GROUP_GAP, cell=50):
    """Group rects that lie within `gap` of each other (transitively) and
    return the bounding box of the group that covers the most area. Uses a
    coarse grid so only nearby rects are compared."""
    parent = list(range(len(rects)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = {}
    for i, r in enumerate(rects):
        for gx in range(int((r.x0 - gap) // cell), int((r.x1 + gap) // cell) + 1):
            for gy in range(int((r.y0 - gap) // cell), int((r.y1 + gap) // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)

    for ids in grid.values():
        for a, i in enumerate(ids):
            ra = rects[i]
            for j in ids[a + 1:]:
                rb = rects[j]
                if (ra.x0 - gap <= rb.x1 and rb.x0 - gap <= ra.x1
                        and ra.y0 - gap <= rb.y1 and rb.y0 - gap <= ra.y1):
                    parent[root(i)] = root(j)

    groups = {}
    for i, r in enumerate(rects):
        g = root(i)
        groups[g] = groups[g] | r if g in groups else fitz.Rect(r)
    return max(groups.values(), key=lambda r: r.width * r.height, default=None)


def find_plan_area(page):
    """Return the part of the sheet that holds just the building, or None if
    no sheet frame is found.

    Inside the sheet frame there's more than the building: a scale bar and a
    north arrow sit off to the side. Those are separate clusters of shapes,
    while the building's walls, doors and room labels all sit close together,
    so the building is the largest cluster inside the frame."""
    drawings = page.get_drawings()
    frame = _find_sheet_frame(page, drawings)
    if frame is None:
        return None

    rects = [d["rect"] for d in drawings]
    for block in page.get_text("dict")["blocks"]:
        rects += [fitz.Rect(line["bbox"]) for line in block.get("lines", [])]
    # Edge comparisons rather than `in`, since zero-height/width lines have
    # an empty Rect. Frame-wide lines are the frame itself or its rules.
    rects = [
        r for r in rects
        if frame.x0 <= r.x0 and r.x1 <= frame.x1 and frame.y0 <= r.y0 and r.y1 <= frame.y1
        and r.width < frame.width * 0.9
    ]

    building = _largest_group(rects)
    if building is None:
        return frame
    return (building + (-_PLAN_MARGIN, -_PLAN_MARGIN, _PLAN_MARGIN, _PLAN_MARGIN)) & frame


def crop_to_plan_area(page):
    """Strip everything outside the building (title block, sheet border,
    crop marks, scale bar, north arrow) from the page and crop the page to that area, so
    both the SVG and the extracted JSON only cover the plan. Coordinates
    after this are relative to the top-left of the plan area. Returns the
    area in original page coordinates, or None if the page was left as-is."""
    area = find_plan_area(page)
    if area is None:
        return None

    pr = page.rect
    outside = [
        fitz.Rect(pr.x0, pr.y0, pr.x1, area.y0),   # above
        fitz.Rect(pr.x0, area.y1, pr.x1, pr.y1),   # below (title block)
        fitz.Rect(pr.x0, pr.y0, area.x0, pr.y1),   # left
        fitz.Rect(area.x1, pr.y0, pr.x1, pr.y1),   # right
    ]
    for r in outside:
        if not r.is_empty:
            page.add_redact_annot(r, fill=False)
    # Removes most of the surrounding vector art and text from the output
    # (not just hiding it). A few degenerate zero-height paths slip through
    # redaction; the cropbox below clips those out of the SVG, and
    # extract_page() filters them out of the JSON.
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_REMOVE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )
    page.set_cropbox(area)
    return area


def extract_page(page, min_feature_size=MIN_FEATURE_SIZE):
    """Return a dict of text, shapes and page info for one PDF page."""
    visible = page.rect
    text_lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = " ".join(s["text"].strip() for s in line["spans"] if s["text"].strip())
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            if not fitz.Rect(line["bbox"]).intersects(visible):
                continue
            text_lines.append({
                "text": text,
                "x": round((x0 + x1) / 2, 2),
                "y": round((y0 + y1) / 2, 2),
                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                "size": round(line["spans"][0]["size"], 2),
                "font": line["spans"][0]["font"],
            })

    # Vector paths: walls, room outlines, symbols, hatching, etc.
    shapes = []
    dropped = 0
    for d in page.get_drawings():
        r = d["rect"]
        # Zero-height/width lines have an empty Rect, which never
        # "intersects" anything, so compare the edges directly.
        if r.x1 < visible.x0 or r.x0 > visible.x1 or r.y1 < visible.y0 or r.y0 > visible.y1:
            continue
        bbox = [round(v, 2) for v in (r.x0, r.y0, r.x1, r.y1)]
        has_fill = bool(d.get("fill"))
        if not has_fill and _bbox_diag(bbox) < min_feature_size:
            dropped += 1
            continue
        shapes.append({
            "bbox": bbox,
            "stroke": _color(d.get("color")),
            "fill": _color(d.get("fill")),
            "width": round(d["width"], 3) if d.get("width") is not None else None,
            "closed": d.get("closePath", False),
            "layer": d.get("layer") or None,   # CAD-exported PDFs sometimes keep layer names
            "items": _merge_path_items(d["items"]),
        })

    images = page.get_images()
    has_text = bool(text_lines)
    likely_scanned = not has_text and len(images) > 0
    # A page with no text layer but very dense line-work usually means labels
    # were exported as outlined vector glyphs rather than real text (common
    # with AutoCAD "print to PDF"). likely_scanned misses this case since
    # there's no raster image either -- flag it separately.
    likely_vector_text = not has_text and len(shapes) > 800

    return {
        "page_size": [round(page.rect.width, 2), round(page.rect.height, 2)],
        "rotation": page.rotation,
        "likely_scanned": likely_scanned,
        "likely_vector_text": likely_vector_text,
        "text_line_count": len(text_lines),
        "shape_count": len(shapes),
        "shapes_filtered": dropped,
        "text_lines": text_lines,
        "shapes": shapes,
    }


def process_pdf(pdf_path, out_dir, log=print, min_feature_size=MIN_FEATURE_SIZE, pretty=True, confirm_overwrite=None):
    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    existing = sorted(out_dir.glob(f"{pdf_path.stem}-p*.json")) + sorted(out_dir.glob(f"{pdf_path.stem}-p*.svg"))
    if existing and confirm_overwrite is not None and not confirm_overwrite(existing):
        log(f"  - {pdf_path.name}: skipped, existing output kept")
        return written

    with fitz.open(pdf_path) as doc:
        if doc.needs_pass:
            log(f"  ! {pdf_path.name} is password protected, skipped")
            return written

        for i, page in enumerate(doc, start=1):
            stem = f"{pdf_path.stem}-p{i}"
            plan_area = crop_to_plan_area(page)
            data = {**building_info(pdf_path.stem), **extract_page(page, min_feature_size=min_feature_size)}
            # Where the cropped plan sits on the original sheet, so JSON/SVG
            # coordinates can be mapped back to the PDF if ever needed.
            data["plan_area"] = [round(v, 2) for v in plan_area] if plan_area else None
            data["source"] = pdf_path.name
            data["page"] = i
            data["format"] = "pdf"

            json_path = out_dir / f"{stem}.json"
            json_path.write_text(_dump(data, pretty=pretty), encoding="utf-8")

            svg_path = out_dir / f"{stem}.svg"
            svg_path.write_text(page.get_svg_image(text_as_path=False), encoding="utf-8")

            written += [json_path, svg_path]
            msg = (f"  page {i}: {data['text_line_count']} text lines, {data['shape_count']} shapes"
                   f" ({data['shapes_filtered']} filtered as noise)")
            if plan_area is None:
                msg += "  (no sheet border found, title block not removed)"
            if data["likely_scanned"]:
                msg += "  (looks scanned: no text layer, will need OCR)"
            elif data["likely_vector_text"]:
                msg += "  (labels look like outlined vector glyphs, not a real text layer)"
            log(msg)

    return written


# ---------------------------------------------------------------------------
# DXF extraction
# ---------------------------------------------------------------------------

# Entity types that are legitimately skipped without needing to be reported
# as "unsupported": HATCH boundaries are exactly the kind of dense fill
# pattern that bloats the PDF path (same reasoning as MIN_FEATURE_SIZE
# above), POINT/DIMENSION/LEADER/MLEADER are annotation-only geometry that
# doesn't describe the floor plan itself.
_DXF_SKIP_TYPES = {"HATCH", "SOLID", "3DFACE", "POINT", "DIMENSION", "LEADER", "MLEADER"}
_DXF_TEXT_TYPES = {"TEXT", "MTEXT"}


def _iter_dxf_entities(entities, depth=0, max_depth=6):
    """Walk a layout's entities, transparently expanding INSERT (block
    reference) entities into their transformed contents so door/window
    symbols etc. show up as real geometry instead of an opaque block ref."""
    for e in entities:
        if e.dxftype() == "INSERT" and depth < max_depth:
            try:
                yield from _iter_dxf_entities(e.virtual_entities(), depth + 1, max_depth)
            except Exception:
                continue
        else:
            yield e


def _dxf_color(doc, entity):
    try:
        aci = entity.dxf.color
        if aci == 256:  # BYLAYER
            aci = doc.layers.get(entity.dxf.layer).color
        if aci and 0 < aci < 256:
            rgb = dxf_colors.aci2rgb(aci)
            return [round(rgb.r / 255, 3), round(rgb.g / 255, 3), round(rgb.b / 255, 3)]
    except Exception:
        pass
    return None


def _dxf_item(e):
    """Convert one simple DXF entity into a single geometry primitive, or
    None if the type isn't one we render as a shape (see _DXF_SKIP_TYPES)."""
    t = e.dxftype()
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        if (s.x, s.y) == (en.x, en.y):
            return None
        return {"op": "line", "points": [_pt(s.x, s.y), _pt(en.x, en.y)]}
    if t == "LWPOLYLINE":
        pts = [_pt(p[0], p[1]) for p in e.get_points()]
        return {"op": "polyline", "points": pts, "closed": bool(e.closed)} if len(pts) >= 2 else None
    if t == "POLYLINE":
        pts = [_pt(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        return {"op": "polyline", "points": pts, "closed": bool(e.is_closed)} if len(pts) >= 2 else None
    if t == "CIRCLE":
        c = e.dxf.center
        return {"op": "circle", "center": _pt(c.x, c.y), "radius": round(e.dxf.radius, 2)}
    if t == "ARC":
        c = e.dxf.center
        return {"op": "arc", "center": _pt(c.x, c.y), "radius": round(e.dxf.radius, 2),
                 "start_angle": round(e.dxf.start_angle, 2), "end_angle": round(e.dxf.end_angle, 2)}
    if t == "ELLIPSE":
        c = e.dxf.center
        return {"op": "ellipse", "center": _pt(c.x, c.y),
                 "major_axis": _pt(e.dxf.major_axis.x, e.dxf.major_axis.y),
                 "ratio": round(e.dxf.ratio, 3)}
    if t == "SPLINE":
        pts = [_pt(p.x, p.y) for p in e.flattening(0.1)]
        return {"op": "polyline", "points": pts} if len(pts) >= 2 else None
    return None


def _item_bbox(item):
    op = item["op"]
    if op in ("line", "polyline"):
        xs = [p[0] for p in item["points"]]
        ys = [p[1] for p in item["points"]]
        return [min(xs), min(ys), max(xs), max(ys)]
    if op in ("circle", "arc"):
        cx, cy = item["center"]
        r = item["radius"]
        return [cx - r, cy - r, cx + r, cy + r]
    if op == "ellipse":
        cx, cy = item["center"]
        mx, my = item["major_axis"]
        r = (mx ** 2 + my ** 2) ** 0.5
        return [cx - r, cy - r, cx + r, cy + r]
    return [0.0, 0.0, 0.0, 0.0]


def _dxf_text(e):
    t = e.dxftype()
    if t == "TEXT":
        text = e.dxf.text
        x, y = e.dxf.insert.x, e.dxf.insert.y
        height = e.dxf.height
    else:  # MTEXT
        text = e.plain_text()
        x, y = e.dxf.insert.x, e.dxf.insert.y
        height = e.dxf.char_height
    text = text.strip()
    if not text:
        return None
    return {
        "text": text,
        "x": round(x, 2),
        "y": round(y, 2),
        "size": round(height, 2) if height else None,
        "font": e.dxf.style if e.dxf.hasattr("style") else None,
        "layer": e.dxf.layer,
    }


def extract_dxf_layout(doc, layout, min_feature_size=MIN_FEATURE_SIZE):
    """Return a dict of text, shapes and layout info -- the DXF counterpart
    of extract_page(). DXF entities already carry meaningful layer names and
    typed geometry (LINE/ARC/CIRCLE/...) instead of raw ink strokes, so this
    needs far less cleanup than the PDF path; the one deliberate loss is
    HATCH boundary detail, skipped for the same reason PDF hatching is
    filtered -- it's fill pattern noise, not wall/room geometry."""
    text_lines = []
    shapes = []
    dropped = 0
    skipped_types = set()

    for e in _iter_dxf_entities(layout):
        t = e.dxftype()
        if t in _DXF_TEXT_TYPES:
            row = _dxf_text(e)
            if row:
                text_lines.append(row)
            continue

        item = _dxf_item(e)
        if item is None:
            if t not in _DXF_SKIP_TYPES:
                skipped_types.add(t)
            continue

        bbox = [round(v, 2) for v in _item_bbox(item)]
        if _bbox_diag(bbox) < min_feature_size:
            dropped += 1
            continue

        shapes.append({
            "bbox": bbox,
            "stroke": _dxf_color(doc, e),
            "fill": None,
            "width": None,
            "closed": item.get("closed", False),
            "layer": e.dxf.layer,
            "items": [item],
        })

    try:
        extents = dxf_bbox.extents(layout, fast=True)
        page_size = [round(extents.extmax.x - extents.extmin.x, 2),
                     round(extents.extmax.y - extents.extmin.y, 2)]
        origin = [round(extents.extmin.x, 2), round(extents.extmin.y, 2)]
    except Exception:
        page_size, origin = None, None

    return {
        "page_size": page_size,
        "origin": origin,
        "rotation": 0,
        "likely_scanned": False,
        "likely_vector_text": False,
        "text_line_count": len(text_lines),
        "shape_count": len(shapes),
        "shapes_filtered": dropped,
        "unsupported_entity_types": sorted(skipped_types),
        "text_lines": text_lines,
        "shapes": shapes,
    }


def _write_dxf_svg(doc, layout, svg_path):
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.svg import SVGBackend
    from ezdxf.addons.drawing.layout import Page, Units

    extents = dxf_bbox.extents(layout, fast=True)
    width = max(extents.extmax.x - extents.extmin.x, 1.0)
    height = max(extents.extmax.y - extents.extmin.y, 1.0)

    backend = SVGBackend()
    Frontend(RenderContext(doc), backend).draw_layout(layout)
    page = Page(width, height, units=Units.px)
    svg_path.write_text(backend.get_string(page), encoding="utf-8")


def process_dxf(dxf_path, out_dir, log=print, min_feature_size=MIN_FEATURE_SIZE, pretty=True, confirm_overwrite=None):
    if ezdxf is None:
        log(f"  ! ezdxf is not installed (pip install ezdxf) -- skipped {Path(dxf_path).name}")
        return []

    dxf_path, out_dir = Path(dxf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    existing = [p for p in (out_dir / f"{dxf_path.stem}.json", out_dir / f"{dxf_path.stem}.svg") if p.exists()]
    if existing and confirm_overwrite is not None and not confirm_overwrite(existing):
        log(f"  - {dxf_path.name}: skipped, existing output kept")
        return written

    try:
        doc = ezdxf.readfile(dxf_path)
    except (IOError, ezdxf.DXFStructureError) as e:
        log(f"  ! {dxf_path.name} could not be read ({e}), skipped")
        return written

    msp = doc.modelspace()
    data = {**building_info(dxf_path.stem), **extract_dxf_layout(doc, msp, min_feature_size=min_feature_size)}
    data["source"] = dxf_path.name
    data["page"] = 1
    data["format"] = "dxf"

    json_path = out_dir / f"{dxf_path.stem}.json"
    json_path.write_text(_dump(data, pretty=pretty), encoding="utf-8")
    written.append(json_path)

    svg_path = out_dir / f"{dxf_path.stem}.svg"
    try:
        _write_dxf_svg(doc, msp, svg_path)
        written.append(svg_path)
    except Exception as e:
        log(f"  ! could not render {dxf_path.name} to SVG ({e})")

    msg = (f"  {data['text_line_count']} text lines, {data['shape_count']} shapes"
           f" ({data['shapes_filtered']} filtered as noise)")
    if data["unsupported_entity_types"]:
        msg += f"  (skipped entity types: {', '.join(data['unsupported_entity_types'])})"
    log(msg)

    return written


# ---------------------------------------------------------------------------
# format dispatch
# ---------------------------------------------------------------------------

def process_file(path, out_dir, log=print, min_feature_size=MIN_FEATURE_SIZE, pretty=True, confirm_overwrite=None):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return process_pdf(path, out_dir, log=log, min_feature_size=min_feature_size, pretty=pretty,
                            confirm_overwrite=confirm_overwrite)
    if suffix == ".dxf":
        return process_dxf(path, out_dir, log=log, min_feature_size=min_feature_size, pretty=pretty,
                            confirm_overwrite=confirm_overwrite)
    log(f"  ! {path.name}: unsupported file type '{suffix or '(none)'}', skipped (only .pdf and .dxf are supported)")
    return []


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Floor Plan Extractor")
    root.geometry("640x480")

    selected_files = []
    out_dir_var = tk.StringVar(value=str(DEFAULT_OUT_DIR))
    filter_noise_var = tk.BooleanVar(value=True)
    pretty_var = tk.BooleanVar(value=True)
    messages = queue.Queue()

    # --- layout ---------------------------------------------------------
    top = ttk.Frame(root, padding=10)
    top.pack(fill="x")

    ttk.Button(top, text="Select PDFs / DXFs…", command=lambda: pick_files()).pack(side="left")
    files_label = ttk.Label(top, text="No files selected")
    files_label.pack(side="left", padx=10)

    out_row = ttk.Frame(root, padding=(10, 0))
    out_row.pack(fill="x")
    ttk.Label(out_row, text="Output folder:").pack(side="left")
    ttk.Entry(out_row, textvariable=out_dir_var).pack(side="left", fill="x", expand=True, padx=5)
    ttk.Button(out_row, text="Browse…", command=lambda: pick_out_dir()).pack(side="left")

    opt_row = ttk.Frame(root, padding=(10, 4))
    opt_row.pack(fill="x")
    ttk.Checkbutton(
        opt_row, text="Filter tiny hatch/noise shapes (recommended)", variable=filter_noise_var
    ).pack(side="left")
    ttk.Checkbutton(
        opt_row, text="Human-readable JSON (larger files)", variable=pretty_var
    ).pack(side="left", padx=(15, 0))

    file_list = tk.Listbox(root, height=6)
    file_list.pack(fill="x", padx=10, pady=8)

    run_row = ttk.Frame(root, padding=(10, 0))
    run_row.pack(fill="x")
    run_btn = ttk.Button(run_row, text="Extract", command=lambda: start())
    run_btn.pack(side="left")
    progress = ttk.Progressbar(run_row, mode="determinate")
    progress.pack(side="left", fill="x", expand=True, padx=10)

    log_box = tk.Text(root, height=10, state="disabled", wrap="word")
    log_box.pack(fill="both", expand=True, padx=10, pady=10)

    def log(msg):
        log_box.configure(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def pick_files():
        paths = filedialog.askopenfilenames(
            title="Select floor plan files",
            filetypes=[
                ("Floor plan files", "*.pdf *.dxf"),
                ("PDF files", "*.pdf"),
                ("DXF files", "*.dxf"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            selected_files[:] = list(paths)
            file_list.delete(0, "end")
            for p in selected_files:
                file_list.insert("end", Path(p).name)
            files_label.config(text=f"{len(selected_files)} file(s) selected")

    def pick_out_dir():
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            out_dir_var.set(d)

    def worker(files, out_dir, min_feature_size, pretty):
        def confirm_overwrite(paths):
            # Tkinter calls must happen on the main thread; hand the question
            # to poll() via the queue and block this worker thread on an
            # Event until it answers.
            event = threading.Event()
            result = {}
            messages.put(("confirm", (paths, event, result)))
            event.wait()
            return result.get("ok", False)

        for n, f in enumerate(files, start=1):
            messages.put(("log", f"Processing {Path(f).name}"))
            try:
                process_file(f, out_dir, log=lambda m: messages.put(("log", m)),
                             min_feature_size=min_feature_size, pretty=pretty,
                             confirm_overwrite=confirm_overwrite)
            except Exception as e:  # keep going if one file is broken
                messages.put(("log", f"  ! Failed: {e}"))
            messages.put(("progress", n))
        messages.put(("done", out_dir))

    def poll():
        try:
            while True:
                kind, value = messages.get_nowait()
                if kind == "log":
                    log(value)
                elif kind == "progress":
                    progress["value"] = value
                elif kind == "confirm":
                    paths, event, result = value
                    names = "\n".join(p.name for p in paths)
                    result["ok"] = messagebox.askyesno(
                        "Overwrite existing output?",
                        f"These files already exist and will be overwritten:\n\n{names}\n\nContinue?",
                    )
                    event.set()
                elif kind == "done":
                    run_btn.config(state="normal")
                    log(f"Done. Output in {value}")
                    messagebox.showinfo("Finished", f"Extraction complete.\n{value}")
                    return
        except queue.Empty:
            pass
        root.after(100, poll)

    def start():
        if not selected_files:
            messagebox.showwarning("No files", "Select at least one PDF or DXF first.")
            return
        run_btn.config(state="disabled")
        progress.config(maximum=len(selected_files), value=0)
        min_feature_size = MIN_FEATURE_SIZE if filter_noise_var.get() else 0
        threading.Thread(
            target=worker,
            args=(list(selected_files), out_dir_var.get(), min_feature_size, pretty_var.get()),
            daemon=True,
        ).start()
        poll()

    root.mainloop()


def _cli_confirm_overwrite(paths):
    names = ", ".join(p.name for p in paths)
    answer = input(f"  ! {names} already exist(s) and will be overwritten. Continue? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        # Command-line mode: python floorplan_extractor.py a.pdf b.dxf -o out/
        out = DEFAULT_OUT_DIR
        if "-o" in args:
            i = args.index("-o")
            out = args[i + 1]
            args = args[:i] + args[i + 2:]
        for f in args:
            print(f"Processing {f}")
            process_file(f, out, confirm_overwrite=_cli_confirm_overwrite)
    else:
        run_gui()
