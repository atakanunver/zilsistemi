# -*- coding: utf-8 -*-
import os
import time
import httpx
import warnings
import vlc
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.request import HTTPXRequest
import yt_dlp

# --- 0. AYARLAR ---
warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(BASE_DIR, 'cookies.txt')

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
            for satir in f:
                satir = satir.strip()
                if satir and "=" in satir:
                    k, v = satir.split("=", 1)
                    ayarlar[k.strip()] = v.strip()
        return ayarlar
    except: return {}

config = ayarlari_yukle()
TOKEN = config.get("TELEGRAM_TOKEN")
auth_raw = config.get("CHAT_ID", "")
AUTHORIZED_IDS = [id.strip() for id in auth_raw.split(",") if id.strip()]

instance = vlc.Instance('--no-video --quiet --file-caching=5000 --network-caching=5000')
player = instance.media_player_new()
current_volume = 70
player.audio_set_volume(current_volume)

async def yetki_kontrol(update: Update):
    chat_id = update.effective_chat.id if update.effective_chat else None
    return str(chat_id) in AUTHORIZED_IDS

async def tenefus_otomasyonu():
    while True:
        simdi = datetime.now().strftime("%H:%M")
        for bas, bit, dosya in TENEFUS_PROGRAMI:
            yol = os.path.join(BASE_DIR, dosya)
            if simdi == bas and not player.is_playing() and os.path.exists(yol):
                player.set_media(instance.media_new(yol)); player.play()
            if simdi == bit and player.is_playing(): player.stop()
        await asyncio.sleep(20)

# --- 1. KOMUTLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    kb = [['/istiklal', '/siren'], ['/list', '/durdur'], ['/ses_artir', '/ses_azalt'], ['/reboot']]
    await update.message.reply_text("🏫 Zil Sistemi Aktif.\n`/youtube link` ile ilk 10 şarkıyı çalabilirsiniz.", 
                                  reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def istiklal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    yol = os.path.join(BASE_DIR, "istiklal.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol)); player.play()
        await update.message.reply_text("🇹🇷 İstiklal Marşı çalınıyor...")

async def siren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    yol = os.path.join(BASE_DIR, "siren.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol)); player.play()
        await update.message.reply_text("🚨 Siren çalınıyor!")

async def youtube_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update) or not context.args: return
    chat_id = update.effective_chat.id
    url = context.args[0]
    sent_msg = await context.bot.send_message(chat_id=chat_id, text="🌐 YouTube listesi (ilk 10) hazırlanıyor...")

    def fetch():
        ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',
            'playlistend': 10, # Sadece ilk 10 şarkıyı alır
            'nocheckcertificate': True,
            'quiet': True,
            'cookiefile': COOKIE_PATH,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(fetch)
        if 'entries' in info:
            media_list = instance.media_list_new()
            count = 0
            for e in info['entries']:
                if e and 'url' in e:
                    media_list.add_media(instance.media_new(e['url']))
                    count += 1
            lp = instance.media_list_player_new()
            lp.set_media_player(player); lp.set_media_list(media_list); lp.play()
            await sent_msg.edit_text(f"🎶 Liste başlatıldı ({count} parça).")
        else:
            player.set_media(instance.media_new(info['url'])); player.play()
            await sent_msg.edit_text(f"▶️ Tek parça çalınıyor: {info.get('title')}")
    except Exception as e:
        await sent_msg.edit_text(f"❌ YouTube Hatası: {str(e)[:100]}")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    files = [f for f in os.listdir(BASE_DIR) if f.lower().endswith(('.mp3', '.wav'))]
    kb = [[InlineKeyboardButton(f"▶️ {f}", callback_data=f"play:{f}")] for f in files]
    await update.message.reply_text("Sesler:", reply_markup=InlineKeyboardMarkup(kb))

async def durdur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    player.stop()
    await update.message.reply_text("🛑 Ses durduruldu.")

async def control_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global current_volume
    current_volume = min(100, current_volume + 10) if "artir" in update.message.text else max(0, current_volume - 10)
    player.audio_set_volume(current_volume)
    await update.message.reply_text(f"🔊 Ses: %{current_volume}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await yetki_kontrol(update): return
    await query.answer()
    if query.data.startswith("play:"):
        f = query.data.split(":", 1)[1]
        player.set_media(instance.media_new(os.path.join(BASE_DIR, f))); player.play()
        await query.edit_message_text(f"▶️ Çalıyor: {f}")

async def main():
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest()).build()
    app.bot.request._client = httpx.AsyncClient(verify=False)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("istiklal", istiklal))
    app.add_handler(CommandHandler("siren", siren))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("youtube", youtube_handler))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler(["ses_artir", "ses_azalt"], control_volume))
    app.add_handler(CommandHandler("reboot", lambda u, c: os.system("systemctl reboot")))
    app.add_handler(CallbackQueryHandler(button_handler))

    asyncio.create_task(tenefus_otomasyonu())
    async with app:
        await app.initialize(); await app.start(); await app.updater.start_polling()
        while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try: asyncio.run(main())
    except: pass