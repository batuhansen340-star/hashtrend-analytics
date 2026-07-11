# HashTrend API — Render'a Ücretsiz Deploy (Railway'in yerine)

> Railway deployment'ı kayboldu (404 "Application not found"). Bu rehber API'yi
> Render'ın ücretsiz planına taşır. Kart istemez, kod değişikliği gerektirmez.

## Adımlar (~5 dk, tek seferlik)

1. **render.com** → GitHub ile kayıt ol / giriş yap.
2. **New → Blueprint** → `batuhansen340-star/hashtrend-analytics` repo'sunu seç.
   Render kökteki `render.yaml`'ı okuyup `hashtrend-api` servisini önerir.
3. Env değerlerini gir (yalnız 2 tane sorar):
   - `SUPABASE_URL` ve `SUPABASE_KEY` → `hashtrend-analytics/.env` dosyandaki değerler.
4. **Apply** → ilk build ~3-5 dk. Bittiğinde servis URL'i şuna benzer:
   `https://hashtrend-api.onrender.com` (isim doluysa Render sonek ekler).
5. URL'i test et: `https://<servis-url>/` → `{"status": ...}` sağlık cevabı dönmeli.

## Deploy sonrası (Claude'a "Render URL'i şu: ..." de, gerisini o yapar)

- `docs/index.html`, `docs/dashboard.html`, `docs/edutrend.html` içindeki
  `var API='https://hashtrend-analytics-production.up.railway.app'` sabiti
  yeni Render URL'iyle değiştirilecek (tek satır × 3 dosya).
- İstenirse `api.hashtrend.app` custom domain'i Render panelinden bağlanabilir
  (Settings → Custom Domains, ücretsiz planda da var).

## Ücretsiz planın bilinen sınırları

- **15 dk boşta kalınca uyur** → ilk istek ~30-60 sn soğuk başlar.
  Plan: dashboard statik-öncelikli yapılacak (kahve.html modeli), API yalnız
  arama/AI-fikir gibi interaktif işlerde çağrılacak → soğuk başlama hissedilmez.
- 512 MB RAM / paylaşımlı CPU — mevcut okuma-ağırlıklı API için yeterli.

## Açık iş (API dirildikten sonra)

- `viral-ideas` / `app-ideas` endpoint'leri hâlâ ölü Ollama Cloud'a bağlı —
  Trend Radar'daki gibi yeni LLM backend'ine taşınacak (ajans kolunun kalbi).
