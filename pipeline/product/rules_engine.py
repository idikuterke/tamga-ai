"""
SEVİYE 2 — Yazım/bağlam kural motoru (orthography rule engine).

Seviye 1 (sınıflandırıcı) tek bir glyph'in HANGİ harf olduğunu söyler.
Seviye 2, bir KELİMEYİ oluşturan glyph DİZİSİNİN Türkçe ünlü uyumu
kurallarına uygun olup olmadığını kontrol eder. Bu, tek görsellerde asla
yakalanamayacak bir hata sınıfını (harf-düzeyinde doğru ama kelime-düzeyinde
tutarsız yazım) tespit etmek için gerekli.

Kural: bir kelimedeki tüm kalın/ince (back/front) etiketli harfler AYNI
kutupta olmalı. "kutupsuz" (harmony=null) harfler her iki bağlamda da
geçerlidir, ihlal sayılmaz. Ş ve EC gibi bilinen bağlam-duyarlı istisnalar
(schema'daki known_exceptions) ayrıca hiçbir zaman ihlal sayılmaz.

Bu motor Tuğrul'un çeviricisinin YERİNE geçmez — onun otoritesine karşı
KALİBRE EDİLMESİ gerekir (codepoint_authority kuralı hâlâ geçerli). Şimdilik
saf dilbilimsel kural (ünlü uyumu) olarak çalışır; ileride Tuğrul'un
çeviricisinden örnek kelimeler alınıp bu motorun çıktısıyla karşılaştırılarak
doğrulanmalı.
"""

import json
from pathlib import Path
from collections import Counter


class OrthographyRuleEngine:
    def __init__(self, schema_path):
        with open(schema_path, encoding="utf-8") as f:
            self.schema = json.load(f)
        self.class_meta = {c["id"]: c for c in self.schema["classes"]}
        self.known_exceptions = set(self.schema.get("known_exceptions", {}).keys())

    def harmony_of(self, class_id):
        meta = self.class_meta.get(class_id)
        if not meta:
            return None
        return meta.get("harmony")  # "back" | "front" | None

    def check_sequence(self, class_id_sequence):
        """
        class_id_sequence: okuma sırasına göre (RTL kaynaktan sağdan sola
        okunmuş, yani listede SOL->SAĞ mantıksal sırada) tahmin edilen
        class_id listesi. Örn: ["t_back", "vowel_a_e", "n_back", ...]

        Döner: {
          "harmony_consistent": bool,
          "dominant_harmony": "back" | "front" | None,
          "violations": [ {index, class_id, harmony, expected} ],
          "notes": [...]
        }
        """
        harmonies = []
        for idx, cid in enumerate(class_id_sequence):
            if cid in self.known_exceptions:
                continue  # bağlam-duyarlı istisna, uyum kontrolüne dahil edilmez
            h = self.harmony_of(cid)
            if h is not None:
                harmonies.append((idx, cid, h))

        if not harmonies:
            return {
                "harmony_consistent": True,
                "dominant_harmony": None,
                "violations": [],
                "notes": ["Dizide kutup taşıyan (back/front) harf yok — ünlü uyumu kontrolü uygulanamadı."],
            }

        counts = Counter(h for _, _, h in harmonies)
        dominant, _ = counts.most_common(1)[0]

        violations = [
            {"index": idx, "class_id": cid, "harmony": h, "expected": dominant}
            for idx, cid, h in harmonies
            if h != dominant
        ]

        return {
            "harmony_consistent": len(violations) == 0,
            "dominant_harmony": dominant,
            "violations": violations,
            "notes": [] if not violations else [
                f"{len(violations)} harf, dizinin baskın kutbu ({dominant}) ile uyuşmuyor — "
                f"ünlü uyumu ihlali olabilir, ya da bu bileşik/alıntı bir kelime olabilir."
            ],
        }


