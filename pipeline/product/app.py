"""
Göktürkçe Doğrulama Aracı — API sunucusu.

Eğitilmiş modeli yükler, /predict endpoint'i üzerinden görsel kabul edip
sınıf + güven + top-5 alternatif döner. Statik frontend'i (index.html) de
aynı sunucudan servis eder.

Çalıştırma:
    uvicorn app:app --host 0.0.0.0 --port 8000

Sonra tarayıcıda: http://localhost:8000
"""

import sys
import json
import io
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image

from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from rules_engine import OrthographyRuleEngine, SpellingEngine

# 07_segment_word.py, product/ klasörünün bir üstünde (pipeline/) duruyor.
# Modül adı rakamla başladığı için normal import çalışmaz, dosya yolundan yükle.
import importlib.util
_seg_path = Path(__file__).parent.parent / "07_segment_word.py"
_spec = importlib.util.spec_from_file_location("segment_mod", _seg_path)
segment_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(segment_mod)

MODEL_DIR = Path("./model")
# NOT (2026-07-21): burası "../gokturk_labels_v1_locked.json" idi ve YANLIŞLIKLA
# pipeline/'deki ESKİ, unutulmuş bir kopyaya işaret ediyordu (pipeline/product/
# -> pipeline/ -> orada da bir şema kopyası var, tarih: 2026-07-20 00:17,
# ko/ku/kö/kü ve changelog eklemelerinden ÖNCEKİ hali). Proje kökündeki
# GÜNCEL/DOĞRU dosya iki seviye yukarıda. Bu yanlış yol yüzünden sunucu
# haftalarca (bu oturum boyunca) syllable_ok/syllable_oek'in ko/ku/kö/kü
# okunuşlarını asla göremedi — "korkınç" gibi kelimelerde ligatür yerine
# düz harf üretiyordu, CLI testleri (doğru dosyayı elle veren) ise hep
# doğru sonuç veriyordu. Kök neden buydu, kod mantığında hata yoktu.
SCHEMA_PATH = Path("../../gokturk_labels_v1_locked.json")
STATIC_DIR = Path("./static")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

RATE_LIMIT_MINUTE = 30
RATE_LIMIT_DAY = 1000

def get_api_key_from_request(request: Request) -> str:
    return request.headers.get(API_KEY_NAME, "anonymous")

limiter = Limiter(key_func=get_api_key_from_request)

app = FastAPI(title="Göktürkçe Doğrulama Aracı")
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Dakikada en fazla {RATE_LIMIT_MINUTE} istek, günde en fazla {RATE_LIMIT_DAY} istek atılabilir."}
    )

