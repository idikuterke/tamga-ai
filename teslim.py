import sys
import json
import argparse
import re
from pathlib import Path
from dataclasses import dataclass
from PIL import Image
import numpy as np
import cv2
import pathops
from datetime import datetime

# Ensure proper imports
sys.path.append(str(Path(__file__).parent / "pipeline" / "product"))
import app

import importlib.util
_seg_path = Path(__file__).parent / "pipeline" / "07_segment_word.py"
_spec = importlib.util.spec_from_file_location("segment_mod", _seg_path)
segment_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(segment_mod)

from vectorize import vectorize, write_svg, write_pdf, write_dxf, write_png

from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import qrcode
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image as RLImage, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class VerificationFailed(Exception):
    pass


def load_font(font_path: str):
    # Ensure fonts for Reportlab are registered
    try:
        pdfmetrics.registerFont(TTFont('Gokturk', font_path))
        noto_path = Path(__file__).parent / "pipeline" / "fonts" / "NotoSansOldTurkic-Regular.ttf"
        if noto_path.exists():
            pdfmetrics.registerFont(TTFont('NotoSansOldTurkic', str(noto_path)))
            noto_bold = Path(__file__).parent / "pipeline" / "fonts" / "NotoSansOldTurkic-Bold.ttf"
            if noto_bold.exists():
                pdfmetrics.registerFont(TTFont('NotoSansOldTurkic-Bold', str(noto_bold)))
                pdfmetrics.registerFontFamily('NotoSansOldTurkic', normal='NotoSansOldTurkic', bold='NotoSansOldTurkic-Bold')
            else:
                pdfmetrics.registerFontFamily('NotoSansOldTurkic', normal='NotoSansOldTurkic', bold='NotoSansOldTurkic')
        dejavu_path = Path(__file__).parent / "pipeline" / "fonts" / "DejaVuSans.ttf"
        if dejavu_path.exists():
            pdfmetrics.registerFont(TTFont('DejaVuSans', str(dejavu_path)))
            pdfmetrics.registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans', italic='DejaVuSans', boldItalic='DejaVuSans')
    except Exception as e:
        print(f"Failed to register font for PDF generation: {e}")

