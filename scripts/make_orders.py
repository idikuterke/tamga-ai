import json, os

orders = [
    {
        "order_id": "ISIM-01-AYSE",
        "musteri": "Ayşe",
        "segment": "kuyumcu",
        "metin": "ayşe",
        "mode": "modern",
        "transliterasyon": "Ayşe",
        "anlam": "Dirlik içinde yaşayan, huzurlu",
        "kaynak": "Modern İsimler — Göktürkçe Birebir Yazım",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "İsim örneği modern harf-harf eşleme ile ses kaybı olmaksızın '𐰀𐰖𐱁𐰀' olarak yazılmıştır.",
            "Kalın 'y' (𐰖) ve nötr 'ş' (𐱁) damgaları kullanılmıştır.",
            "Geleneksel Orhun kuralında ilk hece ünlüsü 'a' düşürülerek '𐰖𐱁𐰀' biçiminde de karşılanabilir."
        ]
    },
    {
        "order_id": "ISIM-02-MEHMET",
        "musteri": "Mehmet",
        "segment": "kuyumcu",
        "metin": "mehmet",
        "mode": "modern",
        "transliterasyon": "Mehmet",
        "anlam": "Övülmüş, methedilmiş",
        "kaynak": "Modern İsimler — Göktürkçe Birebir Yazım",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "Eski Türkçede 'h' sesi bulunmadığı için fonetik karşılık olarak ön damak ince 'k' (𐰚) damgası kullanılmıştır (𐰢𐰀𐰚𐰢𐰀𐱅).",
            "İnce sıra ünlü ve ünsüz uyumu (m_nopolar, k_front, t_front) gözetilmiştir.",
            "Geleneksel Türk dillerindeki özleşmiş okunuş 'Mamet' ya da 'Mekmet' şeklindedir."
        ]
    },
    {
        "order_id": "ISIM-03-ZEYNEP",
        "musteri": "Zeynep",
        "segment": "kuyumcu",
        "metin": "zeynep",
        "mode": "modern",
        "transliterasyon": "Zeynep",
        "anlam": "Değerli taşlar, süs",
        "kaynak": "Modern İsimler — Göktürkçe Birebir Yazım",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "İsim örneği modern harf-harf eşleme ile '𐰔𐰀𐰘𐰤𐰀𐰯' olarak yazılmıştır.",
            "İnce 'y' (𐰘) ve ince 'n' (𐰤) damgaları ile ince sıra ünlü uyumu sağlanmıştır.",
            "Geleneksel Orhun yazıt kuralında '𐰔𐰘𐰤𐰯' biçiminde kapalı hece tasarrufuyla da yazılabilir."
        ]
    },
    {
        "order_id": "ISIM-04-EMIR",
        "musteri": "Emir",
        "segment": "kuyumcu",
        "metin": "emir",
        "mode": "modern",
        "transliterasyon": "Emir",
        "anlam": "Buyruk veren, bey, önder",
        "kaynak": "Modern İsimler — Göktürkçe Birebir Yazım",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "İsim örneği modern harf-harf eşleme ile ses kaybı olmaksızın '𐰀𐰢𐰃𐰼' olarak yazılmıştır.",
            "İnce 'r' (𐰼) damgası kullanılarak ön damak uyumu muhafaza edilmiştir.",
            "Geleneksel Orhun yazıt kuralında kapalı heceler '𐰢𐰼' şeklinde kısaltılabilir."
        ]
    },
    {
        "order_id": "KLASIK-01-BENGU",
        "musteri": "Klasikler Koleksiyonu",
        "segment": "dovme",
        "metin": "𐰋𐰭𐰏𐰇",
        "already_gokturk": True,
        "transliterasyon": "Beŋgü (Bengü)",
        "anlam": "Sonsuzluk, Ebediyet, Ölümsüzlük",
        "kaynak": "Kül Tigin, Bilge Kağan ve Tonyukuk Yazıtları ('Bengü Taş')",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "Kitabelerdeki orijinal yazım: '𐰋𐰭𐰏𐰇' (B - Ŋ - G - Ü).",
            "Eski Türkçede ilk hecedeki düz-geniş ünlü 'e' kural gereği yazılmamış, ince 'b' (𐰋) damgasının doğası gereği okunmuştur.",
            "Sağır nun (𐰭) ve ince 'g' (𐰏) damgaları birleşimiyle 'ebediyet/sonsuzluk' kavramını simgeler.",
            "Modern harf-harf yazım alternatifi: '𐰋𐰀𐰭𐰏𐰇'."
        ]
    },
    {
        "order_id": "KLASIK-02-ALP",
        "musteri": "Klasikler Koleksiyonu",
        "segment": "dovme",
        "metin": "𐰞𐰯",
        "already_gokturk": True,
        "transliterasyon": "Alp",
        "anlam": "Cesaret, Yiğitlik, Kahraman Savaşçı",
        "kaynak": "Orhun Yazıtları ve Eski Türk Destanları (Alp Er Tunga)",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 40,
        "letter_spacing_em": 0.08,
        "skip_ai_verify": True,
        "rule_notes": [
            "Kitabelerdeki özgün yazım: '𐰞𐰯' (L - P).",
            "Kelime başındaki kısa 'a' sesi kalın 'l' (𐰞) damgasının ses değeri içinde erir ve yazılmaz.",
            "Türk epigrafisinde cesaret, metanet ve savaşçı ruhu temsil eden en köklü unvandır.",
            "Modern harf-harf yazım alternatifi: '𐰀𐰞𐰯'."
        ]
    },
    {
        "order_id": "KITABE-01-TONYUKUK",
        "musteri": "Tonyukuk Koleksiyonu",
        "segment": "dovme",
        "metin": "𐰴𐰆𐰺𐰴𐰢𐰑𐰢𐰕⁚𐰾𐰇𐰭𐰇𐰱𐰓𐰇𐰢𐰕",
        "already_gokturk": True,
        "transliterasyon": "Qorqmadımız, süŋüşdümüz!",
        "anlam": "Korkmadık, savaştık (vuruştuk)!",
        "kaynak": "Tonyukuk Yazıtı (Güneybatı Yüzü, Satır 17)",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 36,
        "letter_spacing_em": 0.07,
        "skip_ai_verify": True,
        "rule_notes": [
            "Tonyukuk'un düşmanın sayısal üstünlüğüne karşı beylerine verdiği o meşhur cesaret nutkundan orijinal alıntı.",
            "𐰴𐰆𐰺𐰴𐰢𐰑𐰢𐰕 (Qorqmadımız): Kalın 'q', 'r', 'd' damgalarıyla kalın sıra ünlü uyumu mükemmel şekilde korunmuştur.",
            "Kelime ayracı (⁚): Yazıtlardaki çift nokta geleneksel damga ayırıcıdır.",
            "𐰾𐰇𐰭𐰇𐰱𐰓𐰇𐰢𐰕 (Süŋüşdümüz): İnce damgalar (s, ü, ng, ç, d, m, z) ile savaşma ve direnme eylemi ifade edilmiştir."
        ]
    },
    {
        "order_id": "KITABE-02-KULTIGIN",
        "musteri": "Kül Tigin & Bilge Kağan Koleksiyonu",
        "segment": "dovme",
        "metin": "𐱅𐰃𐰕𐰠𐰃𐰏𐰃𐰏⁚𐰾𐰇𐰚𐰇𐰼𐱅𐰇𐰢𐰕⁚𐰉𐰱𐰞𐰍𐰃𐰍⁚𐰘𐰇𐰚𐰇𐰤𐰓𐰇𐰼𐱅𐰇𐰢𐰕",
        "already_gokturk": True,
        "transliterasyon": "Tizligig sökürtümüz, başlıgıg yükündürtümüz.",
        "anlam": "Dizliye diz çöktürdük, başlıya baş eğdirdik!",
        "kaynak": "Kül Tigin Doğu 2 / Bilge Kağan Doğu 2",
        "font": "Gokturk-Regular.ttf",
        "yukseklik_mm": 30,
        "letter_spacing_em": 0.06,
        "skip_ai_verify": True,
        "rule_notes": [
            "Türk Kağanlığı'nın cihan hakimiyeti ve yenilmezlik ülküsünün kitabelerdeki en görkemli ifadesidir.",
            "𐱅𐰃𐰕𐰠𐰃𐰏𐰃𐰏 (Tizligig): İnce damga dizisi ('dizliye').",
            "𐰾𐰇𐰚𐰇𐰼𐱅𐰇𐰢𐰕 (Sökürtümüz): 'Diz çöktürdük' fiilinin çoğul geçmiş zaman biçimi.",
            "𐰉𐰱𐰞𐰍𐰃𐰍 (Başlıgıg): Kalın damgalarla 'başlıya, mağrur düşmana' hitabı.",
            "𐰘𐰇𐰚𐰇𐰤𐰓𐰇𐰼𐱅𐰇𐰢𐰕 (Yükündürtümüz): 'Baş eğdirdik, boyun eğdirdik' zafer mühürü."
        ]
    }
]

os.makedirs('siparisler', exist_ok=True)
for o in orders:
    oid = o['order_id']
    p = f"siparisler/{oid}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=2)
    print("Yazıldı:", p)
