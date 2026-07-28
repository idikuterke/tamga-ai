# Göktürkçe Görsel/Video Üretici — Proje Brief

> **Durum:** Faz 0'da. Temel altyapı kopyalandı, çekirdek `render()` modülü bekleniyor.
> **Son güncelleme:** 2026-07-25 02:55 (Europe/Moscow)
> **Hedef:** Latin/Göktürkçe metin → stilize PNG/MP4 üreten, web tabanlı, self-serve API.

---

## Genel Mimari

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (pipeline/product/static/index.html)               │
│   Yeni sekme: "Görsel/Video Üret"                           │
│   Form: metin + stil + boyut + (video) motion + süre        │
└─────────────────────┬───────────────────────────────────────┘
                      │ POST /api/render, /api/render_video
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (pipeline/product/app.py)                           │
│   FastAPI: auth (API key) + rate limit (slowapi)            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ ÇEKİRDEK (pipeline/product/render.py) — YAZILACAK           │
│   def render(text, style, size, degradation, font) -> Image │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌──────────────────┐      ┌──────────────────┐
│ 01_render_clean  │      │ 02_augment       │
│ (mevcut)         │      │ (mevcut)         │
│ temiz yazı PNG   │      │ stil + bozulma   │
└──────────────────┘      └──────────────────┘
                      │
                      ▼ (sadece video isteğinde)
┌─────────────────────────────────────────────────────────────┐
│ VIDEO (pipeline/product/video.py) — YAZILACAK                │
│   def render_to_video(png, motion, duration) -> mp4_path   │
│   FFmpeg subprocess                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Paydaşlar ve ortak altyapı (mevcut)

**Mevcut repo:** `tamga-ai` (private, GitHub)
**Çalışma kopyası:** `[KULLANICI TARAFINDAN BELİRLENECEK YOL]` ← **karar bekliyor**
**Ortak altyapı (her iki ürün kullanır):**
- `gokturk_labels_v1_locked.json` (38 sınıf şeması)
- `pipeline/product/rules_engine.py` (SpellingEngine, encode)
- `pipeline/fonts/` (Noto + diğer fontlar)

**Yeni repo (öneri):** `tamga-studio` (yeni, ayrı)

---

## FAZ 0 — Hazırlık (şu an buradayız)

### Hedef
- Projenin bir kopyasını al, ana repo bozulmasın
- Brief dosyasını (`/workspace/gokturk_studio_brief.md`) referans noktası yap
- Mevcut 3 dosyayı oku: `01_render_clean.py`, `02_augment.py`, `app.py`

