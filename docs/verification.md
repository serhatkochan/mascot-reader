# Doğrulama kaydı

- Python 3.11.17, CPU PyTorch 2.14.1+cpu, PySide6 6.11.2, EMA Lightning 1.0.1.
- Masa kayması düzeltmesinden sonra son toplu offscreen koşusunda **158 test geçti**.
  Yeni 30 regresyon, on maskotun 120 karesinde masanın bütün piksel alanını ve
  gerçek Qt widget çizimindeki konumunu karşılaştırıyor; üç animasyonun da canlı
  kaldığını doğruluyor. Düzeltme öncesi 20 sabitlik testi başarısızdı; düzeltme
  sonrası maskot testlerinin 65'i de geçti.
  Aynı 30 sabitlik/hareket testi Native Windows platformunda %150 ve %200
  ekran ölçeğinde ayrı ayrı geçti; widget kontrolü fiziksel piksel oranını hesaba katıyor.
- Kayma, üretim sheetlerinde kolon yerleşiminin tam hücre aralığına uymamasından
  ve masa geometrisinin kareler arasında değişmesinden kaynaklanıyordu. Üst
  karakter bölgesi her karede bağımsız hizalanıyor; masa, boşta duran ilk kareden
  sabit çiziliyor. Dış baseline ofseti sıfır; hizalama yalnız kare içinde uygulanıyor.
  PNG kaynakları değişmedi ve maskot seçim ekranı görüntüsünün SHA256 değeri önceki
  sürümle birebir aynı kaldı. Başlangıç görünümü ve konumu korunuyor.
- Windows Qt widget'ından on filmstripte bütün 120 kare alındı; masa birleşimleri,
  görünür karakter alanı ve canlı göz/el/ağız hareketleri görsel olarak incelendi.
- On maskot ve tıklanabilir Markdown paneli eklendikten sonra son toplu offscreen
  koşusunda **128 test geçti**. Katalogdaki tüm karakterlerin üç animasyonu,
  şeffaf frame sınırları, seçim penceresi, oynatmayı koruyan maskot değişimi ve
  izole kullanıcı ayarlarında seçimin sonraki açılışta hatırlanması doğrulandı.
- Panel testleri, gerçek fare tıklamasıyla bölüm atlama, duraklatmayı koruma,
  geç gelen/eski belge bağlantılarını reddetme, hazırlanmış belge kopyasını koruma
  ve açık panelin 600/350 piksel genişliğe daralan ekrana sığmasını kapsıyor.
  Biçim testleri tablo yapısı/hizalama, listeler, vurgular, görsel açıklamaları,
  kod satırları/girintileri ve uzun metin parçalarını denetliyor. Kesirli milisaniye
  başlangıçları, önceki bölüme düşmemek için yukarı yuvarlanıyor.
  `...` ile biten üstbilgiler ve üstbilgideki bağlantı tanımları için de iki
  regresyon eklendi; panel ve ses ayrıştırıcı aynı gövde bağlamını kullanıyor.
- Gerçek CPU modeliyle hazırlanan 14,64 saniyelik örnekte 10 ses bölümü ve panelde
  10 tıklanabilir bölüm doğrulandı. Windows Qt/FFmpeg oynatıcısı ikinci bölüme
  1.040 ms konumunda duraklatmayı koruyarak atladı; baştan başlatma, durdurma ve
  belgenin uçlarında sarma kontrolleri geçti. Windows seçim ekranı ve panel
  görüntüleri görsel olarak incelendi.
- Son paketlenmiş EXE aynı 14,64 saniyelik örnekte on maskotu ve 10/10 bölüm
  bağlantısını doğruladı. Ağ bağlantıları engellenmiş ayrı frozen sentez koşusu
  111.360 örneklik WAV üretti; iki bölümün gerçek kare sınırları ve ikinci bölüme
  duraklatılmış 520 ms atlama, baştan başlatma ve durdurma kontrolleri geçti.
- Son EXE'den Windows ve offscreen platformlarında, %100/%150/%200 ölçeklerinde
  galeri ve Markdown paneli için toplam 12 görüntü başarıyla alındı. Native Windows
  %100 ve %200 görüntüleri görsel olarak incelendi. Offscreen görüntüler sistem
  yazı tiplerini yüklemediğinden yalnız yerleşim kontrolü için kullanıldı.
- Son ZIP bütünlük denetimi: CRC, 31 maskot dosyasının kaynakla birebirliği,
  güncel README/belgeler, üç model dosyasının sabit SHA256 değeri ve arşiv sağlama
  toplamı geçti.
- Markdown ayrıştırma ve ses üretimi: 30 test; paket modeli: 3 test;
  masaüstü oynatma, iptal, dosya seçimi, sürükleme, konum, ayarlar ve kapanma: 24 test.
