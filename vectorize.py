import sys
import math
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
import pathops
import ezdxf
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import mm
import fitz  # PyMuPDF

PRODUCT_DIR = Path(__file__).parent / "pipeline" / "product"
sys.path.append(str(PRODUCT_DIR))
from rules_engine import SpellingEngine

class PathopsPen(BasePen):
    def __init__(self, glyphSet):
        super().__init__(glyphSet)
        self.path = pathops.Path()

    def _moveTo(self, pt):
        self.path.moveTo(*pt)

    def _lineTo(self, pt):
        self.path.lineTo(*pt)

    def _curveToOne(self, pt1, pt2, pt3):
        self.path.cubicTo(*pt1, *pt2, *pt3)

    def _qCurveToOne(self, pt1, pt2):
        self.path.quadTo(*pt1, *pt2)

    def _closePath(self):
        self.path.close()


class MissingGlyphError(Exception):
    pass


@dataclass
class GlyphPath:
    codepoint: int
    path_line: pathops.Path
    path_local: pathops.Path
    width_mm: float
    height_mm: float

@dataclass
class VectorResult:
    path: pathops.Path
    width_mm: float
    height_mm: float
    gokturk_text: str
    codepoints: list[int]
    rule_notes: list[str]
    glyphs: list[GlyphPath]


def vectorize(
    text: str,
    font_path: str,
    height_mm: float,
    letter_spacing_em: float = 0.08,
    line_gap_em: float = 0.35,
    bold_offset_mm: float = 0.0,
    already_gokturk: bool = False,
) -> VectorResult:
    
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    
    rule_notes = []
    codepoints = []
    gokturk_text = ""
    
    if not already_gokturk:
        schema_path = Path(__file__).parent / "gokturk_labels_v1_locked.json"
        engine = SpellingEngine(str(schema_path))
        
        sequence_with_letters = engine.expected_sequence_with_letters(text)
        
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        class_meta = {c["id"]: c for c in schema["classes"]}
        
        for cid, latin_chunk, note in sequence_with_letters:
            if cid == ":":
                codepoints.append(0x205A)
                gokturk_text += "⁚"
                if note: rule_notes.append(note)
            elif cid == "literal_colon":
                codepoints.append(0x003A)
                gokturk_text += ":"
                if note: rule_notes.append(note)
            elif cid is None:
                # Dropped character
                if note: rule_notes.append(note)
            elif cid in class_meta:
                core = class_meta[cid].get("glyph_ref", {}).get("core_orhun")
                if core:
                    gokturk_text += core
                    codepoints.append(ord(core))
                    if note: rule_notes.append(f"'{latin_chunk}' -> {core}: {note}")
    else:
        gokturk_text = text
        codepoints = [ord(c) for c in text]
        rule_notes.append("Hazır Göktürkçe metin kullanıldı.")
        
    units_per_em = font['head'].unitsPerEm
    lines = gokturk_text.split('\n')
    
    min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
    
    individual_glyphs = []
    
    current_y = 0.0
    
    # Process RTL
    for line in lines:
        x = 0.0
        for ch in line:
            cp = ord(ch)
            glyph_name = cmap.get(cp)
            if not glyph_name:
                raise MissingGlyphError(f"Codepoint {cp:04X} ({ch}) not found in font.")
            
            advance = glyph_set[glyph_name].width
            advance += letter_spacing_em * units_per_em
            x -= advance
            
            pen = PathopsPen(glyph_set)
            glyph_set[glyph_name].draw(pen)
            
            p = pen.path
            p.simplify() # 1. Tek başına union (self-intersection temizliği)
            
            mat = (1.0, 0.0, 0.0, 1.0, x, current_y)
            p_pos = p.transform(*mat)
            b = p_pos.bounds
            if b:
                min_x = min(min_x, b[0])
                min_y = min(min_y, b[1])
                max_x = max(max_x, b[2])
                max_y = max(max_y, b[3])
                
            individual_glyphs.append({"cp": cp, "path": p, "x": x, "y": current_y})
            
        current_y -= (units_per_em + line_gap_em * units_per_em)
        
    if min_x == float('inf'):
        min_x, min_y, max_x, max_y = 0, 0, 0, 0
        
    actual_h_units = max_y - min_y
    if actual_h_units == 0:
        actual_h_units = units_per_em
        
    scale = height_mm / actual_h_units
    
    final_glyphs = []
    final_line_path = pathops.Path()
    
    for g in individual_glyphs:
        p = g["path"]
        
        # Position in font units
        mat_pos = (1.0, 0.0, 0.0, 1.0, g["x"], g["y"])
        p_pos = p.transform(*mat_pos)
        
        # Scale and flip to mm
        mat_scale = (
            scale, 0.0, 0.0, -scale,
            -scale * min_x, scale * max_y
        )
        path_line = p_pos.transform(*mat_scale)
        
        # Apply bold to individual glyph
        if bold_offset_mm > 0:
            g_bold_path = pathops.Path()
            angles = [0, 45, 90, 135, 180, 225, 270, 315]
            for a in angles:
                rad = math.radians(a)
                dx = bold_offset_mm * math.cos(rad)
                dy = bold_offset_mm * math.sin(rad)
                c_path = pathops.Path(path_line)
                c_path = c_path.transform(1.0, 0.0, 0.0, 1.0, dx, dy)
                g_bold_path = pathops.op(g_bold_path, c_path, pathops.PathOp.UNION)
            path_line = g_bold_path
            
        path_line.simplify()
        
        # Build path_local (min_x=0, min_y=0)
        bounds_line = path_line.bounds
        if bounds_line:
            pl_min_x, pl_min_y, pl_max_x, pl_max_y = bounds_line
            gw = pl_max_x - pl_min_x
            gh = pl_max_y - pl_min_y
            path_local = path_line.transform(1.0, 0.0, 0.0, 1.0, -pl_min_x, -pl_min_y)
        else:
            gw, gh = 0, 0
            path_local = pathops.Path()
            
        final_glyphs.append(GlyphPath(
            codepoint=g["cp"],
            path_line=path_line,
            path_local=path_local,
            width_mm=gw,
            height_mm=gh
        ))
        
        # Satırın birleşik yolu, tekil damgaların birleşmesinden oluşur
        final_line_path = pathops.op(final_line_path, path_line, pathops.PathOp.UNION)
        
    bounds_mm = final_line_path.bounds
    if bounds_mm:
        w_mm = bounds_mm[2] - bounds_mm[0]
        h_mm = bounds_mm[3] - bounds_mm[1]
    else:
        w_mm = 0
        h_mm = 0

    return VectorResult(
        path=final_line_path,
        width_mm=w_mm,
        height_mm=h_mm,
        gokturk_text=gokturk_text,
        codepoints=codepoints,
        rule_notes=rule_notes,
        glyphs=final_glyphs
    )

