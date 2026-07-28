"""
Göktürkçe (Orhun) AI Assistant — Model Context Protocol (MCP) Server.

Mevcut Göktürkçe Doğrulama Aracı'nın (MobileNetV2 sınıflandırıcı + OrthographyRuleEngine + SpellingEngine)
MCP arayüzünü sunar.

Sunulan Araçlar (Tools):
  1. gokturkce_translate(text: str, mode: "geleneksel"|"modern"):
     Latin metni Göktürkçe kod noktaları dizisine çevirir ve Orhun yazım kurallarını kontrol eder.
  2. gokturkce_verify_image(image_path_or_base64: str):
     Görseldeki Göktürkçe işaretleri otomatik olarak segmentlere ayırır, MobileNetV2 ile sınıflandırır
     ve ünlü uyumu kurallarını doğrular.

Taşıma Katmanları (Transports):
  - stdio (Varsayılan): Claude Desktop / Claude Code gibi yerel LLM istemcileri için.
  - streamable-http / sse: Uzaktan kullanım veya API paylaşımı için (X-API-Key doğrulaması ile).

Kullanım:
  # Stdio modu (Yerel kullanım - Claude Desktop):
  python pipeline/product/mcp_server.py --transport stdio

  # HTTP modu (Uzaktan kullanım / API Key doğrulamalı):
  python pipeline/product/mcp_server.py --transport streamable-http --host 127.0.0.1 --port 8001
"""

import argparse
import base64
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Literal

warnings.filterwarnings("ignore")

import numpy as np
from PIL import Image
import mcp.types as t
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Pipeline product klasörünü sys.path'e ekle
PRODUCT_DIR = Path(__file__).resolve().parent
if str(PRODUCT_DIR) not in sys.path:
    sys.path.insert(0, str(PRODUCT_DIR))

from app import (
    ModelBundle,
    OrthographyRuleEngine,
    SpellingEngine,
    prepare_image_for_segmentation,
    segment_mod,
    SCHEMA_PATH,
    WORD_SEPARATOR,
)
from rules_engine import SpellingDecoder
from render import render as render_func

# Global tekil nesneler (Lazy Loading)
_bundle: ModelBundle | None = None
_rule_engine: OrthographyRuleEngine | None = None
_spelling_engine: SpellingEngine | None = None
_spelling_decoder: SpellingDecoder | None = None
_video_renderer = None


def get_engines():
    global _bundle, _rule_engine, _spelling_engine, _spelling_decoder
    if _bundle is None:
        _bundle = ModelBundle()
        _rule_engine = OrthographyRuleEngine(SCHEMA_PATH)
        _spelling_engine = SpellingEngine(SCHEMA_PATH)
        _spelling_decoder = SpellingDecoder(SCHEMA_PATH)
    return _bundle, _rule_engine, _spelling_engine, _spelling_decoder


def get_video_renderer():
    global _video_renderer
    if _video_renderer is None:
        from video import VideoRenderer
        _video_renderer = VideoRenderer()
    return _video_renderer


def is_valid_api_key(key: str) -> bool:
    keys_path = PRODUCT_DIR / "api_keys.json"
    if not keys_path.exists():
        return False
    try:
        with open(keys_path, encoding="utf-8") as f:
            keys = json.load(f)
        return key in keys and keys[key].get("active", False)
    except Exception:
        return False


def load_image_from_path_or_base64(input_str: str) -> Image.Image:
    input_str = input_str.strip()
    # 1. Dosya yolu kontrolü
    path = Path(input_str)
    if path.exists() and path.is_file():
        return Image.open(path)

    # 2. Data URI / Base64 kontrolü
    if input_str.startswith("data:image"):
        if "," in input_str:
            input_str = input_str.split(",", 1)[1]

    try:
        raw_bytes = base64.b64decode(input_str)
        return Image.open(io.BytesIO(raw_bytes))
    except Exception as e:
        raise ValueError(
            f"Görsel okunamadı. Verilen girdi ne geçerli bir dosya yolu ne de geçerli bir base64 dizesi: {e}"
        )


# FastMCP Server nesnesi
mcp = FastMCP(
    "Gokturkce AI Assistant",
    instructions=(
        "Göktürkçe (Orhun) alfabesi çevirisi, görsel harf doğrulaması ve "
        "Orhun Türkçe ünlü uyumu kontrolü sunan Model Context Protocol (MCP) sunucusu."
    )
)