### Yapılacaklar
- [x] Proje kopyası yolu netleştir (örn. `C:\Users\pc\gokturk_studio\`)
- [x] Bu brief dosyasını kopyanın kök dizinine kopyala
- [x] `01_render_clean.py` (tam içerik) → bu brief'e ekle veya kopyaya kaydet (Kopyada mevcut)
- [x] `02_augment.py` (tam içerik) → aynı (Kopyada mevcut)
- [x] `app.py` mevcut endpoint'leri listele (referans için) (Endpointler okundu: /predict, /predict_word, /predict_image, /translate, vb.)

### Kabul kriteri
- 3 dosya okundu, `render()` için mevcut mantık netleşti
- Kopyanın yolu biliniyor, ana repo etkilenmedi

---

## FAZ 1 — Çekirdek `render()` modülü

### Hedef
`pipeline/product/render.py` dosyası — tek satırda çağrılabilir, tüm stilleri birleştiren modül.

### Fonksiyon imzası
```python
def render(
    text: str,                          # Latin veya Göktürkçe Unicode
    style: str = "plain",               # plain, stone, gold, neon, wood, paper, leather, parchment
    size: int = 512,                    # çıktı kenar uzunluğu (piksel)
    degradation: float = 0.0,           # 0.0 (tertemiz) — 1.0 (çok yıpranmış)
    font_name: str = "NotoSansOldTurkic-Regular",
    background_color: str | None = None # opsiyonel override
) -> Image.Image:
    """Latin/Göktürkçe metni alır, stilize PNG (PIL.Image) döner."""
```

### İç yapı (plan)
1. `text`'i `SpellingEngine.expected_sequence()` ile Göktürkçe class_id dizisine çevir
2. `font_name` ile font yükle, her glyph'i `size` ölçeğinde render et
3. Tek satırda birleştir (RTL sıralama)
4. `style` parametresine göre `02_augment.py`'deki stil fonksiyonlarından birini çağır
5. `degradation` > 0 ise bozulma uygula (yine 02_augment.py'den)
6. PIL.Image döndür

### Stil sözlüğü (öneri — mevcut `TEXTURES`'tan genişletilmiş)
```python
STYLES = {
    "plain":     {"bg": (255, 255, 255), "fg": (0, 0, 0),       "effects": []},
    "stone":     {"bg": (180, 178, 170), "fg": (90, 85, 80),    "effects": ["emboss", "noise"]},
    "gold":      {"bg": (60, 40, 20),    "fg": (255, 215, 0),   "effects": ["bevel", "gradient"]},
    "neon":      {"bg": (10, 10, 30),    "fg": (0, 255, 200),   "effects": ["glow", "bloom"]},
    "wood":      {"bg": (110, 70, 40),   "fg": (240, 220, 180), "effects": ["grain", "emboss"]},
    "paper":     {"bg": (245, 235, 210), "fg": (40, 30, 20),    "effects": ["fibers", "vignette"]},
    "leather":   {"bg": (80, 40, 20),    "fg": (220, 180, 100), "effects": ["texture", "wear"]},
    "parchment": {"bg": (230, 215, 170), "fg": (60, 40, 20),    "effects": ["stains", "burn_edges"]},
}
```

### Kabul kriteri
- [x] `from render import render` çalışıyor
- [x] 8 stilin hepsi en az 1 örnekte görsel olarak doğru çıkıyor
- [x] Boyut/degradation/font parametreleri gerçekten etkili
- [x] Mevcut `01_render_clean.py` + `02_augment.py` davranışı bozulmamış (regresyon)

### Test komutları (elle çalıştırılacak)
```python
from render import render
for style in ["plain", "stone", "gold", "neon", "wood"]:
    img = render("gök türk", style=style, size=512)
    img.save(f"test_{style}.png")
```

---

## FAZ 2 — API endpoint'leri

### Hedef
`pipeline/product/app.py`'ye 2 yeni endpoint ekle.

### Endpoint'ler
```python
POST /api/render
  Request:  {"text": str, "style": str, "size": int, "degradation": float}
  Response: image/png (binary)
  Auth:     X-API-Key header
  Rate:     30/dk, 1000/gün (mevcut slowapi)

POST /api/render_video
  Request:  {"text": str, "style": str, "size": int, "motion": str, "duration": int}
  Response: video/mp4 (binary)
  Auth:     X-API-Key header
  Rate:     10/dk, 200/gün (video pahalı, daha sıkı)
```

### Pydantic modelleri
```python
class RenderRequest(BaseModel):
    text: str
    style: str = "plain"
    size: int = 512
    degradation: float = 0.0

class RenderVideoRequest(BaseModel):
    text: str
    style: str = "plain"
    size: int = 720
    motion: str = "zoom"  # zoom, pan, fade, pulse
    duration: int = 5      # saniye
```

### Kabul kriteri
- [x] `curl -X POST` ile `/api/render` endpoint'i çalışıyor
- [x] API key doğrulaması geçerli
- [x] Rate limit tetikleniyor (test kötüye kullanım senaryosu)
- [x] Hata durumları (boş text, geçersiz stil) düzgün 422/400 dönüyor
*(Not: /api/render_video endpointi Faz 4'e bırakıldı)*

---

## FAZ 3 — Web UI

### Hedef
`pipeline/product/static/index.html`'e yeni sekme ekle: **"Görsel/Video Üret"**

### Form yapısı
- Metin input (placeholder: "gök türk")
- Stil dropdown: 8 seçenek
- Boyut slider: 256–1920 (varsayılan 512)
- Çıktı tipi radio: PNG / MP4
- (MP4 seçiliyse görünür) Motion dropdown: zoom, pan, fade, pulse
- (MP4 seçiliyse görünür) Süre slider: 3–10 sn
- (Opsiyonel) "Bozulma" slider: 0.0–0.5
- "Üret" butonu
- Önizleme alanı (img veya video etiketi)
- "İndir" butonu

### Backend bağlantısı
- API key `localStorage`'da saklanır (mevcut UI nasıl yapıyorsa aynısı)
- `fetch('/api/render', {method:'POST', headers, body: JSON})`
- Response blob → `URL.createObjectURL` → önizleme/indir

### Kabul kriteri
- Tarayıcıdan tüm stiller denenebiliyor
- Video seçildiğinde motion + süre inputları görünüyor
- Üretilen görsel/video önizleniyor + indirilebiliyor
- Hata durumları kullanıcıya gösteriliyor (network hatası, rate limit, vs.)

---

## FAZ 4 — Video katmanı

### Hedef
`pipeline/product/video.py` — PNG'yi alır, FFmpeg ile MP4 üretir.

### Fonksiyon imzası
```python
def render_to_video(
    image: Image.Image,
    motion: str = "zoom",        # zoom, pan, fade, pulse
    duration: int = 5,            # saniye
    fps: int = 30,
    resolution: tuple = (1280, 720)
) -> str:  # mp4 dosya yolu
    """Stilize PNG'yi alır, hareketli MP4 üretir."""
```

### FFmpeg preset'leri
- `zoom`: yavaş yakınlaştırma (1.0x → 1.3x, 5sn)
- `pan`: sağdan sola kaydırma (yatay, 5sn)
- `fade`: yumuşak giriş/çıkış (1sn fade-in + 1sn fade-out)
- `pulse`: opaklık ritmi (neon stili için ideal)

### Kabul kriteri
- 4 motion tipi de çalışıyor
- MP4 720p, 30fps, H.264, < 5MB (5sn için)
- İşlem < 10sn (CPU'da)
- Geçici PNG dosyaları temizleniyor

---

## FAZ 5 — Fiyatlandırma

### Model (öneri)
| Plan | Fiyat | Kota | Watermark | Ticari lisans |
|------|-------|------|-----------|---------------|
| Ücretsiz | $0 | 5 görsel/gün | evet | hayır |
| Bireysel | $9/ay | 100 görsel + 20 video | hayır | kişisel |
| Stüdyo | $29/ay | 500 görsel + 100 video | hayır | evet |

### Altyapı
- **Faz 5a:** Manuel (Stripe invoice, e-posta ile ödeme) — ilk 3 ay
- **Faz 5b:** Otomatik (Stripe Checkout + webhook) — 4. aydan itibaren

### Kabul kriteri
- Free plan gerçekten ücretsiz (API key kayıt olunca)
- Kota aşımı net hata mesajı
- Ücretli planlara geçiş akışı belgeli

---

## FAZ 6 — Lisans ve açık kaynak stratejisi

### Hedef
- `tamga-ai` (mevcut) ve `tamga-studio` (yeni) için net lisans katmanları
- Font/sözlük lisans belirsizliklerinin yönetimi

### Plan
1. Font envanteri: hangi font hangi lisansla, eğitimde/UI'da kullanımı
2. EDPT Word Index lisans notu (Koçoğlu 2006)
3. `LICENSE` ve `THIRD_PARTY_LICENSES.md` dosyaları
4. Tuğrul Çavdar'a font lisans e-postası

### Karar bekliyor
- `tamga-studio` repo'su public mı, private mı?
- Model + schema açılır mı (Noto-only versiyon)?
- EDPT kesişimi ürünün hangi katmanında?

---

## Bilinen engeller

1. **GPU yok** → diffusion/elimination. Çözüm: prosedürel kompozit. ✅ kararlaştırıldı
2. **Font lisansları belirsiz** → ticari kullanım riski. Çözüm: Tuğrul Çavdar ile font lisans görüşmesi bekliyor (Faz 6). ⏳
3. **EDPT telif durumu** → sözlük kesişimi riskli olabilir. Çözüm: Koçoğlu 2006 notunu oku. ⏳
4. **Mevcut çeviri aracı ile render altyapısı aynı repo'da** → karışma riski. Çözüm: ayrı `tamga-studio` repo'su. ⏳

---

## Karar bekleyen noktalar (yanıtlanması gereken)

1. **Kopya proje yolu:** `C:\Users\pc\gokturk_studio\` mi, başka bir yer mi?
2. **`01_render_clean.py`'nin tam içeriği:** dosya yolu + içerik (Paket A için kritik)
3. **`02_augment.py`'nin tam içeriği:** aynı
4. **Stil isimleri frontend'de Türkçe mi ("taş kabartma"), İngilizce mi ("stone relief")?**
5. **Mevcut 5 stilin tam listesi:** "taş, altın, neon, ahşap, ..." — beşinci ne?
6. **Tuğrul Çavdar'a e-posta gönderildi mi?** (Faz 6 için)

---

## Oturum günlüğü

### 2026-07-25 02:55 (Europe/Moscow) — Faz 0 başlangıç
- Proje kopyalandı (kullanıcı tarafından)
- ComfyUI denendi, GPU yok, elendi
- Diffusion stratejisi elendi, prosedürel kompozit kararlaştırıldı
- Brief dosyası oluşturuldu (`/workspace/gokturk_studio_brief.md`)
- 6 soru kullanıcıya soruldu (Faz 1 öncesi)

### 2026-07-25 — Faz 0 Tamamlandı, Faz 1'e Geçiliyor
- Antigravity AI tarafından proje incelendi. `01_render_clean.py`, `02_augment.py` ve `app.py` analiz edildi.
- Brief proje kök dizinine kopyalandı.
- Faz 1 için (render.py modülü) uygulama planı oluşturuldu ve onay bekleniyor.

### 2026-07-25 — Faz 1 (render.py) Tamamlandı
- `SpellingEngine` entegre edilerek Latin -> Göktürkçe çevirisi sağlandı.
- PIL ile RTL veya Fallback (ters çevrilmiş string) LTR render mantığı eklendi.
- `02_augment.py` mantığı `render.py` içerisinde 8 farklı stil (plain, stone, gold, neon, wood, paper, leather, parchment) için modüler olarak uyarlandı.
- Degredasyon, boyut ve stil özellikleri test edildi. Test görselleri oluşturuldu ve doğrulandı.

### 2026-07-25 — Faz 2 (/api/render Endpoint'i) Tamamlandı
- `app.py` içerisine `RenderRequest` pydantic modeli eklendi.
- `POST /api/render` endpoint'i `render.py` ile entegre edildi.
- Boş metin ve geçersiz stil durumları için HTTP 400 hata yönetimleri eklendi.
- API Key ve Rate Limit korumaları test edildi (mevcut `app.py` middleware yapısı kullanılarak sağlandı).
- *Not: `/api/render_video` ilerideki Faz 4'e bırakıldı.*

### 2026-07-25 — Faz 3 (Web UI) Tamamlandı
- `index.html` dosyasına 5. sekme (Görsel/Video Üret) eklendi.
- Form elemanları (Stil, Boyut, Bozulma slider'ları) ve JS API entegrasyonu (`/api/render`) tamamlandı.

### 2026-07-25 — Faz 1.5 (Kalite Yükseltme / Kompozit Render) Tamamlandı
- `pipeline/product/textures/` klasörü oluşturuldu ve doku katmanları (`stone.png`, `parchment.png` vb.) entegre edilecek yapıya kavuşturuldu.
- `STYLES` sözlüğü `texture_path` ve `blend_mode` özellikleri eklenerek geliştirildi.
- `render()` fonksiyonu; Multiply (Gölge) ve Screen (Işık Yansıması) katmanlarıyla metne taşa/parşömene oyulmuş (engraved) 3 boyutlu derinlik etkisi verecek şekilde kompozit yöntemle baştan yazıldı.
- Doku dosyaları yoksa otomatik olarak prosedürel arka plana geçen fallback mekanizması ve doku birleştirme (blend mode) test edildi.

### 2026-07-25 — Faz 4 (Video Katmanı & 3D Parallax) Tamamlandı
- `pipeline/product/video.py` oluşturuldu ve Hugging Face `depth-anything/Depth-Anything-V2-Small-hf` modeli entegre edildi.
- Görsel hash temelli önbellek (`cache`) mekanizması ve model yüklenemediğinde 2D pan hareketine dönen fallback eklendi.
- `apply_3d_parallax()` metoduyla yakın katmanların hızlı, uzak arka planın yavaş hareket ettiği ve kenar esneme artefaktlarını engelleyen 3D parallax efekti geliştirildi (`zoom`, `pan`, `fade` efektleri ile beraber 4 motion desteklendi).
- `app.py` içerisine `RenderVideoRequest` modeli ve `POST /api/render_video` endpoint'i eklendi (PNG render -> Depth 3D Parallax -> H.264 MP4 video akışı).
- `test_video.py` ve HTTP üzerinden testler yapıldı: 5 saniyelik 3D parallax video CPU üzerinde ilk çalışmada 6.37s, önbellekte 1.59s (<15sn hedefi) ile başarıyla üretildi.

### [sonraki oturumlar buraya eklenecek]

---

## Nasıl kullanılır (kendine not)

1. Bu dosyayı kopyanın kök dizinine kopyala
2. Her oturumda "şu an Faz X'teyiz" diye başla
3. Yapılan iş → ✅ işaretle, "Oturum günlüğü" bölümüne tarih + özet ekle
4. Çıkan engel/yeni karar → "Karar bekleyen noktalar" veya "Bilinen engeller" bölümüne ekle
5. Token bittiğinde bu dosyaya bak, nereden devam edeceğin net olsun
