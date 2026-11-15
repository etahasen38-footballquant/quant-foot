# QuantFoot — Canlıya Alma (Deployment) ve Otomatik Veri Çekme Rehberi

Bu paket, **QuantFoot** platformunu kendi alan adında (domain) yayınlaman için gereken tüm ön yüz (Frontend) ve arka uç (Sofascore + ClubElo veri çekici Python servisi) dosyalarını içerir.

## 1. Hızlı Yayınlama (Sıfır Kurulumla Ön Yüzü Yayınlama)
`frontend/index.html` dosyası tamamen bağımsızdır:
1. [Vercel](https://vercel.com), [Netlify](https://app.netlify.com/drop) veya [Cloudflare Pages](https://pages.cloudflare.com) hesabına gir.
2. `frontend` klasörünü sürükleyip bırak. Siten 30 saniye içinde `https://senin-siten.vercel.app` adresinde yayına girer.

## 2. Otomatik Maç & Reyting Çekici Backend'i Çalıştırma (Sofascore + ClubElo)
`backend/sofascore_clubelo_scraper.py` dosyası:
- **ClubElo**'nun resmi günlük CSV API'sinden (`http://api.clubelo.com/YYYY-MM-DD`) Avrupa'daki tüm liglerin güncel takım Elo puanlarını çeker.
- **Sofascore** maç uç noktalarından (`/api/v1/event/{event_id}/lineups`) maç bitiminde oyuncuların `1.0 - 10.0` arası reytinglerini ve dakika/gol/asist/xG istatistiklerini çeker.
- **Anti-Farming** ve **Turnuva Tavanı** kurallarıyla (Sıradan lig maçında maks `±%0.20`, Şampiyonlar Ligi'nde maks `±%1.60`) oyuncu değerlerini günceller.