VOWEL_LETTERS = set("aeıioöuü")
# Latin girdide uzun ünlü işareti (āt, kōp, kūt gibi) makron ile belirtilir.
# Bu motorun kabul ettiği tek uzun-ünlü kuralı budur (bkz. rapor III.3.3);
# başka bir gösterim (örn. çift ünlü "aa") desteklenmez.
MACRON_MAP = {"ā": "a", "ē": "e", "ī": "ı", "ō": "o", "ū": "u"}
# Modern harflerin Göktürkçe karşılıkları (rapor I.2).
MODERN_LETTER_MAP = {"f": "p", "v": "b", "h": "k", "j": "ç", "c": "ç", "ğ": "g"}
# ASCII digraph -> tek ses. "tengri", "meniŋ" gibi kelimeler ŋ'yi "ng" ile
# yazabilir; bunu tek harf ŋ'ye çevirmezsek n+g olarak ayrı ayrı (yanlış)
# işlenir. Bilinen risk: "ng"/"ny" içeren ama gerçekten n+g/n+y olan
# kelimeler de yanlışlıkla ŋ/ñ'e çevrilir — nadir ama olası, İstisna
# Sözlüğü (Aşama 1) dolduruldukça buradan istisna edilebilir.
DIGRAPH_MAP = {"ng": "ŋ", "ny": "ñ"}
# "Kapalı é" — şemada ayrı bir sınıfı yok (bkz. proje notları), bu motor
# şimdilik düz 'e' gibi işler; expected_sequence/letter_by_letter_sequence
# bu ve "ng" içeren kelimelerde konsola uyarı basar (bkz. _maybe_warn_unverified).
VOWEL_ALIAS_MAP = {"é": "e"}


