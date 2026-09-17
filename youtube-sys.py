# -*- coding: utf-8 -*-
import os
import time
import ssl
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

# Teneffüs Programı (Resimdeki saatlere göre)
TENEFUS_PROGRAMI = [
    ("08:50", "09:00", "muzik2.mp3"),
    ("09:40", "09:50", "muzik3.mp3"),
    ("10:30", "10:40", "muzik7.mp3"),
    ("11:20", "11:30", "muzik2.mp3"),
    ("12:10", "13:30", "muzik3.mp3"),
    ("14:10", "14:20", "muzik7.mp3"),
    ("15:00", "15:10", "muzik2.mp3")
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
    except Exception: return None

config = ayarlari_yukle()
TOKEN = config.get("TELEGRAM_TOKEN")
AUTHORIZED_IDS = [id.strip() for id in config.get("CHAT_ID", "").split(",") if id.strip()]

instance = vlc.Instance('--no-video --quiet')
player = instance.media_player_new()
current_volume = 70
player.audio_set_volume(current_volume)

# --- 1. YARDIMCI FONKSİYONLAR ---
async def yetki_kontrol(update: Update):
    return str(update.effective_chat.id) in AUTHORIZED_IDS

def dosya_listele():
    uzantilar = ('.mp3', '.wav', '.ogg', '.opus', '.m4a')
    return [f for f in os.listdir(BASE_DIR) if f.lower().endswith(uzantilar)]

async def tenefus_otomasyonu():
    while True:
        simdi = datetime.now().strftime("%H:%M")
        for baslangic, bitis, dosya in TENEFUS_PROGRAMI:
            if simdi == baslangic and not player.is_playing():
                yol = os.path.join(BASE_DIR, dosya)
                if os.path.exists(yol):
                    media = instance.media_new(yol)
                    player.set_media(media)
                    player.play()
                    print(f"🔔 Zil Çaldı: {dosya}")
            if simdi == bitis and player.is_playing():
                player.stop()
        await asyncio.sleep(30)

# --- 2. KOMUTLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    kb = [['/istiklal', '/siren'], ['/list', '/durdur'], ['/ses_artir', '/ses_azalt'], ['/reboot']]
    await update.message.reply_text("🏫 Okul Zil Sistemi Aktif.\nYouTube: `/youtube link`", 
                                  reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def istiklal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    yol = os.path.join(BASE_DIR, "istiklal.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        await update.message.reply_text("🇹🇷 İstiklal Marşı çalınıyor...")
    else:
        await update.message.reply_text("❌ istiklal.mp3 bulunamadı!")

async def siren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    yol = os.path.join(BASE_DIR, "siren.mp3")
    if os.path.exists(yol):
        player.set_media(instance.media_new(yol))
        player.play()
        await update.message.reply_text("🚨 Siren çalınıyor!")
    else:
        await update.message.reply_text("❌ siren.mp3 bulunamadı!")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    dosyalar = dosya_listele()
    if not dosyalar:
        return await update.message.reply_text("Klasörde ses dosyası yok.")
    kb = [[InlineKeyboardButton(f"▶️ {f}", callback_data=f"play:{f}")] for f in dosyalar]
    await update.message.reply_text("Mevcut Sesler:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_audio_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    try:
        msg = update.message
        audio_source = msg.audio or msg.voice
        file = await audio_source.get_file()
        ext = os.path.splitext(msg.audio.file_name)[1] if msg.audio and msg.audio.file_name else ".ogg"
        dosya_adi = f"gelen_{int(time.time())}{ext}"
        save_path = os.path.join(BASE_DIR, dosya_adi)
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"✅ Kaydedildi: {dosya_adi}")
    except Exception as e:
        await update.message.reply_text(f"❌ Kayıt hatası: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.message.chat_id) not in AUTHORIZED_IDS: return
    await query.answer()
    if query.data.startswith("play:"):
        dosya = query.data.split(":", 1)[1]
        yol = os.path.join(BASE_DIR, dosya)
        if os.path.exists(yol):
            player.set_media(instance.media_new(yol))
            player.play()
            await query.edit_message_text(f"▶️ Çalıyor: {dosya}")

async def control_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global current_volume
    current_volume = min(100, current_volume + 10) if "artir" in update.message.text else max(0, current_volume - 10)
    player.audio_set_volume(current_volume)
    await update.message.reply_text(f"🔊 Ses Seviyesi: %{current_volume}")

async def youtube_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    if not context.args: return
    url = context.args[0]
    await update.message.reply_text("🌐 Bağlanıyor...")
    try:
        ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'referer': 'https://www.google.com/'
}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            player.set_media(instance.media_new(info['url']))
            player.play()
        await update.message.reply_text("▶️ YouTube çalınıyor...")
    except Exception as e:
        await update.message.reply_text(f"❌ YouTube Hatası: {e}")

async def reboot_pc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    await update.message.reply_text("🔄 Bilgisayar yeniden başlatılıyor...")
    os.system("sudo /usr/sbin/reboot")

async def durdur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    player.stop()
    await update.message.reply_text("🛑 Durduruldu.")

# --- 3. ANA ÇALIŞTIRICI ---
async def main():
    client = httpx.AsyncClient(verify=False)
    app = ApplicationBuilder().token(TOKEN).request(HTTPXRequest()).build()
    app.bot.request._client = client

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("istiklal", istiklal))
    app.add_handler(CommandHandler("siren", siren))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("youtube", youtube_handler))
    app.add_handler(CommandHandler("reboot", reboot_pc))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler(["ses_artir", "ses_azalt"], control_volume))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_upload))
    app.add_handler(CallbackQueryHandler(button_handler))

    asyncio.create_task(tenefus_otomasyonu())

    print("--- SİSTEM VE TENEFFÜS OTOMASYONU AKTİF ---")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass