import os
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TTF_DIR = ROOT_DIR / "outputs" / "ttf"
TESTS_DIR = ROOT_DIR / "outputs" / "tests"
os.makedirs(TESTS_DIR, exist_ok=True)

def run_fontbakery():
    ttf_files = list(TTF_DIR.glob("*.ttf"))
    if not ttf_files:
        print("No TTF files found in outputs/ttf!")
        sys.exit(1)
        
    html_report = TESTS_DIR / "report.html"
    cmd = [
        sys.executable, "-m", "fontbakery", "check-universal",
        "--html", str(html_report),
        *[str(f) for f in ttf_files]
    ]
    
    print("Running FontBakery (check-universal)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"FontBakery exit code: {result.returncode}")
    print(f"HTML report saved to: {html_report}")
    
    if html_report.exists():
        print(f"Report HTML size: {html_report.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    run_fontbakery()