class SpellingEngine:
    """
    SEVİYE 2'NİN AYRI BİR KATMANI — Latin metinden BEKLENEN Göktürkçe
    class_id dizisini üretir (kodlama yönü). OrthographyRuleEngine
    (ünlü uyumu KONTROLÜ, zaten üretilmiş bir class_id dizisini
    denetler) ile KARIŞTIRILMAMALI — ikisi farklı işler yapar ve farklı
    girdiler alır.

    Uygulanan öncelik/çakışma sırası (onaylanan tabloya göre):
      0. Ön-işleme: küçük harf, modern harf dönüşümü (F/V/H/J/C/Ğ).
         İKİZ ÜNSÜZ TEKİLLEŞTİRME YOK (rapor II.4'ün aksine) — tamga.org'un
         gerçek çıktısıyla çelişiyordu ("eller" -> 𐰠𐰠𐰼 = l_front,l_front,r_front,
         iki L AYRI yazılmış, tekilleşmemiş; kaldırıldı 2026-07-21, bkz.
         feedback-gokturk-tamga-authority).
      1. İstisna sözlüğü — henüz BOŞ (v1 kapsamı), eklenirse her şeyi ezer.
      2. Hece harfi/ligatür tespiti (look-ahead, harf döngüsünden önce).
         KESİN KURAL (9 kelimelik tamga.org kanıtıyla çözüldü, 2026-07-21):
         ünlü-önce kalıplar (ok,uk,ık,ök,ük) HER pozisyonda (baş/orta/son)
         serbest, ekstra ünlü asla eklenmez. Ünsüz-önce "ko/ku/kı" SADECE
         kelime başında ligatür + ekstra ünlü; ortada/sonda yasak, düz
         harflere döner. Ünsüz-önce "kö/kü" hiçbir pozisyonda doğrudan
         ligatür olmaz (sadece dolaylı "ök/ük" olarak yakalanabilir).
         Doğrulama kelimeleri: korkut, koku, koruk, körküt, kökü, körük,
         kırkık, kıkı, kırık.
      3. Ünlü yazım/düşürme (bayrak tabanlı): kelime sonu HER ZAMAN yazılır
         (en yüksek öncelik); a/e başta/ortada HER ZAMAN atlanır (uzun-ünlü
         işareti bu kuralı ezer); aynı ünlü sınıfı ikinci kez atlanır;
         ilk hece a/e ise sonraki ı/i atlanır.
      4. Ünsüz kutupluluk ataması — BASİTLEŞTİRİLMİŞ (onay: 2026-07-20):
         SADECE en yakın önceki (yoksa sonraki) ünlünün kutbu kullanılır.
         ın/nı, sı/ıs, yı gibi tarihi yazıt istisnaları BİLEREK
         uygulanmıyor — Tuğrul Çavdar'ın (tamga.org/tamga.ktu.edu.tr)
         güncel çeviricisi bunları kullanmıyor, codepoint_authority
         ilkesiyle tutarlı olmak için motor da kullanmıyor.
      5. Ek kuralları (III.1, kök/ek sınırı gerektirir) — v1'de
         UYGULANMIYOR: ham Latin metinden güvenilir morfolojik ayrıştırma
         yapılamıyor. Kapsam dışı, ileride kök/ek sınırı elle işaretlenirse
         eklenebilir.
    """

    def __init__(self, schema_path):
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)

        self.vowel_class_map = {}        # 'a' -> 'vowel_a_e'
        self.neutral_consonant_map = {}  # 'ç' -> 'c_nopolar'
        self.polar_consonant_map = {}    # ('b','back') -> 'b_back'
        self.ligature_map = {}           # 'nd' -> 'cluster_nd'

        for c in schema["classes"]:
            cat = c.get("category")
            sounds = c.get("sound", [])
            harmony = c.get("harmony")
            cid = c["id"]
            if cat == "vowel":
                for s in sounds:
                    self.vowel_class_map[s] = cid
            elif cat == "consonant":
                if harmony is None:
                    for s in sounds:
                        self.neutral_consonant_map[s] = cid
                else:
                    for s in sounds:
                        self.polar_consonant_map[(s, harmony)] = cid
            elif cat in ("cluster", "syllable"):
                for s in sounds:
                    self.ligature_map[s] = cid

        # NOT: syllable_ok/syllable_oek/syllable_ik'in çift yönlü okunuşu
        # (ko/ku, kö/kü, ık/kı) artık şemanın "sound" alanında birebir
        # tanımlı (bkz. şemanın "changelog" girdisi, 2026-07-20) — burada
        # ayrıca patch/duplicate gerekmiyor, ligature_map yukarıdaki
        # döngüde şemadan otomatik doğru kuruluyor.
        self.polar_consonant_letters = {l for l, _h in self.polar_consonant_map.keys()}
        self.exception_dictionary = {}  # v1: boş, ileride Aşama 1 için doldurulacak

    # ---------- ön-işleme ----------

    def _apply_digraphs(self, word):
        for k, v in DIGRAPH_MAP.items():
            word = word.replace(k, v)
        return word

    def _normalize(self, word):
        word = word.lower()
        word = self._apply_digraphs(word)
        return "".join(MODERN_LETTER_MAP.get(ch, ch) for ch in word)

    def _base_vowel(self, ch):
        if ch in VOWEL_LETTERS:
            return ch
        if ch in MACRON_MAP:
            return MACRON_MAP[ch]
        if ch in VOWEL_ALIAS_MAP:
            return VOWEL_ALIAS_MAP[ch]
        return None

    def _maybe_warn_unverified(self, raw_word):
        """İstisna Sözlüğü Testi: ŋ/ñ (ng/ny) ya da kapalı é içeren, sözlükte
        henüz doğrulanmamış kelimeler için konsola uyarı basar."""
        lw = raw_word.lower()
        if lw in self.exception_dictionary:
            return
        if "ng" in lw or "ny" in lw or "é" in lw or "ñ" in lw or "ŋ" in lw:
            print(f"WARNING: Unverified word with 'ng' or 'é': {raw_word}")

    def _harmony_of_vowel(self, base_vowel):
        return "back" if base_vowel in ("a", "ı", "o", "u") else "front"

    def _nearest_harmony(self, word, vowel_positions, i):
        before = [p for p in vowel_positions if p < i]
        if before:
            return self._harmony_of_vowel(self._base_vowel(word[max(before)]))
        after = [p for p in vowel_positions if p > i]
        if after:
            return self._harmony_of_vowel(self._base_vowel(word[min(after)]))
        return "back"  # ünlüsüz kelime (olağandışı) — varsayılan

    # ---------- "modern" mod: kural uygulamadan harf-harf birebir eşleme ----------

    def letter_by_letter_sequence(self, latin_text):
        """
        "Modern" mod: ünlü düşürme yok, ligatür/hece sıkıştırma yok, ikiz
        ünsüz tekilleştirme yok — sadece modern harf dönüşümü (F/V/H/J/C/Ğ)
        uygulanır, ardından her Latin karakter TEK BİR glyph'e eşlenir.
        Kutuplu ünsüzler için hâlâ en yakın ünlü bağlamı gerekir (nötr bir
        formu yok), bu tek istisna dışında Aşama 2/3 hiç çalışmaz.
        Döner: class_id listesi (bkz. letter_by_letter_sequence_with_letters
        hangi Latin harfin hangi class_id'ye karşılık geldiğini de istiyorsan).
        """
        return [cid for cid, _ in self.letter_by_letter_sequence_with_letters(latin_text)]

    def letter_by_letter_sequence_with_letters(self, latin_text):
        """Aynı motor, ama her class_id'nin hangi Latin karakterden geldiğini de döner: [(class_id, latin_chunk), ...]."""
        words = latin_text.split()
        out = []
        for wi, w in enumerate(words):
            if wi > 0:
                out.append((":", None))
            self._maybe_warn_unverified(w)
            out.extend(self._letter_by_letter_word(w))
        return out

    def _letter_by_letter_word(self, raw_word):
        word = raw_word.lower()
        word = self._apply_digraphs(word)
        word = "".join(MODERN_LETTER_MAP.get(ch, ch) for ch in word)
        vowel_positions = [i for i, ch in enumerate(word) if self._base_vowel(ch) is not None]

        output = []
        for i, ch in enumerate(word):
            base = self._base_vowel(ch)
            if base is not None:
                output.append((self.vowel_class_map[base], ch))
            elif ch in self.neutral_consonant_map:
                output.append((self.neutral_consonant_map[ch], ch))
            elif ch in self.polar_consonant_letters:
                harmony = self._nearest_harmony(word, vowel_positions, i)
                output.append((self.polar_consonant_map[(ch, harmony)], ch))
            # tanınmayan karakter (rakam, noktalama vb.) -> sessizce atla
        return output

    # ---------- ana motor ("geleneksel" mod) ----------

    def expected_sequence(self, latin_text):
        """
        latin_text: bir kelime ya da boşlukla ayrılmış birden fazla kelime.
        Döner: class_id listesi (birden fazla kelime varsa aralarına
        literal ":" kelime-ayracı işareti eklenir — bu bir model sınıfı
        değil, yapısal bir işarettir). Hangi Latin harfin hangi class_id'ye
        karşılık geldiğini de istiyorsan expected_sequence_with_letters kullan.
        """
        return [cid for cid, _ in self.expected_sequence_with_letters(latin_text)]

    def expected_sequence_with_letters(self, latin_text):
        """Aynı motor, ama her class_id'nin hangi Latin karakter(ler)den geldiğini de döner: [(class_id, latin_chunk), ...]."""
        words = latin_text.split()
        out = []
        for wi, w in enumerate(words):
            if wi > 0:
                out.append((":", None))
            self._maybe_warn_unverified(w)
            if w in self.exception_dictionary:
                out.extend((cid, None) for cid in self.exception_dictionary[w])
            else:
                out.extend(self._expected_sequence_word(w))
        return out

    def _expected_sequence_word(self, raw_word):
        word = self._normalize(raw_word)
        n = len(word)
        vowel_positions = [i for i, ch in enumerate(word) if self._base_vowel(ch) is not None]

        output = []
        seen_vowel_class = {}
        i = 0
        while i < n:
            # --- Aşama 2: hece harfi / ligatür (2 karakterlik look-ahead) ---
            pair = word[i:i + 2]
            if len(pair) == 2 and pair in self.ligature_map:
                is_word_start = (i == 0)

                # KESİN KURAL (2026-07-21, 9 kelimelik tamga.org kanıtıyla
                # çözüldü — korkut/koku/koruk, körküt/kökü/körük,
                # kırkık/kıkı/kırık):
                #
                # - ÜNLÜ-ÖNCE kalıplar (ok,uk,ık,ök,ük): kelimenin HER
                #   YERİNDE (baş/orta/son) ligatür olur, EKSTRA ÜNLÜ ASLA
                #   eklenmez. Hiçbir konum kısıtı yok.
                # - ÜNSÜZ-ÖNCE kalıplar (ko,ku,kı): SADECE kelime BAŞINDA
                #   ligatür + ekstra ünlü. Kelime ORTASI ve SONUNDA ligatür
                #   YASAK — düz harflere döner (orta: normal ünlü-düşürme
                #   kuralları; son: kelime-sonu-ünlü-daima-yazılır kuralı
                #   devreye girer).
                # - ÜNSÜZ-ÖNCE kö/kü: HİÇBİR pozisyonda (baş dahil)
                #   doğrudan ligatür olmaz — sadece dolaylı olarak "ök/ük"
                #   (ünlü-önce) kalıbı yakalanırsa ligatüre girer.
                if pair in ("ko", "ku", "kı") and not is_word_start:
                    pass  # başta değil -> düz harflere düş (fall through)
                elif pair in ("kö", "kü"):
                    pass  # hiçbir pozisyonda doğrudan ligatür değil -> düş
                else:
                    # buraya düşen her şey: ünlü-önce hece (ok,uk,ık,ök,ük —
                    # konum kısıtsız), diğer cluster/hece damgaları
                    # (nd,nt,ld,lt,nc,nç,iç,çi — konum kısıtsız), VE
                    # kelime başındaki "ko/ku/kı" (ekstra ünlü burada eklenir).
                    output.append((self.ligature_map[pair], pair))
                    for vch in pair:
                        vb = self._base_vowel(vch)
                        if vb:
                            seen_vowel_class[self.vowel_class_map[vb]] = True
                    if is_word_start and pair in ("ko", "ku", "kı"):
                        extra = "o" if pair == "ko" else ("u" if pair == "ku" else "ı")
                        output.append((self.vowel_class_map[extra], ""))  # sentetik ek ünlü, girdiden gelmiyor
                        seen_vowel_class[self.vowel_class_map[extra]] = True
                    i += 2
                    continue

            ch = word[i]
            base = self._base_vowel(ch)

            if base is not None:
                is_long = ch in MACRON_MAP
                vclass = self.vowel_class_map[base]
                is_word_start = (i == 0)
                is_word_end = (i == n - 1)

                if is_word_end:
                    output.append((vclass, ch))  # kelime sonu -> her zaman yaz (en yüksek öncelik)
                    seen_vowel_class[vclass] = True
                elif base in ("a", "e"):
                    if is_long:
                        output.append((vclass, ch))  # uzun-ünlü işareti a/e-atlama kuralını ezer
                    seen_vowel_class[vclass] = True
                elif is_word_start:
                    output.append((vclass, ch))
                    seen_vowel_class[vclass] = True
                else:
                    if seen_vowel_class.get(vclass):
                        pass  # aynı ünlü sınıfı tekrarı -> atla
                    elif base in ("ı", "i"):
                        if seen_vowel_class.get(self.vowel_class_map["a"]):
                            pass  # ilk hece a/e ise sonraki ı/i atlanır
                        else:
                            output.append((vclass, ch))
                            seen_vowel_class[vclass] = True
                    else:
                        output.append((vclass, ch))  # o/u, ö/ü kelime ortası ilk kez -> yaz
                        seen_vowel_class[vclass] = True
                i += 1
                continue

            # --- ünsüz ---
            if ch in self.neutral_consonant_map:
                output.append((self.neutral_consonant_map[ch], ch))
            elif ch in self.polar_consonant_letters:
                harmony = self._nearest_harmony(word, vowel_positions, i)
                output.append((self.polar_consonant_map[(ch, harmony)], ch))
            # tanınmayan karakter (rakam, noktalama vb.) -> sessizce atla
            i += 1

        return output


