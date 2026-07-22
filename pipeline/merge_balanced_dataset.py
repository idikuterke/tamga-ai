"""
merge_balanced_dataset.py — Ham Verileri Bozmadan Dengeli Birleşik Veri Seti Oluşturucu.

DURUM & GÜVENLİK:
1. MEVCUT clean, augmented, style_augmented ve style_augmented_v2 KLASÖRLERİNİ SADECE OKUR.
2. Hiçbir ham dosyayı SİLMEZ, TAŞIMAZ veya DEĞİŞTİRMEZ.
3. Çıktı: pipeline/data/combined_dataset/ klasörüne izole bir şekilde yazılır:
   - images/: Seçilen 36,509 adet PNG görseli
   - manifest.jsonl: Tüm birleşik veri seti manifestosu
   - train.jsonl: %80 stratifiye eğitim seti
   - val.jsonl: %20 stratifiye doğrulama seti
   - summary.json: Sınıf dağılım istatistikleri
"""

import json
import random
import shutil
import sys
from pathlib import Path
from collections import Counter

# Windows CP1254 terminal çıktısı çökmesini önle
sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Kaynak Klasörleri
CLEAN_DIR = PROJECT_ROOT / "pipeline" / "data" / "clean"
AUG_DIR = PROJECT_ROOT / "pipeline" / "data" / "augmented"
SYNTH1_DIR = PROJECT_ROOT / "pipeline" / "data" / "style_augmented"
SYNTH2_DIR = PROJECT_ROOT / "pipeline" / "data" / "style_augmented_v2"

# Çıktı Klasörü (İzole)
COMBINED_DIR = PROJECT_ROOT / "pipeline" / "data" / "combined_dataset"
IMAGES_DIR = COMBINED_DIR / "images"
COMBINED_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA_PATH = PROJECT_ROOT / "gokturk_labels_v1_locked.json"
with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)

classes = schema["classes"]
class_meta = {c["id"]: c for c in classes}

def get_clean_class_id(raw_name):
    # e.g. "00_vowel_a_e" -> "vowel_a_e"
    parts = raw_name.split("__")
    cid = parts[0]
    if "_" in cid and cid.split("_")[0].isdigit():
        cid = "_".join(cid.split("_")[1:])
    return cid

def collect_original_font_samples():
    print("1. Orijinal ham font verileri taranıyor (clean + augmented)...")
    samples = []
    
    for folder in [CLEAN_DIR, AUG_DIR]:
        if folder.exists():
            for fpath in folder.rglob("*.png"):
                cid = get_clean_class_id(fpath.name)
                if cid in class_meta:
                    samples.append({
                        "source": folder.name,
                        "src_path": fpath,
                        "class_id": cid,
                        "class_index": class_meta[cid]["index"]
                    })
                    
    print(f"   Toplam orijinal font örneği: {len(samples)}")
    return samples

