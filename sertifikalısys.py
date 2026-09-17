# -*- coding: utf-8 -*-
import os
import httpx
import warnings
import vlc
import asyncio
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
import yt_dlp

# --- AYARLAR ---
warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_TXT = os.path.join(BASE_DIR, 'cookies.txt')

# Okul Tenefüs Saatleri (Sizin belirttiğiniz program)
TENEFUS_PROGRAMI = [
    ("08:51", "08:54", "1.mp3"), ("09:41", "09:45", "2.mp3"),
    ("10:31", "10:36", "3.mp3"), ("11:21", "11:25", "4.mp3"),
    ("12:21", "13:10", "5.mp3"), ("14:11", "14:15", "6.mp3"),
    ("15:01", "15:09", "7.mp3")
]

def ayarlari_yukle():
    ayarlar = {}
    try:
        with open(os.path.join(BASE_DIR, "env.txt"), "r", encoding="utf-8-sig") as f:
            for s in f:
                s = s.strip()
                if s and "=" in s:
                    k, v = s.split("=", 1)
                    ayarlar[k.strip()] = v.strip()
    except: pass
    return ayarlar

conf = ayarlari_yukle()
TOKEN = conf.get("TELEGRAM_TOKEN")
AUTH_IDS = [id.strip() for id in conf.get("CHAT_ID", "").split(",") if id.strip()]

# --- VLC SETUP (Hata veren gnutls parametresi buradan kaldırıldı) ---
instance = vlc.Instance('--no-video --quiet --file-caching=10000 --network-caching=10000')
player = instance.media_player_new()
list_player = instance.media_list_player_new()
list_player.set_media_player(player)

current_vol = 70
player.audio_set_volume(current_vol)

async def yetki(u: Update):
    if not u or not u.effective_chat: return False
    return str(u.effective_chat.id) in AUTH_IDS

# --- KOMUTLAR ---

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    kb = [['/istiklal', '/siren'], ['/list', '/durdur'], ['/ileri', '/geri'], ['/reboot']]
    await u.message.reply_text(
        "🏫 Zil Sistemi Aktif.\n"
        "▶️ /youtube [link]\n"
        "⏭ /ileri | ⏮ /geri\n"
        "🔊 /ses_artir | 🔉 /ses_azalt", 
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def youtube_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u) or not c.args: return
    url = c.args[0]
    m = await u.message.reply_text("🔍 Playlist taranıyor (MEB Sertifika Modu)...")
    
    # MEB Hattı için yt-dlp ayarları
    opts = {
        'format': 'bestaudio/best',
        'playlistend': 10,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True, 
        'cookiefile': COOKIE_TXT if os.path.exists(COOKIE_TXT) else None,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        
        new_playlist = instance.media_list_new()
        count = 0
        
        # VLC için sertifika kontrolünü burada (: ile başlayan parametreyle) kapatıyoruz
        vlc_args = [":gnutls-verify-trust=0", ":no-video"]

        if 'entries' in info:
            for e in info['entries']:
                if e and 'url' in e:
                    media = instance.media_new(e['url'], *vlc_args)
                    new_playlist.add_media(media)
                    count += 1
        else:
            media = instance.media_new(info['url'], *vlc_args)
            new_playlist.add_media(media)
            count = 1

        list_player.set_media_list(new_playlist)
        list_player.play()
        
        kb = [[InlineKeyboardButton("⏮ Geri", callback_data="prev"), 
               InlineKeyboardButton("İleri ⏭", callback_data="next")]]
        await m.edit_text(f"🎶 {count} parça yüklendi.\n/ileri | /geri butonları hazır.", 
                          reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        await m.edit_text(f"❌ YouTube Hatası: {str(e)[:150]}")

async def next_song(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    list_player.next()
    await u.message.reply_text("⏭ Sonraki şarkı")

async def prev_song(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    list_player.previous()
    await u.message.reply_text("⏮ Önceki şarkı")

async def istiklal(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    list_player.stop()
    yol = os.path.join(BASE_DIR, "istiklal.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        await u.message.reply_text("🇹🇷 İstiklal Marşı çalınıyor...")

async def siren(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    list_player.stop()
    yol = os.path.join(BASE_DIR, "siren.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        await u.message.reply_text("🚨 Siren çalınıyor!")

async def durdur(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    list_player.stop()
    player.stop()
    await u.message.reply_text("🛑 Durduruldu.")

async def control_vol(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    global current_vol
    t = u.message.text
    if "artir" in t: current_vol = min(100, current_vol + 10)
    else: current_vol = max(0, current_vol - 10)
    player.audio_set_volume(current_vol)
    await u.message.reply_text(f"🔊 Ses Seviyesi: %{current_vol}")

async def list_files(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not await yetki(u): return
    files = [f for f in os.listdir(BASE_DIR) if f.lower().endswith(('.mp3', '.wav', '.ogg'))]
    if not files:
        await u.message.reply_text("Klasörde müzik dosyası yok.")
        return
    kb = [[InlineKeyboardButton(f"▶️ {f}", callback_data=f"play:{f}")] for f in files]
    await u.message.reply_text("Dosyalar:", reply_markup=InlineKeyboardMarkup(kb))

async def button_handler(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not q or not await yetki(u): return
    await q.answer()
    if q.data == "next": list_player.next()
    elif q.data == "prev": list_player.previous()
    elif q.data.startswith("play:"):
        f = q.data.split(":", 1)[1]
        list_player.stop()
        player.set_media(instance.media_new(os.path.join(BASE_DIR, f)))
        player.play()

async def tenefus_otomasyonu():
    while True:
        simdi = datetime.now().strftime("%H:%M")
        for bas, bit, dosya in TENEFUS_PROGRAMI:
            yol = os.path.join(BASE_DIR, dosya)
            if simdi == bas and not player.is_playing() and os.path.exists(yol):
                list_player.stop()
                player.set_media(instance.media_new(yol))
                player.play()
            if simdi == bit and player.is_playing(): player.stop()
        await asyncio.sleep(25)

async def main():
    # Telegram Bot Başlatma
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest()).build()
    
    # Komutlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("istiklal", istiklal))
    app.add_handler(CommandHandler("siren", siren))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("youtube", youtube_handler))
    app.add_handler(CommandHandler("ileri", next_song))
    app.add_handler(CommandHandler("geri", prev_song))
    app.add_handler(CommandHandler(["ses_artir", "ses_azalt"], control_vol))
    app.add_handler(CommandHandler("reboot", lambda u, c: os.system("sudo systemctl restart ses_bot.service")))
    app.add_handler(CallbackQueryHandler(button_handler))

    asyncio.create_task(tenefus_otomasyonu())
    
    print("Atakan Zil Botu Çalışıyor...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass