"""
Kahve & Tatlı Trend Radarı — izleme listesi (watchlist).

Her kavram (concept) bir dict:
    id        : stabil slug (rollup JSON + sayfa bunu anahtar olarak kullanır)
    name_tr   : sayfada gösterilen Türkçe ad
    name_en   : İngilizce ad
    group     : "kahve" | "tatli"
    variants  : trend_scores.topic_name / raw_mentions.topic içinde aranan
                küçük-harf alt dizgiler. TEK KELİMELİK muğlak terimler yerine
                nitelikli kalıplar kullan ("magnolia" değil "magnolia tatlısı*").

Kullanım:
    from config.food_watchlist import WATCHLIST, all_variants
"""

from __future__ import annotations

WATCHLIST: list[dict] = [
    # ─── Kahve & içecek ─────────────────────────────────────────────────────
    # NOT: concept_for İLK eşleşen kavramı döndürür → spesifik kavramlar
    # genel olanlardan ÖNCE gelmeli (strawberry-matcha < matcha gibi).
    {"id": "strawberry-matcha", "name_tr": "Çilekli Matcha", "name_en": "Strawberry Matcha",
     "group": "kahve", "variants": ["strawberry matcha", "çilekli matcha*"]},
    {"id": "matcha", "name_tr": "Matcha", "name_en": "Matcha",
     "group": "kahve", "variants": ["matcha"]},
    {"id": "hojicha", "name_tr": "Hojicha", "name_en": "Hojicha",
     "group": "kahve", "variants": ["hojicha"]},
    {"id": "pistachio-latte", "name_tr": "Fıstıklı Latte", "name_en": "Pistachio Latte",
     "group": "kahve", "variants": ["pistachio latte", "fıstıklı latte*", "pistachio coffee"]},
    {"id": "spanish-latte", "name_tr": "Spanish Latte", "name_en": "Spanish Latte",
     "group": "kahve", "variants": ["spanish latte"]},
    {"id": "cold-brew", "name_tr": "Cold Brew", "name_en": "Cold Brew",
     "group": "kahve", "variants": ["cold brew"]},
    {"id": "espresso-tonic", "name_tr": "Espresso Tonik", "name_en": "Espresso Tonic",
     "group": "kahve", "variants": ["espresso tonic"]},
    {"id": "cortado", "name_tr": "Cortado", "name_en": "Cortado",
     "group": "kahve", "variants": ["cortado"]},
    {"id": "flat-white", "name_tr": "Flat White", "name_en": "Flat White",
     "group": "kahve", "variants": ["flat white"]},
    {"id": "freddo", "name_tr": "Freddo", "name_en": "Freddo",
     "group": "kahve", "variants": ["freddo espresso", "freddo cappuccino"]},
    {"id": "einspanner", "name_tr": "Einspänner (Viyana)", "name_en": "Einspänner",
     "group": "kahve", "variants": ["einspanner", "einspänner", "viyana kahvesi*"]},
    {"id": "dirty-chai", "name_tr": "Dirty Chai", "name_en": "Dirty Chai",
     "group": "kahve", "variants": ["dirty chai"]},
    {"id": "chai-latte", "name_tr": "Chai Latte", "name_en": "Chai Latte",
     "group": "kahve", "variants": ["chai latte"]},
    {"id": "protein-coffee", "name_tr": "Protein Kahve", "name_en": "Protein Coffee",
     "group": "kahve", "variants": ["protein coffee", "proffee", "protein kahve*"]},
    {"id": "mushroom-coffee", "name_tr": "Mantar Kahvesi", "name_en": "Mushroom Coffee",
     "group": "kahve", "variants": ["mushroom coffee", "mantar kahvesi*"]},
    {"id": "iced-americano", "name_tr": "Buzlu Americano", "name_en": "Iced Americano",
     "group": "kahve", "variants": ["iced americano", "buzlu americano*"]},
    {"id": "turk-kahvesi", "name_tr": "Türk Kahvesi", "name_en": "Turkish Coffee",
     "group": "kahve", "variants": ["türk kahvesi*", "turkish coffee"]},
    {"id": "filtre-kahve", "name_tr": "Filtre / Demleme", "name_en": "Filter / Pour Over",
     "group": "kahve", "variants": ["filtre kahve*", "filter coffee", "pour over", "v60 "]},
    {"id": "specialty-coffee", "name_tr": "3. Dalga / Specialty", "name_en": "Specialty Coffee",
     "group": "kahve", "variants": ["specialty coffee", "nitelikli kahve*", "third wave coffee"]},
    {"id": "salep", "name_tr": "Salep", "name_en": "Salep",
     "group": "kahve", "variants": ["salep*", "sahlep*"]},
    {"id": "ube-latte", "name_tr": "Ube Latte", "name_en": "Ube Latte",
     "group": "kahve", "variants": ["ube latte", "ube coffee"]},
    {"id": "brown-sugar", "name_tr": "Brown Sugar", "name_en": "Brown Sugar Latte/Boba",
     "group": "kahve", "variants": ["brown sugar latte", "brown sugar boba", "brown sugar milk"]},
    {"id": "yuzu-coffee", "name_tr": "Yuzu / Narenciye Kahve", "name_en": "Yuzu Coffee",
     "group": "kahve", "variants": ["yuzu coffee", "yuzu latte", "citrus coffee", "orange coffee"]},
    {"id": "affogato", "name_tr": "Affogato", "name_en": "Affogato",
     "group": "kahve", "variants": ["affogato"]},
    {"id": "bubble-tea", "name_tr": "Bubble Tea / Boba", "name_en": "Bubble Tea",
     "group": "kahve", "variants": ["bubble tea", "boba tea", "milk tea"]},
    {"id": "dalgona", "name_tr": "Dalgona", "name_en": "Dalgona",
     "group": "kahve", "variants": ["dalgona"]},

    # ─── Tatlı ──────────────────────────────────────────────────────────────
    {"id": "dubai-cikolatasi", "name_tr": "Dubai Çikolatası", "name_en": "Dubai Chocolate",
     "group": "tatli", "variants": ["dubai chocolate", "dubai çikolatası", "dubai cikolatasi"]},
    {"id": "kunefe", "name_tr": "Künefe / Kunafa", "name_en": "Kunafa",
     "group": "tatli", "variants": ["künefe*", "kunefe*", "kunafa", "knafeh"]},
    # NOT: çıplak "san sebastian" KULLANMA — İspanya'daki şehir/film festivali
    # haberleriyle çakışıyor; yalnız nitelikli kalıplar.
    {"id": "san-sebastian", "name_tr": "San Sebastian", "name_en": "Basque Cheesecake",
     "group": "tatli", "variants": ["san sebastian cheesecake", "san sebastian tatlı*",
                                    "basque cheesecake"]},
    {"id": "cheesecake", "name_tr": "Cheesecake (genel)", "name_en": "Cheesecake",
     "group": "tatli", "variants": ["cheesecake"]},
    {"id": "tiramisu", "name_tr": "Tiramisu", "name_en": "Tiramisu",
     "group": "tatli", "variants": ["tiramisu", "tiramisù"]},
    {"id": "mochi", "name_tr": "Mochi", "name_en": "Mochi",
     "group": "tatli", "variants": ["mochi"]},
    {"id": "cromboloni", "name_tr": "Cromboloni / NY Roll", "name_en": "Cromboloni",
     "group": "tatli", "variants": ["cromboloni", "new york roll"]},
    {"id": "crookie", "name_tr": "Crookie", "name_en": "Crookie",
     "group": "tatli", "variants": ["crookie"]},
    {"id": "flat-croissant", "name_tr": "Flat Croissant", "name_en": "Flat Croissant",
     "group": "tatli", "variants": ["flat croissant", "crushed croissant"]},
    {"id": "croissant", "name_tr": "Kruvasan (genel)", "name_en": "Croissant",
     "group": "tatli", "variants": ["croissant", "kruvasan*"]},
    {"id": "cinnamon-roll", "name_tr": "Tarçınlı Rulo", "name_en": "Cinnamon Roll",
     "group": "tatli", "variants": ["cinnamon roll", "tarçınlı rulo*"]},
    {"id": "banana-pudding", "name_tr": "Banana Pudding", "name_en": "Banana Pudding",
     "group": "tatli", "variants": ["banana pudding"]},
    {"id": "creme-brulee", "name_tr": "Krem Brüle", "name_en": "Crème Brûlée",
     "group": "tatli", "variants": ["creme brulee", "crème brûlée", "krem brüle*"]},
    {"id": "canele", "name_tr": "Canelé", "name_en": "Canelé",
     "group": "tatli", "variants": ["canelé", "canele"]},
    {"id": "tanghulu", "name_tr": "Tanghulu", "name_en": "Tanghulu",
     "group": "tatli", "variants": ["tanghulu"]},
    {"id": "pavlova", "name_tr": "Pavlova", "name_en": "Pavlova",
     "group": "tatli", "variants": ["pavlova"]},
    {"id": "profiterol", "name_tr": "Profiterol", "name_en": "Profiterole",
     "group": "tatli", "variants": ["profiterol*", "profiterole"]},
    {"id": "baklava", "name_tr": "Baklava", "name_en": "Baklava",
     "group": "tatli", "variants": ["baklava*"]},
    {"id": "trilece", "name_tr": "Trileçe", "name_en": "Tres Leches",
     "group": "tatli", "variants": ["trileçe*", "trilece*", "tres leches"]},
    # NOT: çıplak "ekler" KULLANMA — Türkçe çoğul eki (-ekler: erkekler,
    # bebekler...) ve "eklemek" fiiliyle çakışıp ~%100 yanlış-pozitif üretiyor.
    # Çıplak "eclair/éclair" de KULLANMA — Fransızca hava durumu haberleri
    # ("266 éclairs recensés" = şimşek) ile çakışıyor.
    {"id": "ekler", "name_tr": "Ekler", "name_en": "Éclair",
     "group": "tatli", "variants": ["ekler tatlısı*", "ekler pasta*",
                                    "çikolatalı ekler*", "chocolate eclair",
                                    "eclair cake", "eclair recipe"]},
    {"id": "magnolia", "name_tr": "Magnolia", "name_en": "Magnolia Dessert",
     "group": "tatli", "variants": ["magnolia tatlısı*", "magnolia dessert", "magnolia banana"]},
    {"id": "sutlac", "name_tr": "Sütlaç", "name_en": "Rice Pudding",
     "group": "tatli", "variants": ["sütlaç*", "sutlac*", "rice pudding"]},
    {"id": "kazandibi", "name_tr": "Kazandibi", "name_en": "Kazandibi",
     "group": "tatli", "variants": ["kazandibi*"]},
    {"id": "katmer", "name_tr": "Katmer", "name_en": "Katmer",
     "group": "tatli", "variants": ["katmer*"]},
    {"id": "lotus-biscoff", "name_tr": "Lotus / Biscoff", "name_en": "Biscoff",
     "group": "tatli", "variants": ["biscoff", "lotus cheesecake", "lotus tatlısı*"]},
    {"id": "ny-cookie", "name_tr": "NY Cookie", "name_en": "NY Cookie",
     "group": "tatli", "variants": ["new york cookie", "ny cookie", "stuffed cookie"]},
    {"id": "brownie", "name_tr": "Brownie", "name_en": "Brownie",
     "group": "tatli", "variants": ["brownie"]},
    {"id": "pistachio-wave", "name_tr": "Fıstık Akımı", "name_en": "Pistachio (wave)",
     "group": "tatli", "variants": ["pistachio", "antep fıstıklı", "fıstıklı"]},
    {"id": "mille-crepe", "name_tr": "Krep Pasta", "name_en": "Mille Crêpe",
     "group": "tatli", "variants": ["mille crepe", "crepe cake", "krep pasta*"]},
    {"id": "swedish-candy", "name_tr": "İsveç Şekeri", "name_en": "Swedish Candy",
     "group": "tatli", "variants": ["swedish candy"]},
    {"id": "gelato", "name_tr": "Gelato / Dondurma", "name_en": "Gelato",
     "group": "tatli", "variants": ["gelato", "soft serve", "maraş dondurma*"]},
]


