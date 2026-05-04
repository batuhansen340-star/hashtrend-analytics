"""
Normalization Engine v2 — Hash-bucket optimizasyonlu.

Performans iyileştirmesi:
  Eski: O(n × g) — her mention × tüm gruplar (500 × 200 = 100K comparison)
  Yeni: O(n) amortized — keyword hash ile bucket, sadece aynı bucket içi karşılaştır
  Beklenen hızlanma: ~10-20x (500 mention'da)

Ek iyileştirmeler:
  • Slug oluşturma (URL-safe konu adları)
  • Kaynak bazlı mention_count takibi (source_breakdown düzeltmesi)
  • Daha agresif dedup (büyük/küçük harf, leading/trailing whitespace)
"""

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional
from loguru import logger

from core.models import RawMention, NormalizedTopic


# TR-spesifik kaynaklar — bu kaynaklardan gelen mention TR olarak yorumlanır.
# Bluesky için ayrı TR sorgu detection bluesky.py içinde yapılır.
TR_SPECIFIC_SOURCES = frozenset({
    "eksisozluk", "webrazzi", "gdelt", "tr_news_rss", "trends24",
})


class Normalizer:
    """Hash-bucket bazlı topic normalization engine."""

    STOPWORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "with", "by", "from", "and", "or", "but",
        "not", "this", "that", "it", "its", "has", "have", "had",
        "be", "been", "being", "do", "does", "did", "will", "would",
        "can", "could", "should", "may", "might", "shall",
        "how", "what", "why", "when", "where", "who", "which",
        "new", "just", "now", "about", "after", "before",
        "show", "hn", "ask", "tell", "me", "my", "your",
        "get", "got", "go", "going", "been", "into", "over",
        "up", "down", "out", "off", "than", "then", "so",
    })

    def __init__(self, similarity_threshold: float = 0.40):
        self.threshold = similarity_threshold

    def normalize(self, mentions: list[RawMention]) -> list[NormalizedTopic]:
        """
        Ham mention'ları normalize et.

        Optimizasyon: İlk keyword'e göre hash bucket oluştur,
        sadece aynı bucket içinde benzerlik karşılaştır.
        O(n × g) → O(n × b) where b << g
        """
        if not mentions:
            return []

        # Adım 1: Keyword extraction + dedup preparation
        processed: list[tuple[RawMention, set[str], str]] = []
        for m in mentions:
            keywords = self._extract_keywords(m.topic)
            if keywords:
                # Primary key: en uzun keyword (bucket key olarak)
                primary = max(keywords, key=len)
                processed.append((m, keywords, primary))

        # Adım 2: Hash bucket ile gruplama
        groups = self._bucket_group(processed)

        # Adım 3: NormalizedTopic'lere dönüştür
        topics = []
        for group in groups:
            topic = self._merge_group(group)
            if topic:
                topics.append(topic)

        logger.info(
            f"Normalizasyon: {len(mentions)} mention → {len(topics)} benzersiz konu"
        )
        return topics

    def _extract_keywords(self, text: str) -> set[str]:
        """Metinden anlamlı keyword'leri çıkar."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s\-]", " ", text)

        words = text.split()
        keywords = {
            w for w in words
            if w not in self.STOPWORDS
            and len(w) > 1
            and not w.isdigit()
        }
        return keywords

    def _bucket_group(
        self, processed: list[tuple[RawMention, set[str], str]]
    ) -> list[list[tuple[RawMention, set[str]]]]:
        """
        Hash bucket bazlı gruplama.

        1. Her mention'ın TÜM keyword'leri için bucket'lara koy
        2. Aynı bucket'ta olan mention'lar arasında similarity kontrol et
        3. Birleşmiş grupları döndür

        Bu yaklaşım O(n²) yerine O(n × avg_keywords) — genelde ~5 keyword/mention
        """
        # Keyword → mention listesi (inverted index)
        keyword_buckets: dict[str, list[int]] = defaultdict(list)
        for idx, (mention, keywords, primary) in enumerate(processed):
            for kw in keywords:
                keyword_buckets[kw].append(idx)

        # Union-Find ile gruplama
        parent = list(range(len(processed)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]  # Path compression
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Aynı bucket'taki mention'ları karşılaştır
        seen_pairs: set[tuple[int, int]] = set()

        for kw, indices in keyword_buckets.items():
            if len(indices) > 50:
                # Çok yaygın keyword — atla (performans koruması)
                continue

            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    idx_a, idx_b = indices[i], indices[j]
                    pair = (min(idx_a, idx_b), max(idx_a, idx_b))

                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    kw_a = processed[idx_a][1]
                    kw_b = processed[idx_b][1]
                    sim = self._similarity(kw_a, kw_b)

                    if sim >= self.threshold:
                        union(idx_a, idx_b)

        # Grupları oluştur
        group_map: dict[int, list[tuple[RawMention, set[str]]]] = defaultdict(list)
        for idx, (mention, keywords, _) in enumerate(processed):
            root = find(idx)
            group_map[root].append((mention, keywords))

        return list(group_map.values())

    def _similarity(self, kw1: set[str], kw2: set[str]) -> float:
        """Jaccard benzerliği."""
        if not kw1 or not kw2:
            return 0.0
        intersection = kw1 & kw2
        union = kw1 | kw2
        return len(intersection) / len(union) if union else 0.0

    def _merge_group(
        self, group: list[tuple[RawMention, set[str]]]
    ) -> Optional[NormalizedTopic]:
        """Bir gruptaki mention'ları birleştir."""
        if not group:
            return None

        # En yüksek skorlu mention → canonical name
        best = max(group, key=lambda x: x[0].mention_count)
        canonical_name = best[0].topic.strip()

        # Slug oluştur (URL-safe)
        slug = self._make_slug(canonical_name)

        # Kaynaklar ve kaynak bazlı mention sayısı
        source_mentions: dict[str, int] = {}
        for mention, _ in group:
            src = mention.source
            if src in source_mentions:
                source_mentions[src] += mention.mention_count
            else:
                source_mentions[src] = mention.mention_count

        sources = list(source_mentions.keys())
        total = sum(source_mentions.values())

        timestamps = [item[0].collected_at for item in group]

        topic = NormalizedTopic(
            canonical_name=canonical_name,
            first_seen=min(timestamps),
            last_seen=max(timestamps),
            total_mentions=total,
            country=self._resolve_country(group),
            sources=sources,
        )

        # Ekstra: source_breakdown'ı raw_data'ya koy (scorer kullanacak)


        # Workaround: source_mentions'ı topic'e attach et
        topic._source_mentions = source_mentions  # type: ignore

        return topic

    @staticmethod
    def _resolve_country(
        group: list[tuple[RawMention, set[str]]]
    ) -> Optional[str]:
        """
        Group'taki mention'lardan dominant country'yi belirle.

        Eski mantık: `next()` + ilk non-GLOBAL — group iteration order'a bağlı,
        rastgele country atıyordu (Chuck Norris=KR, Tim Cook=TR vs.).

        Yeni mantık:
        1. TR-spesifik kaynak mention'ları toplam'ın %30+'ı ise → 'TR'
        2. Aksi halde mention_count ağırlıklı çoğunluk (en çok bahsedilen country)
        3. Hiç non-GLOBAL country yoksa → 'GLOBAL'
        """
        if not group:
            return "GLOBAL"

        total = sum(m.mention_count for m, _ in group) or 1

        tr_weight = sum(
            m.mention_count for m, _ in group
            if (m.source in TR_SPECIFIC_SOURCES) or (m.country == "TR")
        )
        if tr_weight / total >= 0.30:
            return "TR"

        # mention_count ağırlıklı country sayımı
        country_weights: Counter[str] = Counter()
        for m, _ in group:
            c = (m.country or "").strip().upper()
            if c and c != "GLOBAL":
                country_weights[c] += m.mention_count

        if country_weights:
            return country_weights.most_common(1)[0][0]
        return "GLOBAL"

    @staticmethod
    def _make_slug(text: str) -> str:
        """URL-safe slug oluştur."""
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        # Max 100 karakter
        return slug[:100]


