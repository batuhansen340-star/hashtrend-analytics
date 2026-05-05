"""
App Idea Generator — Trend → uygulama fikri + retention skoru.

HashTrend'i Exploding Topics'ten ayıran katman: Sadece "şu trend var" değil,
"bu trend için şu uygulamayı yap, retention 0.74" diyor.

LLM: Ollama Cloud gpt-oss:120b ($0 marjinal, kullanıcı subscription'ı var).
Output schema: structured JSON, Pydantic ile validated.
Country-aware: TR vs GLOBAL pazar dinamikleri prompt'ta ayrı.

NOT: Bu LLM-based smart scoring. Gerçek custom ML model (LightGBM ile
retention prediction) v1.1'e bırakıldı — yeterli training data toplanınca.
"""

import json
import os
from loguru import logger
from config.settings import settings


SYSTEM_PROMPT = """You are a senior product strategist + ML engineer + market analyst.
Given a TRENDING TOPIC and its METADATA, generate 3 application ideas with calibrated retention scores.

CRITICAL RULES:
1. Each idea MUST solve a real pain (painkiller, not vitamin)
2. ML/AI/data component is the core, not just "let's add AI"
3. MVP <= 30 days for solo developer
4. If TARGET_COUNTRY is 'TR': consider Turkish market specifics
   - Faladdin shutdown opportunity (astrology), KOSGEB grants, retail investor 7M
   - Local ecosystem: Webrazzi audience, Ekşi Sözlük community
5. If 'GLOBAL': USA/EU primary
6. retention_score (0-1): probability user opens app on day 7 after install
   - 0.0-0.3: unlikely (one-shot utility)
   - 0.4-0.6: medium (some recurring value)
   - 0.7-0.9: high (daily/weekly recurring need)
7. feasibility_score (0-1): likelihood solo dev ships MVP in <30 days
8. NEVER fabricate competitor names — if unsure, use generic descriptors

Output STRICT JSON, no markdown, no explanation:
{
  "country_context": "1-sentence about the target market dynamic",
  "ideas": [
    {
      "name": "AppName",
      "tagline": "10-word value prop",
      "problem": "1-2 sentences on pain",
      "solution": "1-2 sentences on approach",
      "tech_stack": ["FastAPI","Supabase",...],
      "mvp_days": 21,
      "retention_score": 0.74,
      "feasibility_score": 0.82,
      "market_size_estimate": "TR retail invest: ~7M",
      "competitors": ["GenericTraderApp1","GenericApp2"],
      "differentiation": "what HashTrend-driven app does that competitors don't",
      "confidence": "high|medium|low"
    }
  ]
}

If trend metadata is too sparse: {"country_context": "...", "ideas": [], "reason": "..."}.
"""


class AppIdeaGenerator:
    """Trend → uygulama fikri + retention/feasibility scoring."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            api_key = (
                os.getenv("OLLAMA_API_KEY")
                or getattr(settings, "OLLAMA_API_KEY", None)
            )
            self._client = OpenAI(
                base_url="https://ollama.com/v1",
                api_key=api_key,
                timeout=60.0,
                max_retries=1,
            )
        return self._client

    def _has_llm_key(self) -> bool:
        key = os.getenv("OLLAMA_API_KEY") or getattr(settings, "OLLAMA_API_KEY", None)
        return bool(key) and "..." not in (key or "") and len(key or "") >= 16

    def generate(self, trend: dict, country: str = "GLOBAL") -> dict:
        """
        Trend için 3 uygulama fikri + skorlar üret.

        Args:
            trend: dict with topic_name, sources, cts_score, velocity, mention_count
            country: 'GLOBAL' veya ISO alpha-2 ('TR', 'US', 'GB', ...)

        Returns:
            {"country_context": "...", "ideas": [{name, retention_score, ...}]}
        """
        if not self._has_llm_key():
            logger.warning("[app_idea] OLLAMA_API_KEY yok — atlandı")
            return {"country_context": "", "ideas": [], "reason": "no_llm_key"}

        prompt = self._build_user_prompt(trend, country)
        model = os.getenv("OLLAMA_DIRECTOR_MODEL", "gpt-oss:120b")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,  # biraz creative ama stable
                max_tokens=2000,
            )
            text = (response.choices[0].message.content or "").strip()
            text = self._strip_markdown_fence(text)
            data = json.loads(text)
            return self._validate(data)
        except json.JSONDecodeError as e:
            logger.warning(f"[app_idea] JSON parse fail: {e}")
            return {"country_context": "", "ideas": [], "reason": "json_parse_error"}
        except Exception as e:
            logger.warning(f"[app_idea] LLM hatası: {e}")
            return {"country_context": "", "ideas": [], "reason": "llm_error"}

    def _build_user_prompt(self, trend: dict, country: str) -> str:
        sources = trend.get("sources") or {}
        if isinstance(sources, dict):
            src_str = ", ".join(f"{k}({v})" for k, v in list(sources.items())[:5])
        else:
            src_str = ", ".join(map(str, sources[:5]))
        return (
            f"TRENDING TOPIC: {trend.get('topic_name','')}\n"
            f"CATEGORY: {trend.get('category','Unknown')}\n"
            f"CTS_SCORE: {trend.get('cts_score',0):.1f}/100\n"
            f"VELOCITY: {trend.get('velocity',0):.4f}\n"
            f"MENTIONS: {trend.get('mention_count',0)}\n"
            f"SOURCES: {src_str}\n"
            f"DETECTED_COUNTRY: {trend.get('country','GLOBAL')}\n"
            f"TARGET_COUNTRY: {country}\n"
            f"\nGenerate 3 application ideas as STRICT JSON."
        )

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl > 0:
                text = text[first_nl + 1:]
            if text.endswith("```"):
                text = text[:-3]
        return text.strip()

    @staticmethod
    def _validate(data: dict) -> dict:
        """Schema check — ideas listesi, her birinde name + score'lar."""
        ideas = data.get("ideas", [])
        cleaned = []
        for it in ideas:
            if not it.get("name"):
                continue
            cleaned.append({
                "name": str(it.get("name"))[:200],
                "tagline": str(it.get("tagline", ""))[:300],
                "problem": str(it.get("problem", ""))[:1000],
                "solution": str(it.get("solution", ""))[:1000],
                "tech_stack": it.get("tech_stack", []) if isinstance(it.get("tech_stack"), list) else [],
                "mvp_days": max(1, min(365, int(it.get("mvp_days", 30) or 30))),
                "retention_score": max(0.0, min(1.0, float(it.get("retention_score", 0.5) or 0.5))),
                "feasibility_score": max(0.0, min(1.0, float(it.get("feasibility_score", 0.5) or 0.5))),
                "market_size_estimate": str(it.get("market_size_estimate", ""))[:300],
                "competitors": it.get("competitors", []) if isinstance(it.get("competitors"), list) else [],
                "differentiation": str(it.get("differentiation", ""))[:500],
                "confidence": str(it.get("confidence", "medium")).lower()[:10],
            })
        return {
            "country_context": str(data.get("country_context", ""))[:500],
            "ideas": cleaned,
        }