def get_api_key(api_key: str = Security(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=401, detail="API Key missing")
    keys_path = Path(__file__).parent / "api_keys.json"
    if not keys_path.exists():
        raise HTTPException(status_code=401, detail="API Key store not found")
    try:
        with open(keys_path, encoding="utf-8") as f:
            keys = json.load(f)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read API Key store")
    
    if api_key not in keys or not keys[api_key].get("active", False):
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

from datetime import datetime, timezone

@app.middleware("http")
async def log_usage_middleware(request: Request, call_next):
    path = request.url.path
    if path in ["/predict", "/predict_word", "/predict_image", "/translate"]:
        api_key = request.headers.get(API_KEY_NAME, "missing")
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        try:
            response = await call_next(request)
            status_code = response.status_code
            success = 200 <= status_code < 300
        except Exception as e:
            status_code = 500
            success = False
            raise e
        finally:
            log_entry = {
                "api_key": api_key,
                "endpoint": path,
                "timestamp": timestamp,
                "status_code": status_code,
                "success": success
            }
            log_path = Path(__file__).parent / "usage_log.jsonl"
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            except Exception as e:
                sys.stderr.write(f"Usage logging failed: {e}\n")
                
        return response
    else:
        return await call_next(request)

# TODO: Production domain should be added here in the future
allowed_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_model(num_classes):
    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


class ModelBundle:
    def __init__(self):
        with open(MODEL_DIR / "idx_to_class.json", encoding="utf-8") as f:
            self.idx_to_class = {int(k): v for k, v in json.load(f).items()}
        with open(MODEL_DIR / "inference_config.json", encoding="utf-8") as f:
            self.cfg = json.load(f)
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        self.class_meta = {c["id"]: c for c in schema["classes"]}

        self.model = build_model(self.cfg["num_classes"])
        self.model.load_state_dict(torch.load(MODEL_DIR / "best_model.pt", map_location="cpu"))
        self.model.eval()

        self.tf = transforms.Compose([
            transforms.Resize((self.cfg["image_size"], self.cfg["image_size"])),
            transforms.ToTensor(),
            transforms.Normalize(mean=self.cfg["normalize_mean"], std=self.cfg["normalize_std"]),
        ])

    def predict(self, img: Image.Image, top_k=5):
        x = self.tf(img.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            probs = torch.softmax(self.model(x), dim=1)[0]
        topk = torch.topk(probs, min(top_k, probs.shape[0]))

        results = []
        for p, i in zip(topk.values, topk.indices):
            cid = self.idx_to_class[i.item()]
            meta = self.class_meta.get(cid, {})
            results.append({
                "class_id": cid,
                "sound": meta.get("sound", []),
                "glyph_ref": (meta.get("glyph_ref") or {}).get("core_orhun"),
                "confidence": round(p.item(), 4),
            })

        top1 = results[0]
        is_valid = (
            top1["class_id"] != "invalid_hard_negative"
            and top1["confidence"] >= self.cfg["conf_threshold"]
        )
        return {
            "valid": is_valid,
            "verdict": top1["class_id"] if is_valid else "invalid_or_uncertain",
            "confidence": top1["confidence"],
            "top_k": results,
        }


bundle = None  # lazy-load, sunucu açılışında yüklenir
rule_engine = None
spelling_engine = None

# Söz ayracı ':' bir model sınıfı değil, yapısal bir işaret (SpellingEngine
# çıktısında literal ":" olarak temsil edilir) — Unicode karşılığı Old
# Turkic word separator U+205A.
WORD_SEPARATOR = {"class_id": ":", "glyph_ref": "⁚", "codepoint": "U+205A"}


@app.on_event("startup")
def load_model():
    global bundle, rule_engine, spelling_engine
    bundle = ModelBundle()
    rule_engine = OrthographyRuleEngine(SCHEMA_PATH)
    spelling_engine = SpellingEngine(SCHEMA_PATH)
    print(f"Model yüklendi: {len(bundle.idx_to_class)} sınıf, conf_threshold={bundle.cfg['conf_threshold']}")


class TranslateRequest(BaseModel):
    text: str
    mode: str = "geleneksel"  # "geleneksel" | "modern"


@app.post("/predict")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def predict(request: Request, file: UploadFile = File(...), api_key: str = Depends(get_api_key)):
    if bundle is None:
        raise HTTPException(status_code=503, detail="Model henüz yüklenmedi")
    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents))
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz görsel dosyası")

    return bundle.predict(img)


@app.post("/predict_word")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def predict_word(request: Request, files: List[UploadFile] = File(...), api_key: str = Depends(get_api_key)):
    """
    Birden fazla görsel, OKUMA SIRASINA GÖRE (soldan sağa mantıksal sırada,
    yani zaten doğru diziliş) yüklenir — her biri bir kelimenin bir harfi.
    Her glyph önce Seviye 1 ile sınıflandırılır, sonra tüm dizi Seviye 2
    ünlü uyumu kontrolünden geçer.
    """
    if bundle is None or rule_engine is None:
        raise HTTPException(status_code=503, detail="Model henüz yüklenmedi")

    per_glyph = []
    for f in files:
        try:
            contents = await f.read()
            img = Image.open(io.BytesIO(contents))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Geçersiz görsel: {f.filename}")
        result = bundle.predict(img)
        per_glyph.append({"filename": f.filename, **result})

    sequence = [g["verdict"] for g in per_glyph]
    harmony_check = rule_engine.check_sequence(sequence)

    any_invalid = any(not g["valid"] for g in per_glyph)

    return {
        "per_glyph": per_glyph,
        "orthography": harmony_check,
        "overall_valid": (not any_invalid) and harmony_check["harmony_consistent"],
    }


