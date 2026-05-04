import time
import requests
from loguru import logger
from collectors.base import BaseCollector
from core.models import RawMention


class RedditCollector(BaseCollector):
    SOURCE_NAME = "reddit"
    COLLECT_INTERVAL_MINUTES = 30
    SUBREDDITS = [
        "technology", "programming", "artificial",
        "MachineLearning", "finance", "cryptocurrency",
        "science", "worldnews", "learnprogramming",
        "SideProject", "startups",
        "turkey", "germany", "france", "india",
        "japan", "korea", "brazil", "mexico",
        "unitedkingdom", "canada", "australia",
        "spain", "italy", "indonesia", "europe",
    ]

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        # Reddit policy: descriptive User-Agent zorunlu. Generic Chrome UA bot
        # detection'a takılıyor. Format: <platform>:<app>:<version> (by /u/<owner>)
        self.session.headers.update({
            "User-Agent": "web:HashTrendAnalytics:2.0 (by /u/hashtrend_bot; contact@hashtrend.app)",
            "Accept": "application/json",
        })

    def collect(self):
        all_mentions = []
        # 1. r/popular global — tek istek, kategorisiz çoklu trend
        all_mentions.extend(self._fetch_popular(geo=None))
        time.sleep(2)
        # 2. r/popular TR — TR pazarı için
        all_mentions.extend(self._fetch_popular(geo="TR"))
        time.sleep(2)
        # 3. Kategorize edilmiş subreddit'ler — niche trend bulmak için
        for sub in self.SUBREDDITS:
            try:
                mentions = self._fetch_subreddit(sub)
                all_mentions.extend(mentions)
                time.sleep(2)
            except Exception as e:
                logger.warning(f"[reddit] r/{sub} hatasi: {e}")
        return all_mentions

    def _fetch_popular(self, geo=None):
        """r/popular.json — Reddit'in global popüler post'ları, opsiyonel ülke filtresi."""
        params = "limit=30"
        if geo:
            params += f"&geo_filter={geo}"
        url = f"https://www.reddit.com/r/popular.json?{params}"
        mentions = []
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"[reddit] popular (geo={geo}) HTTP {resp.status_code}")
                return []
            data = resp.json()
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                title = p.get("title", "").strip()
                score = p.get("score", 0)
                if not title or score < 100:
                    continue
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=title,
                    mention_count=score,
                    country=geo,
                    url=f"https://reddit.com{p.get('permalink', '')}",
                    raw_data={
                        "subreddit": p.get("subreddit", "popular"),
                        "score": score,
                        "num_comments": p.get("num_comments", 0),
                        "type": "reddit_popular",
                        "geo": geo or "global",
                    },
                ))
            logger.info(f"[reddit] popular (geo={geo or 'global'}): {len(mentions)} post")
        except Exception as e:
            logger.warning(f"[reddit] popular fetch hatasi: {e}")
        return mentions

    def _fetch_subreddit(self, subreddit):
        url = f"https://www.reddit.com/r/{subreddit}/hot/.json?limit=10&t=day"
        mentions = []
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 429:
                time.sleep(10)
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"[reddit] r/{subreddit} 429 retry HTTP {resp.status_code}")
                    return []
            if resp.status_code != 200:
                logger.warning(f"[reddit] r/{subreddit} HTTP {resp.status_code}")
                return []
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                p = post.get("data", {})
                title = p.get("title", "").strip()
                score = p.get("score", 0)
                if not title or score < 5:
                    continue
                permalink = p.get("permalink", "")
                mentions.append(RawMention(
                    source=self.SOURCE_NAME,
                    topic=title,
                    mention_count=score,
                    url=f"https://reddit.com{permalink}",
                    raw_data={
                        "subreddit": subreddit,
                        "score": score,
                        "num_comments": p.get("num_comments", 0),
                        "type": "reddit_hot",
                    },
                ))
            logger.debug(f"[reddit] r/{subreddit}: {len(mentions)} post")
        except Exception as e:
            logger.warning(f"[reddit] r/{subreddit} fetch hatasi: {e}")
        return mentions


if __name__ == "__main__":
    collector = RedditCollector()
    mentions = collector.run()
    print(f"Toplam {len(mentions)} Reddit mention")
    for m in mentions[:15]:
        sub = m.raw_data.get("subreddit", "?")
        score = m.raw_data.get("score", 0)
        print(f"  [r/{sub}] {m.topic[:60]} ({score:,} upvote)")
