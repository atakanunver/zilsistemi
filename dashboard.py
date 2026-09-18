# -*- coding: utf-8 -*-
"""Zil sistemi web dashboard — ders programı / zil sesi / teneffüs ayarları.

sys.py ile canlı IPC yok, sadece dosya paylaşımı (ders_programi.json, zil_sesi.mp3,
atomik os.replace yazımıyla) — bkz. docs/superpowers/specs/2026-09-18-zil-dashboard-design.md.
"""
import os
import json
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, Response, redirect, url_for, send_file, abort, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlist")
DERS_PROGRAMI_DOSYASI = os.path.join(BASE_DIR, "ders_programi.json")
ZIL_SESI_DOSYASI = os.path.join(BASE_DIR, "zil_sesi.mp3")
ZIL_SESI_GECICI = os.path.join(BASE_DIR, "zil_sesi.mp3.tmp")
ENV_DOSYASI = os.path.join(BASE_DIR, "env.txt")
# sys.py ile paylaşılan dosya-tabanlı komut kanalı (bkz. sys.py'deki etkinlik_dinleyici()).
OYNATMA_ISTEGI_DOSYASI = os.path.join(BASE_DIR, "oynatma_istegi.json")
OYNATMA_DURUMU_DOSYASI = os.path.join(BASE_DIR, "oynatma_durumu.json")
YOUTUBE_LINK_RE = re.compile(r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/\S+", re.IGNORECASE)

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
  nav a {{ color:var(--muted); text-decoration:none; padding:8px 14px; border-radius:6px; font-size:14px; border-bottom:2px solid transparent; transition:background .15s,color .15s; }}
  nav a:hover {{ background:#22303d; color:var(--text); }}
  nav a.active {{ background:var(--accent); color:#fff; border-bottom-color:#fff; }}
  main {{ max-width:860px; margin:0 auto; padding:24px 20px 60px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  h2 {{ font-size:15px; color:var(--muted); margin:28px 0 10px; text-transform:uppercase; letter-spacing:.04em; }}
  .card {{ background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:18px 20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.3); }}
  table {{ width:100%; border-collapse:collapse; }}
  th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid var(--border); font-size:14px; }}
  th {{ color:var(--muted); font-weight:500; font-size:12px; text-transform:uppercase; }}
  input[type=text], input[type=time], input[type=date], input[type=number], input[type=file], input[type=password] {{
    background:#0f1720; border:1px solid var(--border); color:var(--text); border-radius:6px; padding:7px 9px; font-size:14px; width:100%;
  }}
  input[type=range] {{ width:100%; }}
  button, .btn {{ background:var(--accent); color:#fff; border:none; border-radius:6px; padding:8px 16px; font-size:14px; cursor:pointer; transition:filter .15s,transform .05s; }}
  button:hover, .btn:hover {{ filter:brightness(1.12); }}
  button:active, .btn:active {{ transform:scale(.98); }}
  button:disabled {{ opacity:.6; cursor:default; filter:none; }}
  button.danger {{ background:var(--err); }}
  button.secondary {{ background:#2d3947; }}
  button.zil-buton {{ background:var(--accent); font-size:17px; font-weight:600; padding:16px 22px; width:100%; border-radius:10px; }}
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
  <a href="/youtube-cal" class="{'active' if baslik=='YouTube Çal' else ''}">🎉 YouTube Çal</a>
</nav>
<main>
  <h1>{baslik}</h1>
  {mesaj_html}{hata_html}
  {icerik}
</main>
</body></html>"""


# --- / : Özet ---
TR_HARF_ESLESTIRME = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _id_uret(ad, mevcut_idler):
    taban = re.sub(r"[^a-z0-9]+", "_", ad.translate(TR_HARF_ESLESTIRME).lower()).strip("_") or "program"
    aday = taban
    n = 2
    while aday in mevcut_idler:
        aday = f"{taban}_{n}"
        n += 1
    return aday


def _saat_ekle(saat_str, dakika):
    t = datetime.strptime(saat_str, "%H:%M") + timedelta(minutes=dakika)
    return t.strftime("%H:%M")


def _zil_programi_hesapla(veri, gun_iso):
    # ozet() sayfasında "bugünkü zil programı"nı katmanlı (öğrenci toplan / giriş /
    # çıkış / öğrenci girişi / öğretmen girişi) etiketleriyle göstermek için — sys.py'deki
    # _ders_programindan_turet ile aynı zaman mantığının, etiketli görüntüleme amaçlı
    # bir tekrarı (2026-09-18, kullanıcı isteği: "zil katmanlı olsun").
    ayarlar = veri.get("ayarlar", {})
    sabit_ziller = veri.get("sabit_ziller", [])
    offset = ayarlar.get("ogrenci_zili_offset_dk", 5)
    max_boslu = ayarlar.get("ogrenci_zili_max_bosluk_dk", 20)
    ogrenci_zili_aktif = ayarlar.get("ogrenci_zili_aktif", True)

    for p in veri.get("programlar", []):
        if gun_iso not in p.get("gunler", []):
            continue
        dersler = sorted(p.get("dersler", []), key=lambda d: d["baslangic"])
        olaylar = []
        for i, d in enumerate(dersler):
            # Bu dersten önce (aynı gün, aynı programda) kısa bir teneffüs varsa "Öğretmen
            # Girişi", yoksa (günün ilk dersi ya da uzun bir aradan sonraysa, ör. öğle
            # arası) sıradan "Giriş" — çünkü o durumda hemen öncesinde bir "toplanma" zili var.
            onceki_kisa_ara_var = False
            if i > 0:
                bosluk = (datetime.strptime(d["baslangic"], "%H:%M") - datetime.strptime(dersler[i - 1]["bitis"], "%H:%M")).total_seconds() / 60
                onceki_kisa_ara_var = 0 < bosluk <= max_boslu
            olaylar.append({"saat": d["baslangic"], "tur": "Öğretmen Girişi" if onceki_kisa_ara_var else "Giriş"})
            olaylar.append({"saat": d["bitis"], "tur": "Çıkış"})
            if ogrenci_zili_aktif and i < len(dersler) - 1:
                bosluk = (datetime.strptime(dersler[i + 1]["baslangic"], "%H:%M") - datetime.strptime(d["bitis"], "%H:%M")).total_seconds() / 60
                if 0 < bosluk <= max_boslu:
                    olaylar.append({"saat": _saat_ekle(d["bitis"], offset), "tur": "Öğrenci Girişi"})
        for sz in sabit_ziller:
            if gun_iso in sz.get("gunler", []):
                olaylar.append({"saat": sz["saat"], "tur": sz.get("aciklama") or "Öğrenci Toplanması"})
        olaylar.sort(key=lambda o: o["saat"])
        return p, dersler, olaylar
    return None, [], []


@app.route("/")
@yetki_gerekli
def ozet():
    veri = ders_programi_oku()
    simdi = datetime.now()
    simdi_hhmm = simdi.strftime("%H:%M")
    bugun_iso = simdi.isoweekday()
    bugun_tarih = simdi.strftime("%Y-%m-%d")
    tatil_gunleri = veri.get("tatil_gunleri", [])
    ayarlar = veri.get("ayarlar", {})

    program_bugun, dersler, zil_programi = _zil_programi_hesapla(veri, bugun_iso)
    bugun_tatil = bugun_tarih in tatil_gunleri
    bugun_okul_gunu = program_bugun is not None and dersler and not bugun_tatil
    sonraki = next((o for o in zil_programi if o["saat"] > simdi_hhmm), None)

    def rozet(aktif, etiket):
        return f'<span class="badge {"on" if aktif else "off"}">{etiket}: {"Açık" if aktif else "Kapalı"}</span>'

    if bugun_tatil:
        durum = "📅 Bugün <b>tatil</b> olarak işaretli — otomasyon çalışmaz."
    elif not program_bugun or not dersler:
        durum = "📅 Bugün için tanımlı bir program/ders yok — otomasyon çalışmaz."
    elif sonraki:
        durum = f"⏰ Sıradaki zil: <b>{sonraki['saat']}</b> — {sonraki['tur']} ({program_bugun['ad']})"
    else:
        durum = f"Bugün ({program_bugun['ad']}) için kalan zil yok."

    icerik = f"""
    <div class="card">
      <button class="zil-buton" id="zil-cal-buton" onclick="zilCal()">🔔 Şimdi Zil Çal</button>
      <div id="zil-cal-durum" class="small" style="margin-top:8px"></div>
    </div>
    <script>
    function zilCal() {{
      if (!confirm('Zil şimdi bina genelinde çalınsın mı?')) return;
      var btn = document.getElementById('zil-cal-buton');
      var durum = document.getElementById('zil-cal-durum');
      btn.disabled = true;
      durum.textContent = '🔔 Çalınıyor...';
      fetch(location.origin + '/zil-cal', {{method: 'POST', credentials: 'same-origin'}})
        .then(function(r) {{ return r.json(); }})
        .then(function(d) {{
          durum.textContent = d.tamam ? '✅ Zil çalındı.' : ('❌ ' + (d.hata || 'Zil çalınamadı.'));
        }})
        .catch(function(e) {{ durum.textContent = '❌ İstek başarısız: ' + e; }})
        .finally(function() {{ setTimeout(function() {{ btn.disabled = false; }}, 2000); }});
    }}
    </script>
    <div class="card">
      <div class="small">Bugün: {GUN_ADLARI.get(bugun_iso, "?")} · {bugun_tarih} · şu an {simdi_hhmm}</div>
      <p style="font-size:15px;margin:10px 0 0">{durum}</p>
    </div>
    <div class="card">
      {rozet(ayarlar.get('zil_aktif', True), 'Zil')}
      {rozet(ayarlar.get('tenefus_muzigi_aktif', True), 'Teneffüs müziği')}
      {rozet(os.path.exists(ZIL_SESI_DOSYASI), 'zil_sesi.mp3 mevcut')}
      <div class="small" style="margin-top:10px">Zil ses seviyesi: %{ayarlar.get('zil_ses_seviyesi', 80)} · Otomatik ses seviyesi: %{ayarlar.get('otomatik_ses_seviyesi', 50)}</div>
    </div>
    <div class="card">
      <h2 style="margin-top:0">Bugünkü Zil Programı</h2>
      {"<table><tr><th>Saat</th><th>Tür</th></tr>" + "".join(f'<tr><td>{o["saat"]}</td><td>{"➡️ " + o["tur"] if sonraki and o["saat"] == sonraki["saat"] else o["tur"]}</td></tr>' for o in zil_programi) + "</table>" if zil_programi else '<p class="small">Bugün için zil programı yok.</p>'}
    </div>
    <div class="card">
      <h2 style="margin-top:0">Tanımlı Programlar</h2>
      <table><tr><th>Program</th><th>Günler</th><th>Ders sayısı</th></tr>
      {''.join(f"<tr><td>{p['ad']}</td><td>{', '.join(GUN_ADLARI.get(g,'?') for g in p.get('gunler',[]))}</td><td>{len(p.get('dersler',[]))}</td></tr>" for p in veri.get('programlar', []))}
      </table>
    </div>
    <p class="small">Detaylı düzenleme: <a class="link" href="/program">Ders Programı</a>, <a class="link" href="/ayarlar">Ayarlar</a>, <a class="link" href="/zil-sesi">Zil Sesi</a>, <a class="link" href="/playlist">Playlist</a>.</p>
    """
    return sayfa("Özet", icerik)


@app.route("/zil-cal", methods=["POST"])
@yetki_gerekli
def zil_cal():
    # sys.py'deki etkinlik_dinleyici() ile paylaşılan aynı dosya-tabanlı IPC kanalı
    # (youtube-cal ile aynı desen) — burada sadece "zil_cal" komutu yazılıyor, sonucu
    # ayrıca sorgulamaya gerek yok çünkü zil sesi kısa (dashboard tarafı sadece isteğin
    # kabul edildiğini bildiriyor, gerçek çalma sys.py tarafında ~3sn içinde gerçekleşir).
    istek = {"istek_id": str(uuid.uuid4()), "komut": "zil_cal"}
    _atomik_yaz(OYNATMA_ISTEGI_DOSYASI, json.dumps(istek, ensure_ascii=False).encode("utf-8"))
    return jsonify({"tamam": True})


def _dersler_form_alanlarindan_olustur(form, alan_no, alan_b, alan_s, boyut_uyari_prefix):
    nolar = form.getlist(alan_no)
    baslangiclar = form.getlist(alan_b)
    bitisler = form.getlist(alan_s)
    yeni_dersler = []
    for no, b, s in zip(nolar, baslangiclar, bitisler):
        b, s = b.strip(), s.strip()
        if not b and not s:
            continue  # boş satır atla
        if not (SAAT_RE.match(b) and SAAT_RE.match(s)):
            raise ValueError(f"{boyut_uyari_prefix} {no}: saat formatı hatalı (HH:MM).")
        if s <= b:
            raise ValueError(f"{boyut_uyari_prefix} {no}: bitiş, başlangıçtan sonra olmalı.")
        yeni_dersler.append({"no": int(no), "baslangic": b, "bitis": s})
    yeni_dersler.sort(key=lambda d: d["baslangic"])
    for i in range(len(yeni_dersler) - 1):
        if yeni_dersler[i + 1]["baslangic"] < yeni_dersler[i]["bitis"]:
            raise ValueError(f"Ders {yeni_dersler[i]['no']} ile {yeni_dersler[i+1]['no']} çakışıyor.")
    return yeni_dersler


# --- /program : programlar (hafta içi/hafta sonu/...) + gün ataması + tatil takvimi ---
@app.route("/program", methods=["GET", "POST"])
@yetki_gerekli
def program():
    mesaj = hata = None
    veri = ders_programi_oku()
    veri.setdefault("programlar", [])

    if request.method == "POST":
        islem = request.form.get("islem", "")
        try:
            if islem == "tatil_ekle":
                tarih = request.form.get("yeni_tatil", "").strip()
                if not TARIH_RE.match(tarih):
                    raise ValueError("Geçersiz tarih formatı (YYYY-AA-GG bekleniyor).")
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

            elif islem == "karsilama_kaydet":
                karsilama_aktif = request.form.get("karsilama_aktif") == "on"
                k_baslama = request.form.get("karsilama_baslama", "").strip()
                k_durdurma = request.form.get("karsilama_durdurma", "").strip()
                if karsilama_aktif:
                    if not (SAAT_RE.match(k_baslama) and SAAT_RE.match(k_durdurma)):
                        raise ValueError("Karşılama müziği saatleri hatalı (HH:MM).")
                    if k_durdurma <= k_baslama:
                        raise ValueError("Karşılama müziği durdurma, başlamadan sonra olmalı.")
                veri["karsilama_muzigi"] = {"aktif": karsilama_aktif, "baslama": k_baslama or "07:50", "durdurma": k_durdurma or "07:55"}
                ders_programi_yaz(veri)
                mesaj = "Karşılama müziği ayarları kaydedildi."

            elif islem == "sabit_zil_ekle":
                saat = request.form.get("yeni_sabit_zil_saat", "").strip()
                aciklama = request.form.get("yeni_sabit_zil_aciklama", "").strip() or "Sabit zil"
                gunler = sorted(int(g) for g in request.form.getlist("yeni_sabit_zil_gun"))
                if not SAAT_RE.match(saat):
                    raise ValueError("Geçersiz saat formatı (HH:MM).")
                if not gunler:
                    raise ValueError("En az bir gün seçilmeli.")
                sabit_ziller = veri.setdefault("sabit_ziller", [])
                sabit_ziller.append({"saat": saat, "aciklama": aciklama, "gunler": gunler})
                sabit_ziller.sort(key=lambda z: z["saat"])
                ders_programi_yaz(veri)
                mesaj = f"Sabit zil eklendi: {saat} — {aciklama}"

            elif islem == "sabit_zil_sil":
                indeks = int(request.form.get("indeks", -1))
                sabit_ziller = veri.get("sabit_ziller", [])
                if 0 <= indeks < len(sabit_ziller):
                    silinen = sabit_ziller.pop(indeks)
                    ders_programi_yaz(veri)
                    mesaj = f"Sabit zil kaldırıldı: {silinen['saat']} — {silinen.get('aciklama','')}"

            elif islem == "program_ekle":
                ad = request.form.get("yeni_program_adi", "").strip()
                if not ad:
                    raise ValueError("Yeni program için bir ad girin.")
                mevcut_idler = {p["id"] for p in veri["programlar"]}
                yeni_id = _id_uret(ad, mevcut_idler)
                veri["programlar"].append({"id": yeni_id, "ad": ad, "gunler": [], "dersler": []})
                ders_programi_yaz(veri)
                mesaj = f"Program eklendi: {ad}. Şimdi günlerini ve ders saatlerini ayarlayın."

            elif islem == "program_sil":
                program_id = request.form.get("program_id", "")
                veri["programlar"] = [p for p in veri["programlar"] if p["id"] != program_id]
                ders_programi_yaz(veri)
                mesaj = "Program silindi. O günlere artık hiçbir program atanmamış durumda (otomasyon çalışmaz)."

            elif islem == "program_kaydet":
                program_id = request.form.get("program_id", "")
                hedef = next((p for p in veri["programlar"] if p["id"] == program_id), None)
                if hedef is None:
                    raise ValueError("Program bulunamadı (sayfa yenilenmiş olabilir).")
                ad = request.form.get("ad", "").strip() or hedef["ad"]
                yeni_dersler = _dersler_form_alanlarindan_olustur(request.form, "ders_no", "ders_baslangic", "ders_bitis", "Ders")
                yeni_gunler = sorted(int(g) for g in request.form.getlist("gun"))
                # Bir gün aynı anda iki programda olamaz — başka bir programla çakışma var mı kontrol et.
                for diger in veri["programlar"]:
                    if diger["id"] == program_id:
                        continue
                    cakisan = set(diger.get("gunler", [])) & set(yeni_gunler)
                    if cakisan:
                        gun_adlari = ", ".join(GUN_ADLARI[g] for g in sorted(cakisan))
                        raise ValueError(f"{gun_adlari} zaten '{diger['ad']}' programına atanmış. Önce oradan kaldırın.")
                hedef["ad"] = ad
                hedef["gunler"] = yeni_gunler
                hedef["dersler"] = yeni_dersler
                ders_programi_yaz(veri)
                mesaj = f"'{ad}' programı kaydedildi."

            veri = ders_programi_oku()
        except ValueError as e:
            hata = str(e)

    tatil_gunleri = sorted(veri.get("tatil_gunleri", []))
    karsilama = veri.get("karsilama_muzigi", {})
    sabit_ziller = veri.get("sabit_ziller", [])
    tum_atanmis_gunler = set()
    for p in veri["programlar"]:
        tum_atanmis_gunler |= set(p.get("gunler", []))

    def program_karti(p):
        dersler = sorted(p.get("dersler", []), key=lambda d: d["baslangic"])
        gunler = set(p.get("gunler", []))
        ders_satirlari = "".join(f"""
          <div class="row">
            <div style="max-width:60px"><label>No</label><input type="text" name="ders_no" value="{d['no']}" readonly></div>
            <div><label>Başlangıç</label><input type="time" name="ders_baslangic" value="{d['baslangic']}"></div>
            <div><label>Bitiş</label><input type="time" name="ders_bitis" value="{d['bitis']}"></div>
          </div>""" for d in dersler)
        for i in range(len(dersler) + 1, len(dersler) + 4):
            ders_satirlari += f"""
          <div class="row">
            <div style="max-width:60px"><label>No</label><input type="text" name="ders_no" value="{i}" readonly></div>
            <div><label>Başlangıç</label><input type="time" name="ders_baslangic" value=""></div>
            <div><label>Bitiş</label><input type="time" name="ders_bitis" value=""></div>
          </div>"""
        gun_togglelari = "".join(f"""
          <label class="gun-toggle"><input type="checkbox" name="gun" value="{g}" {"checked" if g in gunler else ""}> {ad}</label>
        """ for g, ad in GUN_ADLARI.items())
        return f"""
        <div class="card">
          <form method="post">
            <input type="hidden" name="islem" value="program_kaydet">
            <input type="hidden" name="program_id" value="{p['id']}">
            <div class="row">
              <div><label>Program adı</label><input type="text" name="ad" value="{p['ad']}"></div>
            </div>
            <h2 style="margin:14px 0 8px">Günler</h2>
            {gun_togglelari}
            <h2 style="margin:14px 0 8px">Ders Saatleri</h2>
            {ders_satirlari}
            <p class="small">Boş satırlar yok sayılır. 0 veya 1 ders girilirse o gün sadece o dersin zili çalar, teneffüs müziği hesaplanmaz.</p>
            <button type="submit" style="margin-top:8px">Kaydet</button>
          </form>
          <form method="post" style="margin-top:10px" onsubmit="return confirm('\\'{p['ad']}\\' programı tamamen silinsin mi?')">
            <input type="hidden" name="islem" value="program_sil">
            <input type="hidden" name="program_id" value="{p['id']}">
            <button type="submit" class="danger">Programı Sil</button>
          </form>
        </div>
        """

    programlar_html = "".join(program_karti(p) for p in veri["programlar"]) or '<p class="small">Henüz program tanımlanmamış.</p>'

    atanmamis_gunler = [ad for g, ad in GUN_ADLARI.items() if g not in tum_atanmis_gunler]
    atanmamis_uyari = (
        f'<div class="msg err" style="margin-top:0">Şu günlere hiçbir program atanmamış, bu günlerde otomasyon çalışmaz: {", ".join(atanmamis_gunler)}</div>'
        if atanmamis_gunler else ""
    )

    tatil_satirlari = "".join(f"""
      <div class="row" style="align-items:center">
        <div>{t}</div>
        <div style="flex:0"><form method="post" style="margin:0"><input type="hidden" name="islem" value="tatil_sil"><input type="hidden" name="tarih" value="{t}"><button type="submit" class="danger">Sil</button></form></div>
      </div>""" for t in tatil_gunleri) or '<p class="small">Tatil günü işaretlenmemiş.</p>'

    icerik = f"""
    {atanmamis_uyari}
    <h2 style="margin-top:0">Programlar</h2>
    <p class="small">Her program kendi günlerine ve kendi ders saatlerine sahiptir — hafta içi ve hafta sonu (hatta Cumartesi/Pazar) tamamen bağımsız ayarlanabilir. Bir gün aynı anda yalnızca bir programa ait olabilir.</p>
    {programlar_html}
    <div class="card">
      <form method="post" class="row">
        <input type="hidden" name="islem" value="program_ekle">
        <div><label>Yeni program adı</label><input type="text" name="yeni_program_adi" placeholder="ör. Cumartesi Kursu" required></div>
        <div style="flex:0"><button type="submit" class="secondary">Program Ekle</button></div>
      </form>
    </div>

    <div class="card">
      <h2 style="margin-top:0">Okul Girişi Karşılama Müziği</h2>
      <p class="small">Ders içeren bir programın atandığı her gün geçerlidir (ör. hafta içi + hafta sonu dersi varsa ikisinde de çalar).</p>
      <form method="post">
        <input type="hidden" name="islem" value="karsilama_kaydet">
        <label class="gun-toggle"><input type="checkbox" name="karsilama_aktif" {"checked" if karsilama.get('aktif') else ""}> Aktif</label>
        <div class="row">
          <div><label>Başlama</label><input type="time" name="karsilama_baslama" value="{karsilama.get('baslama','07:50')}"></div>
          <div><label>Durdurma</label><input type="time" name="karsilama_durdurma" value="{karsilama.get('durdurma','07:55')}"></div>
        </div>
        <button type="submit">Kaydet</button>
      </form>
    </div>

    <div class="card">
      <h2 style="margin-top:0">Sabit Ziller</h2>
      <p class="small">Belirli bir derse bağlı olmayan, sabit saatte çalan ziller — ör. gün başında veya öğle arası sonrasında öğrenci toplanma zili. (Teneffüsler arasındaki "öğrenci zili" ayrı bir ayar — bkz. <a class="link" href="/ayarlar">Ayarlar</a>.)</p>
      {"".join(f'''
      <div class="row" style="align-items:center">
        <div style="flex:0;min-width:60px"><b>{z["saat"]}</b></div>
        <div>{z.get("aciklama","")} <span class="small">({", ".join(GUN_ADLARI.get(g,"?") for g in z.get("gunler",[]))})</span></div>
        <div style="flex:0"><form method="post" style="margin:0"><input type="hidden" name="islem" value="sabit_zil_sil"><input type="hidden" name="indeks" value="{i}"><button type="submit" class="danger">Sil</button></form></div>
      </div>''' for i, z in enumerate(sabit_ziller)) or '<p class="small">Sabit zil tanımlanmamış.</p>'}
      <form method="post" style="margin-top:12px">
        <input type="hidden" name="islem" value="sabit_zil_ekle">
        <div class="row">
          <div style="max-width:120px"><label>Saat</label><input type="time" name="yeni_sabit_zil_saat" required></div>
          <div><label>Açıklama</label><input type="text" name="yeni_sabit_zil_aciklama" placeholder="ör. Öğrenci toplanması"></div>
        </div>
        {"".join(f'<label class="gun-toggle"><input type="checkbox" name="yeni_sabit_zil_gun" value="{g}" checked> {ad}</label>' for g, ad in GUN_ADLARI.items() if g <= 5)}
        {"".join(f'<label class="gun-toggle"><input type="checkbox" name="yeni_sabit_zil_gun" value="{g}"> {ad}</label>' for g, ad in GUN_ADLARI.items() if g > 5)}
        <div style="margin-top:8px"><button type="submit" class="secondary">Sabit Zil Ekle</button></div>
      </form>
    </div>

    <div class="card">
      <h2 style="margin-top:0">Tatil Günleri</h2>
      {tatil_satirlari}
      <form method="post" class="row" style="margin-top:12px">
        <input type="hidden" name="islem" value="tatil_ekle">
        <div><label>Yeni tatil günü</label><input type="date" name="yeni_tatil" required></div>
        <div style="flex:0"><button type="submit" class="secondary">Ekle</button></div>
      </form>
      <p class="small">İşaretli günlerde, hangi programa denk gelirse gelsin zil/teneffüs/karşılama müziğinin hepsi otomatik olarak kapanır.</p>
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
        ayarlar["ogrenci_zili_aktif"] = request.form.get("ogrenci_zili_aktif") == "on"
        ayarlar["ogrenci_zili_offset_dk"] = max(1, min(30, int(request.form.get("ogrenci_zili_offset_dk", 5) or 5)))
        ayarlar["ogrenci_zili_max_bosluk_dk"] = max(1, min(120, int(request.form.get("ogrenci_zili_max_bosluk_dk", 20) or 20)))
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
      <div class="card">
        <h2 style="margin-top:0">Öğrenci Zili</h2>
        <p class="small">Kısa teneffüslerde (ders çıkışı ile sonraki giriş arası belirlenen eşiğin altındaysa) çıkış zilinden birkaç dakika sonra ekstra bir uyarı zili çalar — ör. 08:50 çıkış → 08:55 öğrenci zili → 09:00 giriş. Uzun aralar (öğle arası gibi) otomatik olarak hariç tutulur.</p>
        <label class="gun-toggle"><input type="checkbox" name="ogrenci_zili_aktif" {"checked" if a.get('ogrenci_zili_aktif', True) else ""}> Öğrenci zili aktif</label>
        <div class="row" style="margin-top:10px">
          <div><label>Kaç dakika sonra çalsın</label><input type="number" min="1" max="30" name="ogrenci_zili_offset_dk" value="{a.get('ogrenci_zili_offset_dk', 5)}"></div>
          <div><label>Bu süreden uzun aralarda uygulanmasın (dk)</label><input type="number" min="1" max="120" name="ogrenci_zili_max_bosluk_dk" value="{a.get('ogrenci_zili_max_bosluk_dk', 20)}"></div>
        </div>
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


# --- /youtube-cal : etkinlik (kermes/festival) icin YouTube link/playlist'ini dogrudan
# hoparlorden calmak (indirme yok, streaming) - playlist/'e hic dokunmaz, tenefus
# otomasyonuyla karismaz. sys.py'deki etkinlik_dinleyici() ile dosya-tabanli komut
# kanaliyla haberlesir (bkz. OYNATMA_ISTEGI_DOSYASI / OYNATMA_DURUMU_DOSYASI).
@app.route("/youtube-cal", methods=["GET"])
@yetki_gerekli
def youtube_cal_sayfasi():
    icerik = """
    <div class="card">
      <p class="small">Kermes/festival gibi etkinliklerde kullanmak için — bir YouTube video veya playlist linki
      yapıştırın, doğrudan zil sunucusunun hoparlöründen çalınmaya başlar (indirme yok, playlist/ klasörüne
      dokunmaz, teneffüs otomasyonuna karışmaz). Playlist ise şarkılar sırayla, kendiliğinden bir sonrakine
      geçilerek çalınır.</p>
      <form id="cal-form" class="row">
        <div><label>YouTube video veya playlist linki</label><input type="text" id="youtube-url" placeholder="https://www.youtube.com/playlist?list=..." required></div>
        <div style="flex:0"><button type="submit">▶️ Çal</button></div>
      </form>
      <form id="durdur-form" style="margin-top:8px">
        <button type="submit" class="danger">⏹ Durdur</button>
      </form>
    </div>
    <div class="card">
      <h2 style="margin-top:0">Durum</h2>
      <div id="durum-alani" class="small">Yükleniyor...</div>
    </div>
    <script>
    function durumGuncelle(d) {
      var el = document.getElementById('durum-alani');
      if (!d || d.durum === 'bos') { el.textContent = 'Henüz bir şey çalınmadı.'; return; }
      if (d.durum === 'calindi') { el.textContent = '▶️ Çalınıyor: ' + d.baslik + ' (' + d.sira + '/' + d.toplam + ')'; return; }
      if (d.durum === 'atlandi') { el.textContent = '⚠️ Parça atlandı (' + d.sira + '/' + d.toplam + '): ' + (d.hata_mesaji || ''); return; }
      if (d.durum === 'tamamlandi') { el.textContent = '✅ Kuyruk tamamlandı.'; return; }
      if (d.durum === 'durduruldu') { el.textContent = '⏹ Durduruldu.'; return; }
      if (d.durum === 'hata') { el.textContent = '❌ Hata: ' + (d.hata_mesaji || ''); return; }
      el.textContent = JSON.stringify(d);
    }
    function durumCek() {
      fetch(location.origin + '/youtube-cal/durum', {credentials: 'same-origin'})
        .then(function(r){ return r.json(); })
        .then(durumGuncelle)
        .catch(function(e){ document.getElementById('durum-alani').textContent = '⚠️ Durum alınamadı: ' + e; });
    }
    document.getElementById('cal-form').addEventListener('submit', function(e) {
      e.preventDefault();
      var url = document.getElementById('youtube-url').value;
      fetch(location.origin + '/youtube-cal/baslat', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: 'url=' + encodeURIComponent(url)})
        .then(function(){ document.getElementById('durum-alani').textContent = 'Başlatılıyor...'; setTimeout(durumCek, 1000); });
    });
    document.getElementById('durdur-form').addEventListener('submit', function(e) {
      e.preventDefault();
      fetch(location.origin + '/youtube-cal/durdur', {method: 'POST', credentials: 'same-origin'}).then(function(){ setTimeout(durumCek, 1000); });
    });
    durumCek();
    setInterval(durumCek, 3000);
    </script>
    """
    return sayfa("YouTube Çal", icerik)


@app.route("/youtube-cal/baslat", methods=["POST"])
@yetki_gerekli
def youtube_cal_baslat():
    url = request.form.get("url", "").strip()
    if not YOUTUBE_LINK_RE.search(url):
        return jsonify({"tamam": False, "hata": "Geçerli bir YouTube linki değil."}), 400
    istek = {"istek_id": str(uuid.uuid4()), "komut": "cal", "url": url}
    _atomik_yaz(OYNATMA_ISTEGI_DOSYASI, json.dumps(istek, ensure_ascii=False).encode("utf-8"))
    return jsonify({"tamam": True})


@app.route("/youtube-cal/durdur", methods=["POST"])
@yetki_gerekli
def youtube_cal_durdur():
    istek = {"istek_id": str(uuid.uuid4()), "komut": "durdur"}
    _atomik_yaz(OYNATMA_ISTEGI_DOSYASI, json.dumps(istek, ensure_ascii=False).encode("utf-8"))
    return jsonify({"tamam": True})


@app.route("/youtube-cal/durum", methods=["GET"])
@yetki_gerekli
def youtube_cal_durum():
    try:
        with open(OYNATMA_DURUMU_DOSYASI, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"durum": "bos"})


if __name__ == "__main__":
    from waitress import serve
    print("--- ZİL DASHBOARD (waitress) 0.0.0.0:8090 ---")
    serve(app, host="0.0.0.0", port=8090)
