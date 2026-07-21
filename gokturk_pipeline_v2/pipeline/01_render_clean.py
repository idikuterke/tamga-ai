"""
STEP 1 — Temiz izole glyph render.
Şema (38 sınıf, her biri core + variation kod noktaları) + font manifest okunur.
Her (sınıf, kod noktası, font) üçlüsü için: font o kod noktasını destekliyorsa
beyaz zemin üzerine siyah, ortalanmış, temiz bir PNG üretir.

Kullanım:
    python 01_render_clean.py --schema ../gokturk_labels_v1_locked.json \
        --fonts font_manifest.json --out ./data/clean --size 256

Fontlar henüz yoksa: script fontsuz da çalışır, sadece 'font_coverage: missing'
raporu üretir — hangi (sınıf, kod noktası) için hiçbir fontta glyph bulunamadığını
gösterir. Bu, "elimde render edecek görsel kaynağım yok" boşluklarını erken yakalar.
"""

import argparse
import json
import os
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont


def load_schema(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_font_manifest(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["fonts"]


def font_supports_codepoint(ttfont: TTFont, codepoint_int: int) -> bool:
    """fontTools ile: bu font gerçekten bu kod noktasını render edebiliyor mu?"""
    try:
        cmap = ttfont.getBestCmap()
        return codepoint_int in cmap
    except Exception:
        return False


def all_codepoints_for_class(cls: dict):
    """Bir sınıfın core + tüm variation kod noktalarını (id, hex, glyph) olarak döner."""
    entries = []
    core_cp = cls["codepoints"].get("core_orhun") or cls["codepoints"].get("core")
    if core_cp:
        entries.append(("core", core_cp, cls["glyph_ref"].get("core_orhun") or cls["glyph_ref"].get("core")))
    for src in cls.get("sample_sources", []):
        if src.get("kind") in ("variation", "regional_variant", "sound_shift_variant", "contextual_variant"):
            cp = src.get("codepoint")
            glyph = src.get("glyph")
            if cp and glyph and glyph != "-":
                entries.append((src["kind"], cp, glyph))
    return entries


def render_glyph(font_path, glyph_char, size=256, margin_ratio=0.15):
    """Beyaz zemin, ortalanmış, siyah glyph. Augmentasyon burada YOK — bu 'temiz' katman."""
    img = Image.new("L", (size, size), color=255)
    draw = ImageDraw.Draw(img)

    font_size = int(size * (1 - 2 * margin_ratio))
    pil_font = ImageFont.truetype(font_path, font_size)

    bbox = draw.textbbox((0, 0), glyph_char, font=pil_font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]

    draw.text((x, y), glyph_char, font=pil_font, fill=0)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=256)
    args = ap.parse_args()

    schema = load_schema(args.schema)
    fonts = load_font_manifest(args.fonts)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    missing_coverage = []  # (class_id, codepoint) hiçbir fontta bulunamadı

    for cls in schema["classes"]:
        class_id = cls["id"]
        class_index = cls["index"]
        cp_entries = all_codepoints_for_class(cls)

        for kind, cp_hex, glyph_char in cp_entries:
            cp_int = int(cp_hex.replace("U+", ""), 16)
            rendered_any = False

            for font_entry in fonts:
                font_path = font_entry["path"]
                if not os.path.exists(font_path):
                    continue  # font henüz indirilmemiş/yerleştirilmemiş — sessizce atla

                try:
                    ttf = TTFont(font_path, lazy=True)
                except Exception:
                    continue

                if not font_supports_codepoint(ttf, cp_int):
                    continue

                img = render_glyph(font_path, glyph_char, size=args.size)

                fname = f"{class_index:02d}_{class_id}__{cp_hex.replace('+','')}__{font_entry['name']}.png"
                fpath = out_dir / fname
                img.save(fpath)

                manifest_rows.append({
                    "file": str(fpath),
                    "class_id": class_id,
                    "class_index": class_index,
                    "codepoint": cp_hex,
                    "variation_kind": kind,
                    "font_name": font_entry["name"],
                    "font_style_tag": font_entry.get("style_tag", ""),
                })
                rendered_any = True

            if not rendered_any:
                missing_coverage.append({"class_id": class_id, "codepoint": cp_hex, "kind": kind})

    with open(out_dir / "manifest_clean.jsonl", "w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(out_dir / "missing_coverage_report.json", "w", encoding="utf-8") as f:
        json.dump(missing_coverage, f, ensure_ascii=False, indent=2)

    print(f"Render edilen görsel sayısı: {len(manifest_rows)}")
    print(f"Hiçbir fontta bulunamayan (sınıf, kod noktası) sayısı: {len(missing_coverage)}")
    if missing_coverage:
        print("Eksik kapsam örnekleri (ilk 10):")
        for m in missing_coverage[:10]:
            print("  ", m)


if __name__ == "__main__":
    main()