@app.post("/predict_image")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def predict_image(request: Request, file: UploadFile = File(...), api_key: str = Depends(get_api_key)):
    """
    GERÇEK ÜRÜN AKIŞI: tek bir görsel yüklenir (bir kelime, birden fazla
    kelime, ya da tam cümle olabilir — aralarında ':' söz ayracı varsa
    otomatik ayrılır). Sunucu tarafında otomatik segmentasyon yapılır,
    her glyph sınıflandırılır, kelimeler kendi içinde ünlü uyumu
    kontrolünden geçer.
    """
    if bundle is None or rule_engine is None:
        raise HTTPException(status_code=503, detail="Model henüz yüklenmedi")

    try:
        contents = await file.read()
        img = Image.open(io.BytesIO(contents)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz görsel dosyası")

    gray = np.array(img.convert("L"))
    binary = gray < 128
    lines = segment_mod.find_components_by_line(binary, merge_gap_px=segment_mod.DEFAULT_MERGE_GAP_PX)

    if not lines:
        return {
            "words": [],
            "overall_valid": False,
            "note": "Görselde hiç işaret tespit edilemedi (tamamen boş ya da eşik değeri uygun değil).",
        }

    # glyph / kolon ayrımı + kırpma + kelimelere bölme, satır satır.
    # left_limit/right_limit (07_segment_word.py'nin CLI main()'indeki
    # mantıkla birebir aynı) SADECE aynı satırdaki komşu kutuya bakar —
    # bir satırın son glyph'i başka satırın ilk glyph'iyle asla komşu
    # sayılmaz. Satır sonu, kolon olmasa bile örtük bir kelime sınırı
    # sayılır (iki satır aynı kompozisyonda ayrı ifadeler olabilir).
    words_raw = []
    for line_boxes in lines:
        current = []
        for idx, box in enumerate(line_boxes):
            if segment_mod.is_colon(box, binary):
                if current:
                    words_raw.append(current)
                    current = []
                continue

            left_limit = 0
            if idx > 0:
                left_limit = (line_boxes[idx - 1][2] + box[0]) // 2

            right_limit = img.width
            if idx < len(line_boxes) - 1:
                right_limit = (box[2] + line_boxes[idx + 1][0]) // 2

            crop = segment_mod.crop_with_margin(
                img, box,
                left_limit=left_limit,
                right_limit=right_limit,
                margin_ratio=0.28,
                size=256,
            )
            result = bundle.predict(crop)
            current.append({"type": "glyph", **result})

        if current:
            words_raw.append(current)

    words_out = []
    any_word_invalid = False
    for w in words_raw:
        sequence = [g["verdict"] for g in w]
        harmony = rule_engine.check_sequence(sequence)
        any_glyph_invalid = any(not g["valid"] for g in w)
        word_valid = (not any_glyph_invalid) and harmony["harmony_consistent"]
        if not word_valid:
            any_word_invalid = True
        words_out.append({
            "glyphs": w,
            "orthography": harmony,
            "word_valid": word_valid,
        })

    return {
        "words": words_out,
        "word_count": len(words_out),
        "overall_valid": (len(words_out) > 0) and (not any_word_invalid),
    }


@app.post("/translate")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
def translate(request: Request, req: TranslateRequest, api_key: str = Depends(get_api_key)):
    """
    Latin metni beklenen Göktürkçe class_id dizisine çevirir (SpellingEngine,
    Seviye 2'nin kodlama yönü — check_sequence'ten AYRI bir katman).
    mode="geleneksel": tam kural seti (ünlü düşürme, ligatür sıkıştırma,
    kalın/ince atama). mode="modern": kural uygulamadan harf-harf birebir
    eşleme.
    """
    if spelling_engine is None:
        raise HTTPException(status_code=503, detail="Motor henüz yüklenmedi")

    if req.mode == "modern":
        pairs = spelling_engine.letter_by_letter_sequence_with_letters(req.text)
    else:
        pairs = spelling_engine.expected_sequence_with_letters(req.text)

    sequence = []
    for cid, latin_chunk in pairs:
        if cid == ":":
            sequence.append(WORD_SEPARATOR)
        elif cid.isdigit():
            sequence.append({
                "class_id": cid,
                "latin": latin_chunk,
                "glyph_ref": cid,
                "codepoint": f"U+{ord(cid):04X}",
            })
        else:
            meta = bundle.class_meta.get(cid, {})
            sequence.append({
                "class_id": cid,
                "latin": latin_chunk,
                "glyph_ref": (meta.get("glyph_ref") or {}).get("core_orhun"),
                "codepoint": (meta.get("codepoints") or {}).get("core_orhun"),
            })

    return {
        "input": req.text,
        "mode": req.mode,
        "sequence": sequence,
        "gokturkce_text": "".join(s["glyph_ref"] or "" for s in sequence),
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