- Zaman çubuğu eklendikten sonra son offscreen koşusunda 57 test geçti. Yeni 9
  regresyon ayrıca bağımsız süreçte geçti: mutlak atlama sınırları, tıklama,
  duraklatılmış/durdurulmuş durumda sessiz kalma, sürükleme önizlemesi ve devam etme,
  dosya değiştirmede eski sürüklemeyi iptal etme, Home/End ve oynatma güncellemelerinin
  çubuk üzerinden yeniden seek üretmemesi.
- Bağımsız incelemede bulunan tepsi bulunmayan ortamda kapanma ve odaklı düğmede
  boşluk tuşu sorunları önce başarısız regresyonlarla gösterildi, sonra düzeltildi.
- Gerçek EMA modeli ağ bağlantısı engellenmişken CPU üzerinde Türkçe ses üretti.
- Son PyInstaller EXE'si, PATH yalnızca Windows dizinleriyle ve boş uygulama
  profiliyle çalıştırıldı. Ağ bağlantıları engellenmişken paketteki model,
  48 kHz mono PCM16 WAV üretti: 111.360 örnek, 2,32 saniye.
- Aynı EXE'nin gerçek Qt/FFmpeg oynatıcısı bu WAV'ı açtı; duraklatılmış halde
  ileri/geri sarma sınırları, baştan başlatma ve durdurulduğunda sıfıra dönme geçti.
- Paketlenmiş maskot Windows ve offscreen platformlarında %100, %150 ve %200
  ekran ölçeğinde açıldı. Altı ekran görüntüsü oluşturuldu; %100 ve %200 Windows
  görüntüleri ayrıca görsel olarak incelendi.
- İlk paketlemede bulunan Qt açılış hatası, derleyicinin başka bir uygulamanın
  uyumsuz ICU DLL'ini toplamasından kaynaklanıyordu. Bağımsız DLL import/export
  incelemesi nedeni doğruladı. Derleme PATH'i sınırlandırıldı ve son paket
  Windows'un ICU bileşenini kullanarak tüm GUI kontrollerini geçti.

Kaynak projede kanıtlar `build/verification` altında: `frozen-smoke.json`,
`frozen-smoke.playback.json`, `frozen-windows-*.png` ve
`qt-dll-compatibility.json`. Yeni kaynak doğrulamaları `reader-preview.playback.json`,
`mascot-gallery-windows.png` ve `reader-panel-windows.png` içindedir.
Paket ekranları `gallery-frozen-windows-*.png` / `reader-frozen-windows-*.png`,
ölçek raporu `gallery-reader-frozen-summary.json` ve arşiv kontrolü
`archive-audit.json` içindedir.
Son taşınabilir ZIP `dist` klasöründedir.

## Kontrol sınırları

İlk iki masaüstü test çalıştırmasında Qt/FFmpeg'in `QMediaPlayer.play()` çağrısında
aralıklı bir bekleme görüldü. Takılan test süreçleri kapatıldıktan sonra ana süreçte
tüm testler geçti; bağımsız inceleyicinin altı ayrı süreçte çalıştırdığı önceki 9
masaüstü testinin her biri de geçti. Aynı bekleme güvenilir biçimde yeniden
üretilemediği için varsayımsal bir oynatıcı değişikliği yapılmadı.

Zaman çubuğu eklenirken Windows platformundaki toplu test koşusunda aynı yerel
Qt/FFmpeg beklemesi, bu kez `setSource()` ile test oynatıcısı kapatılırken tekrar
görüldü. Son 57 testin tamamı offscreen platformunda, yeni zaman çubuğu testleri
ayrı süreçte geçti. Windows medya arka ucu da tanı amaçlı denendi; durdurduktan sonra
seçilen konumu oynatma başladığında sıfıra çektiği için mevcut FFmpeg arka ucu korundu.

Markdown panelinin ilk ayrı test koşusunda da aynı bekleme görüldü; yalnız bu
görevin takılan test süreci kapatıldı. Son üstbilgi sonrası koşusunda Qt kapanışı
beklemesi de tekrar görüldü; bu test süreci kapatılıp temiz süreçte yeniden denendi.
Son panel koşusu (10 test) ve masa düzeltmesini de içeren tüm 158 testlik
koşu offscreen platformunda geçti. Native Windows gerçek ses doğrulaması da geçti.

Çoklu monitör konum sınırları otomatik geometri testleriyle doğrulanmıştır; fiziksel
birden fazla monitörde elle denenmemiştir. Ayrı temiz bir Windows bilgisayarı veya
sanal makine mevcut değildir; kurulu Python'a ihtiyaç duymama kontrolü paket EXE'si,
sınırlı PATH ve ayrı boş profil ile bu bilgisayarda yapılmıştır.

Masa düzeltmesinin kanıtları `mascot-drift-measurements.json`, `stability-*.png`
ve `stability-source-png-hashes.json` dosyalarında bulunur.