def collect_synthetic_samples():
    print("2. Sentetik veri manifesları taranıyor (style_augmented v1 + v2)...")
    samples = []
    
    for base_dir in [SYNTH1_DIR, SYNTH2_DIR]:
        mpath = base_dir / "manifest.jsonl"
        if mpath.exists():
            with open(mpath, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        src_img_path = base_dir / rec["file"]
                        if src_img_path.exists():
                            samples.append({
                                "source": base_dir.name,
                                "src_path": src_img_path,
                                "class_id": rec["class_id"],
                                "class_index": rec["class_index"],
                                "font": rec.get("font", "unknown"),
                                "style_preset": rec.get("style_preset", "normal")
                            })
                            
    print(f"   Toplam mevcut sentetik örnek: {len(samples)}")
    return samples

def run_balanced_merge(target_synth_per_class=736, val_ratio=0.20):
    random.seed(42)  # Tekrarlanabilir rastgele örnekleme
    
    orig_samples = collect_original_font_samples()
    synth_samples = collect_synthetic_samples()
    
    # Sentetik örnekleri sınıfa göre grupla
    synth_by_class = {}
    for s in synth_samples:
        synth_by_class.setdefault(s["class_id"], []).append(s)
        
    print(f"\n3. Sınıf bazlı dengeli örnekleme yapılıyor (Sınıf başına {target_synth_per_class} sentetik örnek)...")
    selected_synth = []
    
    for c in classes:
        cid = c["id"]
        avail = synth_by_class.get(cid, [])
        sample_count = min(len(avail), target_synth_per_class)
        picked = random.sample(avail, sample_count)
        selected_synth.extend(picked)
        print(f"   - Sınıf {c['index']:2d} ({cid:18s}): Mevcut Sentetik={len(avail):5d} -> Seçilen={sample_count:4d}")
        
    print(f"\n   Seçilen Toplam Sentetik Örnek: {len(selected_synth)}")
    
    # 4. Orijinal + Seçilen Sentetik Birleştirme
    combined_samples = orig_samples + selected_synth
    random.shuffle(combined_samples)
    print(f"   TOPLAM BİRLEŞİK EĞİTİM VERİSİ: {len(combined_samples)}")
    
    # 5. Görselleri izole combined_dataset/images/ dizinine kopyala ve yeni manifest yaz
    print("\n4. Görseller kopyalanıyor ve manifestolar yazılıyor (Salt-okunur non-destructive)...")
    
    manifest_records = []
    class_counts = Counter()
    
    manifest_out = COMBINED_DIR / "manifest.jsonl"
    with open(manifest_out, "w", encoding="utf-8") as f_man:
        for idx, s in enumerate(combined_samples, 1):
            dst_name = f"sample_{idx:06d}.png"
            dst_path = IMAGES_DIR / dst_name
            shutil.copy(s["src_path"], dst_path)
            
            rec = {
                "file": f"images/{dst_name}",
                "class_id": s["class_id"],
                "class_index": s["class_index"],
                "source": s["source"],
                "font": s.get("font", "clean_or_aug"),
                "style_preset": s.get("style_preset", "clean_or_aug")
            }
            manifest_records.append(rec)
            class_counts[s["class_id"]] += 1
            f_man.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 6. Stratified Train / Val Bölünmesi (%80 Train, %20 Val)
    print("\n5. %80 Train / %20 Val Stratified (Sınıf Dengeli) Bölünmesi Yapılıyor...")
    recs_by_class = {}
    for r in manifest_records:
        recs_by_class.setdefault(r["class_id"], []).append(r)
        
    train_recs = []
    val_recs = []
    
    for cid, recs in recs_by_class.items():
        random.shuffle(recs)
        val_count = max(1, int(len(recs) * val_ratio))
        val_recs.extend(recs[:val_count])
        train_recs.extend(recs[val_count:])
        
    random.shuffle(train_recs)
    random.shuffle(val_recs)
    
    train_out = COMBINED_DIR / "train.jsonl"
    val_out = COMBINED_DIR / "val.jsonl"
    
    with open(train_out, "w", encoding="utf-8") as f_tr:
        for r in train_recs:
            f_tr.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    with open(val_out, "w", encoding="utf-8") as f_va:
        for r in val_recs:
            f_va.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Özet Dosyası
    summary = {
        "total_samples": len(combined_samples),
        "original_font_samples": len(orig_samples),
        "synthetic_samples": len(selected_synth),
        "train_samples": len(train_recs),
        "val_samples": len(val_recs),
        "class_breakdown": {cid: class_counts[cid] for cid in sorted(class_counts.keys())}
    }
    
    with open(COMBINED_DIR / "summary.json", "w", encoding="utf-8") as f_sum:
        json.dump(summary, f_sum, ensure_ascii=False, indent=2)

    print("\n=====================================================")
    print("=== BİRLEŞTİRME BAŞARIYLA TAMAMLANDI ===")
    print("=====================================================")
    print(f"Toplam Örnek Sayısı: {len(combined_samples)}")
    print(f"  - Orijinal Font Örnekleri: {len(orig_samples)}")
    print(f"  - Sentetik Stil Örnekleri: {len(selected_synth)}")
    print(f"Train Seti (%80): {len(train_recs)}")
    print(f"Val Seti   (%20): {len(val_recs)}")
    print(f"Çıktı Klasörü: {COMBINED_DIR.resolve()}")
    print(f"Manifest: {manifest_out.resolve()}")
    print(f"Train Split: {train_out.resolve()}")
    print(f"Val Split: {val_out.resolve()}")

if __name__ == "__main__":
    run_balanced_merge(target_synth_per_class=736, val_ratio=0.20)
