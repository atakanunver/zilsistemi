# -*- coding: utf-8 -*-
import os
import pygame
import time
import ssl
import httpx
import warnings
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.request import HTTPXRequest

# --- 0. SSL VE GÜVENLİK AYARLARI ---
warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEB_SERTIFIKA_YOLU = os.path.join(BASE_DIR, "fatihca.cer")

# Python genel SSL ayarlarını esnetiyoruz
try:
    ssl_context = ssl._create_unverified_context()
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

# --- 1. AYARLAR ---
def ayarlari_yukle():
    ayarlar = {}
    try:
        # utf-8-sig BOM (Byte Order Mark) sorununu önler
        with open(os.path.join(BASE_DIR, "env.txt"), "r", encoding="utf-8-sig") as f:
            for satir in f:
                satir = satir.strip()
                if satir and "=" in satir:
                    k, v = satir.split("=", 1)
                    ayarlar[k.strip()] = v.strip()
        return ayarlar
    except Exception as e:
        print(f"❌ env.txt hatası: {e}")
        return None

config = ayarlari_yukle()
if not config:
    print("❌ env.txt bulunamadı veya okunamadı!")
    exit()

TOKEN = config.get("TELEGRAM_TOKEN")
# Virgülle ayrılmış CHAT_ID'leri listeye çeviriyoruz
AUTHORIZED_IDS = [id.strip() for id in config.get("CHAT_ID", "").split(",") if id.strip()]

# Pygame Ses Başlatma
pygame.mixer.init()
current_volume = 0.7
pygame.mixer.music.set_volume(current_volume)

# --- 2. YARDIMCI FONKSİYONLAR ---
async def yetki_kontrol(update: Update):
    user_id = str(update.effective_chat.id)
    if user_id in AUTHORIZED_IDS:
        return True
    else:
        print(f"⚠️ Yetkisiz erişim denemesi: {user_id}")
        return False

def dosya_listele():
    return [f for f in os.listdir(BASE_DIR) if f.lower().endswith(('.mp3', '.wav', '.ogg'))]

# --- 3. KOMUTLAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    kb = [['/istiklal', '/siren'], ['/list', '/durdur'], ['/ses_artir', '/ses_azalt']]
    await update.message.reply_text("🎙️ Zil ve Ses Sistemi Aktif!\nKomutları kullanabilirsiniz.", 
                                  reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def durdur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    pygame.mixer.music.stop()
    await update.message.reply_text("🛑 Ses durduruldu.")

async def istiklal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    dosya = "istiklal.mp3"
    yol = os.path.join(BASE_DIR, dosya)
    if os.path.exists(yol):
        pygame.mixer.music.stop()
        pygame.mixer.music.load(yol)
        pygame.mixer.music.play()
        await update.message.reply_text("🇹🇷 İstiklal Marşı çalınıyor...")
    else:
        await update.message.reply_text(f"❌ {dosya} bulunamadı!")

async def siren(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    dosya = "siren.mp3"
    yol = os.path.join(BASE_DIR, dosya)
    if os.path.exists(yol):
        pygame.mixer.music.stop()
        pygame.mixer.music.load(yol)
        pygame.mixer.music.play()
        await update.message.reply_text("🚨 Siren çalınıyor!")
    else:
        await update.message.reply_text(f"❌ {dosya} bulunamadı!")

async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    dosyalar = dosya_listele()
    if not dosyalar:
        return await update.message.reply_text("Klasörde ses dosyası yok.")
    
    # Her dosya için bir buton oluştur
    kb = [[InlineKeyboardButton(f"▶️ {f}", callback_data=f"play:{f}")] for f in dosyalar]
    await update.message.reply_text("Mevcut Sesler:", reply_markup=InlineKeyboardMarkup(kb))

async def control_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    global current_volume
    komut = update.message.text
    if "artir" in komut:
        current_volume = min(1.0, current_volume + 0.1)
    else:
        current_volume = max(0.0, current_volume - 0.1)
    
    pygame.mixer.music.set_volume(current_volume)
    await update.message.reply_text(f"🔊 Ses Seviyesi: %{int(current_volume*100)}")

async def handle_audio_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await yetki_kontrol(update): return
    try:
        audio_source = update.message.audio or update.message.voice
        file = await audio_source.get_file()
        
        # Dosya uzantısını belirle
        ext = ".mp3"
        if update.message.audio and update.message.audio.file_name:
            ext = os.path.splitext(update.message.audio.file_name)[1]
            
        save_path = os.path.join(BASE_DIR, f"gelen_{int(time.time())}{ext}")
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"✅ Dosya kaydedildi: {os.path.basename(save_path)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Yükleme hatası: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(query.message.chat_id) not in AUTHORIZED_IDS: return
    
    await query.answer()
    if query.data.startswith("play:"):
        dosya = query.data.split(":", 1)[1]
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(os.path.join(BASE_DIR, dosya))
            pygame.mixer.music.play()
            await query.edit_message_text(f"▶️ Şu an çalıyor: {dosya}")
        except Exception as e:
            await query.edit_message_text(f"❌ Çalma hatası: {e}")

# --- 4. ANA DÖNGÜ ---
if __name__ == '__main__':
    # SSL doğrulamasını kapatmak için bir HTTPX istemcisi oluşturuyoruz
    # verify=False burada tanımlanır
    proxy_url = None # Eğer okulda proxy gerekirse buraya eklenebilir
    
    # httpx Client oluştururken verify=False veriyoruz
    client = httpx.AsyncClient(verify=False)

    # HTTPXRequest'e bu istemciyi (client) paslıyoruz
    t_request = HTTPXRequest(
        connection_pool_size=20,
        read_timeout=30,
        connect_timeout=30,
    )
    
    # Application oluşturulurken hem istemciyi hem de isteği bağlıyoruz
    app = ApplicationBuilder().token(TOKEN).request(t_request).build()
    
    # Önemli: Telegram kütüphanesine iç istemcide SSL kontrolünü kapatmasını söylüyoruz
    # Bazı sürümlerde bu gereklidir:
    app.bot.request._client = client 

    # Komut İşleyiciler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_files))
    app.add_handler(CommandHandler("istiklal", istiklal))
    app.add_handler(CommandHandler("siren", siren))
    app.add_handler(CommandHandler("durdur", durdur))
    app.add_handler(CommandHandler(["ses_artir", "ses_azalt"], control_volume))
    
    # Ses Dosyası ve Sesli Mesaj İşleyici
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_upload))
    
    # Buton İşleyici
    app.add_handler(CallbackQueryHandler(button_handler))

    print(f"--- BOT BAŞLATILDI (SSL Bypass v2 Aktif) ---")
    app.run_polling()