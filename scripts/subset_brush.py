import os
import sys
from pathlib import Path
from fontTools import subset

ROOT_DIR = Path(__file__).resolve().parent.parent
TTF_DIR = ROOT_DIR / "outputs" / "ttf"
WEB_DIR = ROOT_DIR / "outputs" / "web"
os.makedirs(WEB_DIR, exist_ok=True)

UNICODE_RANGES = "U+10C00-10C4F,U+0020,U+205A"

def subset_brush_fonts():
    brush_fonts = list(TTF_DIR.glob("Gokturk-Brush-*.ttf"))
    if not brush_fonts:
        print("No Gokturk-Brush-*.ttf files found in outputs/ttf/")
        sys.exit(1)
        
    print(f"Subsetting {len(brush_fonts)} Gokturk Brush fonts to WOFF2...")
    for ttf_path in brush_fonts:
        woff2_name = ttf_path.name.replace(".ttf", ".woff2")
        woff2_path = WEB_DIR / woff2_name
        
        args = [
            str(ttf_path),
            f"--unicodes={UNICODE_RANGES}",
            "--flavor=woff2",
            f"--output-file={woff2_path}",
            "--layout-features=*",
            "--no-hinting",
            "--desubroutinize",
        ]
        
        subset.main(args)
        
        ttf_size = ttf_path.stat().st_size / 1024
        woff2_size = woff2_path.stat().st_size / 1024
        print(f" -> {ttf_path.name:30s} TTF: {ttf_size:5.1f} KB | WOFF2: {woff2_size:5.1f} KB [{woff2_path.name}]")

if __name__ == "__main__":
    subset_brush_fonts()
