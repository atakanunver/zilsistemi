# -*- coding: utf-8 -*-
import os
import re
import json
import time
import ssl
import uuid
import httpx
import warnings
import vlc
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.request import HTTPXRequest
import yt_dlp

# --- 0. AYARLAR ---
warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlist")
os.makedirs(PLAYLIST_DIR, exist_ok=True)

# Ders programı — 2026-09-18'den itibaren ders_programi.json'dan okunuyor (bkz.
# docs/superpowers/specs/2026-09-18-zil-dashboard-design.md). Kaynak: Farabi
# sunucusundaki resmi e-Okul çizelgesi (/home/ata/farabi/tahtayoklama/dashboard/data/zil.json).
# Okul zili değişirse iki dosya da elle senkron edilmeli (otomatik senkron yok).
DERS_PROGRAMI_DOSYASI = os.path.join(BASE_DIR, "ders_programi.json")

def saat_ekle(saat_str, dakika):
    t = datetime.strptime(saat_str, "%H:%M") + timedelta(minutes=dakika)
    return t.strftime("%H:%M")

# ders_programi.json okunamazsa/bozuksa kullanılan güvenli varsayılan — bot canlı
# yayında konfigürasyon dosyasının bozulmasıyla çökmesin diye (2026-09-16 öncesi
# hardcoded TENEFUS_PROGRAMI ile birebir aynı hafta içi ders saatleri).
# 2026-09-18: "dersler"/"ders_gunleri" tekliğinden "programlar" listesine geçildi —
# her program kendi gün kümesine (gunler) ve kendi ders saatlerine sahip, böylece
# hafta içi ve hafta sonu (hatta istenirse Cumartesi/Pazar ayrı ayrı) bağımsız
# saatlerle yapılandırılabiliyor. Bir gün hiçbir programın gunler'inde değilse o gün
# otomasyon hiç çalışmaz (varsayılan: hafta sonu için boş/pasif).
_VARSAYILAN_DERS_PROGRAMI = {
    "programlar": [
        {
            "id": "hafta_ici",
            "ad": "Hafta İçi",
            "gunler": [1, 2, 3, 4, 5],
            "dersler": [
                {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
                {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
                {"no": 3, "baslangic": "09:50", "bitis": "10:30"},
                {"no": 4, "baslangic": "10:40", "bitis": "11:20"},
                {"no": 5, "baslangic": "11:30", "bitis": "12:10"},
                {"no": 6, "baslangic": "13:30", "bitis": "14:10"},
                {"no": 7, "baslangic": "14:20", "bitis": "15:00"},
                {"no": 8, "baslangic": "15:10", "bitis": "15:50"},
            ],
        },
        {"id": "hafta_sonu", "ad": "Hafta Sonu", "gunler": [6, 7], "dersler": []},
    ],
    # Sabit (belirli bir derse bağlı olmayan) ziller — ör. gün başlangıcı/öğle sonrası
    # öğrenci toplanma zili. Her biri kendi "gunler" listesine sahip (program günleriyle
    # aynı ISO gün no'ları), o gün için bir program atanmışsa VE tatil değilse çalar.
    "sabit_ziller": [
        {"saat": "08:00", "aciklama": "Öğrenci toplanması", "gunler": [1, 2, 3, 4, 5]},
        {"saat": "13:20", "aciklama": "Öğrenci toplanması (öğleden sonra)", "gunler": [1, 2, 3, 4, 5]},
    ],
    "tatil_gunleri": [],
    "karsilama_muzigi": {"aktif": True, "baslama": "07:50", "durdurma": "07:55"},
    "ayarlar": {
        "zil_aktif": True,
        "tenefus_muzigi_aktif": True,
        "otomatik_ses_seviyesi": 50,
        "zil_ses_seviyesi": 80,
        # Kısa teneffüslerde (ders çıkışı ile sonraki giriş arası ≤ ogrenci_zili_max_bosluk_dk
        # olan aralar) çıkış zilinden ogrenci_zili_offset_dk dakika sonra ekstra bir "öğrenci
        # zili" çalar (ör. 08:50 çıkış → 08:55 öğrenci zili → 09:00 giriş). Uzun aralar (öğle
        # arası gibi) bu eşiği aştığı için otomatik olarak dışarıda kalır.
        "ogrenci_zili_aktif": True,
        "ogrenci_zili_offset_dk": 5,
        "ogrenci_zili_max_bosluk_dk": 20,
    },
}

ders_programi = {}
ders_programi_mtime = None
GUNLUK_PROGRAM = {}  # {isoweekday(1-7): {"olaylar": [...], "zil_saatleri": [...]}}
TATIL_GUNLERI = set()
OTOMATIK_SES_SEVIYESI = 50
son_calinan_zil_dakikasi = None

def _program_olaylarini_hesapla(program, karsilama, ayarlar):
    # Teneffüs çiftleri: her ardışık ders ikilisi için (bitiş, sonraki başlangıç) —
    # eski hardcoded TENEFUS_PROGRAMI mantığının aynısı, artık ders listesinden türetilmiş.
    # Müzik çıkıştan 3dk sonra başlar, girişe 2dk kala (hâlâ çalıyor VE otomatik başlatıldıysa) durur.
    dersler = sorted(program.get("dersler", []), key=lambda d: d["baslangic"])
    if len(dersler) < 2:
        olaylar = []
    else:
        olaylar = [
            {"baslama": saat_ekle(dersler[i]["bitis"], 3), "durdurma": saat_ekle(dersler[i + 1]["baslangic"], -2)}
            for i in range(len(dersler) - 1)
        ]
    # Karşılama müziği sadece o gün gerçekten ders varsa eklenir (dersler boşsa gün zaten pasif sayılır).
    if dersler and karsilama.get("aktif"):
        olaylar = olaylar + [{"baslama": karsilama["baslama"], "durdurma": karsilama["durdurma"]}]
    # Zil saatleri: tüm ders başlangıç/bitiş saatlerinin birleşimi (öğle arası için ayrı
    # bir nokta gerekmiyor — dersler[i].bitis ve dersler[i+1].baslangic zaten kümede).
    zil_saatleri = {d["baslangic"] for d in dersler} | {d["bitis"] for d in dersler}
    # Öğrenci zili (2026-09-18, kullanıcı isteği): kısa teneffüslerde ders çıkışından
    # birkaç dakika sonra, girişten hemen önce ekstra bir uyarı zili — ör. 08:50 çıkış →
    # (offset=5) 08:55 öğrenci zili → 09:00 giriş. Uzun aralar (öğle arası gibi) elenir.
    if ayarlar.get("ogrenci_zili_aktif", True) and len(dersler) >= 2:
        offset = ayarlar.get("ogrenci_zili_offset_dk", 5)
        max_boslu = ayarlar.get("ogrenci_zili_max_bosluk_dk", 20)
        for i in range(len(dersler) - 1):
            cikis = datetime.strptime(dersler[i]["bitis"], "%H:%M")
            giris = datetime.strptime(dersler[i + 1]["baslangic"], "%H:%M")
            bosluk_dk = (giris - cikis).total_seconds() / 60
            if 0 < bosluk_dk <= max_boslu:
                zil_saatleri.add(saat_ekle(dersler[i]["bitis"], offset))
    return olaylar, sorted(zil_saatleri)

def _ders_programindan_turet(veri):
    karsilama = veri.get("karsilama_muzigi", {})
    ayarlar = veri.get("ayarlar", {})
    sabit_ziller = veri.get("sabit_ziller", [])
    gunluk = {}
    for program in veri["programlar"]:
        olaylar, zil_saatleri = _program_olaylarini_hesapla(program, karsilama, ayarlar)
        for gun in program.get("gunler", []):
            # Sabit ziller (ör. 08:00/13:20 öğrenci toplanması) — sadece bu güne atanmış
            # olanlar eklenir; bir program o gün geçerliyse (ders var/yok fark etmez) çalar.
            ek_ziller = {sz["saat"] for sz in sabit_ziller if gun in sz.get("gunler", [])}
            gunluk[gun] = {"olaylar": olaylar, "zil_saatleri": sorted(set(zil_saatleri) | ek_ziller)}
    return gunluk

def ders_programi_yukle_gerekirse():
    # sys.py 30sn'de bir çağırır; dosya değişmediyse hiçbir şey yapmaz (mtime kontrolü).
    global ders_programi, ders_programi_mtime, GUNLUK_PROGRAM, TATIL_GUNLERI, OTOMATIK_SES_SEVIYESI
    try:
        mtime = os.path.getmtime(DERS_PROGRAMI_DOSYASI)
    except OSError:
        mtime = None
    if mtime == ders_programi_mtime and ders_programi:
        return
    veri = None
    if mtime is not None:
        try:
            with open(DERS_PROGRAMI_DOSYASI, "r", encoding="utf-8") as f:
                veri = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️ ders_programi.json okunamadı, önceki/varsayılan program kullanılıyor: {e}")
    if veri is None:
        veri = ders_programi if ders_programi else _VARSAYILAN_DERS_PROGRAMI
    try:
        gunluk = _ders_programindan_turet(veri)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        print(f"⚠️ ders_programi.json geçersiz, varsayılan program kullanılıyor: {e}")
        veri = _VARSAYILAN_DERS_PROGRAMI
        gunluk = _ders_programindan_turet(veri)
    ders_programi = veri
    ders_programi_mtime = mtime
    GUNLUK_PROGRAM = gunluk
    # Tatil günleri: "YYYY-AA-GG" formatında tarihler — takvimden işaretlenen bu günlerde
    # hangi programa denk gelirse gelsin zil/teneffüs otomasyonu tamamen devre dışı kalır.
    TATIL_GUNLERI = set(veri.get("tatil_gunleri", []))
    OTOMATIK_SES_SEVIYESI = veri.get("ayarlar", {}).get("otomatik_ses_seviyesi", 50)

ders_programi_yukle_gerekirse()

otomatik_calan = False

def ayarlari_yukle():
    ayarlar = {}
    try:
        # UTF-8-SIG kullanarak BOM karakteri sorununu önlüyoruz
        with open(os.path.join(BASE_DIR, "env.txt"), "r", encoding="utf-8-sig") as f:
            for satir in f:
                satir = satir.strip()
                if satir and "=" in satir:
                    k, v = satir.split("=", 1)
                    ayarlar[k.strip()] = v.strip()
        return ayarlar
    except Exception as e:
        print(f"Ayar dosyası okuma hatası: {e}")
        return None

config = ayarlari_yukle()
if not config:
    print("HATA: env.txt dosyası bulunamadı veya okunamadı!")
    exit()

TOKEN = config.get("TELEGRAM_TOKEN")
# CHAT_ID listesini integer listesine çeviriyoruz (Daha güvenli kontrol için)
AUTHORIZED_IDS = [int(id.strip()) for id in config.get("CHAT_ID", "").split(",") if id.strip()]

# Zamanlanmış tek seferlik duyurular — kalıcı JSON, servis restart/reboot sonrası korunur.
DUYURU_DOSYASI = os.path.join(BASE_DIR, "duyurular.json")

def duyurulari_yukle():
    try:
        with open(DUYURU_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def duyurulari_kaydet(duyurular):
    with open(DUYURU_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(duyurular, f, ensure_ascii=False, indent=2)

# VLC Ayarları
instance = vlc.Instance('--no-video --quiet')
player = instance.media_player_new()
current_volume = 70
# OTOMATIK_SES_SEVIYESI artık ders_programi.json'daki ayarlar.otomatik_ses_seviyesi'nden
# geliyor (bkz. ders_programi_yukle_gerekirse() yukarıda) — burada YENİDEN ATAMA YAPMAYIN,
# yoksa dashboard'dan yapılan ses seviyesi değişikliği dosya bir daha değişene kadar sessizce
# 50'ye geri döner (2026-09-18'de bulunan bug, bkz. DECISIONS.md).
player.audio_set_volume(current_volume)

# --- 1. YARDIMCI FONKSİYONLAR ---
async def yetki_kontrol(update: Update):
    chat_id = update.effective_chat.id
    return chat_id in AUTHORIZED_IDS

def dosya_listele():
    uzantilar = ('.mp3', '.wav', '.ogg', '.opus', '.m4a')
    # Sadece playlist/ alt klasöründeki dosyaları getir (istiklal/siren ayrı komut/buton)
    return [f for f in os.listdir(PLAYLIST_DIR) if f.lower().endswith(uzantilar)]

def rastgele_playlist_dosyasi():
    dosyalar = dosya_listele()
    return random.choice(dosyalar) if dosyalar else None

def playlist_sayfa_metni(sayfa=1, sayfa_boyutu=40):
    dosyalar = sorted(dosya_listele())
    toplam = len(dosyalar)
    if toplam == 0:
        return "Playlist'te dosya yok."
    toplam_sayfa = (toplam + sayfa_boyutu - 1) // sayfa_boyutu
    sayfa = max(1, min(sayfa, toplam_sayfa))
    baslangic = (sayfa - 1) * sayfa_boyutu
    parca = dosyalar[baslangic: baslangic + sayfa_boyutu]
    satirlar = "\n".join(parca)
    return (
        f"📁 Playlist ({toplam} dosya) — sayfa {sayfa}/{toplam_sayfa}:\n{satirlar}\n\n"
        f"Silmek için: /sil <dosya_adi>\nDiğer sayfa: /sil sayfa <n>"
    )

async def tenefus_otomasyonu():
    global otomatik_calan, son_calinan_zil_dakikasi
    while True:
        ders_programi_yukle_gerekirse()
        simdi_dt = datetime.now()
        bugun_tatil = simdi_dt.strftime("%Y-%m-%d") in TATIL_GUNLERI
        gunun_programi = GUNLUK_PROGRAM.get(simdi_dt.isoweekday())
        if gunun_programi and not bugun_tatil:
            simdi = simdi_dt.strftime("%H:%M")
            ayarlar = ders_programi.get("ayarlar", {})
            zil_saatleri = gunun_programi["zil_saatleri"]
            olaylar = gunun_programi["olaylar"]

            # Gerçek zil sesi (ders giriş/çıkış anı) — teneffüs müziğinden farklı olarak
            # kısa bir ses olduğu için "not player.is_playing()" yeterli çift-tetiklenme
            # koruması sağlamaz (30sn'lik döngü aynı dakikada 2 kez kontrol edebilir).
            # Bu yüzden ayrı, açık bir "bu dakika zaten çalındı" bayrağı kullanılıyor.
            if ayarlar.get("zil_aktif", True) and simdi in zil_saatleri and simdi != son_calinan_zil_dakikasi:
                son_calinan_zil_dakikasi = simdi
                zil_yolu = os.path.join(BASE_DIR, "zil_sesi.mp3")
                if os.path.exists(zil_yolu):
                    player.set_media(instance.media_new(zil_yolu))
                    player.play()
                    player.audio_set_volume(ayarlar.get("zil_ses_seviyesi", 80))
                    otomatik_calan = True
                    print(f"🔔 Zil çalındı: {simdi}")
                else:
                    print(f"⚠️ Zil çalınamadı, zil_sesi.mp3 bulunamadı (saat {simdi})")

            if ayarlar.get("tenefus_muzigi_aktif", True):
                for olay in olaylar:
                    if simdi == olay["baslama"] and not player.is_playing():
                        dosya = rastgele_playlist_dosyasi()
                        if dosya:
                            yol = os.path.join(PLAYLIST_DIR, dosya)
                            player.set_media(instance.media_new(yol))
                            player.play()
                            player.audio_set_volume(OTOMATIK_SES_SEVIYESI)
                            otomatik_calan = True
                            print(f"🔔 Otomatik teneffüs müziği başladı: {dosya} (%{OTOMATIK_SES_SEVIYESI})")
                    if simdi == olay["durdurma"] and player.is_playing() and otomatik_calan:
                        player.stop()
                        print("🔕 Ders girişine 2 dk kala otomatik müzik durduruldu.")
        await asyncio.sleep(30)

# --- 2. KOMUTLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    kb = [
        ['/istiklal', '/siren'], ['/list', '/durdur'],
        ['/ses_artir', '/ses_azalt'], ['/sil', '/duyuru_liste'], ['/reboot'],
    ]
    await update.message.reply_text(
        "🏫 Okul Zil Sistemi Aktif.\n"
        "YouTube: bir YouTube linki yapıştırmanız yeterli, otomatik çalar.\n"
        "Dosya silme: /sil (liste) veya /sil <dosya_adi>\n"
        "Zamanlanmış duyuru: /duyuru_ekle YYYY-AA-GG SS:DD <dosya_veya_link>, /duyuru_liste, /duyuru_sil <id>",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def istiklal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global otomatik_calan
    yol = os.path.join(BASE_DIR, "istiklal.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        player.audio_set_volume(current_volume)
        otomatik_calan = False
        await update.message.reply_text("🇹🇷 İstiklal Marşı çalınıyor...")
    else:
        await update.message.reply_text("❌ istiklal.mp3 bulunamadı!")

async def siren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global otomatik_calan
    yol = os.path.join(BASE_DIR, "siren.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        player.audio_set_volume(current_volume)
        otomatik_calan = False
        await update.message.reply_text("🚨 Siren çalınıyor!")
    else:
        await update.message.reply_text("❌ siren.mp3 bulunamadı!")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    dosyalar = dosya_listele()
    if not dosyalar:
        return await update.message.reply_text("Klasörde ses dosyası yok.")
    
    kb = []
    for f in dosyalar:
        # Telegram callback_data 64 byte sınırı vardır. Dosya adı çok uzunsa kırpıyoruz.
        callback_data = f"play:{f}"
        if len(callback_data.encode('utf-8')) > 64:
            # Sınırı aşan dosyaları listede göster ama uyarı ver (veya güvenli bir ID ata)
            kb.append([InlineKeyboardButton(f"⚠️ İsim Çok Uzun: {f[:20]}...", callback_data="error_long")])
        else:
            kb.append([InlineKeyboardButton(f"▶️ {f}", callback_data=callback_data)])
            
    await update.message.reply_text("Mevcut Sesler:", reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await yetki_kontrol(update): return
    global otomatik_calan

    await query.answer()
    if query.data == "error_long":
        await query.message.reply_text("❌ Bu dosyanın adı çok uzun olduğu için Telegram üzerinden başlatılamıyor.")
        return

    if query.data.startswith("play:"):
        dosya = query.data.split(":", 1)[1]
        yol = os.path.join(PLAYLIST_DIR, dosya)
        if os.path.exists(yol):
            player.set_media(instance.media_new(yol))
            player.play()
            player.audio_set_volume(current_volume)
            otomatik_calan = False
            await query.edit_message_text(f"▶️ Şu an çalıyor: {dosya}")
        else:
            await query.edit_message_text(f"❌ Dosya bulunamadı: {dosya}")

async def handle_audio_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    try:
        msg = update.message
        audio_source = msg.audio or msg.voice
        file = await audio_source.get_file()
        
        # Dosya adını belirleme
        if msg.audio and msg.audio.file_name:
            dosya_adi = msg.audio.file_name
        else:
            ext = ".ogg" if msg.voice else ".mp3"
            dosya_adi = f"gelen_{int(time.time())}{ext}"
            
        save_path = os.path.join(PLAYLIST_DIR, dosya_adi)
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"✅ Kaydedildi: {dosya_adi}")
    except Exception as e:
        await update.message.reply_text(f"❌ Kayıt hatası: {e}")

async def control_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global current_volume
    if "artir" in update.message.text:
        current_volume = min(100, current_volume + 10)
    else:
        current_volume = max(0, current_volume - 10)
        
    player.audio_set_volume(current_volume)
    await update.message.reply_text(f"🔊 Ses Seviyesi: %{current_volume}")

YOUTUBE_LINK_RE = re.compile(r'(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/\S+', re.IGNORECASE)

# Okul LAN'ının güvenlik duvarı bu sunucudan YouTube'un CDN'ine (googlevideo.com) doğrudan
# TLS bağlantısı kurulmasını engelliyor (2026-09-18'de doğrulandı: VLC "TLS handshake:
# Connection reset by peer" / "Network is unreachable" ile başarısız oluyordu — yt-dlp'nin
# nocheckcertificate'i ve VLC'nin :gnutls-verify-trust=0'ı bile bunu çözmedi, sertifika
# değil bağlantının kendisi engelleniyor). Ama yt-dlp'nin KENDİ indirme mekanizması çalışıyor
# (aynı doğrulamada: eski yt-dlp 2026.3.17 "403 Forbidden" veriyordu, 2026.8.19'a yükseltince
# düzeldi — YouTube'un bot-koruması ile ilgiliymiş, ağ engeliyle ilgisi yokmuş). Bu yüzden
# VLC'ye asla ham CDN akış URL'si verilmiyor: önce yt-dlp ile geçici bir dosyaya indirilip
# VLC o YEREL dosyayı çalıyor (playlist/'teki mp3'leri çalmasıyla aynı, ağ gerektirmez).
YOUTUBE_CACHE_DIR = os.path.join(BASE_DIR, "youtube_cache")
os.makedirs(YOUTUBE_CACHE_DIR, exist_ok=True)
_son_youtube_gecici_dosya = None

def youtube_indir(url):
    global _son_youtube_gecici_dosya
    if _son_youtube_gecici_dosya and os.path.exists(_son_youtube_gecici_dosya):
        try:
            os.remove(_son_youtube_gecici_dosya)
        except OSError:
            pass
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'outtmpl': os.path.join(YOUTUBE_CACHE_DIR, f"{uuid.uuid4()}.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        dosya_yolu = ydl.prepare_filename(info)
    _son_youtube_gecici_dosya = dosya_yolu
    return dosya_yolu, info.get('title', 'YouTube Video')

async def youtube_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Komut değil: mesaj metninde YouTube linki geçiyorsa direkt çalar (2026-09-16, kullanıcı isteği)
    if not await yetki_kontrol(update): return
    global otomatik_calan
    eslesme = YOUTUBE_LINK_RE.search(update.message.text or "")
    if not eslesme:
        return
    url = eslesme.group(0)

    durum_mesaji = await update.message.reply_text("🌐 YouTube'dan indiriliyor...")
    try:
        dosya_yolu, baslik = youtube_indir(url)
        player.set_media(instance.media_new(dosya_yolu))
        player.play()
        player.audio_set_volume(OTOMATIK_SES_SEVIYESI)  # bu özellik için sabit %50 istendi
        otomatik_calan = False
        await durum_mesaji.edit_text(f"▶️ Oynatılıyor (%{OTOMATIK_SES_SEVIYESI} ses): {baslik}")
    except Exception as e:
        await durum_mesaji.edit_text(f"❌ YouTube Hatası: {str(e)[:100]}")

# --- Etkinlik oynatma kuyruğu (dashboard'dan tetiklenir, 2026-09-18) ---
# Kermes/festival gibi etkinliklerde kullanıcının kendi YouTube playlist'ini (veya tek
# video linkini) dashboard'dan yapıştırıp doğrudan hoparlörden çaldırabilmesi için.
# İndirilen dosyalar geçici (YOUTUBE_CACHE_DIR, playlist ile ilgisi yok) — playlist/
# klasörüne hiç dokunmuyor, teneffüs otomasyonunun rastgele seçimine karışmıyor
# (bilinçli, kullanıcı isteği: "etkinlikler kermes festival tarzı için, teneffüslerde
# çalması için değil").
# dashboard.py ile bu process arasında canlı IPC yok (proje kuralı, ders_programi.json'la
# aynı desen) — basit bir dosya-tabanlı komut kanalı: dashboard oynatma_istegi.json'a
# yazar, burada 3sn'de bir okunup işlenir, sonuç oynatma_durumu.json'a yazılır (dashboard
# bunu polling'ler).
OYNATMA_ISTEGI_DOSYASI = os.path.join(BASE_DIR, "oynatma_istegi.json")
OYNATMA_DURUMU_DOSYASI = os.path.join(BASE_DIR, "oynatma_durumu.json")

etkinlik_kuyrugu = []
etkinlik_indeks = 0
etkinlik_calisiyor = False
_son_istek_id = None

def _oynatma_durumu_yaz(veri):
    tmp = OYNATMA_DURUMU_DOSYASI + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(tmp, OYNATMA_DURUMU_DOSYASI)

def _youtube_kuyruk_cikar(url):
    # extract_flat=True: her videoyu tek tek çözmeden hızlıca id/başlık listesi alır
    # (playlist linkiyse entries döner, tek video linkiyse tek kayıt döner). Her parçanın
    # gerçek indirmesi (youtube_indir) çalınmadan hemen önce, tek tek yapılıyor.
    ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get('entries'):
        kayitlar = [e for e in info['entries'] if e]
        return [f"https://www.youtube.com/watch?v={e['id']}" for e in kayitlar if e.get('id')]
    return [url]

def _etkinlik_parca_cal(sira_no):
    global otomatik_calan
    dosya_yolu, baslik = youtube_indir(etkinlik_kuyrugu[sira_no])
    player.set_media(instance.media_new(dosya_yolu))
    player.play()
    player.audio_set_volume(current_volume)
    otomatik_calan = False
    _oynatma_durumu_yaz({
        "durum": "calindi", "baslik": baslik,
        "sira": sira_no + 1, "toplam": len(etkinlik_kuyrugu),
    })
    print(f"🎉 Etkinlik oynatma: {baslik} ({sira_no + 1}/{len(etkinlik_kuyrugu)})")

async def etkinlik_dinleyici():
    global etkinlik_kuyrugu, etkinlik_indeks, etkinlik_calisiyor, _son_istek_id
    while True:
        # 1) Dashboard'dan yeni bir istek geldi mi? (istek_id her tıklamada değişir)
        try:
            with open(OYNATMA_ISTEGI_DOSYASI, "r", encoding="utf-8") as f:
                istek = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            istek = None

        if istek and istek.get("istek_id") != _son_istek_id:
            _son_istek_id = istek["istek_id"]
            # İşlenen istek hemen silinir — yoksa servis restart olduğunda (_son_istek_id
            # bellekte sıfırlanır) eski istek "yeni" sanılıp tekrar çalınır (2026-09-18'de
            # canlı derste yakalandı: bir önceki test isteği restart sonrası kendiliğinden
            # tekrar başlamıştı). Dashboard zaten her tıklamada yeni bir dosya yazıyor.
            try:
                os.remove(OYNATMA_ISTEGI_DOSYASI)
            except OSError:
                pass
            if istek.get("komut") == "durdur":
                player.stop()
                etkinlik_kuyrugu, etkinlik_indeks, etkinlik_calisiyor = [], 0, False
                _oynatma_durumu_yaz({"durum": "durduruldu"})
                print("🛑 Etkinlik oynatma durduruldu (dashboard isteği).")
            elif istek.get("komut") == "cal":
                url = istek.get("url", "")
                try:
                    kuyruk = _youtube_kuyruk_cikar(url)
                    if not kuyruk:
                        raise ValueError("Listede video bulunamadı.")
                    etkinlik_kuyrugu, etkinlik_indeks, etkinlik_calisiyor = kuyruk, 0, True
                    _etkinlik_parca_cal(0)
                except Exception as e:
                    etkinlik_calisiyor = False
                    _oynatma_durumu_yaz({"durum": "hata", "hata_mesaji": str(e)[:200]})
                    print(f"⚠️ Etkinlik oynatma hatası: {e}")
            elif istek.get("komut") == "zil_cal":
                # Dashboard'daki "Şimdi Zil Çal" butonu — zamanlanmış zil mantığına
                # (tenefus_otomasyonu) dokunmadan, aynı zil_sesi.mp3'ü hemen manuel çalar.
                global otomatik_calan
                zil_yolu = os.path.join(BASE_DIR, "zil_sesi.mp3")
                if os.path.exists(zil_yolu):
                    ders_programi_yukle_gerekirse()
                    player.set_media(instance.media_new(zil_yolu))
                    player.play()
                    player.audio_set_volume(ders_programi.get("ayarlar", {}).get("zil_ses_seviyesi", 80))
                    otomatik_calan = True
                    _oynatma_durumu_yaz({"durum": "zil_calindi"})
                    print("🔔 Zil manuel çalındı (dashboard isteği).")
                else:
                    _oynatma_durumu_yaz({"durum": "hata", "hata_mesaji": "zil_sesi.mp3 bulunamadı."})
                    print("⚠️ Manuel zil çalınamadı, zil_sesi.mp3 bulunamadı.")

        # 2) Kuyrukta bir sonraki parçaya geçiş (mevcut parça kendiliğinden bittiyse).
        # DİKKAT: "not player.is_playing()" burada YANLIŞ olurdu — play() çağrıldıktan
        # hemen sonra akış henüz buffer'lanıyor olabilir ve is_playing() kısa süre False
        # döner, bu da parçayı anında "bitti" sanıp bir sonrakine atlamaya yol açar
        # (2026-09-18'de canlı testte yakalandı: 3.5dk'lık şarkı aynı saniyede "bitti"
        # görünmüştü). Bunun yerine VLC'nin kendi state makinesi kullanılıyor: sadece
        # gerçekten Ended (doğal bitiş) veya Error (akış açılamadı) durumunda ilerlenir;
        # Opening/Buffering/Playing/Paused durumlarında dokunulmaz.
        # Bir parça çözülemez/çalınamazsa (ör. kaldırılmış video) atlanıp bir sonraki
        # döngüde (3sn sonra) otomatik olarak sıradakine geçilir — tüm kuyruğu iptal etmez.
        if etkinlik_calisiyor and player.get_state() in (vlc.State.Ended, vlc.State.Error):
            etkinlik_indeks += 1
            if etkinlik_indeks < len(etkinlik_kuyrugu):
                try:
                    _etkinlik_parca_cal(etkinlik_indeks)
                except Exception as e:
                    print(f"⚠️ Etkinlik parçası atlandı ({etkinlik_indeks + 1}/{len(etkinlik_kuyrugu)}): {e}")
                    _oynatma_durumu_yaz({
                        "durum": "atlandi", "sira": etkinlik_indeks + 1,
                        "toplam": len(etkinlik_kuyrugu), "hata_mesaji": str(e)[:200],
                    })
            else:
                etkinlik_calisiyor = False
                _oynatma_durumu_yaz({"durum": "tamamlandi"})
                print("🎉 Etkinlik oynatma kuyruğu tamamlandı.")

        await asyncio.sleep(3)

def duyuru_hedefi_gecerli_mi(hedef):
    if YOUTUBE_LINK_RE.search(hedef):
        return "youtube"
    if hedef in ("istiklal.mp3", "siren.mp3"):
        return "dosya"
    if os.path.exists(os.path.join(PLAYLIST_DIR, os.path.basename(hedef))):
        return "dosya"
    return None

async def reboot_pc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    await update.message.reply_text("🔄 Sistem yeniden başlatılıyor (Sudo yetkisi gerektirir)...")
    os.system("sudo reboot")

async def durdur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    player.stop()
    await update.message.reply_text("🛑 Ses durduruldu.")

async def sil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # playlist/ içindeki dosyaları Telegram üzerinden silmek için (2026-09-16).
    # 286 dosya var, bu yüzden /list gibi buton değil düz metin+sayfalama kullanılıyor.
    if not await yetki_kontrol(update): return
    if not context.args:
        return await update.message.reply_text(playlist_sayfa_metni(1))
    if context.args[0].lower() == "sayfa":
        try:
            sayfa_no = int(context.args[1]) if len(context.args) > 1 else 1
        except ValueError:
            sayfa_no = 1
        return await update.message.reply_text(playlist_sayfa_metni(sayfa_no))

    # os.path.basename ile olası "../" gibi path traversal denemeleri etkisizleştirilir.
    dosya_adi = os.path.basename(" ".join(context.args).strip())
    if not dosya_adi or dosya_adi in ("istiklal.mp3", "siren.mp3"):
        return await update.message.reply_text("❌ Bu dosya silinemez.")
    yol = os.path.join(PLAYLIST_DIR, dosya_adi)
    if os.path.exists(yol):
        os.remove(yol)
        await update.message.reply_text(f"✅ Silindi: {dosya_adi}")
    else:
        await update.message.reply_text(f"❌ Dosya bulunamadı: {dosya_adi}")

async def duyuru_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Belirli bir tarih/saatte tek seferlik otomatik anons (2026-09-16).
    if not await yetki_kontrol(update): return
    if len(context.args) < 3:
        return await update.message.reply_text(
            "Kullanım: /duyuru_ekle YYYY-AA-GG SS:DD <dosya_adi_veya_youtube_linki>"
        )
    tarih, saat = context.args[0], context.args[1]
    hedef = " ".join(context.args[2:]).strip()

    try:
        zaman = datetime.strptime(f"{tarih} {saat}", "%Y-%m-%d %H:%M")
    except ValueError:
        return await update.message.reply_text("❌ Tarih/saat formatı hatalı. Örnek: 2026-09-20 10:00")
    if zaman <= datetime.now():
        return await update.message.reply_text("❌ Belirtilen an geçmişte kalıyor.")

    tur = duyuru_hedefi_gecerli_mi(hedef)
    if not tur:
        return await update.message.reply_text(f"❌ Hedef bulunamadı/tanınmadı: {hedef}")

    duyurular = duyurulari_yukle()
    yeni_id = max((d["id"] for d in duyurular), default=0) + 1
    duyurular.append({
        "id": yeni_id, "tarih": tarih, "saat": saat,
        "tur": tur, "hedef": hedef, "olusturan": update.effective_chat.id,
    })
    duyurulari_kaydet(duyurular)
    await update.message.reply_text(f"✅ Duyuru eklendi (#{yeni_id}): {tarih} {saat} → {hedef}")

async def duyuru_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    duyurular = duyurulari_yukle()
    if not duyurular:
        return await update.message.reply_text("Bekleyen duyuru yok.")
    satirlar = [
        f"#{d['id']} — {d['tarih']} {d['saat']} → {d['hedef']}"
        for d in sorted(duyurular, key=lambda d: (d["tarih"], d["saat"]))
    ]
    await update.message.reply_text("📋 Bekleyen duyurular:\n" + "\n".join(satirlar))

async def duyuru_sil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    if not context.args:
        return await update.message.reply_text("Kullanım: /duyuru_sil <id>")
    try:
        hedef_id = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Geçersiz id.")
    duyurular = duyurulari_yukle()
    kalanlar = [d for d in duyurular if d["id"] != hedef_id]
    if len(kalanlar) == len(duyurular):
        return await update.message.reply_text(f"❌ #{hedef_id} bulunamadı.")
    duyurulari_kaydet(kalanlar)
    await update.message.reply_text(f"🗑️ Duyuru silindi: #{hedef_id}")

async def duyuru_otomasyonu(bot):
    # Hafta içi kısıtı yok: kullanıcı hangi günü seçtiyse o gün çalışır (tenefus_otomasyonu'ndan farklı).
    global otomatik_calan
    while True:
        simdi = datetime.now()
        duyurular = duyurulari_yukle()
        if duyurular:
            kalanlar = []
            degisti = False
            for d in duyurular:
                try:
                    zaman = datetime.strptime(f"{d['tarih']} {d['saat']}", "%Y-%m-%d %H:%M")
                except (ValueError, KeyError):
                    degisti = True  # bozuk kayıt, listeden düş
                    continue

                fark_dk = (simdi - zaman).total_seconds() / 60
                if fark_dk < 0:
                    kalanlar.append(d)  # zamanı henüz gelmedi
                    continue

                degisti = True
                if fark_dk <= 2:
                    try:
                        if d["tur"] == "youtube":
                            dosya_yolu, baslik = youtube_indir(d["hedef"])
                            player.set_media(instance.media_new(dosya_yolu))
                        else:
                            kok = BASE_DIR if d["hedef"] in ("istiklal.mp3", "siren.mp3") else PLAYLIST_DIR
                            baslik = d["hedef"]
                            player.set_media(instance.media_new(os.path.join(kok, d["hedef"])))
                        player.play()
                        player.audio_set_volume(current_volume)
                        otomatik_calan = False
                        mesaj = f"📢 Duyuru çalınıyor (#{d['id']}): {baslik}"
                    except Exception as e:
                        mesaj = f"❌ Duyuru çalınamadı (#{d['id']}): {str(e)[:100]}"
                else:
                    # Servis o dakikayı kaçırmış (ör. uzun süre kapalıydı) — günler sonra
                    # beklenmedik çalmasın diye artık çalınmaz, sadece bildirilir.
                    mesaj = f"⚠️ Kaçırılan duyuru (#{d['id']}, {d['tarih']} {d['saat']}): {d['hedef']}"

                for chat_id in AUTHORIZED_IDS:
                    try:
                        await bot.send_message(chat_id=chat_id, text=mesaj)
                    except Exception as e:
                        print(f"Duyuru bildirimi gönderilemedi ({chat_id}): {e}")

            if degisti:
                duyurulari_kaydet(kalanlar)
        await asyncio.sleep(30)

# --- 3. ANA ÇALIŞTIRICI ---
async def main():
    # SSL Sertifika hatalarını önlemek için httpx istemcisi
    client = httpx.AsyncClient(verify=False)
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest()).build()
    
    # Komutları Tanımla
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("istiklal", istiklal))
    app.add_handler(CommandHandler("siren", siren))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("reboot", reboot_pc))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler(["ses_artir", "ses_azalt"], control_volume))
    app.add_handler(CommandHandler("sil", sil))
    app.add_handler(CommandHandler("duyuru_ekle", duyuru_ekle))
    app.add_handler(CommandHandler("duyuru_liste", duyuru_liste))
    app.add_handler(CommandHandler("duyuru_sil", duyuru_sil))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_upload))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(YOUTUBE_LINK_RE), youtube_link_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Teneffüs ve duyuru döngülerini arka planda başlat
    asyncio.create_task(tenefus_otomasyonu())
    asyncio.create_task(duyuru_otomasyonu(app.bot))
    asyncio.create_task(etkinlik_dinleyici())

    print("--- SİSTEM VE TENEFFÜS OTOMASYONU AKTİF ---")
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        # Uygulamanın kapanmaması için sonsuz döngü
        while True: 
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Sistem kapatıldı.")