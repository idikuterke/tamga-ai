import os
import sys
from pathlib import Path
from fontTools.subset import main as subset_main

ROOT_DIR = Path(__file__).resolve().parent.parent
TTF_DIR = ROOT_DIR / "outputs" / "ttf"
WEB_DIR = ROOT_DIR / "outputs" / "web"
os.makedirs(WEB_DIR, exist_ok=True)

def run_subset():
    unicodes_str = "U+10C00-10C4F,U+0020,U+205A"
    print("Running pyftsubset on outputs/ttf/*.ttf ...")
    
    for ttf_file in sorted(TTF_DIR.glob("*.ttf")):
        name = ttf_file.stem
        woff2_file = WEB_DIR / f"{name}.woff2"
        
        args = [
            str(ttf_file),
            f"--unicodes={unicodes_str}",
            "--layout-features=*",
            "--flavor=woff2",
            f"--output-file={woff2_file}"
        ]
        subset_main(args)
        size_kb = woff2_file.stat().st_size / 1024
        print(f"   -> Generated {woff2_file.name:25s} ({size_kb:5.1f} KB)")

if __name__ == "__main__":
    run_subset()
