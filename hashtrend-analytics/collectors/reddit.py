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
        self.session.headers.update({
            "User-Agent": "HashTrend/1.0 (trend analytics bot)"
        })

    def collect(self):
        all_mentions = []
        for sub in self.SUBREDDITS:
            try:
                mentions = self._fetch_subreddit(sub)
                all_mentions.extend(mentions)
                time.sleep(1.5)
            except Exception as e:
                logger.warning(f"[reddit] r/{sub} hatasi: {e}")
        return all_mentions

    def _fetch_subreddit(self, subreddit):
        url = f"https://www.reddit.com/r/{subreddit}/hot/.json?limit=10&t=day"
        mentions = []
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 429:
                time.sleep(5)
                return []
            if resp.status_code != 200:
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
