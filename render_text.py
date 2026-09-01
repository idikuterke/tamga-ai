import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PRODUCT_DIR = Path(__file__).resolve().parent / "pipeline" / "product"
if str(PRODUCT_DIR) not in sys.path:
    sys.path.insert(0, str(PRODUCT_DIR))

try:
    from app import SpellingEngine, WORD_SEPARATOR
except ImportError:
    print("HATA: Göktürkçe çeviri motoru (app.py) bulunamadı.")
    sys.exit(1)

SCHEMA_PATH = Path(__file__).resolve().parent / "gokturk_labels_v1_locked.json"

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(description="Göktürkçe metin render aracı")
    ap.add_argument("--text", required=True, help="Göktürkçe'ye çevrilip render edilecek Latin metin")
    ap.add_argument("--font", required=True, help="Font dosya adı (ör. NotoSansOldTurkic-Regular) veya tam yol")
    ap.add_argument("--size", type=int, default=96, help="Font boyutu (piksel)")
    ap.add_argument("--out", required=True, help="Çıktı PNG dosyası")
    args = ap.parse_args()

    engine = SpellingEngine(SCHEMA_PATH)
    pairs = engine.expected_sequence_with_letters(args.text)
    
    import json
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    class_meta = {c["id"]: c for c in schema["classes"]}
    
    gokturkce_chars = []
    for cid, _, _ in pairs:
        if cid == ":":
            gokturkce_chars.append("⁚")
        elif cid == "literal_colon":
            gokturkce_chars.append(":")
        elif cid in class_meta:
            glyph_ref = (class_meta[cid].get("glyph_ref") or {}).get("core_orhun")
            if glyph_ref:
                gokturkce_chars.append(glyph_ref)
        else:
            gokturkce_chars.append(cid)
            
    gokturkce_text = "".join(gokturkce_chars)
    print(f"Çevrilen Göktürkçe Metin: {gokturkce_text}")

    font_path = Path(args.font)
    if not font_path.exists():
        pipeline_font_path = Path(__file__).parent / "pipeline" / "fonts" / f"{args.font}.ttf"
        pipeline_font_path_2 = Path(__file__).parent / "pipeline" / "fonts" / args.font
        if pipeline_font_path.exists():
            font_path = pipeline_font_path
        elif pipeline_font_path_2.exists():
            font_path = pipeline_font_path_2
        elif "NotoSansOldTurkic" in args.font:
            font_path = Path(__file__).parent / "pipeline" / "fonts" / "NotoSansOldTurkic-Regular.ttf"
            
    try:
        pil_font = ImageFont.truetype(str(font_path), args.size)
    except Exception as e:
        print(f"HATA: Font yüklenemedi '{font_path}': {e}")
        return

    # Göktürkçe RTL (Sağdan Sola) yazıldığı için render ederken harfleri ters çevirmemiz gerekiyor
    display_text = gokturkce_text[::-1]

    dummy_img = Image.new("L", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    try:
        bbox = dummy_draw.textbbox((0, 0), display_text, font=pil_font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        w, h = dummy_draw.textsize(display_text, font=pil_font)
        bbox = (0, 0, w, h)
    
    padding = args.size // 2
    img_w, img_h = w + padding * 2, h + padding * 2
    
    img = Image.new("L", (img_w, img_h), color=255)
    draw = ImageDraw.Draw(img)
    
    draw.text((padding - bbox[0], padding - bbox[1]), display_text, font=pil_font, fill=0)
    
    img.save(args.out)
    print(f"Görsel başarıyla kaydedildi: {args.out}")

if __name__ == "__main__":
    main()