def all_variants() -> list[str]:
    """Tüm varyantlar, düz liste (küçük harf, '*' ek-toleransı işareti soyulmuş).

    REST coarse ilike filtresi için kullanılır — '*' yalnız concept_for'un
    kesin eşlemesinde anlamlıdır.
    """
    out: list[str] = []
    for c in WATCHLIST:
        out.extend(v.lower().rstrip("*") for v in c["variants"])
    return out


import re as _re

# Kavram bazlı dışlama kalıpları — bilinen çok-dilli çakışmalar.
# Metinde bu kalıplardan biri geçiyorsa o kavramla eşleşme İPTAL edilir.
_EXCLUDES: dict[str, list[str]] = {
    # PT/ES "cortado" = "kesilmiş" (futbol kadrosu, bütçe haberleri)
    "cortado": ["seleção", "selecao", "orçamento", "orcamento"],
    # GitHub repo "Anil-matcha/...", "MATCHA: Matching..." akademik kısaltma
    "matcha": ["anil-matcha", "contrastive", "matching text"],
    # "MOCHI: Motion Enhancement..." akademik kısaltma
    "mochi": ["motion enhancement", "human-object"],
    # İngilizce deyim "brownie points"
    "brownie": ["brownie points"],
}

_PATTERN_CACHE: list[tuple[str, list, list]] = []