@mcp.tool(
    name="gokturkce_translate",
    description=(
        "Latin harfli Türkçe metni Göktürkçe (Orhun) yazısına çevirir.\n\n"
        "Parametreler:\n"
        "- text: Çevrilecek metin (ör. 'bodun', 'tengri', 'turk')\n"
        "- mode: 'geleneksel' (ünlü düşürme, ligatür ve kalınlık-incelik uyumu kuralları uygular, varsayılan) "
        "veya 'modern' (birebir harf harf eşleme yapar)\n\n"
        "Örnek girdi: text='bodun', mode='geleneksel'\n"
        "Örnek çıktı: Göktürkçe metin '𐰉𐰆𐰑𐰆𐰣' ve harf harf sınıf/kod noktası detayları."
    ),
    annotations=t.ToolAnnotations(readOnlyHint=True, idempotentHint=True)
)
def gokturkce_translate(text: str, mode: str = "geleneksel") -> dict:
    bundle, rule_engine, spelling_engine, spelling_decoder = get_engines()
    text_clean = text.strip()
    if not text_clean:
        return {"error": "Boş metin çevrilemez."}

    if mode == "modern":
        pairs = spelling_engine.letter_by_letter_sequence_with_letters(text_clean)
    else:
        pairs = spelling_engine.expected_sequence_with_letters(text_clean)

    sequence = []
    gokturkce_chars = []
    for cid, latin_chunk in pairs:
        if cid == ":":
            sequence.append(WORD_SEPARATOR)
            gokturkce_chars.append("⁚")
        elif cid == "literal_colon":
            sequence.append({
                "class_id": "literal_colon",
                "latin": ":",
                "glyph_ref": ":",
                "codepoint": "U+003A",
            })
            gokturkce_chars.append(":")
        elif cid in bundle.class_meta:
            meta = bundle.class_meta[cid]
            glyph_ref = (meta.get("glyph_ref") or {}).get("core_orhun")
            codepoint = (meta.get("codepoints") or {}).get("core_orhun")
            sequence.append({
                "class_id": cid,
                "latin": latin_chunk,
                "glyph_ref": glyph_ref,
                "codepoint": codepoint,
            })
            if glyph_ref:
                gokturkce_chars.append(glyph_ref)

    gokturkce_text = "".join(gokturkce_chars)

    # Orhun ünlü uyumu kontrolü (ayraçlar hariç)
    class_ids = [item["class_id"] for item in sequence if item["class_id"] not in (":", "literal_colon")]
    harmony_check = rule_engine.check_sequence(class_ids)

    return {
        "input_text": text_clean,
        "mode": mode,
        "gokturkce_text": gokturkce_text,
        "sequence": sequence,
        "orthography": harmony_check
    }


@mcp.tool(
    name="gokturkce_decode_text",
    description=(
        "Göktürkçe Unicode metni ('𐰉𐰆𐰑𐰣 ⁚ 𐱅𐰇𐰼𐰜𐰢') deşifre eder.\n\n"
        "Metindeki karakterleri şemadaki sınıflara eşler, olası Latin okuma adaylarını türetir "
        "ve EDPT etimolojik sözlük dizininde (Vildan Koçoğlu, 2006) sorgular.\n\n"
        "Parametreler:\n"
        "- text: Göktürkçe Unicode metin (isteğe bağlı ':' veya ⁚ kelime ayracı ile)\n"
        "- mode: Deşifre modu (varsayılan 'auto')\n"
        "    'modern'    — doğrudan class_id→ses çevirisi, tek kesin okuma (kombinatoryal üretim yok)\n"
        "    'geleneksel' — kombinatoryal aday üretimi + EDPT sözlük kesişimi\n"
        "    'auto'       — her zaman 'geleneksel'e çözülür (en güvenli/eksiksiz sonuç)\n"
    ),
    annotations=t.ToolAnnotations(readOnlyHint=True, idempotentHint=True)
)
def gokturkce_decode_text(text: str, mode: str = "auto") -> dict:
    bundle, rule_engine, spelling_engine, spelling_decoder = get_engines()
    text_clean = text.strip()
    if not text_clean:
        return {"error": "Boş metin girildi."}
    return spelling_decoder.decode_gokturk_text(text_clean, mode=mode)


