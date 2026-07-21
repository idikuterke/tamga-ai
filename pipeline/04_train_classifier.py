"""
STEP 4 — Sınıflandırıcı eğitimi.

Mimari: MobileNetV2 (ImageNet ön-eğitimli) fine-tune, 38 sınıf + hafif backbone.
Ağır transformer yok — 38 sınıf için gereksiz, CPU'da bile makul sürede eğitilir.

OOD ("geçersiz/uydurma glyph") tespiti iki katmanlı:
  1. HARD NEGATIVES (varsa): --negatives_dir altında Futhark fontlarıyla render
     edilmiş görseller veya rastgele runik-benzeri çizimler. Bunlar 39. sınıf
     olarak ("invalid") eğitime dahil edilir. Bu en güçlü yöntemdir.
  2. GÜVEN EŞİĞİ (her zaman aktif): softmax olasılığı --conf_threshold altındaysa
     çıktı "invalid/emin değil" sayılır — hard negative verisi olmasa bile çalışır.

Kullanım:
    python 04_train_classifier.py --dataset_dir ./data/dataset --data_root . \
        --epochs 15 --batch_size 32 --out ./model

    # Hard negative (Futhark vb.) eklemek istersen:
    python 04_train_classifier.py --dataset_dir ./data/dataset --data_root . \
        --negatives_dir ./data/negatives --epochs 15 --out ./model
"""

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image


class GlyphDataset(Dataset):
    def __init__(self, jsonl_path, data_root, class_to_idx, transform, negative_files=None):
        self.items = []
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                self.items.append((Path(data_root) / r["file"], class_to_idx[r["class_id"]]))
        if negative_files:
            invalid_idx = max(class_to_idx.values()) + 1
            for fp in negative_files:
                self.items.append((fp, invalid_idx))
        self.transform = transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        path, label = self.items[idx]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


def build_model(num_classes):
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset_dir", required=True, help="03_build_dataset.py çıktısı (train.jsonl/val.jsonl burada)")
    ap.add_argument("--data_root", default=".", help="jsonl içindeki 'file' path'lerinin göreli olduğu kök klasör")
    ap.add_argument("--negatives_dir", default=None, help="opsiyonel: Futhark/çöp glyph görselleri (39. sınıf)")
    ap.add_argument("--schema", default="../gokturk_labels_v1_locked.json")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--conf_threshold", type=float, default=0.6,
                     help="softmax güveni bu değerin altındaysa 'invalid/emin değil' say")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    with open(args.schema, encoding="utf-8") as f:
        schema = json.load(f)
    class_to_idx = {c["id"]: c["index"] for c in schema["classes"]}
    idx_to_class = {v: k for k, v in class_to_idx.items()}
    num_core_classes = len(class_to_idx)

    negative_files = None
    num_classes = num_core_classes
    if args.negatives_dir and Path(args.negatives_dir).exists():
        negative_files = sorted(Path(args.negatives_dir).glob("*.png")) + sorted(Path(args.negatives_dir).glob("*.jpg"))
        if negative_files:
            num_classes = num_core_classes + 1
            idx_to_class[num_core_classes] = "invalid_hard_negative"
            print(f"Hard negative bulundu: {len(negative_files)} görsel -> 39. sınıf ('invalid') eklendi.")
    if not negative_files:
        print("UYARI: hard negative yok. Sadece güven-eşiği (confidence threshold) ile OOD tespiti yapılacak — "
              "Futhark gibi bilinen hatalarda ek sağlamlık için --negatives_dir eklemen önerilir.")

    train_tf = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    val_tf = train_tf

    train_negs = negative_files[: int(len(negative_files) * 0.85)] if negative_files else None
    val_negs = negative_files[int(len(negative_files) * 0.85):] if negative_files else None

    train_ds = GlyphDataset(Path(args.dataset_dir) / "train.jsonl", args.data_root, class_to_idx, train_tf, train_negs)
    val_ds = GlyphDataset(Path(args.dataset_dir) / "val.jsonl", args.data_root, class_to_idx, val_tf, val_negs)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    model = build_model(num_classes).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    history = []

    for epoch in range(args.epochs):
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            out = model(imgs)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * imgs.size(0)
            train_correct += (out.argmax(1) == labels).sum().item()
            train_total += imgs.size(0)
        scheduler.step()

        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for imgs, labels in val_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                out = model(imgs)
                val_correct += (out.argmax(1) == labels).sum().item()
                val_total += imgs.size(0)

        train_acc = train_correct / max(train_total, 1)
        val_acc = val_correct / max(val_total, 1)
        print(f"epoch {epoch+1}/{args.epochs}  train_loss={train_loss/train_total:.4f}  "
              f"train_acc={train_acc:.3f}  val_acc={val_acc:.3f}")
        history.append({"epoch": epoch + 1, "train_acc": train_acc, "val_acc": val_acc})

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), out_dir / "best_model.pt")

    with open(out_dir / "idx_to_class.json", "w", encoding="utf-8") as f:
        json.dump(idx_to_class, f, ensure_ascii=False, indent=2)
    with open(out_dir / "training_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    with open(out_dir / "inference_config.json", "w", encoding="utf-8") as f:
        json.dump({
            "conf_threshold": args.conf_threshold,
            "num_classes": num_classes,
            "has_hard_negative_class": negative_files is not None,
            "image_size": 224,
            "normalize_mean": [0.485, 0.456, 0.406],
            "normalize_std": [0.229, 0.224, 0.225],
        }, f, ensure_ascii=False, indent=2)

    print(f"En iyi val_acc: {best_val_acc:.3f}  -> {out_dir/'best_model.pt'}")


if __name__ == "__main__":
    main()
