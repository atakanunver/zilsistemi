#!/bin/bash
set -uo pipefail
DIR=/home/atakan/ses/playlist
LOG=/home/atakan/ses/split_progress.log

echo "START $(date)" > "$LOG"

shopt -s nullglob
for f in "$DIR"/muzik*.mp3; do
  base=$(basename "$f" .mp3)
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
  dur_int=${dur%.*}
  n=$(( dur_int / 120 ))
  if [ "$n" -lt 1 ]; then
    echo "SKIP $f (sure ${dur}s < 120s, tam parca yok)" >> "$LOG"
    continue
  fi
  echo "ISLENIYOR: $f -> $n parca (toplam sure ${dur}s)" >> "$LOG"
  ok=1
  for ((i=0; i<n; i++)); do
    start=$((i*120))
    idx=$(printf "%03d" $((i+1)))
    out="$DIR/${base}_${idx}.mp3"
    if ! ffmpeg -y -ss "$start" -t 120 -i "$f" -af "afade=t=in:st=0:d=2,afade=t=out:st=118:d=2" -b:a 128k "$out" >> "$LOG" 2>&1; then
      echo "HATA: $out olusturulamadi" >> "$LOG"
      ok=0
      break
    fi
  done
  if [ "$ok" -eq 1 ]; then
    rm -f "$f"
    echo "SILINDI (orijinal): $f" >> "$LOG"
  else
    echo "ORIJINAL KORUNDU (hata oldugu icin): $f" >> "$LOG"
  fi
done

rm -f "$DIR"/*.ogg
echo "OGG DOSYALARI SILINDI" >> "$LOG"
echo "TAMAMLANDI $(date)" >> "$LOG"
