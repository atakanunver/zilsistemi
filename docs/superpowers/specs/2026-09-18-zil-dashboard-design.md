# Gerçek Zil Sesi + Web Dashboard (Ders Programı / Zil Sesi / Teneffüs Yönetimi)

**Tarih:** 2026-09-18
**Durum:** Faz A uygulandı ve production'a alındı (bkz. altta "Faz A Güncellemesi — Tatil Günleri"). Faz B-D henüz uygulanmadı.
**Proje:** `/home/atakan/ses` (zil sunucusu, 192.168.23.230)

## Kapsam

Bu spec iki şeyi kapsar:
1. `sys.py`'ye **gerçek zil sesi** özelliği eklemek — şu an sadece teneffüs arasında (ders çıkışından 3dk sonra başlayıp girişten 2dk önce duran) arka plan müziği var, ders giriş/çıkış anlarının kendisinde hiçbir ses çalmıyor.
2. Yeni bir **web dashboard** (`dashboard.py`, ayrı systemd servisi) — ders programı, zil sesi dosyası ve teneffüs müziği ayarlarını yönetmek için.

Kapsam dışı (bilinçli, 2026-09-18'de kullanıcı kararı):
- Farabi'nin `zil.json`'u ile hiçbir entegrasyon/senkronizasyon yok. Ders programı tamamen bu projenin kendi `ders_programi.json`'unda, elle girilir.
- Dashboard'dan fiziksel hoparlörden "test çal" yok — sadece tarayıcıda `<audio>` önizleme.
- Playlist dosya yüklemesi dashboard'a taşınmıyor — Telegram'daki mevcut akış (`handle_audio_upload`) kalıyor, dashboard sadece listeleme/silme yapıyor.

## Mevcut Durum (doğrulandı, 2026-09-18)

- `sys.py`: `TENEFUS_PROGRAMI` hardcoded 7 tuple `(ders_çıkışı, sonraki_ders_girişi)`, kaynağı Farabi'nin `zil.json`'u (elle kopyalanmış). `TENEFUS_OLAYLARI` bunlardan +3dk/-2dk offsetli `{baslama, durdurma}` çiftleri türetiyor. Ayrıca sabit bir 8. slot: `{"baslama": "07:50", "durdurma": "07:55"}` (okul girişi karşılama müziği).
- `tenefus_otomasyonu()`: 30 saniyede bir `HH:MM` string karşılaştırması yapan sonsuz döngü. `baslama`'da `not player.is_playing()` ise playlist'ten rastgele parça çalar (`otomatik_calan=True`), `durdurma`'da hâlâ çalıyorsa VE `otomatik_calan==True` ise durdurur.
- `siren.mp3` **121 saniye** — kısa bir zil/ding sesi değil, ayrı bir amaç için (`/siren` komutu). Zil özelliği için kullanılamaz.
- Farabi'nin gerçek ders programı (doğrulandı, `/home/ata/farabi/tahtayoklama/data/zil.json`): 8 ders, `08:10-08:50, 09:00-09:40, 09:50-10:30, 10:40-11:20, 11:30-12:10, [öğle arası 12:10-13:30], 13:30-14:10, 14:20-15:00, 15:10-15:50`. Bu, `sys.py`'deki 7 teneffüs çiftiyle birebir tutarlı (çapraz kontrol edildi).
- `env.txt`: `KEY=VALUE` formatında `TELEGRAM_TOKEN` ve `CHAT_ID` tutuyor, `.gitignore`'da hariç tutulmuş — yeni gizli değerler (dashboard parolası) aynı dosyaya, aynı yönteme eklenecek.

## Mimari

```
[Web Dashboard — dashboard.py, ayrı systemd servisi (ses_dashboard), Flask+waitress, port 8090]
        │ okur/yazar (atomik dosya yazımı — os.replace)
        ▼
   ders_programi.json  ──┐
   zil_sesi.mp3          │   (BASE_DIR'de, sys.py ile PAYLAŞILAN dosyalar — tek iletişim kanalı)
        │                │
        ▼                ▼
[sys.py — tenefus_otomasyonu(), HER 30 SANİYEDE ders_programi.json'u YENİDEN OKUR]
        │
        ▼
   VLC player (mevcut tek global instance) → hoparlör
```

**Kilit karar:** Dashboard ile `sys.py` arasında canlı süreçler-arası iletişim (HTTP, soket, kuyruk dosyası) YOK — sadece dosya sistemi paylaşımı. `sys.py` zaten 30 saniyede bir döngü çalıştırıyor; bu döngüye "config'i yeniden oku" eklemek, ayrı bir IPC mekanizması kurmaktan çok daha basit ve bu donanımda (Pentium E5500, 1.6GB RAM, zaten flaky ağ) daha az kırılgan.

## `ders_programi.json` Şeması

```json
{
  "dersler": [
    {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
    {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
    {"no": 3, "baslangic": "09:50", "bitis": "10:30"},
    {"no": 4, "baslangic": "10:40", "bitis": "11:20"},
    {"no": 5, "baslangic": "11:30", "bitis": "12:10"},
    {"no": 6, "baslangic": "13:30", "bitis": "14:10"},
    {"no": 7, "baslangic": "14:20", "bitis": "15:00"},
    {"no": 8, "baslangic": "15:10", "bitis": "15:50"}
  ],
  "ders_gunleri": [1, 2, 3, 4, 5],
  "tatil_gunleri": ["2026-10-29", "2026-11-24"],
  "karsilama_muzigi": {"aktif": true, "baslama": "07:50", "durdurma": "07:55"},
  "ayarlar": {
    "zil_aktif": true,
    "tenefus_muzigi_aktif": true,
    "otomatik_ses_seviyesi": 50,
    "zil_ses_seviyesi": 80
  }
}
```

Bu dosya `BASE_DIR/ders_programi.json`'da yaşar, `.gitignore`'a eklenmez (gizli veri içermiyor, tam tersine mevcut hardcoded `TENEFUS_PROGRAMI`'nin yerini alan konfigürasyon — git'te takip edilmesi, değişiklik geçmişini görünür kılması faydalı; ilk sürümü mevcut 7 tuple'dan bire bir üretilip commit edilecek).

`sys.py` bu dosyadan şunları türetir (her 30sn'lik döngü başında, dosya değiştiyse):
- **Teneffüs çiftleri**: `dersler[i].bitis` → `dersler[i+1].bitis` ardışık ikilileri (bugünkü `TENEFUS_PROGRAMI` mantığının aynısı, artık türetilmiş).
- **`TENEFUS_OLAYLARI`**: yukarıdakilerden +3/-2dk offsetli, artı `karsilama_muzigi.aktif` ise o slot.
- **`ZIL_SAATLERI`**: tüm `dersler[].baslangic` ve `dersler[].bitis` değerlerinin birleşim kümesi (sıralı, tekrarsız) — öğle arası ayrı bir zil noktası gerektirmiyor çünkü `dersler[5].bitis` (12:10) ve `dersler[6].baslangic` (13:30) zaten bu kümede.

## Zil Çalma Mantığı (yeni, `tenefus_otomasyonu()` içine eklenir)

```
her 30 saniyede:
    dosya değiştiyse ders_programi.json'u yeniden oku (mtime kontrolü), türetilmiş listeleri güncelle
    if simdi_dt.isoweekday() not in ders_gunleri: devam etme (bugünkü sabit (1,2,3,4,5) kontrolünün yerini alır)
    simdi = "HH:MM"
    if ayarlar.zil_aktif and simdi in ZIL_SAATLERI and simdi != son_calinan_zil_dakikasi:
        eğer zil_sesi.mp3 mevcutsa: çal (ses seviyesi = ayarlar.zil_ses_seviyesi), son_calinan_zil_dakikasi = simdi
        değilse: bir kereliğine uyarı logla ("zil_sesi.mp3 bulunamadı") — mevcut "playlist boşsa sessizce hiçbir şey çalma" bug'ının aynısına düşmemek için
    (mevcut teneffüs müziği mantığı — artık ayarlar.tenefus_muzigi_aktif ile koşullu — aynen devam eder)
```

**Neden `son_calinan_zil_dakikasi` gerekli (kritik, tasarım sırasında bulundu):** Mevcut teneffüs mantığındaki `not player.is_playing()` koruması, break müziğinin (~2 dk) 30 saniyelik döngü aralığından uzun sürmesi sayesinde tesadüfen çalışıyor — aynı dakika içinde 2. kontrol geldiğinde müzik hâlâ çalıyor olduğundan tekrar tetiklenmiyor. Ama zil sesi kısa (birkaç saniye) olacağı için, aynı dakika içindeki 2. döngü kontrolünde `player.is_playing()` çoktan `False` olur ve zil **iki kere çalar**. Bu yüzden zil için ayrı, açık bir "bu dakika zaten çalındı" bayrağı şart — `not player.is_playing()` yeterli değil.

## Dashboard (`dashboard.py`, ayrı systemd servisi `ses_dashboard`)

**Teknoloji:** Flask (Jinja2 dahili) + `waitress` (WSGI sunucu, Flask'ın dev sunucusundan biraz daha sağlam, düşük ek yük). Port `8090` (implementasyon sırasında boş olduğu doğrulanmalı). HTTP Basic Auth — kullanıcı adı sabit `admin`, parola `env.txt`'e yeni `DASHBOARD_PASSWORD` anahtarıyla eklenir (kullanıcı deploy sonrası elle set eder), `ayarlari_yukle()`'nin zaten yaptığı gibi okunur.

**Sayfalar:**
1. `GET /` — Özet: bugünün programı, sıradaki zil saati, mevcut ayarların durumu (aktif/pasif rozetleri).
2. `GET/POST /program` — Ders programı editörü: `dersler` listesi (no/başlangıç/bitiş), `karşılama_muzigi`. Kaydetmeden önce doğrulama: `HH:MM` formatı, `bitis > baslangic`, ardışık dersler çakışmıyor. Kayıt atomik (`ders_programi.json.tmp` yaz, `os.replace`).
   - **`ders_gunleri`**: haftanın 7 günü (Pazartesi–Pazar) için ayrı aç/kapa toggle olarak gösterilir — sadece hafta içi değil, istenirse hafta sonu da açılabilir (2026-09-18, kullanıcı isteği). Değer olarak seçili günlerin ISO gün numaraları (`1`=Pazartesi...`7`=Pazar) `ders_gunleri` listesine yazılır.
   - **`tatil_gunleri`**: takvimden gün(ler) seçilerek eklenen/çıkarılan tarih listesi (`YYYY-AA-GG`, `<input type="date">` + "ekle"/"listeden sil" butonları — ayrı bir tam takvim widget'ı şart değil). Bu listedeki bir tarihte `ders_gunleri`'nde olsa dahi zil/teneffüs otomasyonu o gün tamamen devre dışı kalır (`sys.py`'de zaten uygulandı, bkz. altta).
3. `GET/POST /zil-sesi` — Dosya yükleme (mp3), yüklenen dosya `<audio controls>` ile tarayıcıda önizlenir, onaylanınca `zil_sesi.mp3.tmp` → `os.replace` ile `zil_sesi.mp3` üzerine yazılır.
4. `GET/POST /ayarlar` — `zil_aktif`, `tenefus_muzigi_aktif` toggle'ları, `otomatik_ses_seviyesi` / `zil_ses_seviyesi` slider'ları (0-100).
5. `GET /playlist` + `POST /playlist/sil` — `PLAYLIST_DIR` dosya listesi (ad, boyut), silme butonu (`os.path.basename` ile path traversal engellenir, `/sil` komutundaki güvenlik deseninin aynısı).

## Global Constraints (plan için)

- `ders_programi.json` ve `zil_sesi.mp3` yazımları HER ZAMAN atomik olmalı (`*.tmp` + `os.replace`) — `sys.py`'nin 30sn'lik pollinguyla yarış durumunu (yarım yazılmış dosya okuma) önlemek için.
- Zil çalma mutlaka `son_calinan_zil_dakikasi` (veya eşdeğeri) ile çift-tetiklenmeye karşı korunmalı — sadece `not player.is_playing()` YETERSİZ (yukarıda açıklandı).
- Dashboard tamamen LAN-only, HTTP Basic Auth zorunlu, parola `env.txt`'den okunur, koda hardcode edilmez, git'e girmez.
- Farabi ile hiçbir ağ çağrısı/entegrasyon kurulmayacak (bilinçli kapsam dışı).
- Playlist yükleme dashboard'a eklenmeyecek (Telegram'daki mevcut akış kalıyor).
- Mevcut Telegram komutları (`/istiklal`, `/siren`, `/list`, `/sil`, `/duyuru_*`, vb.) davranışı değişmeyecek — sadece `tenefus_otomasyonu()` ve ayar kaynağı değişiyor.
- `sys.py` dışındaki tarihli/isimli kopya dosyalar (`sys14052026.py` vb.) bu değişikliklerden etkilenmeyecek/güncellenmeyecek (zaten production'da kullanılmıyorlar).

## Uygulama Planı (yüksek seviye)

1. **Faz A — Zil sesi çekirdek mantığı**: `ders_programi.json` oluştur (mevcut 7 tuple'dan üretilmiş), `sys.py`'de `TENEFUS_PROGRAMI`/`TENEFUS_OLAYLARI`'yı JSON'dan türetilir hale getir, `ZIL_SAATLERI` + `son_calinan_zil_dakikasi` guard'ı ekle, `ayarlar.*` ile davranışları koşullu yap. Henüz `zil_sesi.mp3` yok — dosya eksikse uyarı loglanıp atlanacak şekilde test edilir.
2. **Faz B — Dashboard temel iskelet**: Flask app + waitress + systemd servisi + Basic Auth, `/` özet sayfası, `/program` editörü.
3. **Faz C — Zil sesi yükleme + ayarlar sayfası**: `/zil-sesi` upload+önizleme, `/ayarlar` toggle'lar.
4. **Faz D — Playlist yönetimi**: `/playlist` listeleme + silme.

Detaylı adım adım uygulama planı `writing-plans` süreciyle ayrıca çıkarılacak.

## Faz A Güncellemesi — Tatil Günleri (2026-09-18, aynı gün içinde eklendi)

Kullanıcı isteği: haftanın 7 günü için zil/teneffüs ayarı web'den yapılabilsin, belirli günler (resmi tatil vb.) takvimden işaretlenip o günlerde zil tamamen kapatılabilsin.

- `ders_programi.json`'a `tatil_gunleri` alanı eklendi: `["YYYY-AA-GG", ...]` formatında, boş başlar.
- `sys.py`'de `ders_programi_yukle_gerekirse()` bu listeyi `TATIL_GUNLERI` (set) olarak tutuyor; `tenefus_otomasyonu()`'nda gün kontrolü artık `isoweekday() in ders_gunleri and bugünün_tarihi not in TATIL_GUNLERI` şeklinde — tatil günü ise zil, teneffüs müziği ve karşılama müziğinin **hepsi** o gün boyunca devre dışı kalıyor (duyuru_otomasyonu etkilenmiyor, o zaten tarihli/tek seferlik ve hafta içi kısıtı yok).
- Bu, dashboard'un `/program` sayfasındaki 7-gün-toggle + takvim gereksinimiyle birlikte yukarıda güncellendi. Faz B uygulanırken bu alanın zaten `sys.py` tarafında okunduğu unutulmamalı — sadece dashboard UI'ı eksik.
- Deploy: aynı gün (2026-09-18, ~09:01) production'a alındı, `ses_bot.service`'e ayrıca `PYTHONUNBUFFERED=1` eklendi (log gecikmesi sorununu çözmek için, davranış değişikliği yok).

## Spec Sonrası Kapsam Genişlemeleri (2026-09-18, bu spec'in kapsamı DIŞINDA — CLAUDE.md/DECISIONS.md güncel kaynak)

Faz A-D bu spec'e birebir uygun ve doğrulanmış şekilde tamamlandıktan sonra, aynı gün içinde kullanıcı isteğiyle bu spec'te öngörülmemiş üç önemli genişleme daha yapıldı. Burada tekrarlamıyorum — ayrıntı için `CLAUDE.md` ve `DECISIONS.md`'ye bakın, sadece bu spec'i güncel tutmak için özetliyorum:

1. **Çoklu program şeması**: `ders_programi.json`'daki tek `dersler`/`ders_gunleri` alanları kaldırıldı, yerine her biri kendi `id`/`ad`/`gunler`/`dersler`'ine sahip `programlar` listesi geldi (hafta içi ≠ Cumartesi saatleri). `sys.py`'de `GUNLUK_PROGRAM = {gun(1-7): {...}}` sözlüğü bunu türetiyor. Yukarıdaki `## ders_programi.json Şeması` bölümü artık **eski** — güncel şema `CLAUDE.md`'nin "`ders_programi.json`" bölümünde.
2. **Katmanlı zil sistemi**: `sabit_ziller` (ör. 08:00 öğrenci toplanması) + `ayarlar.ogrenci_zili_*` ile "öğrenci girişi" / "öğretmen girişi" ayrımı. Gerçek çalma mantığı `sys.py`'de zaten vardı, dashboard'a etiketleme/görselleştirme (`_zil_programi_hesapla()`) eklendi.
3. **Etkinlik (kermes/festival) YouTube çalma** (`/youtube-cal`) — bu spec'in "Kapsam" bölümünde tanımlanmamış tamamen yeni bir alt sistem: dashboard→sys.py dosya-tabanlı komut kanalı (`oynatma_istegi.json`/`oynatma_durumu.json`), teneffüs otomasyonuna hiç karışmıyor. Beraberinde **kritik bir altyapı düzeltmesi** geldi: VLC'ye artık hiçbir yerde canlı YouTube stream URL'si verilmiyor (okul LAN'ı VLC'nin YouTube CDN'ine doğrudan TLS bağlantısını engelliyordu) — önce yerel diske indirilip oradan çalınıyor. Bu, mevcut `/youtube` link-yakalama ve zamanlanmış duyuru YouTube kolunu da düzeltti (muhtemelen önceden sessizce bozuktu).

**Denetim notu (2026-09-19, bu Claude oturumu):** Yukarıdaki üç genişleme kod ve `DECISIONS.md`'deki test kanıtlarıyla doğrulandı, spec'in orijinal "kapsam dışı" kararlarından hiçbirini ihlal etmiyor (Farabi entegrasyonu hâlâ yok, playlist yüklemesi hâlâ Telegram'da, dashboard'dan fiziksel test-çal hâlâ yok). Ayrıca şu an `sys.py`'de commit'lenmemiş bir YouTube bot-koruması düzeltmesi (`player_client: ['android','web']`) var — son servis restart'ından beri hiç YouTube denemesi loglanmadığından henüz doğrulanmadı, commit edilmeden önce test edilmeli.
