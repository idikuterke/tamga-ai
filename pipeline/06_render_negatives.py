"""
STEP 6 — Hard negative üretimi (Futhark ve benzeri).

negatives_dir altında (alt klasörler dahil) bulunan TÜM .ttf/.otf fontlarını
tarar, her fontun desteklediği kod noktalarından rastgele örnekler alır,
01/02'deki AYNI temiz-render + augmentasyon mantığıyla işler. Böylece negatif
sınıf, pozitif sınıflarla birebir aynı görsel dağılımdan (doku, blur, perspektif)
gelir — model gerçek glyph farkını öğrenir, yüzeysel "dokulu/dokusuz" farkını değil.

Ayrıca negatives_dir altında doğrudan bulunan .png/.jpg dosyalarını (ör. daha
önce test ettiğin Generated_image.png gibi alakasız görseller) da negatif
örnek olarak dahil eder.

Kullanım:
    python 06_render_negatives.py --negatives_dir ./negatives \
        --out ./data/negatives --per_font 60 --augment_per_image 4
"""

import argparse
import random
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

# 01 ve 02'deki fonksiyonları tekrar yazmak yerine aynı klasörden içe aktar
import importlib.util

_here = Path(__file__).parent
spec01 = importlib.util.spec_from_file_location("render_clean_mod", _here / "01_render_clean.py")
render_clean_mod = importlib.util.module_from_spec(spec01)
spec01.loader.exec_module(render_clean_mod)

spec02 = importlib.util.spec_from_file_location("augment_mod", _here / "02_augment.py")
augment_mod = importlib.util.module_from_spec(spec02)
spec02.loader.exec_module(augment_mod)


def find_fonts(root):
    root = Path(root)
    return list(root.rglob("*.ttf")) + list(root.rglob("*.otf"))


def find_loose_images(root):
    root = Path(root)
    return list(root.rglob("*.png")) + list(root.rglob("*.jpg")) + list(root.rglob("*.jpeg"))


def usable_codepoints(ttfont: TTFont, limit=None, rng=None):
    """Kontrol karakterleri ve boşluk hariç, gerçekten çizilebilir kod noktaları."""
    cmap = ttfont.getBestCmap()
    cps = [cp for cp in cmap.keys() if cp > 32 and cp != 0xFFFF]
    if limit and len(cps) > limit:
        cps = rng.sample(cps, limit)
    return cps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--negatives_dir", required=True, help="Futhark vb. font klasörlerinin kökü")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per_font", type=int, default=60, help="fontdan kaç rastgele kod noktası örneklenecek")
    ap.add_argument("--augment_per_image", type=int, default=4)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    fonts = find_fonts(args.negatives_dir)
    print(f"Bulunan font sayısı: {len(fonts)}")

    count = 0
    for font_path in fonts:
        try:
            ttf = TTFont(str(font_path), lazy=True)
            cps = usable_codepoints(ttf, limit=args.per_font, rng=rng)
        except Exception as e:
            print(f"  atlandı ({font_path.name}): {e}")
            continue

        for cp in cps:
            glyph_char = chr(cp)
            try:
                clean_img = render_clean_mod.render_glyph(str(font_path), glyph_char, size=args.size)
            except Exception:
                continue  # font bu kod noktası için çizilebilir outline vermiyor olabilir

            # boş/neredeyse-boş render'ları ele (bazı kod noktaları görünmez karakter olabilir)
            extrema = clean_img.getextrema()
            if extrema[0] == extrema[1]:  # tamamen düz renk = muhtemelen boş glyph
                continue

            base_name = f"{font_path.stem}__U{cp:04X}"
            clean_fpath = out_dir / f"{base_name}__clean.png"
            clean_img.save(clean_fpath)
            count += 1

            for i in range(args.augment_per_image):
                aug_img, _ = augment_mod.augment_one(clean_img, rng, size=args.size)
                aug_img.save(out_dir / f"{base_name}__aug{i:02d}.png")
                count += 1

    # negatives_dir altında hazır duran alakasız görselleri (ör. Generated_image.png) de ekle
    loose = find_loose_images(args.negatives_dir)
    for img_path in loose:
        try:
            img = Image.open(img_path).convert("RGB").resize((args.size, args.size))
            img.save(out_dir / f"loose__{img_path.stem}.png")
            count += 1
        except Exception as e:
            print(f"  atlandı ({img_path.name}): {e}")

    print(f"Toplam negatif görsel: {count}  (font-türetilmiş + {len(loose)} hazır görsel)")
    print(f"Çıktı klasörü: {out_dir}")
    print("\nSıradaki adım:")
    print(f"  python 04_train_classifier.py --dataset_dir ./data/dataset --data_root . "
          f"--schema ../gokturk_labels_v1_locked.json --negatives_dir {out_dir} "
          f"--epochs 8 --batch_size 8 --out ./model")


if __name__ == "__main__":
    main()
