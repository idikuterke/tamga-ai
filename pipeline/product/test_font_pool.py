import sys
from pathlib import Path
from PIL import Image
import numpy as np
from render import render, resolve_style, STYLE_DECISION_TABLE, get_font_path

FONTS_DIR = Path(r"C:\Users\pc\gokturk_studio\pipeline\fonts")
OUTPUTS_TTF = Path(r"C:\Users\pc\gokturk_studio\outputs\ttf")
OUTPUTS_WEB = Path(r"C:\Users\pc\gokturk_studio\outputs\web")

print("1. Verifying Gokturk Mechanical Font Pool files:")
gokturk_fonts = [
    "Gokturk-Regular.ttf",
    "Gokturk-Oblique.ttf",
    "Gokturk-Bold.ttf",
    "Gokturk-Light.ttf",
    "Gokturk-Condensed.ttf",
]

for fname in gokturk_fonts:
    ttf_p = OUTPUTS_TTF / fname
    woff2_p = OUTPUTS_WEB / fname.replace(".ttf", ".woff2")
    ttf_exists = ttf_p.exists()
    woff2_exists = woff2_p.exists()
    ttf_size = ttf_p.stat().st_size / 1024 if ttf_exists else 0
    woff2_size = woff2_p.stat().st_size / 1024 if woff2_exists else 0
    print(f"   -> {fname:25s} TTF: {ttf_size:5.1f} KB [{'OK' if ttf_exists else 'MISSING'}] | WOFF2: {woff2_size:5.1f} KB [{'OK' if woff2_exists else 'MISSING'}]")

print("\n2. Verifying 3-Layer STYLE_DECISION_TABLE resolution:")
styles_to_test = ["plain", "fircha", "ink_bleed", "chalk", "ash", "stamp", "carved", "stencil", "parchment", "ember", "neon"]

for st in styles_to_test:
    spec = resolve_style(st)
    out_name = f"test_fontpool_{st}.png"
    img = render("tengri", style=st, size=512)
    img.save(out_name)
    print(f"   -> Style '{st:10s}' -> Font: '{spec['font']:22s}' | Effect: '{str(spec['effect']):10s}' | Fallback: '{spec['fallback']:22s}' -> Saved {out_name}")

print("\n3. Verifying Unknown Style Fallback:")
unknown_spec = resolve_style("non_existent_style")
assert unknown_spec["font"] == "Gokturk-Regular.ttf"
assert unknown_spec["effect"] is None
print("   -> Unknown style successfully resolves to plain fallback!")

print("\n4. Verifying Explicit Font Override:")
override_img = render("tengri", style="carved", font_name="NotoSansOldTurkic-Regular.ttf", size=512)
override_img.save("test_fontpool_override_regular.png")
print("   -> Explicit override font_name='NotoSansOldTurkic-Regular.ttf' for 'carved' rendered successfully!")

print("\nFont Pool Decision Table Verification completed successfully!")