@mcp.tool(
    name="gokturkce_verify_image",
    description=(
        "Görseldeki Göktürkçe yazıyı otomatik segmentasyon ve MobileNetV2 yapay zeka modeli ile doğrular.\n\n"
        "Parametreler:\n"
        "- image_path_or_base64: Yerel dosya yolu (ör. 'C:/Users/pc/gokturk_pipeline/kelimeçıktı/gokturkce (14).png') "
        "veya base64 veri dizesi ('data:image/png;base64,...' ya da ham base64)\n\n"
        "Dönüş Değeri:\n"
        "- overall_valid: Görseldeki tüm kelimelerin ve ünlü uyumunun geçerli olup olmadığı (True/False)\n"
        "- word_count: Görseldeki kelime sayısı\n"
        "- words: Her kelime için tespit edilen harfler, sınıf tahminleri, olasılık dağılımı ve ünlü uyumu doğrulama sonucu."
    ),
    annotations=t.ToolAnnotations(readOnlyHint=True, idempotentHint=True)
)
def gokturkce_verify_image(image_path_or_base64: str) -> dict:
    bundle, rule_engine, spelling_engine, spelling_decoder = get_engines()
    try:
        raw_img = load_image_from_path_or_base64(image_path_or_base64)
    except Exception as e:
        return {"error": str(e), "overall_valid": False}

    img = prepare_image_for_segmentation(raw_img)
    gray = np.array(img.convert("L"))
    binary = gray < 128
    lines = segment_mod.find_components_by_line(binary, merge_gap_px=segment_mod.DEFAULT_MERGE_GAP_PX, rtl=True)

    if not lines:
        return {
            "reading_order": "rtl",
            "words": [],
            "word_count": 0,
            "overall_valid": False,
            "note": "Görselde hiç işaret tespit edilemedi.",
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


@mcp.tool(
    name="gokturkce_render_image",
    description=(
        "Göktürkçe (veya Latin) metni seçilen doku ve yazı stili üzerinde taşa kazınmış, parşömen, altın varak, neon vb. "
        "kompozit derinlik efektleriyle yüksek kaliteli PNG görseline dönüştürür ve diske kaydeder.\n\n"
        "Parametreler:\n"
        "- text: Üretilecek metin (örn: 'bodun', 'tengri', veya çok satırlı 'gök türk\\nbodun')\n"
        "- style: Yazı/vuruş stili ('plain' [Düz], 'fircha' [Fırça], 'ink_bleed' [Mürekkep Dağılması], 'stamp' [Damga], 'carved' [Kazıma/Oyma], 'parchment' [Parşömen Emilimi] veya eski uyumluluk için 'stone', 'gold' vb.)\n"
        "- texture: Arka plan dokusu ('stone.png', 'gold.png', 'neon.png', 'wood.png', 'paper.png', 'leather.png', 'parchment.png', None ise stilin önerdiği varsayılan doku seçilir)\n"
        "- size: Genişlik çözünürlüğü piksel olarak (varsayılan 512)\n"
        "- degradation: Eskime/yıpranma ve gürültü miktarı (0.0 ile 1.0 arası, varsayılan 0.0)\n"
        "- text_color: Özel yazı rengi hex kodu (örn: '#FF0000', None ise stilin varsayılanı)\n"
        "- transparent_bg: Şeffaf arka plan (True ise doku yerine saydam RGBA zemin olur)\n"
        "- output_path: Kaydedilecek hedef PNG dosya yolu (varsayılan 'rendered_image.png')\n\n"
        "Dönüş Değeri:\n"
        "- Kaydedilen dosya yolu, görsel boyutu (en-boy oranı korunduğunu gösterir), renk modu ve başarı mesajı."
    ),
    annotations=t.ToolAnnotations(readOnlyHint=False, idempotentHint=False)
)
def gokturkce_render_image(
    text: str,
    style: str = "plain",
    texture: str | None = None,
    size: int = 512,
    degradation: float = 0.0,
    text_color: str | None = None,
    transparent_bg: bool = False,
    output_path: str = "rendered_image.png"
) -> dict:
    text_clean = text.strip()
    if not text_clean:
        return {"error": "Boş metin görselleştirilemez."}
    try:
        img = render_func(
            text_clean,
            style=style,
            texture=texture,
            size=size,
            degradation=degradation,
            text_color=text_color,
            transparent_bg=transparent_bg
        )
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_p))
        return {
            "status": "success",
            "message": f"Görsel başarıyla üretildi ve '{out_p}' konumuna kaydedildi.",
            "output_path": str(out_p),
            "dimensions": img.size,
            "mode": img.mode,
            "style": style,
            "transparent_bg": transparent_bg
        }
    except Exception as e:
        return {"error": f"Görsel üretim hatası: {str(e)}", "status": "failed"}


