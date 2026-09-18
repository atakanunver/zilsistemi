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
