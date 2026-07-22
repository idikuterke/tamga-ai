"""
generate_style_augmented_dataset.py — Gece boyu çalışacak sentetik veri üretim ve kendi kendini doğrulama betiği.

Amaç:
1. Alfabedeki 38 sınıfın tamamını kapsayan rastgele/sistematik kelimeler üretir.
2. PIL ve Noto Sans Old Turkic / Tuğrul Çavdar Göktürkçe fontu ile farklı görsel
   stillerde (punto, renk, zemin, harf boşluğu >= 20px) render eder.
3. 07_segment_word.py bağlı-bileşen analizi ile kendi kendini doğrular:
   - Glyph sayısı beklenen sayıyla EŞLEŞİYORSA: her glyph kırpılıp pipeline/data/style_augmented/
     klasörüne kaydedilir ve manifest.jsonl'e eklenir.
   - EŞLEŞMİYORSA: eğitim setine katılmaz, suspicious_mismatches.jsonl dosyasına kaydedilir.
4. İlerlemeyi progress.log dosyasına yazar ve 3000 kelimeye ulaşınca otomatik durur.
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
from PIL import Image, ImageDraw, ImageFont

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

# Klasör yapılarını hazırla
OUTPUT_BASE = PROJECT_ROOT / "pipeline" / "data" / "style_augmented"
GLYPHS_DIR = OUTPUT_BASE / "glyphs"
MISMATCHES_DIR = OUTPUT_BASE / "mismatches"
GLYPHS_DIR.mkdir(parents=True, exist_ok=True)
MISMATCHES_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = OUTPUT_BASE / "manifest.jsonl"
MISMATCH_PATH = OUTPUT_BASE / "suspicious_mismatches.jsonl"
PROGRESS_LOG_PATH = OUTPUT_BASE / "progress.log"

SCHEMA_PATH = PROJECT_ROOT / "gokturk_labels_v1_locked.json"
FONT_PATH = PROJECT_ROOT / "pipeline" / "fonts" / "KokTuruk2004UnicodeTugrulCavdar.ttf"

# Şema ve Motor Yükle
with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)

classes = schema["classes"]
class_meta = {c["id"]: c for c in classes}
engine = SpellingEngine(str(SCHEMA_PATH))

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

# Stil varyasyon havuzları
FONT_SIZES = [36, 42, 48, 54, 60]
TEXT_COLORS = ["#000000", "#1a1a1a", "#2b2b2b", "#3f2a15", "#1a2a3a"]
BG_COLORS = ["#ffffff", "#f8f9fa", "#f5f0eb", "#ede6dc", "#e2e2e2"]

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

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

def render_word_image(char_glyphs, font_size, text_color_hex, bg_color_hex, letter_spacing):
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    chars = [c for c in char_glyphs if c]
    if not chars:
        return None
        
    char_widths = [font.getlength(c) for c in chars]
    gap = 20 + letter_spacing  # Her zaman en az 20px güvenli segmentasyon boşluğu
    text_width = sum(char_widths) + gap * (len(chars) - 1)
    
    padding = font_size
    width = int(text_width + padding * 2)
    height = int(font_size * 1.8 + padding)
    
    img = Image.new("RGB", (width, height), bg_color_hex)
    draw = ImageDraw.Draw(img)
    
    x_pos = width - padding
    y_pos = height // 2
    
    # Karakterleri sağdan sola (RTL) yerleştir
    for i, c in enumerate(chars):
        cw = char_widths[i]
        draw.text((x_pos - cw, y_pos - font_size // 2), c, font=font, fill=text_color_hex)
        x_pos -= (cw + gap)
        
    return img

def log_progress(processed_words, total_target, total_attempts, valid_samples, mismatches):
    mismatch_rate = (mismatches / total_attempts * 100) if total_attempts > 0 else 0.0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = (f"[{now_str}] Kelimeler: {processed_words:4d}/{total_target:4d} | "
           f"Üretim Denemesi: {total_attempts:5d} | Üretilen Glyph: {valid_samples:6d} | "
           f"Mismatch (Uyuşmazlık): {mismatches:4d} ({mismatch_rate:.2f}%)\n")
    
    print(msg, end="")
    with open(PROGRESS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg)

def run_dataset_generation(target_word_count=3000, variations_per_word=3):
    print("=== GECE BOYU GÖZETİMSİZ SENTETİK VERİ ÜRETİMİ BAŞLADI ===")
    print(f"Hedef: {target_word_count} kelime x {variations_per_word} stil varyasyonu")
    print(f"Çıktı Dizini: {OUTPUT_BASE.resolve()}\n")

    word_list = generate_word_list(target_word_count)
    
    total_attempts = 0
    total_valid_glyphs = 0
    total_mismatches = 0
    glyph_global_index = 0
    mismatch_global_index = 0
    
    # Mevcut en yüksek index'i tespit et (devam edilebilirlik için)
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

    start_time = time.time()
    
    for word_idx, word in enumerate(word_list, 1):
        try:
            # 1. SpellingEngine ile Göktürkçe sequence al
            pairs = engine.expected_sequence_with_letters(word)
            expected_cids = [cid for cid, _ in pairs if cid != ":"]
            
            if not expected_cids:
                continue
                
            expected_char_refs = [
                (class_meta[cid]["glyph_ref"]["core_orhun"]) for cid in expected_cids
            ]

            # 2. Farklı stillerde varyasyon üret
            for var_idx in range(variations_per_word):
                total_attempts += 1
                
                font_size = random.choice(FONT_SIZES)
                text_color = random.choice(TEXT_COLORS)
                bg_color = random.choice(BG_COLORS)
                letter_spacing = random.randint(0, 15)  # 20 + 0..15 = 20-35px boşluk
                
                img = render_word_image(expected_char_refs, font_size, text_color, bg_color, letter_spacing)
                if img is None:
                    continue
                    
                # 3. Kendi Kendini Doğrulama (Segmentasyon)
                gray = np.array(img.convert("L"))
                bg_lum = np.mean(hex_to_rgb(bg_color))
                text_lum = np.mean(hex_to_rgb(text_color))
                threshold = (bg_lum + text_lum) / 2.0
                
                binary = gray < threshold
                lines = segment_mod.find_components_by_line(binary, merge_gap_px=6)
                
                found_boxes = []
                for line in lines:
                    for box in line:
                        if not segment_mod.is_colon(box, binary):
                            found_boxes.append(box)

                # 4. Karşılaştırma & Kayıt
                if len(found_boxes) != len(expected_cids):
                    # MISMATCH: Uyuşmazlık!
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
                        "font_size": font_size,
                        "letter_spacing": letter_spacing
                    }
                    with open(MISMATCH_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(m_record, ensure_ascii=False) + "\n")
                else:
                    # MATCH: Tam doğrulama! RTL sırasıyla (x0 azalan) kutuları eşle
                    rtl_boxes = sorted(found_boxes, key=lambda b: b[0], reverse=True)
                    
                    for g_idx, (cid, box) in enumerate(zip(expected_cids, rtl_boxes)):
                        glyph_global_index += 1
                        total_valid_glyphs += 1
                        
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
                            "glyph_idx": g_idx
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
    print(f"\n=== ÜRETİM TAMAMLANDI ===")
    print(f"Toplam Süre: {elapsed:.1f} saniye")
    print(f"İşlenen Kelime: {target_word_count}")
    print(f"Toplam Deneme: {total_attempts}")
    print(f"Başarıyla Üretilen ve Kırpılan Glyph: {total_valid_glyphs}")
    print(f"Şüpheli Uyuşmazlık (Mismatch): {total_mismatches}")
    print(f"Manifest: {MANIFEST_PATH.resolve()}")
    print(f"Uyuşmazlık Logu: {MISMATCH_PATH.resolve()}")

if __name__ == "__main__":
    run_dataset_generation(target_word_count=3000, variations_per_word=3)