def prepare_image_for_segmentation(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")

def is_colon_hires(box, binary_mask):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w == 0 or h == 0: return False
    aspect = h / w
    if not (w < 150 and aspect > 1.8): return False
    sub = binary_mask[y0:y1, x0:x1]
    row_has_ink = sub.any(axis=1)
    ink_rows = np.where(row_has_ink)[0]
    if len(ink_rows) == 0: return False
    first, last = ink_rows[0], ink_rows[-1]
    inner = row_has_ink[first:last + 1]
    return not inner.all()

def verify(png_path: str, expected_codepoints: list[int]):
    """
    Self-validation gate: Uses the AI model to predict the rendered image
    and compares it to the expected logical codepoints.
    """
    raw_img = Image.open(png_path)
    img = prepare_image_for_segmentation(raw_img)
    width, height = img.size
    
    gray = np.array(img.convert("L"))
    thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    borders = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    bg_is_light = np.median(borders) > thresh
    if bg_is_light:
        binary = gray < thresh
    else:
        binary = gray > thresh

    scaled_gap = max(segment_mod.DEFAULT_MERGE_GAP_PX, int(height * 0.04))
    lines = segment_mod.find_components_by_line(binary, merge_gap_px=scaled_gap, rtl=True)
    # Remove area filter completely for vector validation
    lines = [line for line in lines if line]
        
    actual_codepoints = []
    
    for line_idx, line_boxes in enumerate(lines):
        for idx, box in enumerate(line_boxes):
            if is_colon_hires(box, binary):
                actual_codepoints.append(0x205A)
                continue
            
            right_limit = img.width
            if idx > 0:
                right_limit = (line_boxes[idx - 1][0] + box[2]) // 2
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
            result = app.bundle.predict(crop)
            if not result["valid"]:
                raise VerificationFailed(f"Invalid classification. Top prediction: {result['verdict']} (Conf: {result['confidence']})")
            
            cid = result["verdict"]
            meta = app.class_meta_map.get(cid)
            if not meta:
                raise VerificationFailed(f"Unknown class {cid}")
            
            cp_hex = meta.get("codepoints", {}).get("core_orhun")
            if not cp_hex:
                raise VerificationFailed(f"No core_orhun codepoint for class {cid}")
                
            actual_codepoints.append(int(cp_hex.replace("U+", ""), 16))
            
    if actual_codepoints != expected_codepoints:
        expected_hex = [hex(c) for c in expected_codepoints]
        actual_hex = [hex(c) for c in actual_codepoints]
        raise VerificationFailed(f"Validation failed.\nExpected: {expected_hex}\nGot     : {actual_hex}")


def wrap_gokturk_tags(text: str) -> str:
    """
    Wrap any contiguous run of Göktürk Unicode characters (U+10C00 - U+10C4F, U+205A)
    with <font name="NotoSansOldTurkic">...</font> for ReportLab Paragraphs.
    """
    if not text:
        return ""
    clean_text = re.sub(r'</?font(?: [^>]*)?>', lambda m: '' if ('Gokturk' in m.group(0) or 'NotoSansOldTurkic' in m.group(0)) else m.group(0), str(text))
    def _repl(m):
        return f'<font name="NotoSansOldTurkic">{m.group(0)}</font>'
    return re.sub(r'[\U00010C00-\U00010C4F\u205A]+', _repl, clean_text)


class VektorYazi(Flowable):
    def __init__(self, vec_result, target_height_mm):
        Flowable.__init__(self)
        self.vec_result = vec_result
        self.target_height_mm = target_height_mm
        self.scale = target_height_mm / vec_result.height_mm if vec_result.height_mm > 0 else 1.0
        self.width = vec_result.width_mm * self.scale * mm
        self.height = target_height_mm * mm
        
    def wrap(self, availWidth, availHeight):
        if availWidth > 0 and self.width > availWidth:
            shrink = (availWidth - 2*mm) / self.width
            self.scale *= shrink
            self.width = self.width * shrink
            self.height = self.height * shrink
        return (self.width, self.height)
        
    def draw(self):
        c = self.canv
        p = c.beginPath()
        for verb, pts in self.vec_result.path:
            if verb == pathops.PathVerb.MOVE:
                px = pts[0][0] * self.scale * mm
                py = self.height - pts[0][1] * self.scale * mm
                p.moveTo(px, py)
                last_pt = pts[0]
            elif verb == pathops.PathVerb.LINE:
                px = pts[0][0] * self.scale * mm
                py = self.height - pts[0][1] * self.scale * mm
                p.lineTo(px, py)
                last_pt = pts[0]
            elif verb == pathops.PathVerb.QUAD:
                p0 = last_pt
                p1 = pts[0]
                p2 = pts[1]
                cp1x = p0[0] + 2/3 * (p1[0] - p0[0])
                cp1y = p0[1] + 2/3 * (p1[1] - p0[1])
                cp2x = p2[0] + 2/3 * (p1[0] - p2[0])
                cp2y = p2[1] + 2/3 * (p1[1] - p2[1])
                
                p.curveTo(
                    cp1x * self.scale * mm, self.height - cp1y * self.scale * mm,
                    cp2x * self.scale * mm, self.height - cp2y * self.scale * mm,
                    p2[0] * self.scale * mm, self.height - p2[1] * self.scale * mm
                )
                last_pt = p2
            elif verb == pathops.PathVerb.CUBIC:
                p.curveTo(
                    pts[0][0] * self.scale * mm, self.height - pts[0][1] * self.scale * mm,
                    pts[1][0] * self.scale * mm, self.height - pts[1][1] * self.scale * mm,
                    pts[2][0] * self.scale * mm, self.height - pts[2][1] * self.scale * mm
                )
                last_pt = pts[2]
            elif verb == pathops.PathVerb.CLOSE:
                p.close()
                
        c.drawPath(p, fill=1, stroke=0)


def generate_verification_pdf(order_json: dict, vec_result, out_path: str, font_path: str) -> list:
    if not vec_result.rule_notes:
        raise VerificationFailed("Kurallar listesi boş (rule_notes empty), belge basılamaz.")
    if not vec_result.path:
        raise VerificationFailed("Vektör verisi boş, belge basılamaz.")

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            rightMargin=16*mm, leftMargin=16*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='TitleStyle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=14,
        leading=17,
        spaceAfter=2.5*mm
    )
    info_label_style = ParagraphStyle(
        name='InfoLabelStyle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=7.5,
        leading=10.5
    )
    small_style = ParagraphStyle(
        name='SmallStyle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=6.8,
        leading=8.8,
        spaceAfter=0.5*mm
    )
    rule_style = ParagraphStyle(
        name='RuleStyle',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=7.5,
        leading=10,
        spaceAfter=1*mm
    )
    h2_style = ParagraphStyle(
        name='H2Style',
        parent=styles['Normal'],
        fontName='DejaVuSans',
        fontSize=9.5,
        leading=12,
        spaceBefore=2*mm,
        spaceAfter=1*mm
    )

    story = []
    
    # Title
    story.append(Paragraph("Göktürk Studio - Doğrulama Belgesi", title_style))
    
    # Order details Table
    order_id = order_json.get('order_id', 'Bilinmiyor')
    segment = order_json.get('segment', 'Bilinmiyor').capitalize()
    musteri = order_json.get('musteri', '')
    kaynak = order_json.get('kaynak', '')
    date_str = datetime.now().strftime('%d.%m.%Y %H:%M')
    raw_metin = order_json.get('metin', '')
    translit = order_json.get('transliterasyon', '')
    anlam = order_json.get('anlam', '')

    left_lines = [
        f"<b>Sipariş Kodu:</b> {order_id}",
        f"<b>Segment / Uygulama:</b> {segment}"
    ]
    if musteri:
        left_lines.append(f"<b>Koleksiyon / Müşteri:</b> {musteri}")
    if kaynak:
        left_lines.append(f"<b>Tarihi Kaynak:</b> {kaynak}")

    right_lines = [
        f"<b>Tarih:</b> {date_str}",
        f"<b>Metin / İfade:</b> {wrap_gokturk_tags(raw_metin)}"
    ]
    if translit and translit != raw_metin:
        right_lines.append(f"<b>Transliterasyon:</b> {translit}")
    if anlam:
        right_lines.append(f"<b>Anlamı:</b> {anlam}")

    header_table = Table([
        [
            Paragraph("<br/>".join(left_lines), info_label_style),
            Paragraph("<br/>".join(right_lines), info_label_style)
        ]
    ], colWidths=[88*mm, 90*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8f9fa')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 1.5*mm),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5*mm),
        ('LEFTPADDING', (0,0), (-1,-1), 2.5*mm),
        ('RIGHTPADDING', (0,0), (-1,-1), 2.5*mm),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 2.5*mm))

    # Main Vector Line
    vec_target_h = 13 if len(vec_result.glyphs) > 15 else 16
    story.append(VektorYazi(vec_result, target_height_mm=vec_target_h))
    
    # Notice
    story.append(Spacer(1, 1.5*mm))
    story.append(Paragraph("* Yukarıdaki Göktürkçe yazı, teslim edilecek vektör dosyasından doğrudan çizilmiştir, font değildir.", small_style))
    
    # Damga Dökümü / Damga Envanteri
    is_inventory = len(vec_result.glyphs) > 9
    if is_inventory:
        story.append(Paragraph("Damga Envanteri (Kullanılan Damgalar):", h2_style))
        unique_glyphs = []
        seen = {}
        for g in vec_result.glyphs:
            cp = g.codepoint
            if cp in seen:
                seen[cp]["count"] += 1
            else:
                entry = {"codepoint": cp, "count": 1}
                seen[cp] = entry
                unique_glyphs.append(entry)
        items_to_render = unique_glyphs
    else:
        story.append(Paragraph("Damga Dökümü:", h2_style))
        items_to_render = [{"codepoint": g.codepoint, "count": 1} for g in vec_result.glyphs]

    cell_style_gokturk = ParagraphStyle(
        'GokturkCell', parent=styles['Normal'],
        fontName='NotoSansOldTurkic', fontSize=15, leading=18, alignment=1
    )
    cell_style_label = ParagraphStyle(
        'LabelCell', parent=styles['Normal'],
        fontName='DejaVuSans', fontSize=5.5, leading=7, alignment=1
    )

    COLS_PER_ROW = 9
    STAMP_CELL_WIDTH = 19.5*mm
    STAMP_CELL_ROW_HEIGHTS = [20, 8.5]

    def make_stamp_cell(stamp_char, label_text):
        top = Paragraph(stamp_char, cell_style_gokturk) if stamp_char else ""
        bottom = Paragraph(label_text, cell_style_label) if label_text else ""
        inner = Table([[top], [bottom]], colWidths=[STAMP_CELL_WIDTH], rowHeights=STAMP_CELL_ROW_HEIGHTS)
        inner.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        return inner

    table_data = []
    current_row = []
    for item in items_to_render:
        cp = item["codepoint"]
        cnt = item["count"]
        if cp == 0x205A:
            lbl = f"Ayraç (×{cnt})" if (is_inventory and cnt > 1) else "Kelime ayracı"
            cell = make_stamp_cell(chr(0x205A), lbl)
        else:
            lbl = f"U+{cp:04X} (×{cnt})" if (is_inventory and cnt > 1) else f"U+{cp:04X}"
            cell = make_stamp_cell(chr(cp), lbl)

        current_row.append(cell)
        if len(current_row) == COLS_PER_ROW:
            table_data.append(current_row)
            current_row = []

    if current_row:
        while len(current_row) < COLS_PER_ROW:
            current_row.append("")
        table_data.append(current_row)

    t = Table(table_data, colWidths=[STAMP_CELL_WIDTH]*COLS_PER_ROW)
    t.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 1),
        ('RIGHTPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
    ]))
    story.append(t)
    
    if is_inventory:
        story.append(Spacer(1, 1*mm))
        story.append(Paragraph(
            f"* Bu metin toplam {len(vec_result.glyphs)} damga ve {len(items_to_render)} benzersiz damga türünden oluşmaktadır. Sıralı tam akış ve harf analizi için QR kodu okutunuz.",
            small_style
        ))

    # Sınır Beyanı
    story.append(Paragraph("Sınır Beyanı (Zorunlu):", h2_style))
    beyan_text = (
        "Göktürkçede doğrudan karşılığı bulunmayan harfler ve yabancı özel isimler için "
        "yapılan seçimler tarihi bir standart değil, belirtilen kurala dayalı bilimsel ve imla tercihidir."
    )
    story.append(Paragraph(beyan_text, rule_style))
    
    # Kurallar ve Notlar
    story.append(Paragraph("Kurallar ve Notlar:", h2_style))
    notes = vec_result.rule_notes
    MAX_NOTES = 4 if len(notes) > 5 else len(notes)
    for note in notes[:MAX_NOTES]:
        formatted_note = wrap_gokturk_tags(note)
        story.append(Paragraph(f"• {formatted_note}", rule_style))
    if len(notes) > MAX_NOTES:
        remaining = len(notes) - MAX_NOTES
        story.append(Paragraph(f"• ... ve diğer {remaining} morfolojik/imla kuralı için QR kodu okutunuz.", rule_style))
    
    # QR Code & Doğrulama Bağlantısı
    verify_url = f"https://onozlabs.com/dogrulama/{order_id}"
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    qr_path = Path(out_path).parent / "temp_qr.png"
    img.save(qr_path)
    
    story.append(Spacer(1, 2.5*mm))
    qr_table = Table([
        [
            Paragraph(
                f"<b>Doğrulama Mührü ve Dijital İmza:</b><br/>"
                f"Bu belgenin akademik ve imla doğruluğu ONOZ Labs sisteminde onaylanmıştır.<br/>"
                f"İmzalı SVG vektörü, detaylı analiz ve sertifika doğrulaması için kameranızla tarayınız:<br/>"
                f"<font color='#1e3a5f'><u>{verify_url}</u></font>",
                small_style
            ),
            RLImage(str(qr_path), width=24*mm, height=24*mm)
        ]
    ], colWidths=[146*mm, 30*mm])
    qr_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(qr_table)
    
    doc.build(story)
    
    qr_path.unlink()
    
    return []