# Standalone test
if __name__ == "__main__":
    import time

    normalizer = Normalizer()

    # Büyük test verisi (performans testi)
    test_mentions = [
        RawMention(source="google_trends", topic="GPT-5 release date", mention_count=90),
        RawMention(source="reddit", topic="OpenAI announces GPT-5 release", mention_count=5000),
        RawMention(source="hackernews", topic="GPT-5 Released by OpenAI", mention_count=800),
        RawMention(source="google_trends", topic="Bitcoin price crash today", mention_count=85),
        RawMention(source="reddit", topic="Bitcoin crashes below 50k", mention_count=3000),
        RawMention(source="hackernews", topic="Bitcoin price analysis", mention_count=200),
        RawMention(source="google_trends", topic="Taylor Swift concert tour", mention_count=70),
        RawMention(source="reddit", topic="NASA Mars sample return mission", mention_count=1500),
        RawMention(source="hackernews", topic="NASA Mars mission update", mention_count=400),
        RawMention(source="reddit", topic="Rust programming language 2026", mention_count=800),
    ]

    start = time.time()
    topics = normalizer.normalize(test_mentions)
    elapsed = (time.time() - start) * 1000

    print(f"\n{'='*60}")
    print(f"{len(test_mentions)} mention → {len(topics)} konu ({elapsed:.1f}ms)")
    print(f"{'='*60}\n")

    for t in topics:
        slug = normalizer._make_slug(t.canonical_name)
        src_info = getattr(t, '_source_mentions', {})
        print(f"  [{', '.join(t.sources)}] {t.canonical_name}")
        print(f"    slug: {slug}")
        print(f"    mentions: {t.total_mentions} | sources: {src_info}")
        print()