def _variant_pattern(v: str):
    """Tek varyant → regex.

    Kural: başta HER ZAMAN kelime sınırı ('erkekler' → 'ekler' eşleşmez).
    Sonda: varyant '*' ile bitiyorsa Türkçe ek toleransı (baklava* →
    'baklavası/baklavacı' eşleşir), yoksa katı sınır ('mochi' → 'mochilas'
    eşleşmez). Lookaround kullanılır (\\b yerine) — aksanlı harflerde güvenli.
    """
    v = v.strip().lower()
    if v.endswith("*"):
        return _re.compile(r"(?<!\w)" + _re.escape(v[:-1]))
    return _re.compile(r"(?<!\w)" + _re.escape(v) + r"(?!\w)")


def _patterns():
    """(concept_id, [variant regex], [exclude regex]) listesi — lazy derlenir."""
    if not _PATTERN_CACHE:
        for c in WATCHLIST:
            vpats = [_variant_pattern(v) for v in c["variants"]]
            xpats = [
                _re.compile(_re.escape(x.lower()))
                for x in _EXCLUDES.get(c["id"], [])
            ]
            _PATTERN_CACHE.append((c["id"], vpats, xpats))
    return _PATTERN_CACHE


def concept_for(text: str) -> str | None:
    """Topic metnini ilk eşleşen kavram id'sine bağla (kelime-sınırı + exclude)."""
    t = (text or "").lower()
    for cid, vpats, xpats in _patterns():
        if any(p.search(t) for p in vpats):
            if any(x.search(t) for x in xpats):
                continue
            return cid
    return None


