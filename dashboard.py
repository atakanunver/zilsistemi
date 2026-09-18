# -*- coding: utf-8 -*-
"""Zil sistemi web dashboard — ders programı / zil sesi / teneffüs ayarları.

sys.py ile canlı IPC yok, sadece dosya paylaşımı (ders_programi.json, zil_sesi.mp3,
atomik os.replace yazımıyla) — bkz. docs/superpowers/specs/2026-09-18-zil-dashboard-design.md.
"""
import os
import json
import re
from datetime import datetime
from functools import wraps
from flask import Flask, request, Response, redirect, url_for, send_file, abort

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlist")
DERS_PROGRAMI_DOSYASI = os.path.join(BASE_DIR, "ders_programi.json")
ZIL_SESI_DOSYASI = os.path.join(BASE_DIR, "zil_sesi.mp3")
ZIL_SESI_GECICI = os.path.join(BASE_DIR, "zil_sesi.mp3.tmp")
ENV_DOSYASI = os.path.join(BASE_DIR, "env.txt")

GUN_ADLARI = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma", 6: "Cumartesi", 7: "Pazar"}
SAAT_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ayarlari_yukle():
    ayarlar = {}
    with open(ENV_DOSYASI, "r", encoding="utf-8-sig") as f:
        for satir in f:
            satir = satir.strip()
            if satir and "=" in satir:
                k, v = satir.split("=", 1)
                ayarlar[k.strip()] = v.strip()
    return ayarlar


_env = ayarlari_yukle()
DASHBOARD_PASSWORD = _env.get("DASHBOARD_PASSWORD", "")
if not DASHBOARD_PASSWORD:
    raise SystemExit("HATA: env.txt içinde DASHBOARD_PASSWORD tanımlı değil.")

app = Flask(__name__)


def _atomik_yaz(yol, veri_bytes):
    tmp = yol + ".tmp-yazim"
    with open(tmp, "wb") as f:
        f.write(veri_bytes)
    os.replace(tmp, yol)


def ders_programi_oku():
    with open(DERS_PROGRAMI_DOSYASI, "r", encoding="utf-8") as f:
        return json.load(f)


def ders_programi_yaz(veri):
    _atomik_yaz(DERS_PROGRAMI_DOSYASI, json.dumps(veri, ensure_ascii=False, indent=2).encode("utf-8"))


def check_auth(username, password):
    return username == "admin" and password == DASHBOARD_PASSWORD


def yetki_gerekli(f):
    @wraps(f)
    def sarici(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Yetkisiz erişim.", 401,
                {"WWW-Authenticate": 'Basic realm="Zil Dashboard"'},
            )
        return f(*args, **kwargs)
    return sarici


def dosya_listele():
    uzantilar = (".mp3", ".wav", ".ogg", ".opus", ".m4a")
    if not os.path.isdir(PLAYLIST_DIR):
        return []
    return sorted(f for f in os.listdir(PLAYLIST_DIR) if f.lower().endswith(uzantilar))


