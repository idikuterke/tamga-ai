"""
generate_extra_rare_clusters.py — Nadir ligatür sınıfları (cluster_ld, cluster_nc, cluster_nd) için hedefli ek veri üretimi.

Amaç:
Mevcut 462'şer adet örneği bulunan bu 3 nadir ligatür sınıfının her birini en az 750-800+ adede çıkarmak.
Görsel stilde tüm 19 fontu ve 5 dekoratif stil ön-ayarlarını (normal, stone, gold, neon, wood) kullanır.
Üretilen glyph'ler pipeline/data/style_augmented_v2/ altındaki glyphs/ ve manifest.jsonl'e eklenir.
"""

import json
import random
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from collections import Counter
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline" / "product"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from rules_engine import SpellingEngine
import importlib.util

spec = importlib.util.spec_from_file_location("segment_mod", str(PROJECT_ROOT / "pipeline" / "07_segment_word.py"))
segment_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(segment_mod)

OUTPUT_BASE = PROJECT_ROOT / "pipeline" / "data" / "style_augmented_v2"
GLYPHS_DIR = OUTPUT_BASE / "glyphs"
MISMATCHES_DIR = OUTPUT_BASE / "mismatches"
GLYPHS_DIR.mkdir(parents=True, exist_ok=True)
MISMATCHES_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = OUTPUT_BASE / "manifest.jsonl"
MISMATCH_PATH = OUTPUT_BASE / "suspicious_mismatches.jsonl"
PROGRESS_LOG_PATH = OUTPUT_BASE / "progress.log"

SCHEMA_PATH = PROJECT_ROOT / "gokturk_labels_v1_locked.json"
FONTS_DIR = PROJECT_ROOT / "pipeline" / "fonts"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)

classes = schema["classes"]
class_meta = {c["id"]: c for c in classes}
engine = SpellingEngine(str(SCHEMA_PATH))

# Fontları Yükle
VALID_FONTS = []
FONT_CMAPS = {}

for font_file in sorted(FONTS_DIR.glob("*.ttf")):
    if font_file.name.lower() == "damgalatin.ttf":
        continue
    try:
        tt = TTFont(font_file)
        cmap = tt.getBestCmap() or {}
        VALID_FONTS.append(font_file)
        FONT_CMAPS[font_file.name] = set(cmap.keys())
    except Exception as e:
        sys.stderr.write(f"Font yükleme hatası ({font_file.name}): {e}\n")

# Hedefli kelime şablonları
RARE_WORDS = [
    # cluster_ld
    "altay", "balda", "kolda", "elda", "gölda", "ülda", "balta", "kolta", "alta", "olta", "ilta", "elta",
    "kaltır", "taltık", "saldır", "boldı", "kaldı", "yaldız", "çaldı", "bildi", "kıldı", "buldu", "doldu",
    # cluster_nc
    "ancak", "kançı", "sançı", "incik", "dinçer", "künçü", "ançak", "konça", "punça", "sinçe", "ançı",
    "künçe", "inçik", "pança", "tança", "kancık", "gençer", "gönçü", "sança", "ançal", "günçü",
    # cluster_nd
    "bunda", "kanda", "sanda", "otonda", "menda", "penda", "bunta", "kanta", "santa", "anta", "inta",
    "unta", "kandı", "sandı", "yandı", "döndü", "göndü", "bindi", "dindi", "sündü", "tündü", "kendi"
]

FONT_SIZES = [36, 42, 48, 54, 60]
STYLE_PRESETS = ["normal", "stone", "gold", "neon", "wood"]

def font_supports_all_chars(font_name, char_refs):
    font_cmap = FONT_CMAPS.get(font_name, set())
    for c in char_refs:
        if c and ord(c) not in font_cmap:
            return False
    return True

