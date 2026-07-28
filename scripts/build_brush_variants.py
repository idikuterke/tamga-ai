import os
import sys
import math
import copy
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._n_a_m_e import NameRecord, makeName
import pathops

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_FONT = ROOT_DIR / "inputs" / "Orkun-Regular.ttf"
OUTPUT_DIR = ROOT_DIR / "outputs" / "ttf"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def update_name_table(font: TTFont, family_name: str, style_name: str):
    name_table = font["name"]
    name_table.names = [n for n in name_table.names if n.nameID not in (1, 2, 3, 4, 6, 16, 17)]
    
    full_name = f"{family_name} {style_name}".strip()
    ps_name = f"{family_name.replace(' ', '')}-{style_name.replace(' ', '')}"
    unique_id = f"{ps_name}:2026"
    
    records = [
        (1, family_name),
        (2, style_name),
        (3, unique_id),
        (4, full_name),
        (6, ps_name),
        (16, family_name),
        (17, style_name),
    ]
    
    for nameID, text in records:
        for platformID, platEncID, langID in [(3, 1, 0x409), (1, 0, 0)]:
            try:
                rec = NameRecord()
                rec.nameID = nameID
                rec.platformID = platformID
                rec.platEncID = platEncID
                rec.langID = langID
                rec.string = text.encode("utf-16be" if platformID == 3 else "utf-8")
                name_table.names.append(rec)
            except Exception:
                pass

def transform_glyph_points(glyph, matrix=None, offset=0):
    if not hasattr(glyph, "coordinates") or glyph.coordinates is None:
        return
    coords = glyph.coordinates
    flags = glyph.flags
    
    if offset != 0 and hasattr(glyph, "endPtsOfContours") and len(glyph.endPtsOfContours) > 0:
        new_coords = []
        start_idx = 0
        for end_idx in glyph.endPtsOfContours:
            contour_indices = list(range(start_idx, end_idx + 1))
            n_pts = len(contour_indices)
            start_idx = end_idx + 1
            if n_pts < 2:
                for idx in contour_indices:
                    new_coords.append(coords[idx])
                continue
            
            normals = []
            for i in range(n_pts):
                prev_pt = coords[contour_indices[(i - 1) % n_pts]]
                curr_pt = coords[contour_indices[i]]
                next_pt = coords[contour_indices[(i + 1) % n_pts]]
                
                dx1, dy1 = curr_pt[0] - prev_pt[0], curr_pt[1] - prev_pt[1]
                dx2, dy2 = next_pt[0] - curr_pt[0], next_pt[1] - curr_pt[1]
                
                len1 = math.hypot(dx1, dy1) or 1.0
                len2 = math.hypot(dx2, dy2) or 1.0
                
                nx1, ny1 = -dy1 / len1, dx1 / len1
                nx2, ny2 = -dy2 / len2, dx2 / len2
                
                nx = (nx1 + nx2) / 2.0
                ny = (ny1 + ny2) / 2.0
                norm_len = math.hypot(nx, ny) or 1.0
                normals.append((nx / norm_len, ny / norm_len))
            
            for i, idx in enumerate(contour_indices):
                x, y = coords[idx]
                nx, ny = normals[i]
                is_on_curve = (flags[idx] & 1) == 1
                scale_factor = 1.0 if is_on_curve else 0.7
                new_x = x + nx * offset * scale_factor
                new_y = y + ny * offset * scale_factor
                new_coords.append((new_x, new_y))
        
        glyph.coordinates = coords.__class__(new_coords)
    
    if matrix is not None:
        (a, b), (c, d) = matrix
        new_coords = []
        for x, y in glyph.coordinates:
            nx = a * x + b * y
            ny = c * x + d * y
            new_coords.append((nx, ny))
        glyph.coordinates = glyph.coordinates.__class__(new_coords)
    
    glyph.recalcBounds(None)

