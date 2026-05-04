"""
App Trends Collector v2 — iTunes RSS Top Free Apps.

Eski v1 (play.google.com/store/apps/trending) endpoint kapanmıştı (404).
v2 Apple'ın iTunes RSS feed'ini kullanır — public, JSON, auth yok.

Endpoint: itunes.apple.com/<country>/rss/topfreeapplications/limit=N/json
Country: US (global proxy) + TR (yerel pazar)
"""

import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


COUNTRIES = [("us", "GLOBAL"), ("tr", "TR")]
LIMIT_PER_COUNTRY = 25


class AppTrendsCollector(BaseCollector):
    SOURCE_NAME = "apptrends"
    COLLECT_INTERVAL_MINUTES = 240

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HashTrendAnalytics/2.0 (https://hashtrend.app)",
            "Accept": "application/json",
        })

    def collect(self) -> list[RawMention]:
        mentions: list[RawMention] = []
        for code, label in COUNTRIES:
            try:
                mentions.extend(self._fetch_country(code, label))
            except Exception as e:
                logger.warning(f"[apptrends] {code} fetch hatası: {e}")
        return mentions

    def _fetch_country(self, code: str, label: str) -> list[RawMention]:
        url = (
            f"https://itunes.apple.com/{code}/rss/topfreeapplications/"
            f"limit={LIMIT_PER_COUNTRY}/json"
        )
        resp = self.session.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[apptrends] {code} HTTP {resp.status_code}")
            return []
        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"[apptrends] {code} JSON parse fail: {e}")
            return []
        entries = (data.get("feed") or {}).get("entry") or []
        # iTunes RSS bazen entry'yi tek dict olarak döndürür (array değil)
        if isinstance(entries, dict):
            entries = [entries]
        mentions = []
        for rank, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue  # defensive: bazı entries str olabilir
            name = ((entry.get("im:name") or {}).get("label") or "").strip()
            if not name:
                continue
            cat = ((entry.get("category") or {}).get("attributes") or {}).get("label", "")
            artist = ((entry.get("im:artist") or {}).get("label") or "").strip()
            link = ""
            for link_entry in entry.get("link") or []:
                attrs = link_entry.get("attributes") or {}
                if attrs.get("rel") == "alternate":
                    link = attrs.get("href") or ""
                    break
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=name,
                mention_count=LIMIT_PER_COUNTRY - rank + 1,
                country=label,
                url=link or None,
                raw_data={
                    "type": "app_chart",
                    "rank": rank,
                    "category": cat,
                    "developer": artist,
                    "country_code": code,
                },
            ))
        logger.info(f"[apptrends] {code}: {len(mentions)} app")
        return mentions


if __name__ == "__main__":
    collector = AppTrendsCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} app trend")
    for m in mentions[:10]:
        rank = m.raw_data.get("rank", "?")
        print(f"  [#{rank:>2} {m.country}] {m.topic[:60]}")