def write_svg(result: VectorResult, out_path: str):
    svg_paths = ""
    for verb, pts in result.path:
        if verb == pathops.PathVerb.MOVE:
            svg_paths += f"M {pts[0][0]:.3f} {pts[0][1]:.3f} "
        elif verb == pathops.PathVerb.LINE:
            svg_paths += f"L {pts[0][0]:.3f} {pts[0][1]:.3f} "
        elif verb == pathops.PathVerb.QUAD:
            svg_paths += f"Q {pts[0][0]:.3f} {pts[0][1]:.3f} {pts[1][0]:.3f} {pts[1][1]:.3f} "
        elif verb == pathops.PathVerb.CUBIC:
            svg_paths += f"C {pts[0][0]:.3f} {pts[0][1]:.3f} {pts[1][0]:.3f} {pts[1][1]:.3f} {pts[2][0]:.3f} {pts[2][1]:.3f} "
        elif verb == pathops.PathVerb.CLOSE:
            svg_paths += "Z "
            
    pad = 2.0
    w = result.width_mm + 2 * pad
    h = result.height_mm + 2 * pad
    
    svg_paths = f'<g transform="translate({pad}, {pad})"><path d="{svg_paths}" fill="#000000" fill-rule="nonzero"/></g>'
    
    svg = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg width="{w:.2f}mm" height="{h:.2f}mm" viewBox="0 0 {w:.2f} {h:.2f}" xmlns="http://www.w3.org/2000/svg">
{svg_paths}
</svg>'''
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)

def write_pdf(result: VectorResult, out_path: str, is_stencil: bool = False, order_id: str = "", font_height_mm: float = 0.0):
    pad = 5.0
    w_pt = (result.width_mm + 2 * pad) * mm
    h_pt = (result.height_mm + 2 * pad) * mm
    
    c = pdf_canvas.Canvas(out_path, pagesize=(w_pt, h_pt))
    
    if is_stencil:
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, w_pt, h_pt, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
    else:
        c.setFillColorRGB(0, 0, 0)
        
    p = c.beginPath()
    
    last_pt = (0, 0)
    for verb, pts in result.path:
        if verb == pathops.PathVerb.MOVE:
            px, py = pts[0][0] * mm + pad * mm, h_pt - (pts[0][1] * mm + pad * mm)
            p.moveTo(px, py)
            last_pt = pts[0]
        elif verb == pathops.PathVerb.LINE:
            px, py = pts[0][0] * mm + pad * mm, h_pt - (pts[0][1] * mm + pad * mm)
            p.lineTo(px, py)
            last_pt = pts[0]
        elif verb == pathops.PathVerb.QUAD:
            p0 = last_pt
            p1 = pts[0]
            p2 = pts[1]
            cp1x = p0[0] + 2/3 * (p1[0] - p0[0])
            cp1y = p0[1] + 2/3 * (p1[1] - p0[1])
            cp2x = p2[0] + 2/3 * (p1[0] - p2[0])
            cp2y = p2[1] + 2/3 * (p1[1] - p2[1])
            
            p.curveTo(
                cp1x * mm + pad * mm, h_pt - (cp1y * mm + pad * mm),
                cp2x * mm + pad * mm, h_pt - (cp2y * mm + pad * mm),
                p2[0] * mm + pad * mm, h_pt - (p2[1] * mm + pad * mm)
            )
            last_pt = p2
        elif verb == pathops.PathVerb.CUBIC:
            p.curveTo(
                pts[0][0] * mm + pad * mm, h_pt - (pts[0][1] * mm + pad * mm),
                pts[1][0] * mm + pad * mm, h_pt - (pts[1][1] * mm + pad * mm),
                pts[2][0] * mm + pad * mm, h_pt - (pts[2][1] * mm + pad * mm)
            )
            last_pt = pts[2]
        elif verb == pathops.PathVerb.CLOSE:
            p.close()
            
    c.drawPath(p, fill=1, stroke=0)
    c.save()

def get_point_on_quad(p0, p1, p2, t):
    x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
    y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
    return (x, y)

def get_point_on_cubic(p0, p1, p2, p3, t):
    x = (1-t)**3 * p0[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
    y = (1-t)**3 * p0[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
    return (x, y)

def flatten_path(path: pathops.Path, tol=0.02) -> List[List[Tuple[float, float]]]:
    steps = 30
    
    polylines = []
    current_poly = []
    last_pt = (0, 0)
    
    for verb, pts in path:
        if verb == pathops.PathVerb.MOVE:
            if current_poly:
                polylines.append(current_poly)
            current_poly = [pts[0]]
            last_pt = pts[0]
        elif verb == pathops.PathVerb.LINE:
            current_poly.append(pts[0])
            last_pt = pts[0]
        elif verb == pathops.PathVerb.QUAD:
            p0 = last_pt
            p1 = pts[0]
            p2 = pts[1]
            for i in range(1, steps + 1):
                t = i / steps
                current_poly.append(get_point_on_quad(p0, p1, p2, t))
            last_pt = p2
        elif verb == pathops.PathVerb.CUBIC:
            p0 = last_pt
            p1 = pts[0]
            p2 = pts[1]
            p3 = pts[2]
            for i in range(1, steps + 1):
                t = i / steps
                current_poly.append(get_point_on_cubic(p0, p1, p2, p3, t))
            last_pt = p3
        elif verb == pathops.PathVerb.CLOSE:
            if current_poly and current_poly[0] != current_poly[-1]:
                current_poly.append(current_poly[0])
            polylines.append(current_poly)
            current_poly = []
            
    if current_poly:
        polylines.append(current_poly)
        
    return polylines

def write_dxf(result: VectorResult, out_path: str):
    doc = ezdxf.new()
    doc.header['$INSUNITS'] = 4 # mm
    msp = doc.modelspace()
    doc.layers.add(name="GOKTURK")
    
    polylines = flatten_path(result.path)
    for poly in polylines:
        dxf_points = [(p[0], result.height_mm - p[1]) for p in poly]
        msp.add_lwpolyline(dxf_points, dxfattribs={"layer": "GOKTURK", "closed": True})
        
    doc.saveas(out_path)

def write_png(pdf_path: str, out_path: str, dpi: int = 300):
    doc = fitz.open(pdf_path)
    pix = doc[0].get_pixmap(dpi=dpi, alpha=True)
    pix.save(out_path)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--font", required=True)
    parser.add_argument("--height", type=float, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    res = vectorize(args.text, args.font, args.height)
    print("Vectorized length:", len(res.gokturk_text))
    
    write_svg(res, str(out_dir / "test.svg"))
    write_pdf(res, str(out_dir / "test.pdf"), font_height_mm=args.height)
    write_dxf(res, str(out_dir / "test.dxf"))
    write_png(str(out_dir / "test.pdf"), str(out_dir / "test.png"), dpi=300)
    print("Files written.")