# --- Ortak sayfa iskeleti ---
def sayfa(baslik, icerik, mesaj=None, hata=None):
    mesaj_html = f'<div class="msg ok">{mesaj}</div>' if mesaj else ""
    hata_html = f'<div class="msg err">{hata}</div>' if hata else ""
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{baslik} — Zil Dashboard</title>
<style>
  :root {{ --bg:#0f1720; --panel:#1a2530; --text:#e6edf3; --muted:#8b98a5; --accent:#3b82f6; --ok:#22c55e; --err:#ef4444; --border:#2d3947; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:system-ui,-apple-system,'Segoe UI',sans-serif; }}
  nav {{ display:flex; gap:4px; flex-wrap:wrap; padding:12px 20px; background:var(--panel); border-bottom:1px solid var(--border); }}
  nav a {{ color:var(--muted); text-decoration:none; padding:8px 14px; border-radius:6px; font-size:14px; }}
  nav a:hover, nav a.active {{ background:var(--accent); color:#fff; }}
  main {{ max-width:860px; margin:0 auto; padding:24px 20px 60px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:15px; color:var(--muted); margin:28px 0 10px; text-transform:uppercase; letter-spacing:.04em; }}
  .card {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:18px 20px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid var(--border); font-size:14px; }}
  th {{ color:var(--muted); font-weight:500; font-size:12px; text-transform:uppercase; }}
  input[type=text], input[type=time], input[type=date], input[type=number], input[type=file], input[type=password] {{
    background:#0f1720; border:1px solid var(--border); color:var(--text); border-radius:6px; padding:7px 9px; font-size:14px; width:100%;
  }}
  input[type=range] {{ width:100%; }}
  button, .btn {{ background:var(--accent); color:#fff; border:none; border-radius:6px; padding:8px 16px; font-size:14px; cursor:pointer; }}
  button.danger {{ background:var(--err); }}
  button.secondary {{ background:#2d3947; }}
  label {{ font-size:13px; color:var(--muted); display:block; margin-bottom:4px; }}
  .row {{ display:flex; gap:10px; align-items:end; margin-bottom:10px; flex-wrap:wrap; }}
  .row > div {{ flex:1; min-width:90px; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; margin-right:6px; }}
  .badge.on {{ background:rgba(34,197,94,.15); color:var(--ok); }}
  .badge.off {{ background:rgba(239,68,68,.15); color:var(--err); }}
  .gun-toggle {{ display:inline-flex; align-items:center; gap:6px; padding:8px 12px; border:1px solid var(--border); border-radius:8px; margin:0 6px 8px 0; cursor:pointer; }}
  .gun-toggle input {{ width:auto; }}
  .msg {{ padding:10px 14px; border-radius:8px; margin-bottom:16px; font-size:14px; }}
  .msg.ok {{ background:rgba(34,197,94,.12); color:var(--ok); }}
  .msg.err {{ background:rgba(239,68,68,.12); color:var(--err); }}
  .small {{ color:var(--muted); font-size:12px; }}
  a.link {{ color:var(--accent); }}
</style></head>
<body>
<nav>
  <a href="/" class="{'active' if baslik=='Özet' else ''}">Özet</a>
  <a href="/program" class="{'active' if baslik=='Ders Programı' else ''}">Ders Programı</a>
  <a href="/zil-sesi" class="{'active' if baslik=='Zil Sesi' else ''}">Zil Sesi</a>
  <a href="/ayarlar" class="{'active' if baslik=='Ayarlar' else ''}">Ayarlar</a>
  <a href="/playlist" class="{'active' if baslik=='Playlist' else ''}">Playlist</a>
</nav>
<main>
  <h1>{baslik}</h1>
  {mesaj_html}{hata_html}
  {icerik}
</main>
</body></html>"""


# --- / : Özet ---
@app.route("/")
@yetki_gerekli
def ozet():
    veri = ders_programi_oku()
    simdi = datetime.now()
    simdi_hhmm = simdi.strftime("%H:%M")
    bugun_iso = simdi.isoweekday()
    bugun_tarih = simdi.strftime("%Y-%m-%d")
    ders_gunleri = veri.get("ders_gunleri", [])
    tatil_gunleri = veri.get("tatil_gunleri", [])
    ayarlar = veri.get("ayarlar", {})
    bugun_okul_gunu = bugun_iso in ders_gunleri and bugun_tarih not in tatil_gunleri

    dersler = sorted(veri.get("dersler", []), key=lambda d: d["baslangic"])
    zil_saatleri = sorted({d["baslangic"] for d in dersler} | {d["bitis"] for d in dersler})
    sonraki = next((s for s in zil_saatleri if s > simdi_hhmm), None)

    def rozet(aktif, etiket):
        return f'<span class="badge {"on" if aktif else "off"}">{etiket}: {"Açık" if aktif else "Kapalı"}</span>'

    icerik = f"""
    <div class="card">
      <div class="small">Bugün: {GUN_ADLARI.get(bugun_iso, "?")} · {bugun_tarih} · şu an {simdi_hhmm}</div>
      <p style="font-size:15px;margin:10px 0 0">
        {'📅 Bugün <b>okul günü değil</b> (' + ('tatil olarak işaretli' if bugun_tarih in tatil_gunleri else 'ders günü değil') + ') — otomasyon çalışmaz.' if not bugun_okul_gunu else ('⏰ Sıradaki zil: <b>' + sonraki + '</b>' if sonraki else 'Bugün için kalan zil yok.')}
      </p>
    </div>
    <div class="card">
      {rozet(ayarlar.get('zil_aktif', True), 'Zil')}
      {rozet(ayarlar.get('tenefus_muzigi_aktif', True), 'Teneffüs müziği')}
      {rozet(os.path.exists(ZIL_SESI_DOSYASI), 'zil_sesi.mp3 mevcut')}
      <div class="small" style="margin-top:10px">Zil ses seviyesi: %{ayarlar.get('zil_ses_seviyesi', 80)} · Otomatik ses seviyesi: %{ayarlar.get('otomatik_ses_seviyesi', 50)}</div>
    </div>
    <div class="card">
      <h2 style="margin-top:0">Bugünkü ders saatleri</h2>
      <table><tr><th>#</th><th>Başlangıç</th><th>Bitiş</th></tr>
      {''.join(f"<tr><td>{d['no']}</td><td>{d['baslangic']}</td><td>{d['bitis']}</td></tr>" for d in dersler)}
      </table>
    </div>
    <p class="small">Detaylı düzenleme: <a class="link" href="/program">Ders Programı</a>, <a class="link" href="/ayarlar">Ayarlar</a>, <a class="link" href="/zil-sesi">Zil Sesi</a>, <a class="link" href="/playlist">Playlist</a>.</p>
    """
    return sayfa("Özet", icerik)


# --- /program : ders programı + gün toggle + tatil takvimi ---
@app.route("/program", methods=["GET", "POST"])
@yetki_gerekli
def program():
    mesaj = hata = None
    veri = ders_programi_oku()

    if request.method == "POST":
        islem = request.form.get("islem", "kaydet")

        if islem == "tatil_ekle":
            tarih = request.form.get("yeni_tatil", "").strip()
            if not TARIH_RE.match(tarih):
                hata = "Geçersiz tarih formatı (YYYY-AA-GG bekleniyor)."
            else:
                tatiller = set(veri.get("tatil_gunleri", []))
                tatiller.add(tarih)
                veri["tatil_gunleri"] = sorted(tatiller)
                ders_programi_yaz(veri)
                mesaj = f"Tatil günü eklendi: {tarih}"

        elif islem == "tatil_sil":
            tarih = request.form.get("tarih", "")
            veri["tatil_gunleri"] = [t for t in veri.get("tatil_gunleri", []) if t != tarih]
            ders_programi_yaz(veri)
            mesaj = f"Tatil günü kaldırıldı: {tarih}"

        else:  # kaydet: dersler + ders_gunleri + karşılama müziği
            try:
                nolar = request.form.getlist("ders_no")
                baslangiclar = request.form.getlist("ders_baslangic")
                bitisler = request.form.getlist("ders_bitis")
                yeni_dersler = []
                for no, b, s in zip(nolar, baslangiclar, bitisler):
                    b, s = b.strip(), s.strip()
                    if not b and not s:
                        continue  # boş satır atla
                    if not (SAAT_RE.match(b) and SAAT_RE.match(s)):
                        raise ValueError(f"Ders {no}: saat formatı hatalı (HH:MM).")
                    if s <= b:
                        raise ValueError(f"Ders {no}: bitiş, başlangıçtan sonra olmalı.")
                    yeni_dersler.append({"no": int(no), "baslangic": b, "bitis": s})
                yeni_dersler.sort(key=lambda d: d["baslangic"])
                for i in range(len(yeni_dersler) - 1):
                    if yeni_dersler[i + 1]["baslangic"] < yeni_dersler[i]["bitis"]:
                        raise ValueError(f"Ders {yeni_dersler[i]['no']} ile {yeni_dersler[i+1]['no']} çakışıyor.")
                if len(yeni_dersler) < 2:
                    raise ValueError("En az 2 ders girilmeli (teneffüs hesaplamak için).")

                ders_gunleri = sorted(int(g) for g in request.form.getlist("ders_gunu"))

                karsilama_aktif = request.form.get("karsilama_aktif") == "on"
                k_baslama = request.form.get("karsilama_baslama", "").strip()
                k_durdurma = request.form.get("karsilama_durdurma", "").strip()
                if karsilama_aktif:
                    if not (SAAT_RE.match(k_baslama) and SAAT_RE.match(k_durdurma)):
                        raise ValueError("Karşılama müziği saatleri hatalı (HH:MM).")
                    if k_durdurma <= k_baslama:
                        raise ValueError("Karşılama müziği durdurma, başlamadan sonra olmalı.")

                veri["dersler"] = yeni_dersler
                veri["ders_gunleri"] = ders_gunleri
                veri["karsilama_muzigi"] = {"aktif": karsilama_aktif, "baslama": k_baslama or "07:50", "durdurma": k_durdurma or "07:55"}
                ders_programi_yaz(veri)
                mesaj = "Ders programı kaydedildi."
                veri = ders_programi_oku()
            except ValueError as e:
                hata = str(e)

    dersler = sorted(veri.get("dersler", []), key=lambda d: d["baslangic"])
    ders_gunleri = set(veri.get("ders_gunleri", []))
    tatil_gunleri = sorted(veri.get("tatil_gunleri", []))
    karsilama = veri.get("karsilama_muzigi", {})

    ders_satirlari = "".join(f"""
      <div class="row">
        <div style="max-width:60px"><label>No</label><input type="text" name="ders_no" value="{d['no']}" readonly></div>
        <div><label>Başlangıç</label><input type="time" name="ders_baslangic" value="{d['baslangic']}"></div>
        <div><label>Bitiş</label><input type="time" name="ders_bitis" value="{d['bitis']}"></div>
      </div>""" for d in dersler)
    # birkaç boş satır (yeni ders eklemek için)
    for i in range(len(dersler) + 1, len(dersler) + 4):
        ders_satirlari += f"""
      <div class="row">
        <div style="max-width:60px"><label>No</label><input type="text" name="ders_no" value="{i}" readonly></div>
        <div><label>Başlangıç</label><input type="time" name="ders_baslangic" value=""></div>
        <div><label>Bitiş</label><input type="time" name="ders_bitis" value=""></div>
      </div>"""

    gun_togglelari = "".join(f"""
      <label class="gun-toggle"><input type="checkbox" name="ders_gunu" value="{g}" {"checked" if g in ders_gunleri else ""}> {ad}</label>
    """ for g, ad in GUN_ADLARI.items())

    tatil_satirlari = "".join(f"""
      <div class="row" style="align-items:center">
        <div>{t}</div>
        <div style="flex:0"><form method="post" style="margin:0"><input type="hidden" name="islem" value="tatil_sil"><input type="hidden" name="tarih" value="{t}"><button type="submit" class="danger">Sil</button></form></div>
      </div>""" for t in tatil_gunleri) or '<p class="small">Tatil günü işaretlenmemiş.</p>'

    icerik = f"""
    <form method="post">
      <input type="hidden" name="islem" value="kaydet">
      <div class="card">
        <h2 style="margin-top:0">Ders Saatleri</h2>
        {ders_satirlari}
        <p class="small">Boş satırlar yok sayılır. Kaydedince otomatik olarak başlangıç saatine göre sıralanır.</p>
      </div>
      <div class="card">
        <h2 style="margin-top:0">Ders Günleri</h2>
        {gun_togglelari}
      </div>
      <div class="card">
        <h2 style="margin-top:0">Okul Girişi Karşılama Müziği</h2>
        <label class="gun-toggle"><input type="checkbox" name="karsilama_aktif" {"checked" if karsilama.get('aktif') else ""}> Aktif</label>
        <div class="row">
          <div><label>Başlama</label><input type="time" name="karsilama_baslama" value="{karsilama.get('baslama','07:50')}"></div>
          <div><label>Durdurma</label><input type="time" name="karsilama_durdurma" value="{karsilama.get('durdurma','07:55')}"></div>
        </div>
      </div>
      <button type="submit">Kaydet</button>
    </form>

    <div class="card">
      <h2 style="margin-top:0">Tatil Günleri</h2>
      {tatil_satirlari}
      <form method="post" class="row" style="margin-top:12px">
        <input type="hidden" name="islem" value="tatil_ekle">
        <div><label>Yeni tatil günü</label><input type="date" name="yeni_tatil" required></div>
        <div style="flex:0"><button type="submit" class="secondary">Ekle</button></div>
      </form>
      <p class="small">İşaretli günlerde zil, teneffüs müziği ve karşılama müziğinin hepsi otomatik olarak kapanır.</p>
    </div>
    """
    return sayfa("Ders Programı", icerik, mesaj, hata)


# --- /zil-sesi : yükle + önizle + onayla ---
@app.route("/zil-sesi", methods=["GET", "POST"])
@yetki_gerekli
def zil_sesi():
    mesaj = hata = None
    if request.method == "POST":
        islem = request.form.get("islem")
        if islem == "yukle":
            dosya = request.files.get("dosya")
            if not dosya or not dosya.filename:
                hata = "Dosya seçilmedi."
            elif not dosya.filename.lower().endswith((".mp3", ".wav", ".ogg", ".m4a")):
                hata = "Sadece mp3/wav/ogg/m4a kabul edilir."
            else:
                dosya.save(ZIL_SESI_GECICI)
                mesaj = "Dosya yüklendi, aşağıda önizleyip onaylayabilirsiniz."
        elif islem == "onayla":
            if os.path.exists(ZIL_SESI_GECICI):
                os.replace(ZIL_SESI_GECICI, ZIL_SESI_DOSYASI)
                mesaj = "Zil sesi güncellendi."
            else:
                hata = "Onaylanacak geçici dosya yok, önce yükleyin."
        elif islem == "vazgec":
            if os.path.exists(ZIL_SESI_GECICI):
                os.remove(ZIL_SESI_GECICI)
            mesaj = "Geçici dosya silindi."

    gecici_var = os.path.exists(ZIL_SESI_GECICI)
    mevcut_var = os.path.exists(ZIL_SESI_DOSYASI)

    icerik = f"""
    <div class="card">
      <h2 style="margin-top:0">Mevcut Zil Sesi</h2>
      {'<audio controls src="/zil-sesi/dosya/mevcut" style="width:100%"></audio>' if mevcut_var else '<p class="small">Henüz zil_sesi.mp3 yok.</p>'}
    </div>
    <div class="card">
      <h2 style="margin-top:0">Yeni Ses Yükle</h2>
      <form method="post" enctype="multipart/form-data">
        <input type="hidden" name="islem" value="yukle">
        <input type="file" name="dosya" accept=".mp3,.wav,.ogg,.m4a" required>
        <button type="submit" style="margin-top:10px">Yükle</button>
      </form>
      {"""
      <div style="margin-top:16px">
        <div class="small">Önizleme (henüz onaylanmadı):</div>
        <audio controls src="/zil-sesi/dosya/gecici" style="width:100%"></audio>
        <form method="post" style="display:inline-block;margin-top:10px">
          <input type="hidden" name="islem" value="onayla">
          <button type="submit">Onayla ve Yayınla</button>
        </form>
        <form method="post" style="display:inline-block;margin-top:10px;margin-left:8px">
          <input type="hidden" name="islem" value="vazgec">
          <button type="submit" class="secondary">Vazgeç</button>
        </form>
      </div>
      """ if gecici_var else ""}
    </div>
    """
    return sayfa("Zil Sesi", icerik, mesaj, hata)


@app.route("/zil-sesi/dosya/<hangisi>")
@yetki_gerekli
def zil_sesi_dosya(hangisi):
    yol = {"mevcut": ZIL_SESI_DOSYASI, "gecici": ZIL_SESI_GECICI}.get(hangisi)
    if not yol or not os.path.exists(yol):
        abort(404)
    return send_file(yol, mimetype="audio/mpeg")


# --- /ayarlar ---
@app.route("/ayarlar", methods=["GET", "POST"])
@yetki_gerekli
def ayarlar_sayfasi():
    mesaj = None
    veri = ders_programi_oku()
    if request.method == "POST":
        ayarlar = veri.get("ayarlar", {})
        ayarlar["zil_aktif"] = request.form.get("zil_aktif") == "on"
        ayarlar["tenefus_muzigi_aktif"] = request.form.get("tenefus_muzigi_aktif") == "on"
        ayarlar["otomatik_ses_seviyesi"] = max(0, min(100, int(request.form.get("otomatik_ses_seviyesi", 50) or 50)))
        ayarlar["zil_ses_seviyesi"] = max(0, min(100, int(request.form.get("zil_ses_seviyesi", 80) or 80)))
        veri["ayarlar"] = ayarlar
        ders_programi_yaz(veri)
        mesaj = "Ayarlar kaydedildi."
        veri = ders_programi_oku()

    a = veri.get("ayarlar", {})
    icerik = f"""
    <form method="post">
      <div class="card">
        <label class="gun-toggle"><input type="checkbox" name="zil_aktif" {"checked" if a.get('zil_aktif', True) else ""}> Zil sesi aktif</label>
        <label class="gun-toggle"><input type="checkbox" name="tenefus_muzigi_aktif" {"checked" if a.get('tenefus_muzigi_aktif', True) else ""}> Teneffüs müziği aktif</label>
      </div>
      <div class="card">
        <label>Zil ses seviyesi: %{a.get('zil_ses_seviyesi', 80)}</label>
        <input type="range" min="0" max="100" name="zil_ses_seviyesi" value="{a.get('zil_ses_seviyesi', 80)}"
          oninput="this.previousElementSibling.textContent='Zil ses seviyesi: %'+this.value">
      </div>
      <div class="card">
        <label>Otomatik (teneffüs/karşılama) ses seviyesi: %{a.get('otomatik_ses_seviyesi', 50)}</label>
        <input type="range" min="0" max="100" name="otomatik_ses_seviyesi" value="{a.get('otomatik_ses_seviyesi', 50)}"
          oninput="this.previousElementSibling.textContent='Otomatik (teneffüs/karşılama) ses seviyesi: %'+this.value">
      </div>
      <button type="submit">Kaydet</button>
    </form>
    """
    return sayfa("Ayarlar", icerik, mesaj)


# --- /playlist ---
@app.route("/playlist", methods=["GET"])
@yetki_gerekli
def playlist_sayfasi():
    dosyalar = dosya_listele()
    satirlar = "".join(f"""
      <tr><td>{f}</td><td>
        <form method="post" action="/playlist/sil" onsubmit="return confirm('Silinsin mi: {f}?')" style="margin:0">
          <input type="hidden" name="dosya_adi" value="{f}">
          <button type="submit" class="danger">Sil</button>
        </form>
      </td></tr>""" for f in dosyalar)
    icerik = f"""
    <div class="card">
      <p class="small">{len(dosyalar)} dosya. Yükleme Telegram üzerinden yapılır (ses/voice mesajı gönderin), buradan sadece listeleme ve silme yapılır.</p>
      <table><tr><th>Dosya</th><th></th></tr>{satirlar or '<tr><td colspan=2 class="small">Playlist boş.</td></tr>'}</table>
    </div>
    """
    return sayfa("Playlist", icerik)


@app.route("/playlist/sil", methods=["POST"])
@yetki_gerekli
def playlist_sil():
    dosya_adi = os.path.basename(request.form.get("dosya_adi", "").strip())
    if dosya_adi:
        yol = os.path.join(PLAYLIST_DIR, dosya_adi)
        if os.path.exists(yol):
            os.remove(yol)
    return redirect(url_for("playlist_sayfasi"))


if __name__ == "__main__":
    from waitress import serve
    print("--- ZİL DASHBOARD (waitress) 0.0.0.0:8090 ---")
    serve(app, host="0.0.0.0", port=8090)
