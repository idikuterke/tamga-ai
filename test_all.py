import os
import json
import subprocess

tests = [
    # (id, text, font, segment, spacing, expect_fail, wrong_expected_text)
    ("ODR-01", "kıldı", "Gokturk-Regular.ttf", "kuyumcu", 0.08, False, None),
    ("ODR-02", "körküt", "Gokturk-Orkun-Regular.ttf", "nakis", 0.08, False, None),
    ("ODR-03", "bodun altay kiçe", "Gokturk-Regular.ttf", "dovme", 0.08, False, None),
    ("ODR-04", "tengri teg tengride bolmış türk bilge kagan", "Gokturk-Regular.ttf", "dovme", 0.08, False, None),
    ("BOZUK-TEST-1", "körküt", "Gokturk-Regular.ttf", "dovme", -0.5, True, None), # geometric overlap failure
    ("BOZUK-TEST-2", "bodun", "Gokturk-Regular.ttf", "dovme", 0.08, True, "badun") # semantic failure
]

os.makedirs("siparisler", exist_ok=True)

for tid, text, font, seg, spacing, expect_fail, wrong_text in tests:
    j = {
        "order_id": tid,
        "musteri": "Test",
        "segment": seg,
        "metin": text,
        "font": font,
        "yukseklik_mm": 40,
        "letter_spacing_em": spacing
    }
    if wrong_text:
        j["wrong_expected_text"] = wrong_text
        
    path = f"siparisler/{tid}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False)
    
    print(f"--- RUNNING TEST {tid} ---")
    res = subprocess.run(["python", "teslim.py", path], capture_output=True)
    stdout = res.stdout.decode('utf-8', errors='replace')
    stderr = res.stderr.decode('utf-8', errors='replace')
    
    if expect_fail:
        if "VerificationFailed" in stderr or res.returncode != 0:
            print(f"SUCCESS (Negative Test Caught Error): {tid} failed as expected.")
        else:
            print(f"FATAL: Negative test {tid} PASSED validation but was expected to FAIL!")
            print(stdout)
            print(stderr)
            exit(1)
    else:
        if res.returncode != 0:
            print(f"FAILED: {tid}")
            try:
                print(stderr)
                print(stdout)
            except UnicodeEncodeError:
                print("Could not print stderr/stdout due to encoding.")
        else:
            # Platypus Doğrulama PDF'ini kontrol et
            pdf_path = f"out/{tid}/dogrulama.pdf"
            if os.path.exists(pdf_path):
                import fitz
                doc = fitz.open(pdf_path)
                
                # Check 1: Ana satırın vektörü var mı? (Drawings içinde mi?)
                has_vector = False
                stamp_label_count = 0
                for page in doc:
                    drawings = page.get_drawings()
                    if drawings:
                        # Ana vektörler büyük ihtimalle var. 
                        # Sadece çizimlerin boş olmadığından emin oluyoruz.
                        has_vector = True
                        
                    # Check 2: Span seviyesinde çakışma (Overlap) test
                    # NOT: get_text("blocks") yakın metinleri tek blokta birleştirir,
                    # bu yüzden damga ile altındaki etiket arasındaki çakışmayı kaçırır.
                    # Span seviyesi bu tür ince örtüşmeleri de yakalar.
                    d = page.get_text("dict")
                    spans = [s for b in d["blocks"] if b["type"] == 0
                               for l in b["lines"] for s in l["spans"]]

                    # Damga sayısı kontrolü için "U+XXXX" etiket span'larını say
                    for s in spans:
                        if s["text"].strip().startswith("U+"):
                            stamp_label_count += 1

                    OVERLAP_TOLERANCE = 0.5  # pt; kenar teması sayılmaz
                    for i, s1 in enumerate(spans):
                        for j, s2 in enumerate(spans):
                            if i >= j: continue
                            b1, b2 = s1["bbox"], s2["bbox"]
                            overlap_x = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
                            overlap_y = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
                            if overlap_x > OVERLAP_TOLERANCE and overlap_y > OVERLAP_TOLERANCE:
                                print(f"FATAL: {tid} failed! Text spans overlap on page {page.number}.")
                                print(f"Span 1: {b1} {s1['text'].encode('utf-8', 'replace')}")
                                print(f"Span 2: {b2} {s2['text'].encode('utf-8', 'replace')}")
                                exit(1)

                doc.close()
                
                if not has_vector:
                    print(f"FATAL: {tid} failed! No vector drawings found in PDF (VektorYazi failed).")
                    exit(1)
            
            # Geometrik (bbox) test
            metrics_path = f"out/{tid}/metrics.json"
            if os.path.exists(metrics_path):
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
                
                # 1. len(glyphs) == (codepoints - U+205A)
                drawn_glyphs = [g for g in metrics["glyphs"] if g["cp"] != 0x205A and g["path_local_bounds"]]
                if len(drawn_glyphs) != len([g for g in metrics["glyphs"] if g["cp"] != 0x205A]):
                    print(f"FATAL: {tid} failed! Mismatch in glyph counts vs U+205A")
                    exit(1)

                # 1b. Damga Dökümü tablosunda çizilen damga sayısı == U+205A olmayan codepoint sayısı
                expected_stamp_count = len([g for g in metrics["glyphs"] if g["cp"] != 0x205A])
                if stamp_label_count != expected_stamp_count:
                    print(f"FATAL: {tid} failed! Stamp table label count ({stamp_label_count}) != expected ({expected_stamp_count})")
                    exit(1)

                sum_area = 0
                for g in drawn_glyphs:
                    lb = g["path_local_bounds"]
                    if abs(lb[0]) > 0.01 or abs(lb[1]) > 0.01:
                        print(f"FATAL: {tid} failed! path_local min corner not (0,0): {lb}")
                        exit(1)
                    sum_area += g["w"] * g["h"]
                    
                line_area = metrics["line_bbox"][0] * metrics["line_bbox"][1]
                if sum_area > line_area + 0.1:
                    print(f"FATAL: {tid} failed! Sum of glyph areas ({sum_area}) > Line area ({line_area})")
                    exit(1)
                            
            print(f"SUCCESS: {tid} passed.")