def _self_test():
    """Şemayla birlikte hızlı, elle yazılmış birkaç örnekle mantığı doğrula."""
    import sys
    schema_path = sys.argv[1] if len(sys.argv) > 1 else "../../gokturk_labels_v1_locked.json"
    engine = OrthographyRuleEngine(schema_path)

    print("--- Tutarlı (hepsi kalın) ---")
    print(engine.check_sequence(["t_back", "vowel_a_e", "n_back", "r_back"]))

    print("\n--- İhlal (kalın + ince karışık) ---")
    print(engine.check_sequence(["t_back", "vowel_a_e", "n_front", "r_back"]))

    print("\n--- Kutupsuz harfler + istisna karışık, ihlal saymamalı ---")
    print(engine.check_sequence(["t_back", "m_nopolar", "sh_nopolar", "r_back"]))


def _self_test_spelling():
    """SpellingEngine.expected_sequence testi — 5 kelime."""
    import sys
    schema_path = sys.argv[1] if len(sys.argv) > 1 else "../../gokturk_labels_v1_locked.json"
    engine = SpellingEngine(schema_path)

    for w in ["bodun", "kiçe", "altay", "kağan", "bunda"]:
        print(w, "geleneksel ->", engine.expected_sequence(w))
        print(w, "modern     ->", engine.letter_by_letter_sequence(w))


if __name__ == "__main__":
    _self_test()
    print()
    _self_test_spelling()
