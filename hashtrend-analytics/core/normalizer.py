"""
Normalization Engine — Farklı kaynaklardan gelen konuları birleştirir.

Problem: Aynı konu farklı kaynaklarda farklı isimlerle geçebilir.
Örnek: "OpenAI GPT-5" (Reddit) = "GPT-5 release" (HN) = "gpt 5" (Google Trends)

Çözüm: Metin benzerliği + keyword extraction ile topic matching.
"""

import re
from collections import defaultdict
from datetime import datetime
from loguru import logger

from core.models import RawMention, NormalizedTopic


class Normalizer:
    """
    Ham mention'ları normalize edip birleştirir.
    Aynı konuyu farklı kaynaklardan gelen verilerle eşleştirir.
    """

    # Temizleme: gereksiz kelimeler (stopwords)
    STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
        "to", "for", "of", "with", "by", "from", "and", "or", "but",
        "not", "this", "that", "it", "its", "has", "have", "had",
        "be", "been", "being", "do", "does", "did", "will", "would",
        "can", "could", "should", "may", "might", "shall",
        "how", "what", "why", "when", "where", "who", "which",
        "new", "just", "now", "about", "after", "before",
        "show", "hn", "ask", "tell", "me", "my", "your",
    }

    def __init__(self, similarity_threshold: float = 0.45):
        """
        Args:
            similarity_threshold: İki konunun aynı sayılması için
                                  minimum benzerlik eşiği (0-1).
        """
        self.threshold = similarity_threshold

    def normalize(self, mentions: list[RawMention]) -> list[NormalizedTopic]:
        """
        Ham mention listesini normalize edilmiş konu listesine çevir.

        Adımlar:
        1. Her mention'ın başlığını temizle (lowercase, stopword removal)
        2. Keyword'leri çıkar
        3. Benzer konuları grupla
        4. Her grup için tek bir NormalizedTopic oluştur
        """
        if not mentions:
            return []

        # Adım 1-2: Keyword extraction
        processed = []
        for m in mentions:
            keywords = self._extract_keywords(m.topic)
            if keywords:
                processed.append((m, keywords))

        # Adım 3: Benzer konuları grupla
        groups = self._group_similar(processed)

        # Adım 4: NormalizedTopic'lere dönüştür
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
        # Küçük harfe çevir, özel karakterleri temizle
        text = text.lower().strip()
        text = re.sub(r"[^\w\s\-]", " ", text)

        # Kelimelere ayır ve stopword'leri filtrele
        words = text.split()
        keywords = {
            w for w in words
            if w not in self.STOPWORDS
            and len(w) > 1
            and not w.isdigit()
        }

        return keywords

    def _similarity(self, kw1: set[str], kw2: set[str]) -> float:
        """
        İki keyword seti arasındaki Jaccard benzerliği.
        Jaccard = |A ∩ B| / |A ∪ B|
        """
        if not kw1 or not kw2:
            return 0.0

        intersection = kw1 & kw2
        union = kw1 | kw2

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _group_similar(
        self, processed: list[tuple[RawMention, set[str]]]
    ) -> list[list[tuple[RawMention, set[str]]]]:
        """
        Benzer konuları grupla (greedy clustering).
        Her mention en benzer gruba eklenir veya yeni grup oluşturur.
        """
        groups: list[list[tuple[RawMention, set[str]]]] = []

        for item in processed:
            mention, keywords = item
            best_group_idx = -1
            best_similarity = 0.0

            # Mevcut gruplarla karşılaştır
            for idx, group in enumerate(groups):
                # Grup temsilcisi: en çok keyword'ü olan üye
                representative_kw = group[0][1]
                sim = self._similarity(keywords, representative_kw)

                if sim > best_similarity:
                    best_similarity = sim
                    best_group_idx = idx

            # Eşik üzerindeyse mevcut gruba ekle, değilse yeni grup
            if best_similarity >= self.threshold and best_group_idx >= 0:
                groups[best_group_idx].append(item)
            else:
                groups.append([item])

        return groups

    def _merge_group(
        self, group: list[tuple[RawMention, set[str]]]
    ) -> NormalizedTopic | None:
        """Bir gruptaki tüm mention'ları tek NormalizedTopic'e birleştir."""
        if not group:
            return None

        # En yüksek mention_count'a sahip olanı canonical name olarak kullan
        best = max(group, key=lambda x: x[0].mention_count)
        canonical_name = best[0].topic.strip()

        # Kaynakları topla (benzersiz)
        sources = list({item[0].source for item in group})

        # Toplam mention sayısı
        total = sum(item[0].mention_count for item in group)

        # Zaman bilgisi
        timestamps = [item[0].collected_at for item in group]

        return NormalizedTopic(
            canonical_name=canonical_name,
            first_seen=min(timestamps),
            last_seen=max(timestamps),
            total_mentions=total,
            sources=sources,
        )


# Standalone test
if __name__ == "__main__":
    normalizer = Normalizer()

    # Test verisi: aynı konu farklı kaynaklarda
    test_mentions = [
        RawMention(source="google_trends", topic="GPT-5 release date", mention_count=90),
        RawMention(source="reddit", topic="OpenAI announces GPT-5 release", mention_count=5000),
        RawMention(source="hackernews", topic="GPT-5 Released by OpenAI", mention_count=800),
        RawMention(source="google_trends", topic="Bitcoin price crash", mention_count=85),
        RawMention(source="reddit", topic="Bitcoin crashes below 50k", mention_count=3000),
        RawMention(source="hackernews", topic="Show HN: I built a new programming language", mention_count=200),
        RawMention(source="google_trends", topic="Taylor Swift concert", mention_count=70),
    ]

    topics = normalizer.normalize(test_mentions)

    print(f"\n{'='*60}")
    print(f"{len(test_mentions)} mention → {len(topics)} benzersiz konu")
    print(f"{'='*60}\n")

    for t in topics:
        print(f"  [{', '.join(t.sources)}] {t.canonical_name}")
        print(f"    Toplam mention: {t.total_mentions}")
        print()