def clean_glyph_overlaps(font: TTFont):
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0:
            try:
                path = pathops.Path()
                g.draw(path.getPen(), glyf)
                simplified = pathops.simplify(path)
                from fontTools.pens.ttGlyphPen import TTGlyphPen
                pen = TTGlyphPen(glyph_set)
                simplified.draw(pen)
                glyf[gname] = pen.glyph()
            except Exception:
                pass

def build_brush_variants():
    if not INPUT_FONT.exists():
        print(f"Error: Base font {INPUT_FONT} not found.")
        sys.exit(1)
        
    print(f"Building Gokturk Brush variants from {INPUT_FONT.name}...")
    
    # 1. Gokturk-Brush-Regular.ttf
    font_reg = TTFont(INPUT_FONT)
    update_name_table(font_reg, "Gokturk Brush", "Regular")
    font_reg.save(OUTPUT_DIR / "Gokturk-Brush-Regular.ttf")
    print(" -> Generated Gokturk-Brush-Regular.ttf")
    
    # 2. Gokturk-Brush-Oblique.ttf
    font_obl = TTFont(INPUT_FONT)
    shear_angle = 11.5
    matrix = ((1.0, math.tan(math.radians(shear_angle))), (0.0, 1.0))
    glyf = font_obl['glyf']
    for gname in font_obl.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0:
            transform_glyph_points(g, matrix=matrix)
    update_name_table(font_obl, "Gokturk Brush", "Oblique")
    font_obl.save(OUTPUT_DIR / "Gokturk-Brush-Oblique.ttf")
    print(" -> Generated Gokturk-Brush-Oblique.ttf")
    
    # 3. Gokturk-Brush-Bold.ttf
    font_bold = TTFont(INPUT_FONT)
    glyf = font_bold['glyf']
    hmtx = font_bold['hmtx']
    bold_offset = 30.0
    for gname in font_bold.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0:
            transform_glyph_points(g, offset=bold_offset)
            w, lsb = hmtx[gname]
            hmtx[gname] = (int(w + bold_offset * 1.5), lsb)
    clean_glyph_overlaps(font_bold)
    update_name_table(font_bold, "Gokturk Brush", "Bold")
    font_bold.save(OUTPUT_DIR / "Gokturk-Brush-Bold.ttf")
    print(" -> Generated Gokturk-Brush-Bold.ttf")
    
    # 4. Gokturk-Brush-Light.ttf
    font_light = TTFont(INPUT_FONT)
    glyf = font_light['glyf']
    hmtx = font_light['hmtx']
    light_offset = -20.0
    for gname in font_light.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0:
            transform_glyph_points(g, offset=light_offset)
            w, lsb = hmtx[gname]
            hmtx[gname] = (max(50, int(w + light_offset * 1.2)), lsb)
    clean_glyph_overlaps(font_light)
    update_name_table(font_light, "Gokturk Brush", "Light")
    font_light.save(OUTPUT_DIR / "Gokturk-Brush-Light.ttf")
    print(" -> Generated Gokturk-Brush-Light.ttf")
    
    # 5. Gokturk-Brush-Condensed.ttf
    font_cond = TTFont(INPUT_FONT)
    glyf = font_cond['glyf']
    hmtx = font_cond['hmtx']
    scale_x = 0.85
    matrix_cond = ((scale_x, 0.0), (0.0, 1.0))
    for gname in font_cond.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0:
            transform_glyph_points(g, matrix=matrix_cond)
        w, lsb = hmtx[gname]
        hmtx[gname] = (int(w * scale_x), int(lsb * scale_x))
    clean_glyph_overlaps(font_cond)
    update_name_table(font_cond, "Gokturk Brush", "Condensed")
    font_cond.save(OUTPUT_DIR / "Gokturk-Brush-Condensed.ttf")
    print(" -> Generated Gokturk-Brush-Condensed.ttf")

if __name__ == "__main__":
    build_brush_variants()