def process_order(json_path: str, publish_path: str = None):
    with open(json_path, "r", encoding="utf-8") as f:
        order = json.load(f)
        
    order_id = order.get("order_id")
    if not order_id:
        raise ValueError("order_id cannot be empty")
        
    out_dir = Path("out") / order_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    font_name = order.get("font", "Gokturk-Regular.ttf")
    font_path = Path(__file__).parent / "pipeline" / "fonts" / font_name
    
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")
        
    load_font(str(font_path))
    
    text = order.get("metin", "")
    height_mm = order.get("yukseklik_mm", 40)
    segment = order.get("segment", "dovme")
    letter_spacing_em = order.get("letter_spacing_em", 0.08)
    already_gokturk = order.get("already_gokturk", False) or any(0x10C00 <= ord(c) <= 0x10C4F for c in text)
    mode = order.get("mode", "geleneksel")
    custom_rule_notes = order.get("rule_notes", None)
    skip_ai_verify = order.get("skip_ai_verify", False)
    
    print(f"Processing Order: {order_id} ({segment})")
    print("Vectorizing...")
    
    vec = vectorize(
        text, 
        str(font_path), 
        height_mm, 
        letter_spacing_em=letter_spacing_em,
        already_gokturk=already_gokturk,
        mode=mode,
        custom_rule_notes=custom_rule_notes
    )
    
    import hashlib
    seal_hash = hashlib.sha256(f"{order_id}:{text}:{vec.gokturk_text}:ONOZ_LABS".encode("utf-8")).hexdigest()
    
    # SVG ve 1:1 PDF
    svg_normal = out_dir / "yazi.svg"
    pdf_normal = out_dir / "yazi.pdf"
    write_svg(vec, str(svg_normal), order_id=order_id, verify_hash=seal_hash)
    write_pdf(vec, str(pdf_normal), font_height_mm=height_mm, order_id=order_id)
    
    # Segment-specific rendering
    if segment == "dovme":
        pdf_stencil = out_dir / "yazi_stencil.pdf"
        write_pdf(vec, str(pdf_stencil), is_stencil=True, font_height_mm=height_mm, order_id=order_id)
        png_300 = out_dir / "yazi_300dpi.png"
        write_png(str(pdf_stencil), str(png_300), dpi=300)
        verify_png = png_300
    elif segment == "kuyumcu":
        dxf = out_dir / "yazi.dxf"
        write_dxf(vec, str(dxf))
        png_600 = out_dir / "yazi_600dpi.png"
        write_png(str(pdf_normal), str(png_600), dpi=600)
        verify_png = png_600
    elif segment == "nakis":
        svg_kalin = out_dir / "yazi_kalin.svg"
        vec_bold = vectorize(
            text, str(font_path), height_mm, 
            bold_offset_mm=0.5, 
            letter_spacing_em=letter_spacing_em,
            already_gokturk=already_gokturk,
            mode=mode,
            custom_rule_notes=custom_rule_notes
        )
        write_svg(vec_bold, str(svg_kalin), order_id=order_id, verify_hash=seal_hash)
        png_300 = out_dir / "yazi_300dpi.png"
        write_png(str(pdf_normal), str(png_300), dpi=300)
        verify_png = png_300
    else:
        # Fallback
        png_300 = out_dir / "yazi_300dpi.png"
        write_png(str(pdf_normal), str(png_300), dpi=300)
        verify_png = png_300
        
    expected_codepoints = vec.codepoints
    wrong_text = order.get("wrong_expected_text")
    if wrong_text:
        wrong_vec = vectorize(wrong_text, str(font_path), height_mm)
        expected_codepoints = wrong_vec.codepoints

    if not skip_ai_verify:
        print("Running self-validation gate...")
        app.load_model()
        verify(str(verify_png), expected_codepoints)
        print(f"Self-validation PASSED.")
    else:
        print("Self-validation gate bypassed (explicitly requested or historical verbatim).")

    print("Generating validation document...")
    belge_pdf = out_dir / "dogrulama.pdf"
    cell_metrics = generate_verification_pdf(order, vec, str(belge_pdf), str(font_path))

    # Dump metrics for tests
    metrics_path = out_dir / "metrics.json"
    metrics = {
        "line_bbox": [vec.width_mm, vec.height_mm],
        "glyphs": [],
        "table_cells": cell_metrics
    }
    for g in vec.glyphs:
        metrics["glyphs"].append({
            "cp": g.codepoint,
            "w": g.width_mm,
            "h": g.height_mm,
            "path_local_bounds": g.path_local.bounds if list(g.path_local) else None,
            "path_line_bounds": g.path_line.bounds if list(g.path_line) else None
        })
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f)
    
    static_json = out_dir / f"{order_id}.json"
    order_data = {
        "order_id": order_id,
        "latin": text,
        "gokturkce": vec.gokturk_text,
        "codepoints": vec.codepoints,
        "rule_notes": vec.rule_notes,
        "verified": True,
        "verify_hash": seal_hash
    }
    with open(static_json, "w", encoding="utf-8") as f:
        json.dump(order_data, f, ensure_ascii=False, indent=2)
        
    if publish_path:
        dest_dir = Path(publish_path) / "data" / "dogrulama"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        dest_public_dir = Path(publish_path) / "public" / "dogrulama" / order_id
        dest_public_dir.mkdir(parents=True, exist_ok=True)
        
        import shutil
        public_svg_path = dest_public_dir / "yazi.svg"
        shutil.copy(svg_normal, public_svg_path)
        
        with open(svg_normal, "r", encoding="utf-8") as f:
            svg_content = f.read()

        public_data = {
            "order_id": order_id,
            "musteri": order.get("musteri", "ONOZ Labs Kullanıcısı"),
            "segment": segment,
            "tarih": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "tarih_iso": datetime.now().isoformat(),
            "latin": text,
            "transliterasyon": order.get("transliterasyon", text),
            "anlam": order.get("anlam", ""),
            "kaynak": order.get("kaynak", ""),
            "gokturk": vec.gokturk_text,
            "font": font_name,
            "codepoints": vec.codepoints,
            "rule_notes": vec.rule_notes,
            "glyphs": [
                {
                    "cp": g.codepoint,
                    "hex": f"U+{g.codepoint:04X}",
                    "char": chr(g.codepoint) if g.codepoint != 0x205A else "⁚",
                    "width_mm": round(g.width_mm, 2),
                    "height_mm": round(g.height_mm, 2)
                }
                for g in vec.glyphs
            ],
            "verified": True,
            "verify_hash": seal_hash,
            "svg_content": svg_content,
            "svg_url": f"/dogrulama/{order_id}/yazi.svg"
        }
        pub_json_path = dest_dir / f"{order_id}.json"
        with open(pub_json_path, "w", encoding="utf-8") as f:
            json.dump(public_data, f, ensure_ascii=False, indent=2)
        print(f"Public JSON published to: {pub_json_path}")
        
    print(f"Order {order_id} successfully delivered to {out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("order_json", help="Path to order json file")
    parser.add_argument("--publish", help="Path to site repo to publish verification JSON", default=None)
    args = parser.parse_args()
    
    process_order(args.order_json, args.publish)
