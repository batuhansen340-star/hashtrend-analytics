"""
Music Charts Collector v2 — iTunes RSS Top Songs (Spotify Charts yerine).

Eski v1 (spotifycharts.com) 2023'te kapatıldı. v2 Apple'ın iTunes top songs
RSS feed'ini kullanır — public, JSON, free.

SOURCE_NAME = "spotify" geriye uyumluluk için korunur (DB schema değişmesin).
İçerik artık Apple Music charts'tan gelir.
"""

import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


COUNTRIES = [("us", "GLOBAL"), ("tr", "TR")]
LIMIT_PER_COUNTRY = 25


class SpotifyCollector(BaseCollector):
    SOURCE_NAME = "spotify"  # geriye uyumlu; içerik Apple Music charts
    COLLECT_INTERVAL_MINUTES = 360

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
                logger.warning(f"[music] {code} fetch hatası: {e}")
        return mentions

    def _fetch_country(self, code: str, label: str) -> list[RawMention]:
        url = (
            f"https://itunes.apple.com/{code}/rss/topsongs/"
            f"limit={LIMIT_PER_COUNTRY}/json"
        )
        resp = self.session.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[music] {code} HTTP {resp.status_code}")
            return []
        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"[music] {code} JSON parse fail: {e}")
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
            artist = ((entry.get("im:artist") or {}).get("label") or "").strip()
            if not name:
                continue
            topic = f"{name} — {artist}" if artist else name
            link = ""
            for link_entry in entry.get("link") or []:
                attrs = link_entry.get("attributes") or {}
                if attrs.get("rel") == "alternate":
                    link = attrs.get("href") or ""
                    break
            mentions.append(RawMention(
                source=self.SOURCE_NAME,
                topic=topic,
                mention_count=LIMIT_PER_COUNTRY - rank + 1,
                country=label,
                url=link or None,
                raw_data={
                    "type": "music_chart",
                    "rank": rank,
                    "song": name,
                    "artist": artist,
                    "country_code": code,
                },
            ))
        logger.info(f"[music] {code}: {len(mentions)} şarkı")
        return mentions


if __name__ == "__main__":
    collector = SpotifyCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} müzik chart")
    for m in mentions[:10]:
        rank = m.raw_data.get("rank", "?")
        print(f"  [#{rank:>2} {m.country}] {m.topic[:60]}")
