"""
generate_style_augmented_v2.py — Sentetik Veri Üretim Motoru v2.

Özellikler:
1. pipeline/fonts/ altındaki DamgaLatin.ttf HARİÇ tüm 19 fontu kullanır.
2. fontTools cmap kontrolü ile eksik kod noktalarını sessizce atlar.
3. 5 Dekoratif Stil Ön-Ayarı (normal, stone, gold, neon, wood) simüle edilir.
4. Kendi Kendini Doğrulama (07_segment_word.py bağlı-bileşen analizi) ile %100 güvenilirlik.
5. Çıktı: pipeline/data/style_augmented_v2/ klasörüne kaydedilir.
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

# Windows CP1254 terminal çıktısı çökmesini önle
sys.stdout.reconfigure(encoding="utf-8")

# Proje yollarını ekle
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline" / "product"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from rules_engine import SpellingEngine
import importlib.util

spec = importlib.util.spec_from_file_location("segment_mod", str(PROJECT_ROOT / "pipeline" / "07_segment_word.py"))
segment_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(segment_mod)

# Klasör yapılarını hazırlama
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

# Şema ve Motor Yükle
with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)

classes = schema["classes"]
class_meta = {c["id"]: c for c in classes}
engine = SpellingEngine(str(SCHEMA_PATH))

# Fontları Tara ve Cmap Önbelleği Oluştur (DamgaLatin.ttf HARİÇ)
VALID_FONTS = []
FONT_CMAPS = {}

for font_file in sorted(FONTS_DIR.glob("*.ttf")):
    if font_file.name.lower() == "damgalatin.ttf":
        continue  # DamgaLatin.ttf kesinlikle dışlandı!
    try:
        tt = TTFont(font_file)
        cmap = tt.getBestCmap() or {}
        codepoints = set(cmap.keys())
        VALID_FONTS.append(font_file)
        FONT_CMAPS[font_file.name] = codepoints
    except Exception as e:
        sys.stderr.write(f"Font yükleme hatası ({font_file.name}): {e}\n")

print(f"Kullanılabilir Font Sayısı (DamgaLatin hariç): {len(VALID_FONTS)}")

# Harf/Ses Havuzları
BACK_VOWELS = ["a", "ı", "o", "u"]
FRONT_VOWELS = ["e", "i", "ö", "ü"]
CONSONANTS = ["b", "c", "ç", "d", "g", "k", "l", "m", "n", "p", "r", "s", "ş", "t", "y", "z", "ng", "ny"]

# 38 sınıfın tamamını tetikleyecek şablon kelimeler
TARGETED_PATTERNS = {
    "vowel_a_e": ["ana", "ata", "efe", "eve", "aka", "ege", "anaç", "alaka"],
    "vowel_i_i": ["iri", "iki", "iyi", "iti", "ilim", "itik"],
    "vowel_o_u": ["odu", "otu", "oku", "onu", "oruk", "orum", "otuz"],
    "vowel_oe_ue": ["ökü", "ötü", "örü", "özü", "öküş", "öbük", "ölüm"],
    "b_back": ["baba", "batar", "barık", "boluk", "bunar", "balkan"],
    "b_front": ["bebe", "bitir", "beler", "büküm", "biler", "beşer"],
    "g_back": ["taga", "bagar", "yaga", "sagan", "togar", "bogaz"],
    "g_front": ["tege", "bege", "yegi", "sigi", "töge", "büge"],
    "d_back": ["dada", "dalak", "donar", "durak", "duran", "dalkı"],
    "d_front": ["dede", "dilik", "diler", "döküm", "diner", "değer"],
    "z_nopolar": ["baza", "yaza", "koza", "düze", "geze", "göze", "boza"],
    "y_back": ["yaya", "yatar", "yoluk", "yutar", "yakar", "yalgı"],
    "y_front": ["yeye", "yiter", "yele", "yüküm", "yiler", "yeğer"],
    "k_back": ["kaka", "katar", "kalık", "koruk", "kutar", "kalkı"],
    "k_front": ["keke", "kiter", "keler", "küküm", "kiler", "keğer"],
    "syllable_ok": ["okum", "okul", "ukus", "korkut", "koku", "koruk"],
    "syllable_oek": ["öküm", "ökül", "üküş", "körküt", "kökü", "körük"],
    "syllable_ik": ["ıkım", "ıkıl", "kırkık", "kıkı", "kırık", "sakık"],
    "l_back": ["lala", "latar", "lalık", "loluk", "lutar", "lalkı"],
    "l_front": ["lele", "liter", "leler", "lüküm", "liler", "leğer"],
    "m_nopolar": ["mama", "mimi", "muma", "müme", "moma", "möme"],
    "n_back": ["nana", "natar", "nalık", "noluk", "nutar", "nalkı"],
    "n_front": ["nene", "niter", "neler", "nüküm", "niler", "neğer"],
    "cluster_nd": ["bunda", "kanda", "sanda", "otonda", "menda", "penda"],
    "cluster_nc": ["ancak", "kançı", "sançı", "incik", "dinçer", "künçü"],
    "ny_nopolar": ["koñak", "añar", "meñi", "señir", "tañar", "yeñi"],
    "p_nopolar": ["papar", "peper", "pıpır", "pipir", "popor", "püpür"],
    "c_nopolar": ["çaça", "çeçe", "çıçı", "çiçi", "çoço", "çöçö"],
    "r_back": ["rara", "ratar", "ralık", "roluk", "rutar", "ralkı"],
    "r_front": ["rere", "riter", "reler", "rüküm", "riler", "reğer"],
    "s_back": ["sasa", "satar", "salık", "soluk", "sutar", "salkı"],
    "s_front": ["sese", "siter", "seler", "süküm", "siler", "seğer"],
    "sh_nopolar": ["şaşa", "şeşe", "şışı", "şişi", "şoşo", "şöşö"],
    "t_back": ["tata", "tatar", "talık", "toluk", "tutar", "talkı"],
    "t_front": ["tete", "titer", "teler", "tüküm", "tiler", "teğer"],
    "cluster_ld": ["altay", "balda", "kolda", "elda", "gölda", "ülda"],
    "ng_nopolar": ["tengri", "baŋa", "saŋa", "meŋi", "deŋiz", "kaŋa"],
    "syllable_ic": ["içik", "içer", "içim", "içki", "içsiz", "içten"]
}

# Stil varyasyonları
FONT_SIZES = [36, 42, 48, 54, 60]
STYLE_PRESETS = ["normal", "stone", "gold", "neon", "wood"]

def generate_random_word():
    harmony = random.choice(["back", "front"])
    vowels = BACK_VOWELS if harmony == "back" else FRONT_VOWELS
    length = random.randint(3, 8)
    use_consonant = random.choice([True, False])
    word = []
    
    while len(word) < length:
        if use_consonant:
            c = random.choice(CONSONANTS)
            word.append(c)
            use_consonant = False
        else:
            v = random.choice(vowels)
            word.append(v)
            use_consonant = True
            
    return "".join(word)

def generate_word_list(target_count=3000):
    words = []
    all_targeted = []
    for pattern_list in TARGETED_PATTERNS.values():
        all_targeted.extend(pattern_list)
        
    while len(words) < target_count // 2:
        words.extend(random.sample(all_targeted, len(all_targeted)))
        
    while len(words) < target_count:
        words.append(generate_random_word())
        
    random.shuffle(words)
    return words[:target_count]

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

def log_progress(processed_words, total_target, total_attempts, valid_samples, mismatches):
    mismatch_rate = (mismatches / total_attempts * 100) if total_attempts > 0 else 0.0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = (f"[{now_str}] Kelimeler: {processed_words:4d}/{total_target:4d} | "
           f"Üretim Denemesi: {total_attempts:6d} | Üretilen Glyph: {valid_samples:7d} | "
           f"Mismatch (Uyuşmazlık): {mismatches:4d} ({mismatch_rate:.2f}%)\n")
    
    print(msg, end="")
    with open(PROGRESS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg)

def run_dataset_generation_v2(target_word_count=3000, variations_per_word=8, max_glyphs_limit=200000):
    print("=== GECE BOYU GÖZETİMSİZ SENTETİK VERİ ÜRETİMİ v2 BAŞLADI ===")
    print(f"Hedef: {target_word_count} kelime x {variations_per_word} stil varyasyonu (Max limit: {max_glyphs_limit} glyph)")
    print(f"Çıktı Dizini: {OUTPUT_BASE.resolve()}\n")

    word_list = generate_word_list(target_word_count)
    
    total_attempts = 0
    total_valid_glyphs = 0
    total_mismatches = 0
    glyph_global_index = 0
    mismatch_global_index = 0
    
    font_stats = Counter()
    style_stats = Counter()
    
    # Mevcut en yüksek index'i tespit et
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    glyph_global_index += 1
                    font_stats[rec.get("font", "unknown")] += 1
                    style_stats[rec.get("style_preset", "unknown")] += 1
                    
    if MISMATCH_PATH.exists():
        with open(MISMATCH_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mismatch_global_index += 1

    start_time = time.time()
    
    for word_idx, word in enumerate(word_list, 1):
        if total_valid_glyphs >= max_glyphs_limit:
            print(f"\nMaksimum glyph limitine ({max_glyphs_limit}) ulaşıldı, durduruluyor...")
            break

        try:
            pairs = engine.expected_sequence_with_letters(word)
            expected_cids = [cid for cid, _ in pairs if cid != ":"]
            
            if not expected_cids:
                continue
                
            expected_char_refs = [
                (class_meta[cid]["glyph_ref"]["core_orhun"]) for cid in expected_cids
            ]

            for var_idx in range(variations_per_word):
                if total_valid_glyphs >= max_glyphs_limit:
                    break

                # Font seçimi (cmap desteği doğrulayarak)
                font_candidates = [f for f in VALID_FONTS if font_supports_all_chars(f.name, expected_char_refs)]
                if not font_candidates:
                    continue
                    
                selected_font = random.choice(font_candidates)
                selected_style = random.choice(STYLE_PRESETS)
                font_size = random.choice(FONT_SIZES)
                letter_spacing = random.randint(0, 15)  # 20 + 0..15 = 20-35px boşluk
                
                img = render_word_with_preset(expected_char_refs, selected_font, font_size, selected_style, letter_spacing)
                if img is None:
                    continue
                    
                total_attempts += 1
                
                # Segmentasyon ve Binarizasyon
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

                # Karşılaştırma & Kayıt
                if len(found_boxes) != len(expected_cids):
                    total_mismatches += 1
                    mismatch_global_index += 1
                    
                    m_rel_filename = f"mismatches/mismatch_{mismatch_global_index:06d}.png"
                    m_full_path = OUTPUT_BASE / m_rel_filename
                    img.save(m_full_path)
                    
                    m_record = {
                        "word": word,
                        "expected_count": len(expected_cids),
                        "found_count": len(found_boxes),
                        "image_path": m_rel_filename,
                        "expected_sequence": expected_cids,
                        "font": selected_font.name,
                        "style_preset": selected_style,
                        "font_size": font_size,
                        "letter_spacing": letter_spacing
                    }
                    with open(MISMATCH_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(m_record, ensure_ascii=False) + "\n")
                else:
                    rtl_boxes = sorted(found_boxes, key=lambda b: b[0], reverse=True)
                    
                    for g_idx, (cid, box) in enumerate(zip(expected_cids, rtl_boxes)):
                        glyph_global_index += 1
                        total_valid_glyphs += 1
                        
                        font_stats[selected_font.name] += 1
                        style_stats[selected_style] += 1
                        
                        crop = segment_mod.crop_with_margin(
                            img, box,
                            left_limit=0,
                            right_limit=img.width,
                            margin_ratio=0.28,
                            size=256
                        )
                        
                        g_rel_filename = f"glyphs/glyph_{glyph_global_index:06d}.png"
                        g_full_path = OUTPUT_BASE / g_rel_filename
                        crop.save(g_full_path)
                        
                        manifest_record = {
                            "file": g_rel_filename,
                            "class_id": cid,
                            "class_index": class_meta[cid]["index"],
                            "word": word,
                            "word_idx": word_idx,
                            "glyph_idx": g_idx,
                            "font": selected_font.name,
                            "style_preset": selected_style
                        }
                        with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
                            f.write(json.dumps(manifest_record, ensure_ascii=False) + "\n")

        except Exception as e:
            sys.stderr.write(f"Kelime hatası ({word}): {e}\n")
            continue

        # Her 100 kelimede bir logla
        if word_idx % 100 == 0 or word_idx == target_word_count:
            log_progress(word_idx, target_word_count, total_attempts, total_valid_glyphs, total_mismatches)

    elapsed = time.time() - start_time
    mismatch_rate = (total_mismatches / total_attempts * 100) if total_attempts > 0 else 0.0
    
    summary_str = f"""