def render_word_with_preset(chars, font_path, font_size, style_preset, letter_spacing):
    try:
        font = ImageFont.truetype(str(font_path), font_size)
    except Exception:
        return None
        
    chars = [c for c in chars if c]
    if not chars:
        return None
        
    char_widths = [font.getlength(c) for c in chars]
    gap = 20 + letter_spacing
    text_width = sum(char_widths) + gap * (len(chars) - 1)
    
    padding = font_size
    width = int(text_width + padding * 2)
    height = int(font_size * 1.8 + padding)
    y_pos = height // 2
    
    if style_preset == "normal":
        bg_color = random.choice(["#ffffff", "#f8f9fa", "#f5f0eb", "#ede6dc", "#e2e2e2"])
        fg_color = random.choice(["#000000", "#1a1a1a", "#2b2b2b", "#3f2a15", "#1a2a3a"])
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        x_pos = width - padding
        for i, c in enumerate(chars):
            cw = char_widths[i]
            draw.text((x_pos - cw, y_pos - font_size // 2), c, font=font, fill=fg_color)
            x_pos -= (cw + gap)
            
    elif style_preset == "stone":
        bg_color = random.choice(["#dcdcdc", "#c8c8c8", "#b4b4b4"])
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        x_pos = width - padding
        for i, c in enumerate(chars):
            cw = char_widths[i]
            x0 = x_pos - cw
            y0 = y_pos - font_size // 2
            draw.text((x0 - 2, y0 - 2), c, font=font, fill="#404040")
            draw.text((x0 + 2, y0 + 2), c, font=font, fill="#ffffff")
            draw.text((x0, y0), c, font=font, fill="#707070")
            x_pos -= (cw + gap)
            
    elif style_preset == "gold":
        bg_color = random.choice(["#18140c", "#241a0b", "#111111"])
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        x_pos = width - padding
        gold_color = random.choice(["#ffd700", "#e0a83e", "#f1b82d"])
        for i, c in enumerate(chars):
            cw = char_widths[i]
            x0 = x_pos - cw
            y0 = y_pos - font_size // 2
            draw.text((x0 + 3, y0 + 3), c, font=font, fill="#000000")
            draw.text((x0 - 1, y0 - 1), c, font=font, fill="#fffae0")
            draw.text((x0, y0), c, font=font, fill=gold_color)
            x_pos -= (cw + gap)
            
    elif style_preset == "neon":
        bg_color = random.choice(["#0a0a12", "#0d0014", "#050e14"])
        img = Image.new("RGB", (width, height), bg_color)
        glow_layer = Image.new("RGB", (width, height), bg_color)
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_color = random.choice(["#39ffe4", "#ff00ea", "#00ff66", "#ffff00"])
        
        x_pos = width - padding
        for i, c in enumerate(chars):
            cw = char_widths[i]
            x0 = x_pos - cw
            y0 = y_pos - font_size // 2
            glow_draw.text((x0, y0), c, font=font, fill=glow_color)
            x_pos -= (cw + gap)
            
        glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=4))
        img = Image.blend(img, glow_blurred, alpha=0.85)
        
        draw = ImageDraw.Draw(img)
        x_pos = width - padding
        for i, c in enumerate(chars):
            cw = char_widths[i]
            x0 = x_pos - cw
            y0 = y_pos - font_size // 2
            draw.text((x0, y0), c, font=font, fill="#ffffff")
            x_pos -= (cw + gap)
            
    elif style_preset == "wood":
        bg_color = random.choice(["#4a2e18", "#5c3a21", "#3d2310"])
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        x_pos = width - padding
        wood_color = random.choice(["#d9b38c", "#e6c9a8", "#c49a6c"])
        for i, c in enumerate(chars):
            cw = char_widths[i]
            x0 = x_pos - cw
            y0 = y_pos - font_size // 2
            draw.text((x0 + 3, y0 + 3), c, font=font, fill="#1f1008")
            draw.text((x0 - 1, y0 - 1), c, font=font, fill="#ffebd6")
            draw.text((x0, y0), c, font=font, fill=wood_color)
            x_pos -= (cw + gap)
            
    return img

def run_targeted_rare_generation(target_extra_per_class=400):
    print("=== NADİR LİGATÜR SINIFLARI HEDEFLİ VERİ ÜRETİMİ BAŞLADI ===")
    
    glyph_global_index = 0
    mismatch_global_index = 0
    
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    glyph_global_index += 1
                    
    if MISMATCH_PATH.exists():
        with open(MISMATCH_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mismatch_global_index += 1

    rare_targets = {"cluster_ld": 0, "cluster_nc": 0, "cluster_nd": 0}
    target_count = target_extra_per_class * len(rare_targets)
    
    start_time = time.time()
    attempts = 0
    
    while any(c < target_extra_per_class for c in rare_targets.values()):
        word = random.choice(RARE_WORDS)
        try:
            pairs = engine.expected_sequence_with_letters(word)
            expected_cids = [cid for cid, _ in pairs if cid != ":"]
            
            if not expected_cids:
                continue
                
            expected_char_refs = [
                (class_meta[cid]["glyph_ref"]["core_orhun"]) for cid in expected_cids
            ]

            font_candidates = [f for f in VALID_FONTS if font_supports_all_chars(f.name, expected_char_refs)]
            if not font_candidates:
                continue
                
            selected_font = random.choice(font_candidates)
            selected_style = random.choice(STYLE_PRESETS)
            font_size = random.choice(FONT_SIZES)
            letter_spacing = random.randint(0, 15)
            
            img = render_word_with_preset(expected_char_refs, selected_font, font_size, selected_style, letter_spacing)
            if img is None:
                continue
                
            attempts += 1
            
            gray = np.array(img.convert("L"))
            bg_sample = np.mean(gray[:5, :5])
            if bg_sample > 128:
                binary = gray < (bg_sample - 25)
            else:
                binary = gray > (bg_sample + 25)
                
            lines = segment_mod.find_components_by_line(binary, merge_gap_px=6)
            found_boxes = []
            for line in lines:
                for box in line:
                    if not segment_mod.is_colon(box, binary):
                        found_boxes.append(box)

            if len(found_boxes) == len(expected_cids):
                rtl_boxes = sorted(found_boxes, key=lambda b: b[0], reverse=True)
                for g_idx, (cid, box) in enumerate(zip(expected_cids, rtl_boxes)):
                    glyph_global_index += 1
                    crop = segment_mod.crop_with_margin(
                        img, box,
                        left_limit=0, right_limit=img.width,
                        margin_ratio=0.28, size=256
                    )
                    g_rel_filename = f"glyphs/glyph_{glyph_global_index:06d}.png"
                    crop.save(OUTPUT_BASE / g_rel_filename)
                    
                    manifest_record = {
                        "file": g_rel_filename,
                        "class_id": cid,
                        "class_index": class_meta[cid]["index"],
                        "word": word,
                        "word_idx": attempts,
                        "glyph_idx": g_idx,
                        "font": selected_font.name,
                        "style_preset": selected_style
                    }
                    with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(manifest_record, ensure_ascii=False) + "\n")

                    if cid in rare_targets:
                        rare_targets[cid] += 1

        except Exception as e:
            continue

    elapsed = time.time() - start_time
    print(f"\n=== NADİR LİGATÜR ÜRETİMİ TAMAMLANDI ({elapsed:.1f}s) ===")
    for cid, cnt in rare_targets.items():
        print(f"  {cid:15s}: +{cnt} yeni glyph üretildi!")

if __name__ == "__main__":
    run_targeted_rare_generation(target_extra_per_class=450)
