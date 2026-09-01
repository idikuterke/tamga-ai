"""
STEP 3 — Etiketli dataset + train/val split + sınıf dengesi raporu.

Step 1 (temiz) + Step 2 (augmente) manifest'lerini birleştirir, sınıf başına
görsel sayısını raporlar (dengesizlik erken yakalanır — ör. 'l_front' gibi
tek font+tek kod noktalı sınıflar, 6 fontlu 'b_back' gibi sınıflara göre çok
daha az örnek alacaktır, bu görülmeli), ardından stratified train/val split
üretir.

Kullanım:
    python 03_build_dataset.py --clean_dir ./data/clean --aug_dir ./data/augmented \
        --out ./data/dataset --val_ratio 0.15
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean_dir", required=True)
    ap.add_argument("--aug_dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--val_ratio", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    rows = []
    with open(Path(args.clean_dir) / "manifest_clean.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            r["source"] = "clean"
            rows.append(r)
    with open(Path(args.aug_dir) / "manifest_augmented.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            r["source"] = "augmented"
            rows.append(r)

    by_class = defaultdict(list)
    for r in rows:
        by_class[r["class_id"]].append(r)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    balance_report = {cid: len(items) for cid, items in sorted(by_class.items())}
    with open(out_dir / "class_balance_report.json", "w", encoding="utf-8") as f:
        json.dump(balance_report, f, ensure_ascii=False, indent=2)

    counts = list(balance_report.values())
    if counts:
        min_c, max_c = min(counts), max(counts)
        print(f"Sınıf başına örnek: min={min_c}  max={max_c}  oran={max_c/max(min_c,1):.1f}x")
        if max_c > 0 and min_c / max(max_c, 1) < 0.3:
            print("UYARI: sınıflar arası dengesizlik yüksek (>3x). Eğitimde class_weight kullan "
                  "ya da az örnekli sınıflar için ek font/varyasyon kaynağı ekle.")

    train_rows, val_rows = [], []
    for cid, items in by_class.items():
        # Kaynak temiz görsel gruplaması
        from collections import defaultdict
        clean_groups = defaultdict(list)
        for r in items:
            clean_src = r["source_clean_file"]
            clean_groups[clean_src].append(r)

        clean_src_keys = list(clean_groups.keys())
        rng.shuffle(clean_src_keys)

        n_val_keys = max(1, int(len(clean_src_keys) * args.val_ratio)) if len(clean_src_keys) > 2 else (1 if len(clean_src_keys) > 1 else 0)
        val_keys = set(clean_src_keys[:n_val_keys])

        for clean_src, group_items in clean_groups.items():
            if clean_src in val_keys:
                val_rows.extend(group_items)
            else:
                train_rows.extend(group_items)

    # Karıştır
    rng.shuffle(train_rows)
    rng.shuffle(val_rows)

    with open(out_dir / "train.jsonl", "w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out_dir / "val.jsonl", "w", encoding="utf-8") as f:
        for r in val_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"GRUP BAZLI BÖLME TAMAMLANDI: train: {len(train_rows)}  val: {len(val_rows)}  toplam sınıf: {len(by_class)}")


if __name__ == "__main__":
    main()
