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

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends, Security
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from rules_engine import OrthographyRuleEngine, SpellingEngine, SpellingDecoder
from render import render as render_img, STYLES
from video import VideoRenderer
from compositor import composite_text

video_renderer = VideoRenderer()

# 07_segment_word.py, product/ klasörünün bir üstünde (pipeline/) duruyor.
# Modül adı rakamla başladığı için normal import çalışmaz, dosya yolundan yükle.
import importlib.util
_seg_path = Path(__file__).parent.parent / "07_segment_word.py"
_spec = importlib.util.spec_from_file_location("segment_mod", _seg_path)
segment_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(segment_mod)

PRODUCT_DIR = Path(__file__).resolve().parent
MODEL_DIR = PRODUCT_DIR / "model" if (PRODUCT_DIR / "model" / "idx_to_class.json").exists() else PRODUCT_DIR.parent / "model"
# NOT (2026-07-21): SCHEMA_PATH projenin kökündeki kilitli şemayı işaret etmeli
SCHEMA_PATH = (PRODUCT_DIR / "../../gokturk_labels_v1_locked.json").resolve()
STATIC_DIR = PRODUCT_DIR / "static"

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

RATE_LIMIT_MINUTE = 30
RATE_LIMIT_DAY = 1000

ENABLE_COMPOSITOR_TAB = True

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

        model_file = (MODEL_DIR / "best_model.pt").resolve()
        mtime_str = datetime.fromtimestamp(model_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        file_size_mb = model_file.stat().st_size / (1024 * 1024)

        self.model = build_model(self.cfg["num_classes"])
        self.model.load_state_dict(torch.load(model_file, map_location="cpu"))
        self.model.eval()

        sys.stderr.write(f"\n==================================================\n")
        sys.stderr.write(f"YUKLENEN MODEL BILGISI:\n")
        sys.stderr.write(f"   Dosya Yolu           : {model_file}\n")
        sys.stderr.write(f"   Son Degistirilme     : {mtime_str}\n")
        sys.stderr.write(f"   Dosya Boyutu         : {file_size_mb:.2f} MB\n")
        sys.stderr.write(f"   Sinif Sayisi         : {self.cfg['num_classes']} sinif\n")
        sys.stderr.write(f"   Guven Esigi (Conf)   : {self.cfg['conf_threshold']}\n")
        sys.stderr.write(f"==================================================\n\n")
        sys.stderr.flush()

        self.model_info = {
            "model_path": str(model_file),
            "last_modified": mtime_str,
            "file_size_mb": round(file_size_mb, 2),
            "num_classes": self.cfg["num_classes"],
            "conf_threshold": self.cfg["conf_threshold"]
        }

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
spelling_decoder = None
class_meta_map = {}

WORD_SEPARATOR = {"class_id": ":", "glyph_ref": "⁚", "codepoint": "U+205A"}


@app.on_event("startup")
def load_model():
    global bundle, rule_engine, spelling_engine, spelling_decoder, class_meta_map
    try:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        class_meta_map = {c["id"]: c for c in schema["classes"]}
    except Exception as e:
        sys.stderr.write(f"Şema yüklenemedi: {e}\n")
        class_meta_map = {}

    try:
        bundle = ModelBundle()
        sys.stderr.write(f"Model Yüklendi: {bundle.model_info['model_path']}\n")
    except Exception as e:
        sys.stderr.write(f"Model Yüklenemedi (render-only modunda olabilir): {e}\n")
        bundle = None
        
    rule_engine = OrthographyRuleEngine(SCHEMA_PATH)
    spelling_engine = SpellingEngine(SCHEMA_PATH)
    spelling_decoder = SpellingDecoder(SCHEMA_PATH)
    sys.stderr.write("Sunucu Baslatildi.\n")
    sys.stderr.flush()

@app.get("/api/model_info")
def get_model_info():
    if bundle is None:
        raise HTTPException(status_code=503, detail="Model bundle not loaded")
    return bundle.model_info


class TranslateRequest(BaseModel):
    text: str
    mode: str = "geleneksel"  # "geleneksel" | "modern"


class RenderRequest(BaseModel):
    text: str
    style: str = "plain"
    size: int = 512
    degradation: float = 0.0
    text_color: str | None = None
    transparent_bg: bool = False
    texture: str | None = None
    texture_var: str | None = None
    stamp_var: str | None = None
    light_direction: tuple[int, int] | None = None
    font_variant: str | None = "auto"


class RenderVideoRequest(BaseModel):
    text: str
    style: str = "plain"
    motion: str = "parallax"
    duration: int = 5
    size: int = 512
    degradation: float = 0.0
    text_color: str | None = None
    transparent_bg: bool = False
    texture: str | None = None
    texture_var: str | None = None
    stamp_var: str | None = None
    light_direction: tuple[int, int] | None = None
    font_variant: str | None = "auto"


class DecodeTextRequest(BaseModel):
    text: str
    mode: str = "auto"  # "auto" | "geleneksel" | "modern"


@app.post("/decode_text")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def decode_text(request: Request, req: DecodeTextRequest, api_key: str = Depends(get_api_key)):
    """
    Kullanıcı doğrudan Göktürkçe Unicode metin yapıştırıp okutur.
    Metni karakter karakter ters haritadan class_id dizisine çevirir,
    kandidatları üretir ve EDPT sözlüğünde sorgular.
    """
    if spelling_decoder is None:
        raise HTTPException(status_code=503, detail="Dekoder henüz yüklenmedi")

    return spelling_decoder.decode_gokturk_text(req.text, mode=req.mode)


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


def prepare_image_for_segmentation(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


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
        raw_img = Image.open(io.BytesIO(contents))
        img = prepare_image_for_segmentation(raw_img)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz görsel dosyası")

    gray = np.array(img.convert("L"))
    binary = gray < 128
    lines = segment_mod.find_components_by_line(binary, merge_gap_px=segment_mod.DEFAULT_MERGE_GAP_PX, rtl=True)

    if not lines:
        return {
            "reading_order": "rtl",
            "words": [],
            "word_count": 0,
            "overall_valid": False,
            "note": "Görselde hiç işaret tespit edilemedi (tamamen boş ya da eşik değeri uygun değil).",
            "segmentation_debug": {
                "total_lines": 0,
                "total_boxes": 0,
                "lines": [],
            }
        }

    words_raw = []
    total_boxes = 0
    seg_debug_lines = []

    for line_idx, line_boxes in enumerate(lines):
        total_boxes += len(line_boxes)
        seg_debug_lines.append({
            "line_index": line_idx + 1,
            "boxes": line_boxes
        })
        current = []
        for idx, box in enumerate(line_boxes):
            if segment_mod.is_colon(box, binary):
                if current:
                    words_raw.append(current)
                    current = []
                continue

            # RTL dizilimde (x0 azalan):
            # Sağ komşu (x koordinatı daha büyük olan): idx - 1
            right_limit = img.width
            if idx > 0:
                right_limit = (line_boxes[idx - 1][0] + box[2]) // 2

            # Sol komşu (x koordinatı daha küçük olan): idx + 1
            left_limit = 0
            if idx < len(line_boxes) - 1:
                left_limit = (box[0] + line_boxes[idx + 1][2]) // 2

            crop = segment_mod.crop_with_margin(
                img, box,
                left_limit=left_limit,
                right_limit=right_limit,
                margin_ratio=0.28,
                size=256,
            )
            result = bundle.predict(crop)
            current.append({
                "type": "glyph",
                "box": box,
                **result
            })

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

        sound_hints = []
        for g in w:
            top_k = g.get("top_k", [])
            sounds = top_k[0].get("sound", []) if top_k else []
            sound_hints.append(sounds[0] if sounds else "")

        sound_hint_seq = "-".join([s for s in sound_hints if s])

        decoder_res = spelling_decoder.decode_sequence(sequence) if spelling_decoder else {}

        words_out.append({
            "glyphs": w,
            "orthography": harmony,
            "sound_hints": sound_hints,
            "sound_hint_sequence": sound_hint_seq,
            "word_valid": word_valid,
            "dictionary_matched_candidates": decoder_res.get("dictionary_matched_candidates", []),
            "unmatched_candidates": decoder_res.get("unmatched_candidates", []),
            "dictionary_note": decoder_res.get("dictionary_note", ""),
        })

    return {
        "reading_order": "rtl",
        "words": words_out,
        "word_count": len(words_out),
        "overall_valid": (len(words_out) > 0) and (not any_word_invalid),
        "segmentation_debug": {
            "total_lines": len(lines),
            "total_boxes": total_boxes,
            "lines": seg_debug_lines,
        }
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
        elif cid == "literal_colon":
            sequence.append({
                "class_id": "literal_colon",
                "latin": ":",
                "glyph_ref": ":",
                "codepoint": "U+003A",
            })
        elif cid in class_meta_map:
            meta = class_meta_map[cid]
            sequence.append({
                "class_id": cid,
                "latin": latin_chunk,
                "glyph_ref": (meta.get("glyph_ref") or {}).get("core_orhun"),
                "codepoint": (meta.get("codepoints") or {}).get("core_orhun"),
            })
        else:
            # Rakam, noktalama, sembol veya bilinmeyen karakter -> olduğu gibi geçir
            cp = f"U+{ord(cid[0]):04X}" if cid else "—"
            sequence.append({
                "class_id": cid,
                "latin": latin_chunk,
                "glyph_ref": cid,
                "codepoint": cp,
            })

    return {
        "input": req.text,
        "mode": req.mode,
        "sequence": sequence,
        "gokturkce_text": "".join(s["glyph_ref"] or "" for s in sequence),
    }


@app.post("/api/render")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def api_render(request: Request, req: RenderRequest, api_key: str = Depends(get_api_key)):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if req.style not in STYLES:
        raise HTTPException(status_code=400, detail=f"Invalid style. Must be one of: {', '.join(STYLES.keys())}")
    
    try:
        img = render_img(
            text=req.text,
            style=req.style,
            size=req.size,
            degradation=req.degradation,
            text_color=req.text_color,
            transparent_bg=req.transparent_bg,
            texture=req.texture,
            texture_var=req.texture_var,
            stamp_var=req.stamp_var,
            light_direction=req.light_direction,
            font_variant=req.font_variant or "auto"
        )
        
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        return Response(content=img_byte_arr, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/render_video")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def api_render_video(request: Request, req: RenderVideoRequest, api_key: str = Depends(get_api_key)):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if req.style not in STYLES:
        raise HTTPException(status_code=400, detail=f"Invalid style. Must be one of: {', '.join(STYLES.keys())}")
    if req.motion not in ["parallax", "zoom", "pan", "fade"]:
        raise HTTPException(status_code=400, detail="Invalid motion. Must be one of: parallax, zoom, pan, fade")
    
    try:
        img = render_img(
            text=req.text,
            style=req.style,
            size=req.size,
            degradation=req.degradation,
            text_color=req.text_color,
            transparent_bg=req.transparent_bg,
            texture=req.texture,
            texture_var=req.texture_var,
            stamp_var=req.stamp_var,
            light_direction=req.light_direction,
            font_variant=req.font_variant or "auto"
        )
        
        video_bytes = video_renderer.render_to_video(
            image=img,
            motion=req.motion,
            duration=req.duration,
            fps=30
        )
        
        return Response(content=video_bytes, media_type="video/mp4")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
def get_config():
    return {"enable_compositor_tab": ENABLE_COMPOSITOR_TAB}


@app.post("/api/composite")
@limiter.limit(f"{RATE_LIMIT_MINUTE}/minute; {RATE_LIMIT_DAY}/day")
async def api_composite(
    request: Request,
    base_image: UploadFile = File(...),
    text: str = Form(...),
    bbox: str = Form("100,100,400,150"),
    style: str = Form("stone"),
    text_color: str | None = Form(None),
    scale: float = Form(0.8),
    auto_color_match: bool = Form(True),
    texture: str | None = Form(None),
    api_key: str = Depends(get_api_key)
):
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if style not in STYLES:
        raise HTTPException(status_code=400, detail=f"Invalid style. Must be one of: {', '.join(STYLES.keys())}")
    
    try:
        bbox_tuple = tuple(int(v.strip()) for v in bbox.split(","))
        if len(bbox_tuple) != 4:
            raise ValueError("bbox must be 4 integers x,y,w,h")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid bbox format. Must be x,y,w,h")
        
    try:
        contents = await base_image.read()
        raw_img = Image.open(io.BytesIO(contents)).convert("RGBA")
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz görsel dosyası")
        
    try:
        result_img = composite_text(
            base_image=raw_img,
            text=text,
            bbox=bbox_tuple,
            style=style,
            perspective_corners=None,
            shadow=True,
            color_match=auto_color_match,
            text_color=text_color,
            scale=scale,
            auto_color_match=auto_color_match,
            texture=texture
        )
        
        img_byte_arr = io.BytesIO()
        result_img.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        return Response(content=img_byte_arr, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
