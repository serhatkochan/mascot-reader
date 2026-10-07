# Mascot Reader landing

Bağımlılıksız HTML/CSS/JavaScript. Backend veya web seslendirmesi yoktur; etkileşimli
oynatıcı yalnız arayüz önizlemesidir. İndirmeler GitHub'ın güncel Setup EXE'sine gider.

Yerelde `landing` klasörünü HTTP üzerinden sunun:

```powershell
python -m http.server 8767 --bind 127.0.0.1 --directory landing
```

Vercel projesinin **Root Directory** ayarı `landing`, **Framework Preset** ayarı
`Other` olmalıdır. Build komutu yok; statik çıktı dizini `.`. `vercel.json` bu
klasördedir. Mevcut GitHub entegrasyonu `main` dalındaki güncellemeleri otomatik
olarak yayımlar. CLI ile dağıtım, proje kök dizininden yapılır:

```powershell
vercel deploy --project mascot-reader --prod --scope serhatkochans-projects
```

Komutu `landing` içinden çalıştırmayın; projenin Root Directory ayarı bu klasörü
zaten seçer. Canlı site: [mascot-reader.serhatkochan.com](https://mascot-reader.serhatkochan.com/).

Canonical, sitemap ve OG adresi: `https://mascot-reader.serhatkochan.com/`.
Sayfa çalışırken dış yazı tipi/CDN isteği, analiz, dosya yükleme veya API çağrısı yoktur.

`assets/reader-panel.png`, `assets/compact-player.png` ve `assets/mascots` içeriği,
projenin gerçek uygulama çizimlerinden alınan README görsellerinin kopyasıdır.
Kıvılcım GIF'i kaynak runtime karelerini kullanır; azaltılmış hareket tercihinde PNG
gösterilir. Diğer dokuz maskot önizlemede statik PNG olarak gösterilir.

Bricolage Grotesque ve DM Sans, Google Fonts'un Latin/Latin Extended WOFF2 alt
kümeleriyle kendinde barındırılır. SIL OFL 1.1 lisans metinleri `assets/fonts` içinde
dağıtılır. Bu font lisansları uygulamanın veya maskotların lisansı değildir.
