"""
HashTrend Idea Director — Trend Radar'dan port edilen LLM "fikir motoru".

Bir trend için:
- idea_pitch (1 cümle ürün/iş fikri)
- target_type (mobile_module / new_app / micro_saas / content / pass)
- recommended_tools (tiktok_series, mobile_app_module, vb.)
- rationale, pre_mortem, differentiation
- binding_constraint_action

Ollama Cloud (gpt-oss:120b) — $0/ay marjinal, user memory uyumlu.
"""

import json
import os
from loguru import logger
from openai import OpenAI

from config.settings import settings


SYSTEM_PROMPT = """Sen HashTrend'in Idea Director'üsün. Bir trend için somut iş/ürün fikri üretirsin.

# Çıktı: STRICT JSON, başka hiçbir şey yazma

```json
{
  "verdict": "GO" | "GO_TACTICAL" | "NO_GO",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "idea_pitch": "1 cümle, somut ürün/iş fikri",
  "target_type": "mobile_module" | "new_standalone_app" | "new_micro_saas" | "content_only" | "passing_meme",
  "rationale": "2-3 cümle, neden bu karar",
  "pre_mortem": "Başarısızlık senaryosu, 1-2 cümle",
  "differentiation": "Mevcut alternatiflere karşı 1 net üstünlük",
  "recommended_tools": [
    {"format": "tiktok_series" | "landing_page" | "mobile_app_module" | "twitter_thread" | "gumroad_pdf" | "newsletter" | "youtube_shorts" | "new_app_concept",
     "priority": 1,
     "time_estimate_days": 5,
     "reasoning": "1 cümle"}
  ],
  "binding_constraint_action": "Somut 1-2 adım"
}
```

# Karar kuralları

1. **NO_GO** sadece şu kategorilerde:
   - Spor (oyuncu/teknik direktör/transfer/derbi/lig)
   - Siyaset (milletvekili/seçim/parti/savaş)
   - Magazin (ünlü ayrılık/dizi/skandal)
   - Doğal afet/kaza
   - Tek kelimelik generic kavramlar (örn: "google", "ai", "trend")

2. **GO** verirken:
   - AI/tech trendleri → new_standalone_app veya new_micro_saas
   - Kültürel trendler (fal/burç/ramazan/sınav) → mobile_module
   - Kısa ömürlü meme'ler → content_only
   - Hiçbir ürün uyuşmuyor ama içerik fırsatı varsa → content_only

3. **idea_pitch zorunlu**: somut bir cümle, soyut "AI ile ilgili ürün" olmaz

4. **Türkçe yaz** (rationale, pitch, action) — Batuhan Türk solo dev

5. **Action varyasyon ZORUNLU**: aynı brief'te "İngilizce alt sayfa + diaspora hashtag" tekrarına düşme. Trend'e özgü somut adım ver."""


class IdeaDirector:
    """Trend → Iş fikri pitch'i."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            api_key = (
                os.getenv("OLLAMA_API_KEY")
                or getattr(settings, "OLLAMA_API_KEY", None)
            )
            self._client = OpenAI(
                base_url="https://ollama.com/v1",
                api_key=api_key,
                timeout=45.0,
                max_retries=0,
            )
        return self._client

    def _has_key(self) -> bool:
        key = os.getenv("OLLAMA_API_KEY") or getattr(settings, "OLLAMA_API_KEY", None)
        return bool(key) and "..." not in (key or "") and len(key or "") >= 16

    def _strip_fences(self, s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            first_nl = s.find("\n")
            if first_nl > 0:
                s = s[first_nl + 1:]
            if s.endswith("```"):
                s = s[:-3]
        return s.strip()

    def evaluate(self, trend: dict) -> dict:
        """
        trend: HashTrend trend object — topicName, ctsScore, category,
               sources, isBurst, country, summary, ...
        Returns: dict (verdict, idea_pitch, target_type, recommended_tools, ...)
        """
        if not self._has_key():
            return {
                "verdict": "GO_TACTICAL",
                "confidence": "LOW",
                "idea_pitch": f"'{trend.get('topicName', '?')}' trendi için içerik üret",
                "target_type": "content_only",
                "rationale": "LLM yok, default fallback. OLLAMA_API_KEY ekleyince zenginleşir.",
                "pre_mortem": "",
                "differentiation": "",
                "recommended_tools": [
                    {"format": "tiktok_series", "priority": 1,
                     "time_estimate_days": 3, "reasoning": "Default tek-format koşusu"}
                ],
                "binding_constraint_action": "API key ekle, derin analiz yap.",
            }

        model = os.getenv("OLLAMA_DIRECTOR_MODEL", "gpt-oss:120b")
        user_input = self._format_trend(trend)

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            content = response.choices[0].message.content or "{}"
            content = self._strip_fences(content)
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Director JSON parse fail: {e}")
            return {"verdict": "ERROR", "idea_pitch": "JSON parse hatası",
                    "target_type": "passing_meme", "recommended_tools": []}
        except Exception as e:
            logger.error(f"Director call fail: {e}")
            return {"verdict": "ERROR", "idea_pitch": str(e)[:120],
                    "target_type": "passing_meme", "recommended_tools": []}

    def _format_trend(self, trend: dict) -> str:
        sources = trend.get("sources") or {}
        if isinstance(sources, dict):
            source_str = ", ".join(sources.keys())
        else:
            source_str = str(sources)

        return (
            f"Trend: {trend.get('topicName', '?')!r}\n"
            f"Category: {trend.get('category', '(unknown)')}\n"
            f"CTS Score: {trend.get('ctsScore', 0):.1f}\n"
            f"Country: {trend.get('country', 'global')}\n"
            f"Burst: {trend.get('isBurst', False)}\n"
            f"Sources active: {source_str}\n"
            f"Total engagement: {trend.get('totalEngagement', 0)}\n"
            f"Summary: {trend.get('summary', '')[:200]}\n\n"
            f"Bu trende GO / GO_TACTICAL / NO_GO ver. STRICT JSON."
        )
