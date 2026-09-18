# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proje Özeti

Okul zil/anons sistemi: Telegram üzerinden komutla veya otomatik teneffüs programıyla ses çalan bir Python botu. `python-telegram-bot` ile Telegram komutlarını dinliyor, `python-vlc` ile yerel ses dosyalarını / YouTube linklerini (`yt-dlp` ile) çalıyor. Bu makine (`zil`, 192.168.23.230) sadece bu bot için kullanılıyor — bkz. global `CLAUDE.md`'deki "Okul Zil ve Ses Sunucu" notu.

## Çalıştırma / Deploy

- **Production**: `ses_bot.service` adlı systemd servisi (`/etc/systemd/system/ses_bot.service`) `sys.py`'yi `venv` içinden çalıştırıyor, `Restart=always`. Kod değişikliğinden sonra:
  ```bash
  sudo systemctl restart ses_bot
  sudo journalctl -u ses_bot -f          # canlı log
  sudo journalctl -u ses_bot -n 100 --no-pager   # son loglar
  ```
- **venv**: `/home/atakan/ses/venv` — Python **3.14.4** (bilinçli tercih değil, sistemde kurulu en yeni sürüm kullanılmış). Paketler: `python-telegram-bot==22.7`, `python-vlc==3.0.21203`, `yt-dlp==2026.3.17`, `httpx`, `playwright` (kullanılmıyor gibi görünüyor, gereksiz bağımlılık olabilir).
- Manuel çalıştırma: `sudo systemctl stop ses_bot && /home/atakan/ses/venv/bin/python3 /home/atakan/ses/sys.py` (servisle çakışmaması için önce durdurun — ikisi aynı anda Telegram polling yaparsa `Conflict` hatası alınır).
- Sudo şifresi SSH şifresiyle aynı (`1`), NOPASSWD **değil** — diğer bazı okul sunucularının aksine burada `sudo -S` ile şifre girilmesi gerekiyor.

## Mimari

Tek dosyalık bot: `sys.py` (aktif/production kod, `BASE_DIR` = proje kökü).

