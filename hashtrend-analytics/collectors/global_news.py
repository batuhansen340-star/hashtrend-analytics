"""Global News Collector — Buyuk haber ajanslari RSS feed'leri."""

import requests
from datetime import datetime
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class GlobalNewsCollector(BaseCollector):
    SOURCE_NAME = "global_news"
    COLLECT_INTERVAL_MINUTES = 120

    FEEDS = {
        "Reuters": ("https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best", "GLOBAL"),
        "BBC World": ("http://feeds.bbci.co.uk/news/world/rss.xml", "GB"),
        "BBC Tech": ("http://feeds.bbci.co.uk/news/technology/rss.xml", "GB"),
        "CNN Top": ("http://rss.cnn.com/rss/edition.rss", "US"),
        "CNN Tech": ("http://rss.cnn.com/rss/edition_technology.rss", "US"),
        "Al Jazeera": ("https://www.aljazeera.com/xml/rss/all.xml", "GLOBAL"),
        "DW": ("https://rss.dw.com/rdf/rss-en-all", "DE"),
        "France24": ("https://www.france24.com/en/rss", "FR"),
        "NHK World": ("https://www3.nhk.or.jp/rss/news/cat0.xml", "JP"),
        "ABC Australia": ("https://www.abc.net.au/news/feed/2942460/rss.xml", "AU"),
        "Times of India": ("https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "IN"),
        "Hurriyet EN": ("https://www.hurriyetdailynews.com/rss.aspx", "TR"),
        "Korea Herald": ("http://www.koreaherald.com/common/rss_xml.php?ct=102", "KR"),
        "Folha BR": ("https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "BR"),
        "El Pais": ("https://feeds.elpais.com/mrss-s/pages/ep/site/english.elpais.com/portada", "ES"),
    }

    def collect(self) -> list[RawMention]:
        mentions = []
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        for source_name, (url, country) in self.FEEDS.items():
            try:
                resp = session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")

                for item in items[:8]:
                    title = item.find("title")
                    link = item.find("link")
                    if not title:
                        continue

                    t = title.text.strip()
                    if not t or len(t) < 10:
                        continue

                    # CDATA temizligi
                    t = t.replace("<![CDATA[", "").replace("]]>", "").strip()

                    mentions.append(RawMention(
                        topic=t,
                        source=self.SOURCE_NAME,
                        mention_count=2000,
                        url=link.text.strip() if link else "",
                        collected_at=self.collected_at,
                        country=country,
                    ))

                logger.debug(f"[{self.SOURCE_NAME}] {source_name}: {min(len(items), 8)} haber")
                import time
                time.sleep(0.3)

            except Exception as e:
                logger.debug(f"[{self.SOURCE_NAME}] {source_name} hata: {e}")

        return mentions
