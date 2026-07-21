"""
STEP 2 — Augmentasyon.
Temiz render'ları (Step 1 çıktısı) alır, her biri için N adet augmente edilmiş
versiyon üretir. Bu, "AI'nın ürettiği bozuk/dokulu görsellerde de doğru glyph'i
tanı" hedefini karşılamak için gerekli — training dağılımını gerçek kullanım
dağılımına yaklaştırıyor.

KURAL — daha önce üzerinde durduğumuz iki orthografik kısıt burada KOD SEVİYESİNDE
zorlanıyor, opsiyonel değil:
  1. Yatay flip YASAK — bazı Göktürkçe harfler ayna görüntüsüyle başka bir harfe
     dönüşür (harmony çiftleri gibi). Flip = yanlış etiketli veri üretir.
  2. Serbest döndürme YASAK — sadece küçük perspektif açısı (±MAX_ROTATION_DEG).
     Büyük döndürme de aynı riski taşır.

Kullanım:
    python 02_augment.py --clean_dir ./data/clean --out ./data/augmented \
        --per_image 8
"""

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

MAX_ROTATION_DEG = 4  # küçük perspektif toleransı — büyük döndürme YASAK (bkz. modül docstring)
TEXTURES = ["plain", "stone", "wood", "paper", "leather", "parchment"]


def make_texture_background(size, texture_kind, rng):
    """Basit prosedürel doku — gerçek doku fotoğrafların varsa onlarla değiştir."""
    base = {
        "plain": (245, 245, 245),
        "stone": (180, 178, 170),
        "wood": (150, 111, 71),
        "paper": (238, 231, 210),
        "leather": (120, 85, 60),
        "parchment": (222, 202, 165),
    }[texture_kind]

    img = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(img)
    # hafif prosedürel gürültü lekesi (gerçek doku fotoğrafı gelene kadar placeholder)
    for _ in range(rng.randint(20, 60)):
        x, y = rng.randint(0, size[0]), rng.randint(0, size[1])
        r = rng.randint(3, 15)
        jitter = rng.randint(-15, 15)
        c = tuple(max(0, min(255, v + jitter)) for v in base)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
    return img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1, 3)))


def composite_glyph_on_texture(glyph_img: Image.Image, rng, size=256):
    texture_kind = rng.choice(TEXTURES)
    bg = make_texture_background((size, size), texture_kind, rng)

    glyph_rgba = glyph_img.convert("L")
    # beyaz zemini şeffaf yap, sadece siyah çizgi kalsın
    glyph_rgba = glyph_rgba.point(lambda p: 255 - p)  # invert -> glyph parlak
    mask = glyph_rgba

    ink_color = rng.choice([(20, 20, 20), (40, 30, 25), (10, 10, 10)])
    ink_layer = Image.new("RGB", (size, size), ink_color)

    bg.paste(ink_layer, (0, 0), mask)
    return bg, texture_kind


def apply_perspective_jitter(img: Image.Image, rng):
    """Küçük açı — flip/serbest rotate YOK. Sadece hafif perspektif hissi."""
    angle = rng.uniform(-MAX_ROTATION_DEG, MAX_ROTATION_DEG)
    return img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(200, 200, 200))


def apply_degradation(img: Image.Image, rng):
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 1.5)))
    if rng.random() < 0.4:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(rng.uniform(0.7, 1.3))
    if rng.random() < 0.4:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(rng.uniform(0.7, 1.4))
    return img


def augment_one(glyph_img: Image.Image, rng, size=256):
    composited, texture_kind = composite_glyph_on_texture(glyph_img, rng, size=size)
    composited = apply_perspective_jitter(composited, rng)
    composited = apply_degradation(composited, rng)
    return composited, {
        "texture": texture_kind,
        "flip_applied": False,   # her zaman False — yasak, kayıt amaçlı sabit
        "free_rotation_applied": False,  # her zaman False — yasak, kayıt amaçlı sabit
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean_dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per_image", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    clean_dir = Path(args.clean_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(clean_dir / "manifest_clean.jsonl", encoding="utf-8") as f:
        clean_rows = [json.loads(line) for line in f]

    aug_rows = []
    for row in clean_rows:
        glyph_img = Image.open(row["file"])
        base_name = Path(row["file"]).stem

        for i in range(args.per_image):
            aug_img, aug_params = augment_one(glyph_img, rng)
            fname = f"{base_name}__aug{i:02d}.png"
            fpath = out_dir / fname
            aug_img.save(fpath)

            aug_rows.append({
                **{k: v for k, v in row.items() if k != "file"},
                "source_clean_file": row["file"],
                "file": str(fpath),
                "augmentation": aug_params,
            })

    with open(out_dir / "manifest_augmented.jsonl", "w", encoding="utf-8") as f:
        for r in aug_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Üretilen augmente görsel sayısı: {len(aug_rows)}")


if __name__ == "__main__":
    main()
