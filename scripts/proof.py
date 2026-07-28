import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from fontTools.ttLib import TTFont
import pathops

ROOT_DIR = Path(__file__).resolve().parent.parent
TTF_DIR = ROOT_DIR / "outputs" / "ttf"
OUTDIR = ROOT_DIR / "outputs" / "proofs"
os.makedirs(OUTDIR, exist_ok=True)

# Old Turkic Unicode codepoints:
# SHORT = 2 glyphs
SHORT = "\U00010C01\U00010C00"
# LONG = 5+ signs ("tengri" in Göktürk Old Turkic Unicode)
LONG = "\U00010C01\U00010C00 \U00010C22\U00010C0F\U00010C14"

CANVAS = (900, 300)

def proof_single(ttf_path: Path, text: str, out_path: Path, px: int):
    font = ImageFont.truetype(str(ttf_path), px)
    img = Image.new("RGB", CANVAS, "white")
    d = ImageDraw.Draw(img)
    # Using textbbox API as strictly mandated (draw.textsize is removed in Pillow 10)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    x = (CANVAS[0] - (r - l)) // 2 - l
    y = (CANVAS[1] - (b - t)) // 2 - t
    d.text((x, y), text, font=font, fill="black")
    img.save(str(out_path))

def render_side_by_side_comparison():
    """Renders Bold, Regular, Light side-by-side at large point size for visual comparison."""
    comp_img = Image.new("RGB", (1200, 450), "white")
    d = ImageDraw.Draw(comp_img)
    
    styles = [("Bold", "Gokturk-Bold.ttf"), ("Regular", "Gokturk-Regular.ttf"), ("Light", "Gokturk-Light.ttf")]
    y_offset = 30
    
    for label, filename in styles:
        ttf_path = TTF_DIR / filename
        if not ttf_path.exists():
            continue
        font = ImageFont.truetype(str(ttf_path), 80)
        label_font = ImageFont.truetype("arial.ttf", 24) if os.path.exists("C:/Windows/Fonts/arial.ttf") else font
        
        d.text((40, y_offset + 25), f"{label:8s}:", font=label_font, fill="#333333")
        d.text((220, y_offset), LONG, font=font, fill="black")
        y_offset += 130
        
    out_path = OUTDIR / "Gokturk-Weight-Comparison.png"
    comp_img.save(str(out_path))
    print(f"   -> Saved side-by-side comparison: {out_path.name}")

def measure_stem_thickness(ttf_path: Path) -> float:
    """Measures average glyph stroke thickness across Old Turkic glyphs."""
    font = TTFont(str(ttf_path))
    glyf = font['glyf']
    thicknesses = []
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates') and len(g.coordinates) > 4:
            path = pathops.Path()
            g.draw(path.getPen(), glyf)
            bounds = path.bounds
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            area = path.area
            if width > 0 and height > 0 and area > 0:
                # Estimate average stroke thickness = area / (perimeter estimate or height)
                approx_thickness = area / (height * 1.5)
                thicknesses.append(approx_thickness)
                
    return float(np.mean(thicknesses)) if thicknesses else 0.0

def verify_self_intersections(ttf_path: Path) -> int:
    """Verifies self-intersections count across all glyphs in font using pathops."""
    font = TTFont(str(ttf_path))
    glyf = font['glyf']
    intersections = 0
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 0 and hasattr(g, 'coordinates'):
            try:
                path = pathops.Path()
                g.draw(path.getPen(), glyf)
                # If pathops simplify changes contour count or area drastically, count as intersection
                simplified = pathops.simplify(path)
                if abs(path.area - simplified.area) > 100:
                    intersections += 1
            except Exception:
                intersections += 1
                
    return intersections

def run_proofs():
    print("Generating proof images with ImageDraw.textbbox()...")
    for filename in sorted(os.listdir(TTF_DIR)):
        if filename.endswith(".ttf"):
            name = filename[:-4]
            ttf_path = TTF_DIR / filename
            proof_single(ttf_path, SHORT, OUTDIR / f"{name}_short.png", 140)
            proof_single(ttf_path, LONG, OUTDIR / f"{name}_long.png", 70)
            print(f"   -> Rendered proofs for {filename}")

    render_side_by_side_comparison()
    
    print("\nNumerical Stem Thickness & Self-Intersection Table:")
    print("-" * 65)
    print(f"{'Variant':20s} | {'Avg Stem Thickness':20s} | {'Self-Intersections':18s}")
    print("-" * 65)
    
    stem_results = {}
    for filename in ["Gokturk-Bold.ttf", "Gokturk-Regular.ttf", "Gokturk-Light.ttf", "Gokturk-Oblique.ttf", "Gokturk-Condensed.ttf"]:
        ttf_path = TTF_DIR / filename
        if ttf_path.exists():
            stem_thick = measure_stem_thickness(ttf_path)
            self_intersects = verify_self_intersections(ttf_path)
            stem_results[filename] = stem_thick
            print(f"{filename:20s} | {stem_thick:20.1f} | {self_intersects:18d}")
            
    print("-" * 65)
    
    # Assert Bold > Regular > Light
    bold_val = stem_results.get("Gokturk-Bold.ttf", 0)
    reg_val = stem_results.get("Gokturk-Regular.ttf", 0)
    light_val = stem_results.get("Gokturk-Light.ttf", 0)
    
    if bold_val > reg_val > light_val:
        print("[OK] Numerical Verification PASSED: Bold > Regular > Light stem thickness relationship verified!")
    else:
        print(f"[WARNING] Stem thickness values: Bold={bold_val:.1f}, Regular={reg_val:.1f}, Light={light_val:.1f}")

if __name__ == "__main__":
    run_proofs()
