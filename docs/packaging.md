# Windows kurulum ve paketleme

## Kurulum, güncelleme ve kaldırma

Son kullanıcı dağıtımı `MascotReader-Setup.exe` dosyasıdır. Kurulum geçerli Windows
kullanıcısına yapılır ve yönetici izni gerekmez. Varsayılan dizin
`%LOCALAPPDATA%\Programs\MascotReader`'dır. Python, Qt ve sabit sürümlü ses modeli
pakete dahildir. Kurulumdan sonra uygulamayı Başlat menüsünden açabilirsiniz.
Masaüstü kısayolu varsayılan olarak seçilidir; kurulumda kapatılabilir ve sonraki
kurulumlarda bu tercih hatırlanır.

Yeni sürüme geçmek için maskotta sağ tık → **Çıkış** yapın ve
[son sürümün kurulum dosyasını](https://github.com/serhatkochan/markdown-to-speech/releases/latest/download/MascotReader-Setup.exe)
çalıştırın. Yeni kurulum mevcut uygulamayı günceller. Aynı Windows kullanıcısının
maskot seçimi, pencere konumu ve diğer tercihleri korunur.
Uygulama otomatik güncelleme denetimi yapmaz; yeni kurulum GitHub'dan elle indirilir.

Kurucunun AppId'si sabittir; güncellemeler mevcut kurulum dizinini ve Windows
uygulama listesi girişini kullanır. Eski dosya temizliği önceki kurulum manifesti
ve SHA256 eşleşmesiyle yalnız `_internal` ve `docs/assets` altında yapılır.
Bu temizleme, değiştirilmiş eski dosyalara ve kullanıcı dosyalarına dokunmaz;
kullanıcı profili korunur.
Eski dosyalar yalnız yeni dosyaların kurulumu başarıyla tamamlandıktan sonra temizlenir.

Kaldırmak için Windows Ayarlar → **Uygulamalar** bölümünü veya Denetim Masası →
**Programlar ve Özellikler** ekranını açın; **MascotReader** için **Kaldır**'ı seçin.
Uygulama hâlâ açıksa kaldırıcı, maskotta veya tepsi simgesinde sağ tık → **Çıkış**
yapmanızı ister. Uygulama kapanmadan dosyaları veya Windows kaydını kaldırmaz.
Kaldırıcı kurulumun kaydettiği dosyaları siler; uygulama klasörünün tamamını
genel bir silme işlemiyle temizlemez.
Kurulum dosyasının SHA256 değeri sürümdeki `MascotReader-Setup.exe.sha256` dosyasındadır.

GitHub sürümünde kurulum EXE'si ve onun SHA256 dosyası yayımlanır. Python, CUDA
ve model indirmesi son kullanıcıda gerekmez.

## Uygulama paketini derleme

64 bit Windows'ta Python 3.11 sanal ortamı ve CPU PyTorch ile derleyin.
README'deki geliştirme kurulumunun ardından:

```powershell
.\scripts\build_windows.ps1
```

Bu komut sabit model sürümünü indirir, boyut ve SHA256 değerlerini denetler,
PyInstaller `onedir` paketini ve `dist/MascotReader-windows-x64.zip` arşivini
oluşturur. ZIP öncesinde paketlenmiş uygulamayla internet bağlantıları engellenmiş
gerçek CPU seslendirmesi çalıştırılır; 48 kHz mono PCM16 çıktı denetlenir.
Paketlenmiş Qt FFmpeg çözücüsü ve duraklatma, ileri/geri atlama,
baştan başlatma, durdurma kontrollerini denetler. Kaydedilen bölüm sınırlarının
gerçek WAV örneklerini tamamen kapsadığı, Markdown panelindeki metin bağlantılarının
ses bölümlerine atladığı ve on maskotun tamamının pakette açıldığı da denetlenir.
Bu kontroller geçmezse ZIP
oluşturulmaz. Test çıktısı `build/verification/frozen-smoke.wav` altında kalır. İndirme zaten
yapıldıysa internet bağlantısı olmadan derlemek için:

```powershell
.\scripts\build_windows.ps1 -SkipModelDownload
```

Derleyici PATH'i Python ve Windows sistem dizinleriyle sınırlandırır; başka
uygulamaların DLL'leri pakete karışmaz. Qt'nin Windows ICU bağımlılığı hedef
Windows kurulumundan sağlanır. Derleme önbelleğini sıfırlamak için `-Clean`
ekleyebilirsiniz.

ZIP yerel geliştirme ve doğrulama için taşınabilir çıktıdır. Arşivin tamamını
çıkarıp `MascotReader/MascotReader.exe` dosyasını çalıştırabilirsiniz; `_internal`
klasörü uygulamayla birlikte kalmalıdır. GitHub'daki son kullanıcı indirmesi Setup
EXE'dir.

Yalnız belgeler güncellendiyse uygulama EXE'sini yeniden derlemeden ZIP ve SHA256 dosyasını
yenilemek için `.venv\Scripts\python.exe scripts\package_windows.py` çalıştırın.
Son arşiv bilgileri `build/verification/package-summary.json` dosyasına yazılır.

## Setup EXE oluşturma

Önce yukarıdaki uygulama derlemesini tamamlayın. Ardından Inno Setup'ı kurun ve
`ISCC.exe` yolunu belirterek mevcut `dist/MascotReader` klasöründen kurulum üretin:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -Iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

Örnekteki derleyici yolunu kendi Inno Setup kurulumunuza göre değiştirin.
Bu betik PyInstaller'ı yeniden çalıştırmaz. Paketlenmiş uygulamanın sürümünü
`pyproject.toml` ile karşılaştırır; eski bir uygulama paketiyle yeni sürüm
kurulumu oluşturulmasını engeller. Çıktılar `dist/MascotReader-Setup.exe` ve
`dist/MascotReader-Setup.exe.sha256` dosyalarıdır.

Yalnız belge veya README görselleri değiştiyse önce `scripts/package_windows.py`
ile dağıtım klasörünü yenileyin, ardından `scripts/build_installer.ps1` komutunu
tekrar çalıştırın. Böylece ZIP ve Setup aynı güncel belgeleri içerir.

## Paket içeriği ve doğrulama

Paket kaynakları `resources/mascots` klasörünün tamamını içerir. GUI görüntüsü
kontrolü için EXE'nin `--screenshot-gallery PNG` seçeneği maskot seçim ekranını;
`--screenshot PNG --preview-audio WAV` seçeneği hazırlanan WAV ve yanındaki
`.cues.json` ile Markdown panelini gösterir. Bu seçenekler kullanıcı tercihlerini
değiştirmez. Ses bölüm bilgileri belge kopyasını ve örnek bazında başlangıç/bitiş
konumlarını içerir; kullanıcıya dışa aktarılan WAV yalnız sesi içerir.

Model sürümü `resources/model-manifest.json` içinde sabittir. İndirme betiği
yalnız bu sürümü kullanır. Hugging Face önbelleği `snapshots/<revision>` altında
gerçek dosyalar ve `refs/main` referansı içerir; Windows'ta sembolik bağlantı
veya geliştirici modu gerekmez. Geçersiz veya eksik ağırlıkla paketleme durur.

Model lisansı, Python lisansı ve kurulu bağımlılıkların lisans dosyaları
`_internal/licenses` içinde bulunur.

Dağıtım doğrulaması: temiz Windows 10/11 x64 ortamında internet kapalıyken
kurulumu tamamlayıp uygulamayı ilk kez açın; Türkçe bir Markdown dosyasını seslendirin,
tüm oynatıcı kontrollerini ve WAV dışa aktarmayı deneyin. Güncellemenin tercihleri
koruduğunu, kısayolları ve Windows uygulama listesinden kaldırmayı da denetleyin.
Bu makinede yapılan derleme ve
çevrimdışı model denetimi, ayrı bir temiz Windows makinesi testinin yerine geçmez.

## GitHub sürümünü yayımlama

Kaynak sürümünü, testleri ve kurulum/güncelleme/kaldırma doğrulamasını tamamlayın;
değişiklikleri `main` üzerinde commit edin. Uygulama ve Setup bu kaynaklardan
üretilmiş olmalıdır. `gh` CLI ile GitHub hesabınızda oturum açın. Aşağıdaki
örnekte `v0.2.0` etiketini yayımlayacağınız `pyproject.toml` sürümüne göre değiştirin:

```powershell
git push origin main
git tag -a v0.2.0 -m "MascotReader 0.2.0"
git push origin v0.2.0
git rev-parse HEAD
git rev-parse 'v0.2.0^{commit}'
git ls-remote origin 'refs/tags/v0.2.0^{}'
```

Yerel HEAD, etiketin commit'i ve uzak annotated etiketin açılmış commit SHA'sı
aynı olmalıdır; `git status --short` çıktısı boş olmalıdır. Sürüm notlarını UTF-8
bir dosyaya yazın, ardından:

```powershell
.\.venv\Scripts\python.exe scripts\publish_release.py --notes-file build\release-notes.md
```

Betik temiz kaynak durumunu ve yerel/uzak etiketin HEAD ile aynı commit'e bağlı
olduğunu da denetler. Yerel kurulum raporunu, sürümü ve dosya SHA256 değerlerini doğrular;
son sürümü yalnız `MascotReader-Setup.exe` ve `MascotReader-Setup.exe.sha256`
ile yayımlar. GitHub'daki iki dosyanın boyutları ve SHA256 değerleri eşleşip
sürümün `latest` olduğu doğrulandıktan sonra önceki yayımlanmış sürümlerin
yönetilen Setup/ZIP dosyaları ve onların SHA256 dosyaları silinir.
Etiketler, sürüm notları, release kayıtları, kaynak geçmişi ve diğer ekler korunur.
Doğrulama başarısızsa eski dosyalar silinmez. Aynı doğrulanmış son sürümle tekrar
çalıştırmak dosyaları yeniden yüklemeden yarım kalan temizlemeyi tamamlayabilir.
