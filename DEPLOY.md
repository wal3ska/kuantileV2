# Deploy Rehberi — Kendi Domain'inde Yayına Alma

Süre: ~1-2 saat. Ön koşul: GitHub repo'n hazır (Faz 1 dosyaları kökte).

## 0. Satın Alımlar

| Ne | Nereden | Maliyet |
|---|---|---|
| Domain | Namecheap / Porkbun / isimtescil | ~$10-15/yıl |
| VPS | Hetzner Cloud → CX22, Ubuntu 24.04, lokasyon: Nürnberg/Falkenstein | €4,51/ay |

Hetzner'da sunucu oluştururken **SSH key** ekle (şifreyle girişten güvenli):
yoksa `ssh-keygen -t ed25519` ile üret, `~/.ssh/id_ed25519.pub` içeriğini yapıştır.

## 1. DNS Ayarları (domain panelinden)

Sunucunun IP'sini Hetzner panelinden kopyala, domain sağlayıcında 3 A kaydı aç:

| Tip | Ad | Değer |
|---|---|---|
| A | @ | SUNUCU_IP |
| A | www | SUNUCU_IP |
| A | api | SUNUCU_IP |

DNS yayılımı 5 dk - 2 saat sürebilir. `ping senindomain.com` IP'yi gösterince hazırsın.

## 2. Sunucuya Bağlan ve Hazırla

```bash
ssh root@SUNUCU_IP

# Güncelle + güvenlik duvarı
apt update && apt upgrade -y
apt install -y ufw
ufw allow 22 && ufw allow 80 && ufw allow 443
ufw --force enable

# Docker kur (resmi script)
curl -fsSL https://get.docker.com | sh
```

## 3. Projeyi Çek ve Domain'i Yaz

```bash
git clone https://github.com/KULLANICI/REPO.git /srv/risk-terminali
cd /srv/risk-terminali

# Bu klasördeki deploy dosyaları repo köküne kopyalanmış olmalı
# (Dockerfile, docker-compose.yml, nginx/, .dockerignore)

# Tüm konfigürasyonlarda placeholder'ı gerçek domain'inle değiştir:
sed -i 's/SENIN-DOMAIN.com/gercekdomainin.com/g' nginx/*
```

## 4. SSL Sertifikası Al (tek seferlik tavuk-yumurta adımı)

Nginx, sertifika yokken HTTPS konfigürasyonuyla açılamaz. Önce HTTP-only başlat:

```bash
docker compose up -d nginx        # sadece http-init.conf aktif
docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
  -d gercekdomainin.com -d www.gercekdomainin.com -d api.gercekdomainin.com \
  --email seninmail@ornek.com --agree-tos --no-eff-email
```

"Successfully received certificate" gördüysen asıl konfigürasyona geç:

```bash
mv nginx/http-init.conf nginx/http-init.conf.disabled
mv nginx/app.conf.disabled nginx/app.conf
```

## 5. Her Şeyi Başlat

```bash
docker compose up -d --build
docker compose ps        # 4 servis de "running" olmalı
```

Kontrol:
- https://gercekdomainin.com → Streamlit arayüzü
- https://api.gercekdomainin.com/docs → FastAPI dokümantasyonu
- https://api.gercekdomainin.com/health → {"status":"ok"}

## 6. Güncelleme Akışı (bundan sonrası)

Kod değişince:
```bash
cd /srv/risk-terminali
git pull
docker compose up -d --build
```

Sertifika yenileme otomatik: certbot container'ı 12 saatte bir kontrol eder,
Let's Encrypt sertifikaları 90 günlük olduğu için dokunman gerekmez.

## Sorun Giderme

| Belirti | Muhtemel neden | Çözüm |
|---|---|---|
| Site açılmıyor | DNS yayılmadı | `ping domain` ile IP'yi doğrula, bekle |
| Sayfa bembeyaz | Websocket başlıkları | nginx/app.conf'taki Upgrade satırları duruyor mu? |
| Sertifika hatası | 4. adım sırası | http-init ile başlayıp certonly'yi öyle çalıştır |
| Log görmek | — | `docker compose logs -f web` (veya api / nginx) |

## Notlar

- API rate limit: nginx üzerinde IP başına 30 istek/dk (apilimit zone). Mobil
  uygulama çıkınca ihtiyaca göre artır.
- Mobil uygulama API'yi doğrudan çağıracağı için CORS gerekmez; ileride
  tarayıcıdan (React) çağıracaksan api.py'ye CORSMiddleware eklenir (tek satırlık iş).
- Yedekleme: durum tutan veri yok (pozisyonlar kullanıcı tarafında), yani
  sunucu ölürse yeni VPS + bu rehber = 1 saatte ayağa kalkar.
