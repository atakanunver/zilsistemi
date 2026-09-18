## 2026-09-17 - Git deposu sifirdan baslatildi (sizan token), sonra GitHub'a push edildi

- `git init` ile ilk kurulumda .gitignore yazilmadan once `git add -A` yapilmisti; env.txt (canli TELEGRAM_TOKEN), cookies.txt, tum mp3/exe/cert dosyalari commit gecmisine girmisti. Hic push edilmeden fark edildi.
- Repo hic paylasilmadigi icin history rewrite yerine `rm -rf .git && git init` ile sifirdan baslatildi, .gitignore yerindeyken `git add .` yapildi. Simdi sadece kod/script dosyalari takipte (env.txt, cookies.txt, mp3ler, sertifikalar, exeler, yedek/ takipte degil).
- Okul LAN'in filtreli interneti GitHub'a SSH (22) ve ssh.github.com:443 ile ulasmayi engelliyordu. Mudur PC'deki WifiHttpProxy (192.168.23.243:8080, CONNECT destekli) uzerinden ~/.ssh/connect_proxy.py (Python HTTP CONNECT tunel scripti) + ~/.ssh/config ProxyCommand ile SSH tunellendi, push basarili oldu (origin main -> github.com:atakanunver/zilsistemi.git).
- Bu proxy-tunel yontemi ayni sekilde farabi, debian/6GB VRAM sunucusu ve yoklama kiosk'a da kuruldu (genel kural olarak global CLAUDE.md'ye eklendi) - okul LAN'daki tum Linux sunuculardan git push/pull icin gecerli.

## 2026-09-18 - Faz A: gercek zil sesi + ders_programi.json (dashboard oncesi cekirdek)

- TENEFUS_PROGRAMI/TENEFUS_OLAYLARI artik hardcoded degil, ders_programi.json'dan (dersler listesi + ders_gunleri + karsilama_muzigi + ayarlar) turetiliyor. sys.py 30sn'lik dongude dosyanin mtime'ini kontrol edip degistiyse yeniden okuyor. Dosya okunamazsa/bozuksa eski hardcoded degerlerle birebir ayni bir varsayilan devreye giriyor (bot canli yayinda config bozulmasiyla cokmesin diye).
- Gercek zil sesi eklendi (ders giris/cikis aninda zil_sesi.mp3 calma) - simdiye kadar sadece teneffus *arasi* muzik vardi. Zil kisa oldugu icin 'not player.is_playing()' korumasi yetersiz kaliyor (30sn dongude ayni dakika 2 kez kontrol edilebilir, cift calar) - bu yuzden ayri bir son_calinan_zil_dakikasi bayragi eklendi.
- zil_sesi.mp3 henuz yok - dosya bulunamazsa sessizce atlaniyor, sadece log uyarisi basiliyor (crash yok).
- Farabi ile hicbir canli baglanti/SSH/senkron yok (kullanici karari, 2026-09-18) - ders_programi.json tek seferlik Farabi'nin zil.json'undan elle kopyalanip artik bagimsiz, ileride web dashboard'dan yonetilecek.
- Deploy: sys.py + ders_programi.json production'a 08:52'de alindi, ses_bot.service restart edildi, teneffus tetikleme anini (08:53) hatasiz gecti.
- Sirada: writing-plans ile detayli uygulama plani + Faz B (Flask+waitress dashboard iskeleti, port 8090).

## 2026-09-18 - Tatil gunleri destegi + PYTHONUNBUFFERED

