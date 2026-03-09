"""
Reddit Collector — PRAW (Python Reddit API Wrapper) ile.

Toplanan veriler:
- Popüler subreddit'lerdeki hot post'lar
- Subreddit bazlı trending konular
- Upvote/comment bazlı popülerlik skoru

Rate limit: 100 req/dk (OAuth free tier) — yeterli.
"""

from datetime import datetime
from loguru import logger

from collectors.base import BaseCollector
from core.models import RawMention
from config.settings import settings


class RedditCollector(BaseCollector):
    SOURCE_NAME = "reddit"
    COLLECT_INTERVAL_MINUTES = 30  # 30 dakikada bir

    # Takip edilecek subreddit'ler (genel + kategori bazlı)
    SUBREDDITS = {
        # Genel / Trending
        "all": {"category": "General", "limit": 25},
        "popular": {"category": "General", "limit": 15},
        # Teknoloji
        "technology": {"category": "Technology", "limit": 10},
        "programming": {"category": "Technology", "limit": 10},
        "artificial": {"category": "Technology", "limit": 10},
        "MachineLearning": {"category": "Technology", "limit": 10},
        # Finans
        "finance": {"category": "Finance", "limit": 10},
        "cryptocurrency": {"category": "Finance", "limit": 10},
        # Bilim
        "science": {"category": "Science", "limit": 10},
        # Dünya haberleri
        "worldnews": {"category": "Politics", "limit": 10},
        # Eğitim
        "learnprogramming": {"category": "Education", "limit": 10},
    }

    def __init__(self):
        super().__init__()
        self._reddit = None

    @property
    def reddit(self):
        """Lazy initialization — API credentials gerekli."""
        if self._reddit is None:
            import praw

            if not settings.REDDIT_CLIENT_ID:
                raise ValueError(
                    "Reddit API credentials eksik. "
                    ".env dosyasında REDDIT_CLIENT_ID ayarla."
                )

            self._reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
            )
            logger.info("[reddit] PRAW bağlantısı kuruldu")
        return self._reddit

    def collect(self) -> list[RawMention]:
        """Tüm subreddit'lerden hot post'ları topla."""
        all_mentions = []

        for subreddit_name, config in self.SUBREDDITS.items():
            try:
                mentions = self._collect_subreddit(
                    subreddit_name,
                    config["category"],
                    config["limit"],
                )
                all_mentions.extend(mentions)
            except Exception as e:
                logger.warning(
                    f"[reddit] r/{subreddit_name} hatası: {e}"
                )
                continue

        return all_mentions

    def _collect_subreddit(
        self, name: str, category: str, limit: int
    ) -> list[RawMention]:
        """Tek bir subreddit'ten hot post'ları topla."""
        mentions = []
        subreddit = self.reddit.subreddit(name)

        for post in subreddit.hot(limit=limit):
            # Pinned post'ları atla
            if post.stickied:
                continue

            # Popülerlik skoru: upvote + yorum sayısı ağırlıklı
            popularity = post.score + (post.num_comments * 2)

            mentions.append(
                RawMention(
                    source=self.SOURCE_NAME,
                    topic=post.title,
                    mention_count=popularity,
                    raw_data={
                        "subreddit": name,
                        "category_hint": category,
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "upvote_ratio": post.upvote_ratio,
                        "created_utc": post.created_utc,
                        "permalink": post.permalink,
                        "is_self": post.is_self,
                    },
                    url=f"https://reddit.com{post.permalink}",
                )
            )

        logger.debug(f"[reddit] r/{name}: {len(mentions)} post")
        return mentions


# Standalone çalıştırma
if __name__ == "__main__":
    collector = RedditCollector()
    mentions = collector.run()

    print(f"\n{'='*60}")
    print(f"Toplam {len(mentions)} Reddit mention toplandı")
    print(f"{'='*60}\n")

    # En popüler 15 post
    sorted_mentions = sorted(
        mentions, key=lambda m: m.mention_count, reverse=True
    )
    for m in sorted_mentions[:15]:
        sub = m.raw_data.get("subreddit", "?")
        print(f"  [r/{sub}] {m.topic[:80]} (skor: {m.mention_count})")
