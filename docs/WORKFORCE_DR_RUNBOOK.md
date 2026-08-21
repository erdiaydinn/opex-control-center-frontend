# Workforce felaket kurtarma ve saklama runbook'u

## Hedefler

- Önerilen RPO: 24 saatlik dump ile en fazla 24 saat; PostgreSQL WAL arşivi eklenirse 5 dakika.
- Önerilen RTO: 4 saat.
- Audit saklama: varsayılan 10 yıl, S3 Object Lock `COMPLIANCE` modu.

## Günlük kontroller

1. `backup` container'ının son `.dump` ve `.sha256` dosyasını ürettiğini kontrol edin.
2. Ayrı bir ortamda haftalık `ops/restore-dr.sh` testi yapın.
3. `/api/workforce/health`, `/metrics`, notification outbox bekleyen/hatalı işlerini izleyin.
4. WORM bucket'ta Object Lock ve retention tarihini doğrulayın.

## Geri dönüş

1. Etkilenen üretim yazmalarını durdurun ve olay zamanını kaydedin.
2. Yeni, boş ve erişimi sınırlı PostgreSQL örneği açın.
3. `DATABASE_URL` hedefi gösterirken `ops/restore-dr.sh <dump>` çalıştırın.
4. Workforce audit zincirinin `previous_hash/hash` sürekliliğini doğrulayın.
5. API health, örnek vardiya, izin, görev ve outbox sorgularını çalıştırın.
6. DNS/ingress'i yeni sisteme alın; kullanıcı ve denetçiye olay kaydını iletin.

## Anahtar kaybı

`OPEX_PII_KEY` veritabanı yedeğinden ayrı, KMS/secret manager içinde yedeklenmelidir.
Bu anahtar kaybolursa şifreli TC alanları geri getirilemez. APNs, Google ve OIDC
anahtarları düzenli rotasyona alınmalı; rotasyon audit kaydı üretmelidir.
