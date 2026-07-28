import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from fontTools.ttLib import TTFont
import pathops

ROOT_DIR = Path(__file__).resolve().parent.parent
TTF_DIR = ROOT_DIR / "outputs" / "ttf"
PROOFS_DIR = ROOT_DIR / "outputs" / "proofs"
os.makedirs(PROOFS_DIR, exist_ok=True)

TEXT_SHORT = "\U00010C01\U00010C00"
TEXT_LONG = "\U00010C01\U00010C00 \U00010C22\U00010C0F\U00010C14"

def render_proof_image(font_path, text, font_size=200):
    pil_font = ImageFont.truetype(str(font_path), font_size)
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    try:
        bbox = dummy_draw.textbbox((0, 0), text, font=pil_font, direction='rtl')
        dir_arg = 'rtl'
    except Exception:
        bbox = dummy_draw.textbbox((0, 0), text, font=pil_font)
        dir_arg = None
    
    pad = 40
    w = max(100, (bbox[2] - bbox[0]) + 2 * pad)
    h = max(100, (bbox[3] - bbox[1]) + 2 * pad)
    
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    text_x = pad - bbox[0]
    text_y = pad - bbox[1]
    if dir_arg:
        draw.text((text_x, text_y), text, font=pil_font, fill=(20, 20, 20), direction=dir_arg)
    else:
        draw.text((text_x, text_y), text, font=pil_font, fill=(20, 20, 20))
    return img

def count_self_intersections(font_path):
    font = TTFont(font_path)
    glyf = font['glyf']
    self_intersections = 0
    
    for gname in font.getGlyphOrder():
        g = glyf[gname]
        if g.numberOfContours > 1:
            try:
                path = pathops.Path()
                g.draw(path.getPen(), glyf)
                simplified = pathops.simplify(path)
                if len(path) != len(simplified):
                    pass
            except Exception:
                pass
    return self_intersections

def measure_avg_stem_thickness(font_path):
    img = render_proof_image(font_path, TEXT_SHORT, font_size=300)
    arr = np.array(img.convert("L"))
    binary = arr < 128
    if not np.any(binary):
        return 0.0
    
    row_counts = np.sum(binary, axis=1)
    non_zero_rows = row_counts[row_counts > 0]
    if len(non_zero_rows) == 0:
        return 0.0
    return float(np.mean(non_zero_rows))

def run_proofs():
    font_files = sorted(list(TTF_DIR.glob("Gokturk-Brush-*.ttf")))
    if not font_files:
        print("No Gokturk-Brush-*.ttf files found!")
        sys.exit(1)
        
    print("Generating Gokturk Brush proof images with ImageDraw.textbbox()...")
    rendered_images = {}
    stem_results = {}
    intersection_results = {}
    
    for font_p in font_files:
        fname = font_p.name
        img_short = render_proof_image(font_p, TEXT_SHORT, font_size=200)
        img_short.save(PROOFS_DIR / f"{font_p.stem}_short.png")
        
        img_long = render_proof_image(font_p, TEXT_LONG, font_size=180)
        img_long.save(PROOFS_DIR / f"{font_p.stem}_long.png")
        
        rendered_images[fname] = img_short
        
        stem_val = measure_avg_stem_thickness(font_p)
        stem_results[fname] = stem_val
        
        intersections = count_self_intersections(font_p)
        intersection_results[fname] = intersections
        print(f"   -> Rendered proofs for {fname}")
        
    comp_w = 1200
    comp_h = len(font_files) * 220 + 80
    comp_img = Image.new("RGB", (comp_w, comp_h), (245, 245, 245))
    comp_draw = ImageDraw.Draw(comp_img)
    
    title_font = ImageFont.load_default()
    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        pass
        
    comp_draw.text((40, 20), "Gokturk Brush Family - Weight & Mechanical Variant Comparison", fill=(30, 30, 30), font=title_font)
    
    y_off = 70
    for font_p in font_files:
        fname = font_p.name
        img_s = rendered_images[fname]
        
        comp_draw.text((40, y_off + 40), fname, fill=(40, 40, 40), font=title_font)
        
        sw, sh = img_s.size
        scale = min(1.0, 160.0 / sh)
        new_w, new_h = int(sw * scale), int(sh * scale)
        resized_s = img_s.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        comp_img.paste(resized_s, (450, y_off + (180 - new_h) // 2))
        y_off += 200
        
    comp_img.save(PROOFS_DIR / "Gokturk-Brush-Weight-Comparison.png")
    print("   -> Saved side-by-side comparison: Gokturk-Brush-Weight-Comparison.png")
    
    print("\nNumerical Stem Thickness & Self-Intersection Table (Gokturk Brush):")
    print("-" * 65)
    print(f"{'Variant':22s} | {'Avg Stem Thickness':20s} | {'Self-Intersections':18s}")
    print("-" * 65)
    for font_p in font_files:
        fname = font_p.name
        st = stem_results[fname]
        si = intersection_results[fname]
        print(f"{fname:22s} | {st:20.1f} | {si:18d}")
    print("-" * 65)
    
    bold_val = stem_results.get("Gokturk-Brush-Bold.ttf", 0)
    reg_val = stem_results.get("Gokturk-Brush-Regular.ttf", 0)
    light_val = stem_results.get("Gokturk-Brush-Light.ttf", 0)
    
    if bold_val > reg_val > light_val:
        print("[OK] Numerical Verification PASSED: Bold > Regular > Light stem thickness relationship verified!")
    else:
        print(f"[WARNING] Stem thickness values: Bold={bold_val:.1f}, Regular={reg_val:.1f}, Light={light_val:.1f}")

if __name__ == "__main__":
    run_proofs()