if __name__ == "__main__":
    print(f"{len(WATCHLIST)} kavram, {len(all_variants())} varyant")
    assert len({c['id'] for c in WATCHLIST}) == len(WATCHLIST), "id çakışması!"
    # Spesifik kavram genel olandan önce eşleşmeli (liste sırası kritik)
    assert concept_for("Strawberry Matcha Latte at home") == "strawberry-matcha"
    assert concept_for("matcha latte art") == "matcha"
    # Türkçe çoğul/fiil yanlış-pozitifleri elenmeli
    assert concept_for("Erkekler Voleybol Milletler Ligi") is None
    assert concept_for("çikolatalı ekler tarifi") == "ekler"
    # Şehir haberi tatlıya sayılmamalı
    assert concept_for("san sebastian film festivali") is None
    assert concept_for("san sebastian cheesecake tarifi") == "san-sebastian"
    # Kelime-sınırı: çok-dilli substring yanlış-pozitifleri elenmeli
    assert concept_for("mochilas escolares em promoção") is None       # PT çanta
    assert concept_for("Los Mochis Sinaloa noticias") is None          # MX şehir
    assert concept_for("caneleira do Neymar") is None                  # PT tekmelik
    assert concept_for("mochi ice cream recipe") == "mochi"
    assert concept_for("canelé de bordeaux") == "canele"
    # Exclude listesi: bilinen çakışmalar
    assert concept_for("jogador cortado da seleção") is None           # PT futbol
    assert concept_for("cortado at the coffee shop") == "cortado"
    assert concept_for("Anil-matcha new release on github") is None    # GH repo
    assert concept_for("earn brownie points with your boss") is None   # deyim
    assert concept_for("fudgy brownie recipe") == "brownie"
    # Türkçe ek toleransı ('*' işaretli varyantlar)
    assert concept_for("bu baklavası efsane olmuş") == "baklava"
    assert concept_for("künefeci amca viral oldu") == "kunefe"
    assert concept_for("türk kahvesiyle güne başlamak") == "turk-kahvesi"
    assert concept_for("trileçesi meşhur") == "trilece"
    print("self-test OK — örnek eşleme:",
          concept_for("Strawberry Matcha Latte at home"))
