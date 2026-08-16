#!/bin/bash

PROJECT_DIR=~/projects/ik-asistan
SESSION="ik-dev"

cd $PROJECT_DIR

echo "=============================================="
echo "🛑 Geliştirme Ortamı Kapatılıyor..."
echo "=============================================="

# 1. Tmux oturumu çalışıyor mu kontrol et ve sonlandır
if tmux has-session -t $SESSION 2>/dev/null; then
  echo "[*] Honcho ve Python servisleri (FastAPI, Celery) durduruluyor..."
  # Oturuma Ctrl+C sinyali gönder (Honcho tüm alt süreçleri temiz kapatsın)
  tmux send-keys -t $SESSION C-c
  sleep 5
  # Oturumu tamamen yok et
  tmux kill-session -t $SESSION 2>/dev/null
  echo "✅ Tmux oturumu ('$SESSION') kapatıldı."
else
  echo "ℹ️ '$SESSION' adında aktif bir tmux oturumu bulunamadı."
fi

# 2. Docker servislerini (Postgres & Redis) durdur
echo ""
echo "[*] Docker servisleri (Postgres & Redis) durduruluyor..."
docker compose down

echo ""
echo "=============================================="
echo "🎉 Tüm servisler başarıyla kapatıldı!"
echo "=============================================="
