"""
Google Trends Collector v2 — interest_over_time bazlı.

Eski versiyon: trending_searches() → Google 404 döndürüyor (endpoint kaldırıldı).
Yeni versiyon: Diğer collector'lardan gelen konuları Google Trends'te doğrulama.
Ayrıca Google Trends Daily Trends RSS feed'ini parse eder.

Strateji:
1. Google Trends Daily RSS → günün trending konularını al
2. Diğer kaynaklardan gelen konuları interest_over_time ile doğrula (Faz 2)
"""

import time
import re
from datetime import datetime
from xml.etree import ElementTree
from loguru import logger
import requests

from collectors.base import BaseCollector
from core.models import RawMention


class GoogleTrendsCollector(BaseCollector):
    SOURCE_NAME = "google_trends"
    COLLECT_INTERVAL_MINUTES = 60

    # Google Trends Daily RSS — ülke bazlı
    RSS_URLS = {
        "US": "https://trends.google.com/trending/rss?geo=US",
        "GB": "https://trends.google.com/trending/rss?geo=GB",
        "DE": "https://trends.google.com/trending/rss?geo=DE",
        "TR": "https://trends.google.com/trending/rss?geo=TR",
        "FR": "https://trends.google.com/trending/rss?geo=FR",
        "BR": "https://trends.google.com/trending/rss?geo=BR",
        "IN": "https://trends.google.com/trending/rss?geo=IN",
        "JP": "https://trends.google.com/trending/rss?geo=JP",
        "KR": "https://trends.google.com/trending/rss?geo=KR",
        "CA": "https://trends.google.com/trending/rss?geo=CA",
        "AU": "https://trends.google.com/trending/rss?geo=AU",
        "ES": "https://trends.google.com/trending/rss?geo=ES",
        "IT": "https://trends.google.com/trending/rss?geo=IT",
        "NL": "https://trends.google.com/trending/rss?geo=NL",
        "MX": "https://trends.google.com/trending/rss?geo=MX",
        "SA": "https://trends.google.com/trending/rss?geo=SA",
        "AE": "https://trends.google.com/trending/rss?geo=AE",
        "PL": "https://trends.google.com/trending/rss?geo=PL",
        "ID": "https://trends.google.com/trending/rss?geo=ID",
        "SE": "https://trends.google.com/trending/rss?geo=SE",
    }

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        })

    def collect(self) -> list[RawMention]:
        """Google Trends Daily RSS feed'lerinden trend topla."""
        all_mentions = []

        for country_code, rss_url in self.RSS_URLS.items():
            try:
                mentions = self._collect_rss(rss_url, country_code)
                all_mentions.extend(mentions)
                time.sleep(1)  # Rate limit koruması
            except Exception as e:
                logger.warning(f"[google_trends] {country_code} RSS hatası: {e}")
                continue

        return all_mentions

    def _collect_rss(self, url: str, country_code: str) -> list[RawMention]:
        """Tek bir ülkenin RSS feed'ini parse et."""
        mentions = []

        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                logger.warning(
                    f"[google_trends] RSS {country_code} HTTP {response.status_code}"
                )
                return []

            # XML parse
            root = ElementTree.fromstring(response.content)

            # RSS namespace
            ns = {"ht": "https://trends.google.com/trending/rss"}

            # Her <item> bir trending konu
            items = root.findall(".//item")

            for idx, item in enumerate(items):
                title = item.findtext("title", "").strip()
                if not title or len(title) < 2:
                    continue

                # Traffic volume (varsa)
                traffic = item.findtext("ht:approx_traffic", "0", ns)
                # "+250,000" gibi formatı sayıya çevir
                traffic_num = self._parse_traffic(traffic)

                # Link
                link = item.findtext("link", "")

                # Pub date
                pub_date = item.findtext("pubDate", "")

                # İlgili haberler (varsa)
                news_items = item.findall("ht:news_item", ns)
                news_titles = []
                for news in news_items[:3]:  # İlk 3 haber
                    news_title = news.findtext("ht:news_item_title", "", ns)
                    if news_title:
                        news_titles.append(news_title)

                # Skor: sıralama + traffic bazlı
                # İlk sıradaki en yüksek skor alır
                rank_score = max(100 - (idx * 3), 10)
                mention_score = rank_score + (traffic_num // 10000)

                mentions.append(
                    RawMention(
                        source=self.SOURCE_NAME,
                        topic=title,
                        mention_count=mention_score,
                        country=country_code,
                        url=link,
                        raw_data={
                            "rank": idx + 1,
                            "country": country_code,
                            "approx_traffic": traffic_num,
                            "traffic_raw": traffic,
                            "pub_date": pub_date,
                            "related_news": news_titles,
                            "type": "daily_rss",
                        },
                    )
                )

            logger.debug(
                f"[google_trends] {country_code}: {len(mentions)} trend (RSS)"
            )

        except ElementTree.ParseError as e:
            logger.warning(f"[google_trends] {country_code} XML parse hatası: {e}")
        except Exception as e:
            logger.warning(f"[google_trends] {country_code} hatası: {e}")

        return mentions

    @staticmethod
    def _parse_traffic(traffic_str: str) -> int:
        """'+250,000' gibi traffic string'ini integer'a çevir."""
        if not traffic_str:
            return 0
        # Rakam olmayan karakterleri sil
        cleaned = re.sub(r"[^\d]", "", traffic_str)
        try:
            return int(cleaned) if cleaned else 0
        except ValueError:
            return 0


# Standalone test
if __name__ == "__main__":
    collector = GoogleTrendsCollector()
    mentions = collector.run()

    print(f"\n{'='*60}")
    print(f"Toplam {len(mentions)} Google Trends mention toplandı")
    print(f"{'='*60}\n")

    for m in mentions[:20]:
        country = m.country or "?"
        traffic = m.raw_data.get("approx_traffic", 0)
        rank = m.raw_data.get("rank", "?")
        print(f"  [{country}] #{rank} {m.topic} (traffic: {traffic:,})")
