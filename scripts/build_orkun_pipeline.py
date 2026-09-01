import os
import sys
import copy
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen

ROOT_DIR = Path(__file__).resolve().parent.parent
ORKUN_OTF = ROOT_DIR / "inputs" / "orkun" / "Orkun-Regular.otf"
NOTO_TTF = ROOT_DIR / "inputs" / "NotoSansOldTurkic-Regular.ttf"
OUT_DIR = ROOT_DIR / "outputs" / "ttf"
os.makedirs(OUT_DIR, exist_ok=True)

# Add scripts directory to path for build_variants import
sys.path.append(str(ROOT_DIR / "scripts"))
from build_variants import modify_weight, apply_oblique, apply_condensed, update_font_metadata

def convert_orkun_otf_to_ttf(otf_path: Path) -> TTFont:
    """Converts Orkun CFF (OTF) font to quadratic TrueType (TTF) using cu2qu."""
    print(f"Step 1: Converting CFF cubic to quadratic TTF for {otf_path.name}...")
    font = TTFont(str(otf_path))
    font.sfntVersion = '\x00\x01\x00\x00'

    gset = font.getGlyphSet()
    glyf = newTable('glyf')
    glyf.glyphs = {}

    for gname in font.getGlyphOrder():
        tpen = TTGlyphPen(gset)
        qpen = Cu2QuPen(tpen, max_err=1.0)
        gset[gname].draw(qpen)
        g = tpen.glyph()
        g.recalcBounds(glyf)
        glyf.glyphs[gname] = g

    glyf.glyphOrder = list(font.getGlyphOrder())
    font['glyf'] = glyf
    font['loca'] = newTable('loca')

    for tag in ['CFF ', 'CFF2', 'VORG']:
        if tag in font:
            del font[tag]

    maxp = newTable('maxp')
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 2
    maxp.maxTwilightPoints = 0
    maxp.maxStorage = 0
    maxp.maxFunctionDefs = 0
    maxp.maxInstructionDefs = 0
    maxp.maxStackElements = 0
    maxp.maxSizeOfInstructions = 0
    maxp.maxComponentElements = 0
    maxp.maxComponentDepth = 0
    font['maxp'] = maxp
    font['head'].glyphDataFormat = 0

    return font

def merge_noto_codepoints(orkun_ttf: TTFont, noto_ttf_path: Path) -> TTFont:
    """Merges missing 4 codepoints (including Yenisey signs and separator) from Noto to Orkun TTF."""
    print("Step 3: Merging missing codepoints from Noto-TTF to Orkun-TTF (with hmtx metrics)...")
    f_noto = TTFont(str(noto_ttf_path))
    cmap_n = f_noto.getBestCmap()
    hmtx_n = f_noto['hmtx']
    glyf_n = f_noto['glyf']
    
    glyf_o = orkun_ttf['glyf']
    hmtx_o = orkun_ttf['hmtx']

    target_unicodes = [0x205A, 0x10C45, 0x10C46, 0x10C47, 0x10C48]
    new_glyph_order = list(orkun_ttf.getGlyphOrder())

    for u in target_unicodes:
        if u in cmap_n:
            noto_gname = cmap_n[u]
            target_gname = f"noto_{noto_gname}"
            
            # Copy quadratic glyph outline
            g_copy = copy.deepcopy(glyf_n[noto_gname])
            glyf_o.glyphs[target_gname] = g_copy
            if target_gname not in new_glyph_order:
                new_glyph_order.append(target_gname)
                
            # Copy hmtx metric (advance width and LSB)
            hmtx_o[target_gname] = copy.deepcopy(hmtx_n[noto_gname])
            
            # Update cmap in Orkun safely based on table format
            for table in orkun_ttf['cmap'].tables:
                if table.format == 0 and u < 256:
                    table.cmap[u] = target_gname
                elif table.format == 4 and u <= 0xFFFF:
                    table.cmap[u] = target_gname
                elif table.format == 12:
                    table.cmap[u] = target_gname

    glyf_o.glyphOrder = new_glyph_order
    orkun_ttf.setGlyphOrder(new_glyph_order)
    orkun_ttf['maxp'].recalc(orkun_ttf)

    return orkun_ttf

def build_orkun_variants(base_font: TTFont):
    """Derives 5 Orkun mechanical variants with dynamic UPM reading."""
    print("Step 4: Deriving 5 Gokturk-Orkun font variants...")
    family_name = "Gokturk Orkun"
    prefix = "Gokturk-Orkun"

    # Invert delta sign to account for counter-clockwise contour winding in Orkun CFF source
    variants = {
        "Regular": copy.deepcopy(base_font),
        "Oblique": apply_oblique(base_font, angle_deg=11.5),
        "Bold": modify_weight(base_font, delta=-30.0),
        "Light": modify_weight(base_font, delta=20.0),
        "Condensed": apply_condensed(base_font, scale_x=0.85),
    }

    for style_name, font_obj in variants.items():
        update_font_metadata(font_obj, style_name, family_override=family_name, prefix_override=prefix)
        out_filename = f"{prefix}-{style_name}.ttf"
        out_path = OUT_DIR / out_filename
        font_obj.save(str(out_path))
        size_kb = out_path.stat().st_size / 1024
        print(f"   -> Generated {out_filename:30s} ({size_kb:5.1f} KB)")

import pathops

def simplify_font_glyphs(font: TTFont) -> TTFont:
    """Passes all glyph outlines in font through pathops.simplify to eliminate self-intersections."""
    print("Step 3.5: Simplifying all glyph contours with pathops.simplify...")
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates') and len(g.coordinates) > 0:
            try:
                path = pathops.Path()
                g.draw(path.getPen(), glyf)
                simplified = pathops.simplify(path)
                pen = TTGlyphPen(glyph_set)
                simplified.draw(pen)
                new_g = pen.glyph()
                new_g.recalcBounds(glyf)
                glyf[gname] = new_g
            except Exception:
                pass
    return font

def main():
    orkun_ttf = convert_orkun_otf_to_ttf(ORKUN_OTF)
    orkun_merged = merge_noto_codepoints(orkun_ttf, NOTO_TTF)
    orkun_simplified = simplify_font_glyphs(orkun_merged)
    build_orkun_variants(orkun_simplified)
    print("\nPhase 2 Orkun font generation complete!")

if __name__ == "__main__":
    main()
