"""
AI Kategorizer — Claude Sonnet API ile otomatik konu sınıflandırma.

Her konuya şu kategorilerden birini atar:
Technology, Finance, Health, Politics, Entertainment,
Education, Science, Sports, Other
"""

from loguru import logger
from config.settings import settings


class Categorizer:
    """Claude API ile toplu kategori atama."""

    SYSTEM_PROMPT = """You are a trend categorizer and analyst. Given a list of trending topics,
assign EXACTLY ONE category and write a brief 1-sentence summary explaining why it is trending or what it is about.

Categories: Technology, Finance, Health, Politics, Entertainment, Education, Science, Sports, Other

Respond ONLY with a JSON array: [{"topic": "...", "category": "...", "summary": "..."}]
No explanation, no markdown, just raw JSON. Summary must be max 15 words, in English."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    def categorize(self, topics: list[str]) -> dict[str, str]:
        """
        Konu listesini kategorize et.
        Returns: {topic_name: category}
        """
        if not topics:
            return {}

        if not settings.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY yok — keyword bazlı fallback kullanılıyor")
            return self._fallback_categorize(topics)

        # Batch halinde gönder (max 30 konu per request, token tasarrufu)
        results = {}
        batch_size = 15

        for i in range(0, len(topics), batch_size):
            batch = topics[i : i + batch_size]
            batch_results = self._categorize_batch(batch)
            results.update(batch_results)

        logger.info(f"{len(results)} konu kategorize edildi")
        return results

    def _categorize_batch(self, topics: list[str]) -> dict[str, str]:
        """Tek bir batch'i Claude API ile kategorize et."""
        import json

        # Konu listesini numaralı olarak hazırla
        topic_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Categorize these trending topics:\n{topic_list}",
                    }
                ],
            )

            # Response'u parse et
            response_text = message.content[0].text.strip()
            # Markdown fence temizliği
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            data = json.loads(response_text)
            result = {}
            for item in data:
                result[item["topic"]] = {"category": item.get("category", "Other"), "summary": item.get("summary", "")}
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Claude JSON parse hatası: {e}")
            return self._fallback_categorize(topics)
        except Exception as e:
            logger.debug(f"Claude API fallback: {e}")
            return self._fallback_categorize(topics)

    def _fallback_categorize(self, topics: list[str]) -> dict[str, str]:
        """
        Claude API çalışmazsa keyword bazlı basit kategorizasyon.
        Production'da bu sadece fallback — ana yol Claude API.
        """
        # Keyword → Kategori eşlemesi
        keyword_map = {
            "Technology": [
                "ai", "gpt", "openai", "anthropic", "claude", "llm", "machine learning",
                "software", "app", "code", "programming", "developer", "tech", "api",
                "cloud", "startup", "github", "python", "javascript", "rust", "vite",
                "chip", "semiconductor", "robot", "automation", "cyber", "hacker",
                "browser", "linux", "windows", "apple", "google", "microsoft",
                "meta", "nvidia", "open source", "database", "algorithm", "docker",
                "react", "node", "typescript", "devops", "kubernetes", "aws", "azure",
                "compiler", "emacs", "vim", "copilot", "chatgpt", "gemini", "hugging",
                "webkit", "chromium", "firefox", "safari", "android", "ios",
                "server", "deploy", "frontend", "backend", "fullstack", "framework",
                "libreoffice", "pgadmin", "sql", "nosql", "redis", "postgres",
                "homelab", "self-host", "raspberry", "arduino", "iot",
            ],
            "Finance": [
                "bitcoin", "crypto", "stock", "market", "invest", "bank",
                "inflation", "economy", "gdp", "trade", "dollar", "euro",
                "fed", "interest rate", "earnings", "ipo", "fintech", "defi",
                "oracle", "debt", "revenue", "billion", "million", "funding",
                "venture", "seed round", "valuation", "acquisition", "acquire",
                "coal", "energy", "oil", "gas", "renewable", "solar",
            ],
            "Health": [
                "health", "medical", "vaccine", "disease", "hospital",
                "mental health", "drug", "fda", "cancer", "virus", "covid",
                "fitness", "nutrition", "surgery", "clinical", "therapy",
                "addiction", "brain", "neuroscience", "dna", "gene",
            ],
            "Politics": [
                "president", "election", "government", "congress", "senate",
                "policy", "war", "military", "nato", "sanctions",
                "democrat", "republican", "vote", "legislation", "diplomat",
                "trump", "biden", "netanyahu", "putin", "zelensky", "khamenei",
                "iran", "ukraine", "russia", "china", "israel", "palestine",
                "doge", "elon musk", "political", "judge", "court", "ruling",
                "constitutional", "unconstitutional", "law", "legal", "lawsuit",
                "fbi", "cia", "nsa", "surveillance", "privacy", "censorship",
                "minister", "parliament", "regime", "coup", "protest",
                "refugee", "immigration", "border", "tariff", "embargo",
                "massacre", "genocide", "bombing", "missile", "strait",
                "hegseth", "leavitt", "maga", "gop",
            ],
            "Entertainment": [
                "movie", "film", "music", "game", "gaming", "netflix",
                "disney", "concert", "album", "tv show", "celebrity",
                "oscar", "grammy", "trailer", "stream", "anime",
                "series", "one piece", "manga", "marvel", "dc",
                "spotify", "youtube", "tiktok", "twitch", "podcast",
                "muppet", "bride", "horror", "comedy", "drama",
            ],
            "Education": [
                "education", "university", "school", "course", "learn",
                "student", "teacher", "tutorial", "certificate", "degree",
                "training", "bootcamp", "scholarship", "academic", "professor",
            ],
            "Science": [
                "science", "research", "study", "space", "nasa", "physics",
                "biology", "climate", "environment", "energy", "quantum",
                "experiment", "discovery", "journal", "arxiv", "nature",
                "telescope", "mars", "moon", "satellite", "rocket",
                "earthquake", "volcano", "ocean", "species", "evolution",
                "boeing", "aircraft", "aviation",
            ],
            "Sports": [
                "football", "soccer", "basketball", "tennis", "nba", "nfl",
                "champions league", "world cup", "olympics", "match",
                "score", "player", "team", "coach", "tournament",
                "cricket", "t20", "baseball", "f1", "formula", "grand prix",
                "transfer", "league", "goal", "striker", "goalkeeper",
                "haaland", "messi", "ronaldo", "samson",
                "nfl", "super bowl", "playoff", "draft", "doubs", "smith nfl",
            ],
        }

        results = {}

        for topic in topics:
            topic_lower = topic.lower()
            assigned = "Other"

            best_match_count = 0
            for category, keywords in keyword_map.items():
                match_count = sum(1 for kw in keywords if kw in topic_lower)
                if match_count > best_match_count:
                    best_match_count = match_count
                    assigned = category

            results[topic] = {"category": assigned, "summary": ""}

        return results


# Standalone test
if __name__ == "__main__":
    categorizer = Categorizer()

    test_topics = [
        "GPT-5 Released by OpenAI",
        "Bitcoin crashes below 50k",
        "New Cancer Treatment Shows Promise",
        "Champions League Final Results",
        "Taylor Swift World Tour 2026",
        "NASA discovers new exoplanet",
        "Federal Reserve raises interest rates",
    ]

    # Fallback test (API key olmadan)
    results = categorizer._fallback_categorize(test_topics)

    print(f"\n{'='*60}")
    print("KATEGORİZASYON SONUÇLARI (fallback)")
    print(f"{'='*60}\n")

    for topic, category in results.items():
        print(f"  [{category:15}] {topic}")
