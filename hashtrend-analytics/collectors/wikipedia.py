"""
Wikipedia Pageviews Collector — Wikimedia REST API ile.

En çok görüntülenen Wikipedia makalelerini toplar.
Tamamen ücretsiz, rate limit yok (makul kullanımda).

API: https://wikimedia.org/api/rest_v1/
Endpoint: /metrics/pageviews/top/{project}/{access}/{year}/{month}/{day}
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention


class WikipediaCollector(BaseCollector):
    SOURCE_NAME = "wikipedia"
    COLLECT_INTERVAL_MINUTES = 120  # 2 saatte bir

    BASE_URL = "https://wikimedia.org/api/rest_v1"

    # Takip edilecek Wikipedia dilleri
    PROJECTS = {
        "en.wikipedia": "GLOBAL",  # İngilizce → global trend
        "tr.wikipedia": "TR",      # Türkçe → Türkiye trendi
    }

    # Filtrelenecek sayfalar (her zaman üstte olan genel sayfalar)
    EXCLUDE_TITLES = {
        "Main_Page", "Special:Search", "-", "Wikipedia:Featured_pictures",
        "Portal:Current_events", "Special:CreateAccount",
        "Special:ElectronSignup", "Ana_Sayfa", "Wikipedia:About",
        "wiki.phtml", "Haber", "Anasayfa",
    }
    EXCLUDE_CONTAINS = ("bölümleri listesi", "Dosya:", "logo.png", "şampiyonları listesi", "padişahları listesi")
    EXCLUDE_PREFIXES = (
        "Special:", "Wikipedia:", "File:", "Kategori:", "Category:",
        "Portal:", "Template:", "Talk:", "User:", "Help:",
        "Özel:", "Vikipedi:", "Şablon:", "Tartışma:",
    )

    TOP_N = 30  # Her projeden en popüler N makale

    def collect(self) -> list[RawMention]:
        """Senkron wrapper."""
        return asyncio.run(self._async_collect())

    async def _async_collect(self) -> list[RawMention]:
        """Tüm projelerden en popüler makaleleri topla."""
        all_mentions = []

        # Dünün tarihini kullan (bugünün verisi henüz tamamlanmamış olabilir)
        yesterday = datetime.utcnow() - timedelta(days=1)
        year = yesterday.strftime("%Y")
        month = yesterday.strftime("%m")
        day = yesterday.strftime("%d")

        async with aiohttp.ClientSession(
            headers={
                "User-Agent": "HashTrend/1.0 (batuhansen340@gmail.com) "
                              "Trend analytics tool",
            }
        ) as session:
            for project, country in self.PROJECTS.items():
                try:
                    mentions = await self._fetch_top_pages(
                        session, project, country, year, month, day
                    )
                    all_mentions.extend(mentions)
                except Exception as e:
                    logger.warning(f"[wikipedia] {project} hatası: {e}")
                    continue

        return all_mentions

    async def _fetch_top_pages(
        self,
        session: aiohttp.ClientSession,
        project: str,
        country: str,
        year: str,
        month: str,
        day: str,
    ) -> list[RawMention]:
        """Tek bir projenin en popüler sayfalarını getir."""
        url = (
            f"{self.BASE_URL}/metrics/pageviews/top/"
            f"{project}/all-access/{year}/{month}/{day}"
        )

        mentions = []

        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[wikipedia] {project} HTTP {resp.status}"
                    )
                    return []

                data = await resp.json()

                # Response format: {"items": [{"articles": [...]}]}
                items = data.get("items", [])
                if not items:
                    return []

                articles = items[0].get("articles", [])

                for article in articles[:self.TOP_N + 20]:  # Fazla al, filtrele
                    title = article.get("article", "")
                    views = article.get("views", 0)
                    rank = article.get("rank", 0)

                    # Genel sayfaları filtrele
                    if title in self.EXCLUDE_TITLES:
                        continue
                    if title.startswith(self.EXCLUDE_PREFIXES):
                        continue
                    if hasattr(self, "EXCLUDE_CONTAINS") and any(x in title for x in self.EXCLUDE_CONTAINS):
                        continue

                    # Başlığı temizle: alt çizgileri boşluğa çevir
                    clean_title = title.replace("_", " ")

                    if len(mentions) >= self.TOP_N:
                        break

                    mentions.append(
                        RawMention(
                            source=self.SOURCE_NAME,
                            topic=clean_title,
                            mention_count=views,
                            country=country,
                            url=f"https://{project}.org/wiki/{title}",
                            raw_data={
                                "project": project,
                                "views": views,
                                "rank": rank,
                                "date": f"{year}-{month}-{day}",
                                "type": "top_pageviews",
                            },
                        )
                    )

            logger.debug(
                f"[wikipedia] {project}: {len(mentions)} makale"
            )

        except Exception as e:
            logger.warning(f"[wikipedia] {project} fetch hatası: {e}")

        return mentions


# Standalone test
if __name__ == "__main__":
    collector = WikipediaCollector()
    mentions = collector.run()

    print(f"\n{'='*60}")
    print(f"Toplam {len(mentions)} Wikipedia mention toplandı")
    print(f"{'='*60}\n")

    for m in mentions[:20]:
        views = m.raw_data.get("views", 0)
        project = m.raw_data.get("project", "?")
        print(f"  [{project}] {m.topic} ({views:,} views)")
