import os
import sys
import math
import copy
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
import pathops

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_PATH = ROOT_DIR / "inputs" / "NotoSansOldTurkic-Regular.ttf"
OUT_DIR = ROOT_DIR / "outputs" / "ttf"
os.makedirs(OUT_DIR, exist_ok=True)

def update_font_metadata(font: TTFont, style_name: str):
    """Updates font name table IDs for OFL compliance (Gokturk family name)."""
    name_table = font['name']
    family_name = "Gokturk"
    full_name = f"{family_name} {style_name}"
    ps_name = f"{family_name}-{style_name}"
    
    # Remove any existing records for IDs 1, 2, 3, 4, 6, 16, 17 and re-add clean Unicode records
    records_to_keep = [r for r in name_table.names if r.nameID not in (1, 2, 3, 4, 6, 16, 17)]
    name_table.names = records_to_keep
    
    for platformID, platEncID, langID in [(3, 1, 0x0409), (1, 0, 0)]:
        try:
            name_table.setName(family_name, 1, platformID, platEncID, langID)
            name_table.setName(style_name, 2, platformID, platEncID, langID)
            name_table.setName(f"Gokturk:{full_name}:2026", 3, platformID, platEncID, langID)
            name_table.setName(full_name, 4, platformID, platEncID, langID)
            name_table.setName(ps_name, 6, platformID, platEncID, langID)
            name_table.setName(family_name, 16, platformID, platEncID, langID)
            name_table.setName(style_name, 17, platformID, platEncID, langID)
        except Exception:
            pass

def modify_weight(font: TTFont, delta: float) -> TTFont:
    """True outline weight modification using contour normal vector offsets and skia-pathops simplify."""
    font = copy.deepcopy(font)
    glyf = font['glyf']
    hmtx = font['hmtx']
    glyph_set = font.getGlyphSet()
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates') and len(g.coordinates) > 0:
            coords = np.array(g.coordinates, dtype=np.float64)
            flags = np.array(g.flags, dtype=bool)
            end_pts = g.endPtsOfContours
            new_coords = coords.copy()
            
            start_idx = 0
            for end_idx in end_pts:
                c_len = end_idx - start_idx + 1
                if c_len >= 3:
                    c = coords[start_idx:end_idx + 1]
                    c_flags = flags[start_idx:end_idx + 1]
                    
                    prev_pts = np.roll(c, 1, axis=0)
                    next_pts = np.roll(c, -1, axis=0)
                    
                    tangents = next_pts - prev_pts
                    normals = np.column_stack([-tangents[:, 1], tangents[:, 0]])
                    norms = np.linalg.norm(normals, axis=1, keepdims=True)
                    norms[norms == 0] = 1.0
                    unit_normals = normals / norms
                    
                    offset_scale = np.where(c_flags[:, None], 1.0, 0.7)
                    new_coords[start_idx:end_idx + 1] += unit_normals * delta * offset_scale
                start_idx = end_idx + 1
                
            for i in range(len(g.coordinates)):
                g.coordinates[i] = (int(round(new_coords[i, 0])), int(round(new_coords[i, 1])))
            g.recalcBounds(glyf)
            
            # Pass through pathops simplify to merge overlaps
            try:
                path = pathops.Path()
                g.draw(path.getPen(), glyf)
                simplified = pathops.simplify(path)
                pen = TTGlyphPen(glyph_set)
                simplified.draw(pen)
                glyf[gname] = pen.glyph()
            except Exception:
                pass
                
            w, lsb = hmtx[gname]
            hmtx[gname] = (max(0, int(round(w + delta * 1.2))), int(round(lsb)))
            
    return font

def apply_oblique(font: TTFont, angle_deg: float = 11.5) -> TTFont:
    """Shear transformation for Oblique slant (11.5 deg)."""
    font = copy.deepcopy(font)
    glyf = font['glyf']
    slant = math.tan(math.radians(angle_deg))
    matrix = ((1, 0), (slant, 1))
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates'):
            g.coordinates.transform(matrix)
            g.recalcBounds(glyf)
            
    return font

def apply_condensed(font: TTFont, scale_x: float = 0.85) -> TTFont:
    """Horizontal scaling transform for Condensed width (0.85)."""
    font = copy.deepcopy(font)
    glyf = font['glyf']
    hmtx = font['hmtx']
    matrix = ((scale_x, 0), (0, 1.0))
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates'):
            g.coordinates.transform(matrix)
            g.recalcBounds(glyf)
            
        w, lsb = hmtx[gname]
        hmtx[gname] = (int(round(w * scale_x)), int(round(lsb * scale_x)))
        
    return font

def build_variants():
    print(f"Loading base font: {SRC_PATH}")
    base_font = TTFont(str(SRC_PATH))
    
    variants = {
        "Regular": copy.deepcopy(base_font),
        "Oblique": apply_oblique(base_font, angle_deg=11.5),
        "Bold": modify_weight(base_font, delta=30.0),
        "Light": modify_weight(base_font, delta=-20.0),
        "Condensed": apply_condensed(base_font, scale_x=0.85),
    }
    
    print("\nGenerating 5 Gokturk mechanical font variants...")
    for style_name, font_obj in variants.items():
        update_font_metadata(font_obj, style_name)
        out_filename = f"Gokturk-{style_name}.ttf"
        out_path = OUT_DIR / out_filename
        font_obj.save(str(out_path))
        size_kb = out_path.stat().st_size / 1024
        print(f"   -> Generated {out_filename:25s} ({size_kb:5.1f} KB)")

if __name__ == "__main__":
    build_variants()
