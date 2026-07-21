"""
/predict_word uç noktasını test etmek için basit script.
Swagger UI'daki (/docs) çoklu dosya seçme kısıtını atlar.

Kullanım:
    python test_predict_word.py glyph1.png glyph2.png glyph3.png

Görselleri, kelimenin SOLDAN SAĞA okuma sırasına göre argüman olarak ver.
"""

import sys
import json
import requests

API_URL = "http://localhost:8000/predict_word"


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python test_predict_word.py <görsel1> <görsel2> ...")
        sys.exit(1)

    paths = sys.argv[1:]
    files = [("files", (p, open(p, "rb"), "image/png")) for p in paths]

    r = requests.post(API_URL, files=files)
    print(f"HTTP {r.status_code}\n")

    if r.status_code != 200:
        print(r.text)
        return

    data = r.json()

    print("--- Harf harf (Seviye 1) ---")
    for g in data["per_glyph"]:
        mark = "✓" if g["valid"] else "✗"
        print(f"  {mark} {g['filename']}: {g['verdict']}  (güven={g['confidence']})")

    print("\n--- Ünlü uyumu (Seviye 2) ---")
    ortho = data["orthography"]
    print(f"  Tutarlı mı: {ortho['harmony_consistent']}")
    print(f"  Baskın kutup: {ortho['dominant_harmony']}")
    if ortho["violations"]:
        print("  İhlaller:")
        for v in ortho["violations"]:
            print(f"    - sıra {v['index']}: {v['class_id']} ({v['harmony']}) — beklenen {v['expected']}")
    for note in ortho.get("notes", []):
        print(f"  Not: {note}")

    print(f"\n--- GENEL SONUÇ: {'GEÇERLİ' if data['overall_valid'] else 'GEÇERSİZ'} ---")


if __name__ == "__main__":
    main()
