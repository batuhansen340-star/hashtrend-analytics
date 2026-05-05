"""
Viral Content Generator (Influencer Fabrikası) — Trend → video fikri + viral skoru.

HashTrend'e bağlı influencer'lar için: "Bu trend var, şu hook'la TikTok video
çeksen viral_score 0.82" gibi yönlendirme.

LLM: Ollama Cloud gpt-oss:120b ($0 marjinal).
Output: structured JSON, platform-aware (TikTok/Instagram/YouTube Shorts).
Country-aware: TR audience (Z kuşağı, Ekşi Sözlük dili) vs GLOBAL.

NOT: viral_score şu an LLM-based heuristic. Gerçek ML model (geçmiş viral
video pattern'leri ile training) v1.1.
"""

import json
import os
from loguru import logger
from config.settings import settings


SYSTEM_PROMPT = """You are a viral content strategist who has helped 100+ creators get 1M+ views.
Given a TRENDING TOPIC and TARGET PLATFORM, generate 3 short-form video ideas with calibrated viral scores.

PLATFORM-SPECIFIC RULES:
- TikTok: 15-60s, hook in first 2s, vertical, music/sound critical, fast cuts
- Instagram Reels: 15-90s, similar to TikTok but more polished, trending audio
- YouTube Shorts: 15-60s, slightly more "value/info" tilt, retention >50% target

VIRAL SCORE CALIBRATION (0-1):
- 0.0-0.3: weak hook, generic, low share probability
- 0.4-0.6: solid concept, decent reach (10K-50K view)
- 0.7-0.9: strong hook + emotional trigger + sharable angle (100K+ likely)

COUNTRY-AWARE:
- TR: Türkçe doğal akıcı, Ekşi Sözlük tonu, "kanka", local references (mahalle, fiyatlar TL, ünlü Türk influencer)
- GLOBAL: English, US/UK pop culture refs, monetization-friendly hooks

CRITICAL — NEVER:
- Fabricate creator/influencer names
- Suggest illegal/harmful content (gambling, MLM, fake reviews)
- Use clickbait that doesn't deliver

Output STRICT JSON, no markdown:
{
  "platform_context": "1-sentence about why this platform fits the trend",
  "video_ideas": [
    {
      "hook": "First 2 seconds — exact words a creator says",
      "format": "60s hook+payoff" | "3-part series" | "duet/stitch" | "tutorial",
      "description": "What happens in the video, 2-3 sentences",
      "viral_score": 0.82,
      "expected_engagement": "10K-50K view" | "100K+" | "1M potential",
      "audio_suggestion": "trending sound name OR 'voice-over' OR 'no audio'",
      "hashtags": ["#hashtag1","#hashtag2",...],
      "visual_style": "fast-cut talking head" | "screen recording" | "B-roll over voice",
      "confidence": "high|medium|low"
    }
  ]
}

If trend is too generic/sparse: {"platform_context":"...","video_ideas":[],"reason":"..."}.
"""


class ViralContentGenerator:
    """Trend + platform + country → 3 video idea + viral score."""

    SUPPORTED_PLATFORMS = {"tiktok", "instagram", "youtube_shorts"}

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

    def generate(
        self, trend: dict, platform: str = "tiktok", country: str = "GLOBAL"
    ) -> dict:
        """
        Trend için 3 video fikri + viral skoru.

        Args:
            trend: topic_name, sources, cts, country, mentions
            platform: 'tiktok' | 'instagram' | 'youtube_shorts'
            country: 'GLOBAL' veya ISO alpha-2

        Returns:
            {"platform_context": "...", "video_ideas": [...]}
        """
        if platform not in self.SUPPORTED_PLATFORMS:
            return {"platform_context": "", "video_ideas": [], "reason": "unsupported_platform"}
        if not self._has_llm_key():
            logger.warning("[viral] OLLAMA_API_KEY yok — atlandı")
            return {"platform_context": "", "video_ideas": [], "reason": "no_llm_key"}

        prompt = self._build_user_prompt(trend, platform, country)
        model = os.getenv("OLLAMA_DIRECTOR_MODEL", "gpt-oss:120b")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,  # daha creative (viral hook için)
                max_tokens=2000,
            )
            text = (response.choices[0].message.content or "").strip()
            text = self._strip_markdown_fence(text)
            data = json.loads(text)
            return self._validate(data, platform)
        except json.JSONDecodeError as e:
            logger.warning(f"[viral] JSON parse fail: {e}")
            return {"platform_context": "", "video_ideas": [], "reason": "json_parse_error"}
        except Exception as e:
            logger.warning(f"[viral] LLM hatası: {e}")
            return {"platform_context": "", "video_ideas": [], "reason": "llm_error"}

    def _build_user_prompt(self, trend: dict, platform: str, country: str) -> str:
        sources = trend.get("sources") or {}
        if isinstance(sources, dict):
            src_str = ", ".join(f"{k}({v})" for k, v in list(sources.items())[:5])
        else:
            src_str = ", ".join(map(str, sources[:5]))
        return (
            f"TRENDING TOPIC: {trend.get('topic_name','')}\n"
            f"CATEGORY: {trend.get('category','Unknown')}\n"
            f"CTS_SCORE: {trend.get('cts_score',0):.1f}/100\n"
            f"MENTIONS: {trend.get('mention_count',0)}\n"
            f"SOURCES: {src_str}\n"
            f"DETECTED_COUNTRY: {trend.get('country','GLOBAL')}\n"
            f"\nTARGET_PLATFORM: {platform}\n"
            f"TARGET_COUNTRY: {country}\n"
            f"\nGenerate 3 video ideas as STRICT JSON."
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
    def _validate(data: dict, platform: str) -> dict:
        ideas = data.get("video_ideas", [])
        cleaned = []
        for it in ideas:
            if not it.get("hook"):
                continue
            cleaned.append({
                "platform": platform,
                "hook": str(it.get("hook"))[:500],
                "format": str(it.get("format", ""))[:50],
                "description": str(it.get("description", ""))[:1000],
                "viral_score": max(0.0, min(1.0, float(it.get("viral_score", 0.5) or 0.5))),
                "expected_engagement": str(it.get("expected_engagement", ""))[:50],
                "audio_suggestion": str(it.get("audio_suggestion", ""))[:200],
                "hashtags": it.get("hashtags", []) if isinstance(it.get("hashtags"), list) else [],
                "visual_style": str(it.get("visual_style", ""))[:200],
                "confidence": str(it.get("confidence", "medium")).lower()[:10],
            })
        return {
            "platform_context": str(data.get("platform_context", ""))[:500],
            "video_ideas": cleaned,
        }