**Dosya düzeni**: `istiklal.mp3` ve `siren.mp3` sabit olarak `BASE_DIR` kökünde duruyor (kendi `/istiklal`, `/siren` komutları ve sabit reply-keyboard butonları var — `dosya_listele()` menüsünde görünmelerine gerek yok). Diğer tüm ses `BASE_DIR/playlist/` alt klasöründe: **286 adet `muzikN_XXX.mp3` parçası** (2026-09-16'da üretildi — her biri tam 120 saniye, başında/sonunda 2sn `afade`, `split_playlist.sh` ile orijinal uzun dosyalardan (bazıları 3+ saat) kesildi, 2 dakikadan kısa kalan artık parçalar hiç üretilmedi, orijinaller ve tüm `.ogg` dosyaları işlem sonunda silindi — bkz. proje kökündeki `split_playlist.sh` ve `split_progress.log`). `dosya_listele()` sadece `PLAYLIST_DIR`'i (`BASE_DIR/playlist`) tarıyor; `/list` komutu, otomatik teneffüs seçimi ve Telegram'dan ses/voice yükleme (`handle_audio_upload`) hepsi bu klasörü kullanıyor. `PLAYLIST_DIR` yoksa `os.makedirs(..., exist_ok=True)` ile başlangıçta otomatik oluşturuluyor.

- **Telegram komutları** (`yetki_kontrol` ile `env.txt`'deki `CHAT_ID` listesine göre yetkilendiriliyor): `/istiklal`, `/siren`, `/list` (klasördeki ses dosyalarını inline-keyboard ile listeler, `play:<dosya>` callback'i çalar — **286 dosyada Telegram'ın buton/mesaj limitlerini aşıyor olabilir, henüz düzeltilmedi**, bkz. Bilinen Sorunlar), `/ses_artir` / `/ses_azalt`, `/durdur`, `/sil`, `/duyuru_ekle`/`/duyuru_liste`/`/duyuru_sil`, `/reboot` (`sudo reboot` çağırıyor — servis kullanıcısının reboot için parolasız sudo yetkisi olması lazım, yoksa komut sessizce başarısız olur).
- **Dosya silme (`/sil`, 2026-09-16)**: `/sil` (argümansız) veya `/sil sayfa <n>` — `playlist_sayfa_metni()` ile 286 dosyayı **düz metin, sayfalanmış** (40/sayfa, ~700 karakter) şekilde listeler (buton kullanmıyor, `/list`'in olası limit sorununa takılmıyor). `/sil <dosya_adi>` — `os.path.basename()` ile path traversal (`../env.txt` vb.) etkisizleştirilip sadece `PLAYLIST_DIR` içinde silme yapar; `istiklal.mp3`/`siren.mp3` adı açıkça reddedilir.
- **Zamanlanmış tek seferlik duyuru (`/duyuru_ekle`, `/duyuru_liste`, `/duyuru_sil`, 2026-09-16)**: Kalıcılık `BASE_DIR/duyurular.json`'da (`duyurulari_yukle()`/`duyurulari_kaydet()`) — servis restart/reboot sonrası kaldığı yerden devam eder. `/duyuru_ekle YYYY-AA-GG SS:DD <dosya_adi_veya_youtube_linki>` hedefi doğrular (`duyuru_hedefi_gecerli_mi()`: playlist dosyası, istiklal/siren, veya `YOUTUBE_LINK_RE` ile eşleşen link). Arka plan görevi `duyuru_otomasyonu()` (30sn'de bir, **`tenefus_otomasyonu()`'ndan farklı olarak hafta içi kısıtı yok**) zamanı gelen duyuruyu çalar: gecikme ≤2 dk ise hemen çalınır (o an otomatik teneffüs müziği çalıyorsa **kesilir**, duyuru öncelikli — manuel/`current_volume` sayılır), gecikme >2 dk ise (servis o dakikayı kaçırmışsa) **çalınmadan** sadece "kaçırıldı" bildirimi gönderilip listeden düşürülür. Her iki durumda da `AUTHORIZED_IDS`'teki herkese `bot.send_message` ile bildirim gidiyor. YouTube hedefleri `youtube_ses_url_al()` ile çekiliyor (bu, `youtube_link_handler`'la paylaşılan ortak yardımcı fonksiyon).
- **YouTube (komut değil, link algılama)**: `/youtube` komutu **kaldırıldı** (2026-09-16). Bunun yerine `MessageHandler(filters.TEXT & filters.Regex(YOUTUBE_LINK_RE), youtube_link_handler)` — mesaj metninin herhangi bir yerinde `youtube.com/...` veya `youtu.be/...` geçen bir link varsa otomatik yakalanıp yt-dlp (`bestaudio/best`, indirmeden stream URL'si) ile çalınıyor, sabit **%50** ses seviyesinde (`OTOMATIK_SES_SEVIYESI`). yt-dlp doğrudan ham ses akışını çektiği için YouTube oynatıcısının reklamları zaten büyük ölçüde bu akışa dahil olmuyor (istisna: SSAI kullanan canlı yayınlar). `cookies.txt` kasıtlı olarak bağlanmadı (kullanıcı kararı, 2026-09-16).
- **Ses yükleme**: Kullanıcı Telegram'dan audio/voice mesajı gönderirse `handle_audio_upload` dosyayı `playlist/` alt klasörüne kaydediyor (`gelen_<timestamp>.mp3/.ogg`).
- **Teneffüs/giriş otomasyonu** (`tenefus_otomasyonu()`, arka plan task, 30sn'de bir `HH:MM` string karşılaştırması, sadece Pazartesi–Cuma çalışır — `isoweekday() in (1,2,3,4,5)`, Farabi'nin `ders_gunleri`siyle tutarlı):
  - `TENEFUS_PROGRAMI`'deki 7 (ders çıkışı, sonraki ders girişi) çifti — kaynak: Farabi sunucusundaki resmi e-Okul çizelgesi (`/home/ata/farabi/tahtayoklama/dashboard/data/zil.json`); okul zili değişirse **iki dosya da elle senkron edilmeli** (otomatik senkron yok).
  - Her çift için `TENEFUS_OLAYLARI` iki türetilmiş zaman hesaplıyor (`saat_ekle()` ile): **`baslama` = ders çıkışı + 3 dk**, **`durdurma` = sonraki ders girişi − 2 dk**. `baslama`'da `playlist/`'ten rastgele bir parça (`rastgele_playlist_dosyasi()`) seçilip %50 sesle çalınır ve `otomatik_calan=True` işaretlenir; parça zaten ~2 dk olduğundan çoğunlukla kendiliğinden biter. `durdurma` sadece **hâlâ çalıyorsa VE `otomatik_calan==True` ise** durdurur — elle başlatılan (istiklal/siren/liste/youtube) çalma bir "etkinlik" sayılır ve bu zorla-durdurmadan muaf tutulur (her manuel komut kendi çalma anında `otomatik_calan=False` ve `player.audio_set_volume(current_volume)` set ediyor, böylece otomasyonun düşürdüğü ses seviyesi/bayrak manuel oynatmaya sızmıyor).
  - Ayrıca sabit bir 8. slot: **07:50–07:55 arası** (ilk ders 08:10'da başlıyor) rastgele bir parça çalınıyor — "okul girişi karşılama müziği" (2026-09-16, kullanıcı isteği), `TENEFUS_OLAYLARI` listesine elle eklendi.
- Tek bir global `vlc.MediaPlayer` instance'ı var — aynı anda tek ses çalınabiliyor, yeni bir çalma isteği öncekini kesiyor. `current_volume` (varsayılan %70, `/ses_artir`/`/ses_azalt` ile değişir) manuel çalmalarda, `OTOMATIK_SES_SEVIYESI` (%50, sabit) otomatik teneffüs/giriş/YouTube çalmalarında kullanılıyor.

## Ortam Değişkenleri (`env.txt`)

`ayarlari_yukle()` proje kökündeki `env.txt`'yi (`utf-8-sig`, BOM'lu) `KEY=VALUE` formatında okuyor: `TELEGRAM_TOKEN` ve `CHAT_ID` (virgülle ayrılmış, yetkili Telegram chat id'leri). **Bu dosyayı asla artifact/web/dış servise göndermeyin veya içeriğini dışarı kopyalamayın** — canlı bot token'ı içeriyor.

## Git (2026-09-17'de eklendi)

`/home/atakan/ses` bugün (2026-09-17) git deposu haline getirildi: `origin` → `git@github.com:atakanunver/zilsistemi.git` (SSH). Push için bir SSH anahtarı da üretildi (`~/.ssh/id_ed25519`, public key yorumu `atakanunver1@gmail.com`).

**Bir kez düzeltme yapıldı (2026-09-17)**: İlk kurulumda `.gitignore` yazılmadan önce `git add -A` ile proje kökü tamamen commit'lenmişti — `env.txt` (canlı `TELEGRAM_TOKEN`), `cookies.txt`, tüm `.mp3`/`.cer`/`.crt`/`.exe` dosyaları ve `yedek/` dahil. Bu **hiç push edilmeden** fark edildi (doğrulama: `refs/remotes/origin/*` yoktu, reflog'da push izi yoktu). Kullanıcı isteğiyle depo sıfırdan başlatıldı (`rm -rf .git && git init` — history rewrite'a gerek kalmadı, çünkü hiç paylaşılmamıştı) ve `.gitignore` zaten yerindeyken `git add .` yapıldı. Şu an takip edilen dosyalar sadece: `.gitignore`, `CLAUDE.md`, `sys.py` ve diğer tarihli/isimli Python kopyaları (`sertifikalısys.py`, `sys14052026.py`, `sys1628saat.py`, `youtube-sys.py`), `split_playlist.sh` — **env.txt, cookies.txt, mp3'ler, sertifikalar, exe'ler ve `yedek/` takipte değil** (`git ls-files` ile doğrulandı).

**Push başarılı (2026-09-17, bkz. `DECISIONS.md`)** — okul LAN'ının filtreli interneti GitHub'a doğrudan SSH (22) ile ulaşmayı engelliyordu; Müdür PC'deki WifiHttpProxy (`192.168.23.243:8080`, CONNECT destekli) üzerinden `~/.ssh/connect_proxy.py` (HTTP CONNECT tünel script'i) + `~/.ssh/config`'teki `ProxyCommand` ile tünellenerek çözüldü, `origin main` → `github.com:atakanunver/zilsistemi.git` push edildi. Bu yöntem aynı şekilde farabi, debian/6GB VRAM sunucusu ve yoklama kiosk'a da kuruldu (genel kural olarak global `CLAUDE.md`'ye eklendi). Kod değişikliğinden sonra normal `git push` yeterli, ekstra bir şey gerekmez.

## Bilinen Sorunlar / Dikkat Edilecekler

- **`/list` muhtemelen 286 dosyada bozuk/kullanışsız** (düzeltilmedi — kullanıcı önerilen 10 özellikten bunu değil, `/sil` ve `/duyuru`'yu seçti, 2026-09-16): `list_files()` her dosya için ayrı bir inline-keyboard butonu oluşturuyor; Telegram'ın mesaj/keyboard limitleri (uzun mesajlarda/çok satırda) aşılabilir. `/sil`'in düz-metin sayfalama yaklaşımı bunun geçici bir yan-çözümü ama `/list`'in kendisi hâlâ eski (buton tabanlı) halinde.
- ~~`TENEFUS_PROGRAMI`daki dosya adları klasörde yok~~ — **2026-09-16'da düzeltildi**, iki aşamalı: önce sabit `muzikN.mp3` adlarına geçildi, sonra tamamen **rastgele seçime** geçildi (`rastgele_playlist_dosyasi()`) — artık `TENEFUS_PROGRAMI` dosya adı taşımıyor, sadece saat çiftleri var. `playlist/` boşalırsa (`dosya_listele()` boş liste dönerse) otomasyon sessizce hiçbir şey çalmaz — hata loglanmıyor, dikkat edilmeli.
- **Kullanılmayan kod**: `main()` içinde `client = httpx.AsyncClient(verify=False)` oluşturuluyor ama hiçbir yerde kullanılmıyor (bot `ApplicationBuilder().token(TOKEN).request(HTTPXRequest()).build()` ile varsayılan SSL doğrulamasıyla kuruluyor). Loglarda tekrar eden `httpx.ConnectError` / `Bad Gateway` / `NetworkError` kayıtları var (son 2000 log satırında 32 adet) — okul LAN'ının filtreli internet çıkışı ile ilgili olabilir (bkz. global `CLAUDE.md`'deki diğer sunucu notları), henüz kök nedeni doğrulanmadı. `Restart=always` sayesinde servis kendini topluyor.
- **Windows kalıntıları**: `ffmpeg.exe`, `ffplay.exe`, `ffprobe.exe` bu Linux makinede işlevsiz (muhtemelen proje ilk Windows'ta geliştirilip sonra buraya taşınmış — `yedek/kur.bat` ve `yedek/run.bat` da Windows kurulum/çalıştırma script'leri, artık kullanılmıyor).
- **`fatihca.cer`, `fatihca1.cer`, `meb_sertifika.crt`**: Hiçbir script tarafından referans edilmiyor (grep ile doğrulandı) — muhtemelen okul ağının SSL/TLS araya-girme sertifikasıyla ilgili teşhis amaçlı indirilmiş, aktif kullanılmıyor.
- **`cookies.txt`**: yt-dlp/Netscape formatında, 7 adet youtube.com cookie'si içeriyor (14 Mayıs 2026 tarihli, muhtemelen artık geçersiz). `ydl_opts`'a kasıtlı olarak bağlanmadı — kullanıcı reklam sorununu zaten çözülmüş kabul etti (yt-dlp ham ses akışını çektiği için YouTube'un oynatıcı-taraflı reklamları zaten devreye girmiyor) ve wiring istemedi (2026-09-16). Gerekirse taze bir cookies.txt ile (`yt-dlp --cookies-from-browser ... --cookies cookies.txt`) tekrar üretilip `'cookiefile': os.path.join(BASE_DIR, 'cookies.txt')` eklenebilir.
- **`split_playlist.sh`, `split_progress.log`, `split_stdout.log`** (proje kökü): 2026-09-16'da playlist'i 286 parçaya bölmek için kullanılan tek seferlik script ve logları — production'da bot tarafından kullanılmıyor, geçmiş referans/denetim amaçlı duruyor. Playlist'e yeni uzun bir dosya eklenip tekrar bölünmesi gerekirse script tekrar çalıştırılabilir (mevcut `muzikN_XXX.mp3` adlarıyla çakışmaz, `basename` orijinal dosya adına göre türetiyor).

## Diğer Python Dosyaları (kök dizin)

`sys.py` dışındakiler **production'da kullanılmıyor**, tarihli/isimli anlık kopyalar (manuel yedekleme alışkanlığı — git 2026-09-17'ye kadar hiç kullanılmıyordu, bkz. yukarıdaki "Git" bölümü):
- `sys14052026.py`, `sys1628saat.py` — tarih/saat etiketli eski sürümler.
- `sertifikalısys.py` — `yt-dlp`'de `nocheckcertificate` ve VLC'de `gnutls-verify-trust=0` deneyen bir varyant (SSL sorunlarını aşmak için).
- `youtube-sys.py` — YouTube entegrasyonunun ayrıca denendiği bir varyant.
- `yedek/` klasörü — daha eski "Kopya" (copy) dosyaları, aynı şekilde referans/yedek amaçlı, silinmemiş.

Yeni bir özellik eklerken/düzeltme yaparken sadece `sys.py`'yi değiştirin; diğerleri tarihsel referans, production'a etkisi yok.
