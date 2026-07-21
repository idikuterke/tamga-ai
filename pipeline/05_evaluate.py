"""
STEP 5 — Değerlendirme + tahmin.

Eğitilmiş modeli yükler, val seti üzerinde per-class doğruluk + en çok
karıştırılan sınıf çiftlerini (confusable_with listesine göre) raporlar.
Tek bir görsel üzerinde tahmin de yapabilir (--image ile).

Güven eşiği burada devreye giriyor: softmax olasılığı inference_config.json'daki
conf_threshold altındaysa sonuç "EMİN DEĞİL / GEÇERSİZ OLABİLİR" döner —
bu, doğrulama aracının asıl amacı olan halüsinasyon tespiti.

Kullanım:
    # Val seti üzerinde toplu değerlendirme:
    python 05_evaluate.py --model_dir ./model --dataset_dir ./data/dataset --data_root .

    # Tek görsel tahmini:
    python 05_evaluate.py --model_dir ./model --image path/to/test.png
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict, Counter

import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image


def build_model(num_classes):
    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


def load_everything(model_dir):
    model_dir = Path(model_dir)
    with open(model_dir / "idx_to_class.json", encoding="utf-8") as f:
        idx_to_class = {int(k): v for k, v in json.load(f).items()}
    with open(model_dir / "inference_config.json", encoding="utf-8") as f:
        cfg = json.load(f)

    model = build_model(cfg["num_classes"])
    model.load_state_dict(torch.load(model_dir / "best_model.pt", map_location="cpu"))
    model.eval()

    tf = transforms.Compose([
        transforms.Resize((cfg["image_size"], cfg["image_size"])),
        transforms.ToTensor(),
        transforms.Normalize(mean=cfg["normalize_mean"], std=cfg["normalize_std"]),
    ])
    return model, idx_to_class, cfg, tf


def predict_one(model, tf, cfg, idx_to_class, image_path):
    img = Image.open(image_path).convert("RGB")
    x = tf(img).unsqueeze(0)
    with torch.no_grad():
        logits = model(x)
        probs = torch.softmax(logits, dim=1)[0]
    conf, pred_idx = probs.max(0)
    conf = conf.item()
    label = idx_to_class[pred_idx.item()]
    if conf < cfg["conf_threshold"]:
        return f"EMİN DEĞİL (güven={conf:.2f}) — muhtemelen geçersiz/uydurma glyph", conf
    return label, conf


def evaluate_val_set(model, tf, cfg, idx_to_class, dataset_dir, data_root, schema):
    class_to_idx = {c["id"]: c["index"] for c in schema["classes"]}
    confusable_map = {c["id"]: c.get("confusable_with", []) for c in schema["classes"]}

    correct_per_class = defaultdict(int)
    total_per_class = defaultdict(int)
    confusion_pairs = defaultdict(int)
    all_errors = Counter()

    with open(Path(dataset_dir) / "val.jsonl", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]

    for r in rows:
        path = Path(data_root) / r["file"]
        true_id = r["class_id"]
        pred_label, conf = predict_one(model, tf, cfg, idx_to_class, path)

        total_per_class[true_id] += 1
        if pred_label == true_id:
            correct_per_class[true_id] += 1
        else:
            all_errors[f"{true_id} -> {pred_label}"] += 1
            if pred_label in confusable_map.get(true_id, []):
                confusion_pairs[f"{true_id} <-> {pred_label}"] += 1

    print("\n--- Sınıf başına doğruluk (en düşük 10) ---")
    accs = {cid: correct_per_class[cid] / total_per_class[cid] for cid in total_per_class}
    for cid, acc in sorted(accs.items(), key=lambda x: x[1])[:10]:
        print(f"  {cid}: {acc:.2f}  ({total_per_class[cid]} örnek)")

    if confusion_pairs:
        print("\n--- Bilinen 'confusable' çiftlerinde gerçekleşen karışıklıklar ---")
        for pair, count in sorted(confusion_pairs.items(), key=lambda x: -x[1]):
            print(f"  {pair}: {count} kez")

    if all_errors:
        print("\n--- En sık 15 hata ---")
        for pair, count in all_errors.most_common(15):
            print(f"  {pair}: {count} kez")

    overall = sum(correct_per_class.values()) / max(sum(total_per_class.values()), 1)
    print(f"\nGenel val doğruluğu: {overall:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_dir", required=True)
    ap.add_argument("--dataset_dir", default=None)
    ap.add_argument("--data_root", default=".")
    ap.add_argument("--schema", default="../gokturk_labels_v1_locked.json")
    ap.add_argument("--image", default=None)
    args = ap.parse_args()

    model, idx_to_class, cfg, tf = load_everything(args.model_dir)

    if args.image:
        label, conf = predict_one(model, tf, cfg, idx_to_class, args.image)
        print(f"Tahmin: {label}  (güven={conf:.2f})")
        return

    if args.dataset_dir:
        with open(args.schema, encoding="utf-8") as f:
            schema = json.load(f)
        evaluate_val_set(model, tf, cfg, idx_to_class, args.dataset_dir, args.data_root, schema)


if __name__ == "__main__":
    main()