=====================================================
=== ÜRETİM v2 TAMAMLANDI ===
=====================================================
Toplam Süre: {elapsed:.1f} saniye ({elapsed/60:.2f} dakika)
İşlenen Kelime Sayısı: {word_idx} / {target_word_count}
Toplam Üretim Denemesi: {total_attempts}
Başarıyla Üretilen ve Kırpılan Glyph: {total_valid_glyphs}
Şüpheli Uyuşmazlık (Mismatch): {total_mismatches} ({mismatch_rate:.2f}%)
Manifest: {MANIFEST_PATH.resolve()}
Uyuşmazlık Logu: {MISMATCH_PATH.resolve()}

--- FONT BAŞINA ÜRETİLEN GLYPH DÖKÜMÜ ---
"""
    for fname, count in sorted(font_stats.items(), key=lambda x: x[1], reverse=True):
        summary_str += f"  {fname:35s}: {count:7d} glyph\n"
        
    summary_str += "\n--- STİL ÖN-AYARI BAŞINA ÜRETİLEN GLYPH DÖKÜMÜ ---\n"
    for sname, count in sorted(style_stats.items(), key=lambda x: x[1], reverse=True):
        summary_str += f"  {sname:15s}: {count:7d} glyph\n"
        
    print(summary_str)
    with open(PROGRESS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(summary_str + "\n")

if __name__ == "__main__":
    run_dataset_generation_v2(target_word_count=3000, variations_per_word=8, max_glyphs_limit=200000)
