# Windows paketleme

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

Yalnız belgeler güncellendiyse EXE'yi yeniden derlemeden ZIP ve SHA256 dosyasını
yenilemek için `.venv\Scripts\python.exe scripts\package_windows.py` çalıştırın.
Son arşiv bilgileri `build/verification/package-summary.json` dosyasına yazılır.

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

ZIP'in tamamını çıkarın ve `MascotReader/MascotReader.exe` dosyasını çalıştırın.
`_internal` klasörü uygulamayla birlikte kalmalıdır. Python, CUDA ve model
indirmesi son kullanıcıda gerekmez. Model lisansı, Python lisansı ve kurulu
bağımlılıkların lisans dosyaları `_internal/licenses` içinde bulunur.

Dağıtım doğrulaması: temiz Windows 10/11 x64 ortamında internet kapalıyken
uygulamayı ilk kez açın; Türkçe bir Markdown dosyasını seslendirin, tüm oynatıcı
kontrollerini ve WAV dışa aktarmayı deneyin. Bu makinede yapılan derleme ve
çevrimdışı model denetimi, ayrı bir temiz Windows makinesi testinin yerine geçmez.
