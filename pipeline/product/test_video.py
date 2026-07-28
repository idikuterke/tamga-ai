import time
from render import render
from video import VideoRenderer

def test_video_generation():
    print("1. 'tengri' metni 'stone' stili ile PNG olarak üretiliyor...")
    t0 = time.time()
    img = render("tengri", style="stone", size=512)
    t_render = time.time() - t0
    print(f"   PNG render süresi: {t_render:.2f}s (boyut: {img.size})")

    print("2. VideoRenderer başlatılıyor ve Depth Anything V2 modeli hazırlanıyor...")
    vr = VideoRenderer()
    
    print("3. 'parallax' motion ile 5 saniyelik video üretiliyor (İlk çağrı - model yükleme dahil)...")
    t0 = time.time()
    vid_bytes = vr.render_to_video(img, motion="parallax", duration=5, fps=30)
    t_video1 = time.time() - t0
    print(f"   İlk video üretimi başarılı! Süre: {t_video1:.2f}s, Boyut: {len(vid_bytes)} bayt")
    
    # Videoyu diske kaydet
    out_path = "test_parallax_stone.mp4"
    with open(out_path, "wb") as f:
        f.write(vid_bytes)
    print(f"   Video kaydedildi: {out_path}")

    print("4. Ön bellekleme (cache) testi için ikinci kez çağrılıyor...")
    t0 = time.time()
    vid_bytes_cached = vr.render_to_video(img, motion="parallax", duration=5, fps=30)
    t_video2 = time.time() - t0
    print(f"   Önbellekten video üretimi başarılı! Süre: {t_video2:.2f}s, Boyut: {len(vid_bytes_cached)} bayt")

    assert t_video2 < 15.0, f"HATA: 5 saniyelik video 15 saniyenin üzerinde sürdü! ({t_video2:.2f}s)"
    print("\nTUM TESTLER BASARIYLA TAMAMLANDI!")

if __name__ == "__main__":
    test_video_generation()