@mcp.tool(
    name="gokturkce_render_video",
    description=(
        "Göktürkçe metni seçilen doku stili üzerinde sinematik 3D Parallax veya kamera hareketleriyle MP4 videosuna dönüştürür ve diske kaydeder.\n\n"
        "ÖNEMLİ BİLGİ / GECİKME UYARISI: Bu araç ilk çalıştırıldığında, derinlik kestirimi (Depth Anything V2) yapay zeka modelini önbellekten veya ağdan yükleyeceği için "
        "ilk render işleminde birkaç saniyelik ek bir gecikme (loading delay) yaşanabilir. Lütfen işlem tamamlanana kadar bekleyiniz. "
        "Sonraki çağrılarda model önbellekte olacağı için video üretimi çok daha hızlı gerçekleşir.\n\n"
        "Parametreler:\n"
        "- text: Üretilecek metin (örn: 'bodun' veya 'tengri')\n"
        "- style: Yazı/vuruş stili ('plain', 'fircha', 'ink_bleed', 'stamp', 'carved', 'parchment')\n"
        "- texture: Arka plan dokusu ('stone.png', 'gold.png', 'neon.png', 'wood.png', 'paper.png', 'leather.png', 'parchment.png')\n"
        "- motion: Hareket tipi ('parallax' [3D Derinlik], 'zoom' [Yakınlaşma], 'pan' [Sağdan sola kaydırma], 'fade' [Yumuşak geçiş])\n"
        "- duration: Video süresi saniye olarak (3 ile 10 arası, varsayılan 5)\n"
        "- size: Temel kare çözünürlüğü (varsayılan 512)\n"
        "- degradation: Eskime/gürültü miktarı (0.0 ile 1.0 arası, varsayılan 0.0)\n"
        "- text_color: Özel yazı rengi hex kodu (örn: '#FF0000', None ise stil varsayılanı)\n"
        "- output_path: Kaydedilecek hedef MP4 dosya yolu (varsayılan 'rendered_video.mp4')\n\n"
        "Dönüş Değeri:\n"
        "- Başarı durumu, kaydedilen dosya tam yolu, video hareketi, süre ve çözünürlük bilgisi."
    ),
    annotations=t.ToolAnnotations(readOnlyHint=False, idempotentHint=False)
)
def gokturkce_render_video(
    text: str,
    style: str = "plain",
    texture: str | None = None,
    motion: str = "parallax",
    duration: int = 5,
    size: int = 512,
    degradation: float = 0.0,
    text_color: str | None = None,
    output_path: str = "rendered_video.mp4"
) -> dict:
    text_clean = text.strip()
    if not text_clean:
        return {"error": "Boş metin için video oluşturulamaz."}
    try:
        base_img = render_func(
            text_clean,
            style=style,
            texture=texture,
            size=size,
            degradation=degradation,
            text_color=text_color,
            transparent_bg=False  # MP4 videosu saydamlık desteklemediği için RGB zemin kullanılır
        )
        renderer = get_video_renderer()
        video_bytes = renderer.render_to_video(base_img, motion=motion, duration=duration)
        
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "wb") as f:
            f.write(video_bytes)
            
        return {
            "status": "success",
            "message": f"Sinematik '{motion}' videosu başarıyla üretildi ve '{out_p}' konumuna kaydedildi.",
            "output_path": str(out_p),
            "motion": motion,
            "duration_seconds": duration,
            "base_dimensions": base_img.size,
            "style": style
        }
    except Exception as e:
        return {"error": f"Video üretim hatası: {str(e)}", "status": "failed"}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        api_key = request.headers.get("X-API-Key")
        if not api_key or not is_valid_api_key(api_key):
            return JSONResponse(
                {"detail": "Geçersiz veya eksik API Key. X-API-Key başlığı gereklidir."},
                status_code=401
            )
        return await call_next(request)


def main():
    parser = argparse.ArgumentParser(description="Göktürkçe MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Taşıma protokolü: 'stdio' (Claude Desktop için) veya 'streamable-http' / 'sse' (HTTP mod)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP sunucusu dinleme adresi")
    parser.add_argument("--port", type=int, default=8001, help="HTTP sunucusu port numarası")
    args = parser.parse_args()

    if args.transport in ("streamable-http", "sse"):
        import uvicorn
        if args.transport == "streamable-http":
            app = mcp.streamable_http_app()
        else:
            app = mcp.sse_app()
        app.add_middleware(APIKeyAuthMiddleware)
        print(f"Göktürkçe MCP HTTP Sunucusu Başlatılıyor ({args.transport}): http://{args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