- Kullanici istegi: haftanin 7 gunu icin zil ayari web'den yapilabilsin, belirli gunler (tatil) takvimden isaretlenip o gun zil tamamen kapatilabilsin.
- ders_programi.json'a tatil_gunleri (['YYYY-AA-GG',...]) eklendi, sys.py bunu TATIL_GUNLERI set'ine yukluyor, tenefus_otomasyonu() gun kontrolune 'bugun tatil degilse' sarti eklendi (zil+tenefus+karsilama muzigi hepsi o gun devre disi kaliyor, duyuru_otomasyonu etkilenmiyor).
- ses_bot.service'e PYTHONUNBUFFERED=1 eklendi - print() ciktilari journalctl'de aninda gorunuyor artik (onceden process restart/exit'e kadar buffer'da bekliyordu, debug'i zorlastiriyordu). Davranis degisikligi yok, sadece log gorunurlugu.
- Spec dosyasi (docs/superpowers/specs/2026-09-18-zil-dashboard-design.md) guncellendi: /program sayfasi artik 7-gun-toggle + tatil takvimi iceriyor.

## 2026-09-18 - Faz B/C/D: web dashboard tamamlandi (dashboard.py, port 8090)

- dashboard.py yazildi (Flask + waitress), ses_dashboard.service olarak deploy edildi (0.0.0.0:8090, PYTHONUNBUFFERED=1, Restart=always). venv'e flask+waitress pip ile eklendi (okul LAN'dan dogrudan calisti, proxy gerekmedi).
- Sayfalar: / (ozet), /program (ders saatleri + haftanin 7 gunu toggle + tatil gunleri ekle/sil), /zil-sesi (yukle+onizle+onayla), /ayarlar (zil/tenefus aç-kapa + ses seviyeleri), /playlist (listele+sil).
- HTTP Basic Auth: admin / env.txt'deki DASHBOARD_PASSWORD (uretildi, kullaniciya iletildi, git'e girmiyor).
- Canli veriyle dikkatli test edildi: mevcut programla idempotent POST (JSON semantik ayni kaldi), gecersiz saat girisi reddedildi + dosya bozulmadi, tatil ekle/sil round-trip calisti, ses_bot.service kesintisiz ayakta kaldi tum test boyunca.
- .gitignore'a *.tmp / *.tmp-yazim eklendi (atomik yazim gecicileri commitlenmesin diye).
- Erisim: http://192.168.23.230:8090 her zaman calisir; avahi aktif oldugundan http://zil.local:8090 da calisir. Salt zil:8090 (NetBIOS, noktasiz) icin nmbd/Samba kurulu degil - istenirse ayrica eklenebilir.
- zil.mp3 kullanici tarafindan proje klasorune eklendi, zil_sesi.mp3 olarak kopyalandi (20sn, siren.mp3'ten farkli olarak kisa - zil icin uygun). siren.mp3'un deprem/sel gibi acil durumlarda SADECE manuel (/siren) kullanilan bir ses oldugu netlesti, hicbir otomasyona baglanmamali (CLAUDE.md'ye eklendi).

## 2026-09-18 - Coklu program semasi: hafta ici / hafta sonu (ve istenirse cumartesi/pazar) ayri ayri

- Kullanici istegi: cumartesi ve pazarin zil programi hafta icinden ayri olsun, saatleri ayri ayarlanabilsin.
- ders_programi.json'daki tekli dersler/ders_gunleri alanlari kaldirildi, yerine programlar listesi geldi: her program kendi id/ad/gunler(1-7)/dersler'ine sahip. Bir gun ayni anda sadece bir programa ait olabilir (dashboard bunu kaydetmeden once kontrol ediyor, cakisirsa reddediyor).
- sys.py: GUNLUK_PROGRAM = {gun(1-7): {olaylar, zil_saatleri}} - _ders_programindan_turet artik her program icin ayri hesaplayip kendi gunlerine dagitiyor. tenefus_otomasyonu() artik o gunun GUNLUK_PROGRAM[bugun] kaydini kullaniyor; gun hicbir programda degilse otomasyon o gun hic calismiyor (guvenli varsayilan).
- Varsayilan migrasyon: mevcut 8 derslik hafta ici program hafta_ici (gun 1-5) olarak tasindi, hafta_sonu (gun 6-7) bos/pasif olarak eklendi - production DAVRANISI DEGISMEDI (hafta sonu zaten otomasyonsuzdu), sadece artik dashboard'dan ayri ayri doldurulabilir.
- Bug fix (ayni oturumda bulundu): sys.py'de VLC ayarlari bolumundeki eski OTOMATIK_SES_SEVIYESI = 50 sabit atamasi, ders_programi.json'dan yuklenen degeri baslangicta eziyor ve dosya tekrar degisene kadar boyle kaliyordu - satir kaldirildi.
- dashboard.py /program sayfasi tamamen coklu-program editorune donusturuldu: her program kendi kartinda (ad, gun toggle'lari, ders saatleri, sil butonu), + yeni program ekleme formu, + hicbir programa atanmamis gunler icin uyari rozeti. Karsilama muzigi ayri bir mini-formda (tum programlar icin ortak).
- Test edildi: gun catismasi (Cuma'yi hem hafta_ici hem hafta_sonuna atamaya calismak) dogru reddedildi, dosya bozulmadi. Python-seviyesinde ayri Cumartesi/Pazar programlariyla farkli saatler dogru hesaplandigi da unit test edildi (test_logic2.py, gecti) - production'a sahte veri konulmadi, gercek hafta sonu saatleri kullanicidan bekleniyor.
- Deploy: sys.py + dashboard.py + ders_programi.json (migrasyonlu) 09:45'te production'a alindi, her iki servis de saglikli restart oldu, traceback yok.
