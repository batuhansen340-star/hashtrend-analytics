# HashTrend Analytics

Global Trend Intelligence Platform — çoklu kaynaktan beslenen, çapraz platform trend tespiti yapan API servisi.

## Mimari

```
collectors/          → Veri toplama scriptleri (her kaynak için ayrı)
core/                → Normalizasyon, skorlama, kategorizasyon
api/                 → FastAPI endpoint'leri
config/              → Ayarlar ve environment değişkenleri
.github/workflows/   → GitHub Actions cron job'ları
```

## Kurulum

```bash
# 1. Repo'yu klonla
git clone https://github.com/batuhansen340-star/hashtrend-analytics.git
cd hashtrend-analytics

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Bağımlılıkları yükle
pip install -r requirements.txt

# 4. Environment değişkenleri
cp .env.example .env
# .env dosyasını düzenle (Supabase URL, API key, vb.)

# 5. Collector'ı test et
python -m collectors.google_trends

# 6. API'yi başlat
uvicorn api.main:app --reload
```

## Veri Kaynakları

| Kaynak | Durum | Maliyet |
|--------|-------|---------|
| Google Trends (pytrends) | ✅ Aktif | Ücretsiz |
| Reddit API | ✅ Aktif | Ücretsiz |
| Hacker News API | ✅ Aktif | Ücretsiz |
| Wikipedia Pageviews | 🔜 Faz 2 | Ücretsiz |
| GitHub Trending | 🔜 Faz 2 | Ücretsiz |
| NewsAPI | 🔜 Faz 2 | Ücretsiz |
| Twitter/X | 🔜 Faz 3 | $100/ay |

## Lisans

Private — Batuhan Şen & Zelimkhan Bey
