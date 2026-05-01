import json
from loguru import logger
from config.settings import settings

CATS = "Yapay Zeka, Programlama, Veri Bilimi, Web Tasarim, Bilisim Guvenligi, Blockchain, Sosyal Medya, Teknoloji, Kisisel Gelisim, Kocluk, Psikoloji, Finans, Pazarlama, Isletme, Saglik, Beslenme, Spor, Dil, Iletisim, Egitim, Hukuk, Moda, Turizm, Muzik, Sinema, Yazarlik, Medya, Doga ve Cevre"

SYS_P = ("You are an education trend analyst. Evaluate trending topics for online course potential. "
    "For each: edu_score 1-10 (10=perfect course material), edu_category from: " + CATS + ". "
    "If none fits use Diger. edu_reason: max 15 words Turkish why. "
    "course_idea: if score>=6 Turkish course title else empty string. "
    "9-10=teachable skill, 7-8=strong angle, 5-6=moderate, 3-4=weak, 1-2=none. "
    'Respond ONLY JSON array: [{"topic":"...","edu_score":N,"edu_category":"...","edu_reason":"...","course_idea":"..."}] '
    "No markdown just raw JSON.")


class EduScorer:
    """Ollama Cloud (gpt-oss:120b) ile egitim potansiyeli skorlama. $0/ay marjinal."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            import os
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

    def _has_llm_key(self) -> bool:
        import os
        key = os.getenv("OLLAMA_API_KEY") or getattr(settings, "OLLAMA_API_KEY", None)
        return bool(key) and "..." not in (key or "") and len(key or "") >= 16

    def score(self, topics):
        if not self._has_llm_key():
            logger.debug("OLLAMA_API_KEY yok, edu scoring skip")
            return topics
        names = [t.get("topic_name", "") for t in topics]
        results = {}
        for i in range(0, len(names), 20):
            results.update(self._score_batch(names[i:i + 20]))
        for t in topics:
            edu = results.get(t.get("topic_name", ""), {})
            t["edu_score"] = edu.get("edu_score", 0)
            t["edu_category"] = edu.get("edu_category", "")
            t["edu_reason"] = edu.get("edu_reason", "")
            t["course_idea"] = edu.get("course_idea", "")
        scored = sum(1 for t in topics if t.get("edu_score", 0) >= 6)
        logger.info(f"Edu scoring: {len(topics)} konu, {scored} egitim potansiyelli")
        return topics

    def _score_batch(self, topics):
        import os
        model = os.getenv("OLLAMA_EDU_MODEL", "gpt-oss:120b")
        lines = [str(i+1) + ". " + t for i, t in enumerate(topics)]
        topic_list = chr(10).join(lines)
        prompt = "Evaluate these trending topics for education potential:" + chr(10) + topic_list
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYS_P},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4000,
            )
            txt = (response.choices[0].message.content or "").strip()
            if txt.startswith("```"):
                first_nl = txt.find(chr(10))
                if first_nl > 0:
                    txt = txt[first_nl+1:]
            if txt.endswith("```"):
                txt = txt[:-3]
            txt = txt.strip()
            data = json.loads(txt)
            return {d["topic"]: d for d in data}
        except json.JSONDecodeError as e:
            logger.warning(f"Edu JSON error: {e}")
            return {}
        except Exception as e:
            logger.debug(f"Edu API error: {e}")
            return {}
