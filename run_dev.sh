#!/bin/bash

PROJECT_DIR=~/projects/ik-asistan
BACKEND_DIR=$PROJECT_DIR/backend
SESSION="ik-dev"

cd $PROJECT_DIR

# 1. Docker servislerini (Postgres & Redis) arka planda başlat
echo "=============================================="
echo "🚀 1/4 Docker servisleri başlatılıyor..."
echo "=============================================="
docker compose up -d

# 2. Tmux oturumunu ve Honcho'yu arka planda başlat
echo ""
echo "🚀 2/4 Honcho (FastAPI + Celery) ayağa kaldırılıyor..."
tmux has-session -t $SESSION 2>/dev/null

if [ $? != 0 ]; then
  tmux new-session -d -s $SESSION -c $BACKEND_DIR "source ../.venv/bin/activate && honcho start -f Procfile.dev"
  echo "✅ Servisler arka planda başlatıldı."
else
  echo "ℹ️ '$SESSION' oturumu zaten çalışıyor."
fi

# 3. Servislerin tam ayağa kalkması için kısa bekleme
echo ""
echo "⏳ Servislerin bağlanması bekleniyor (15 sn)..."
sleep 15

# 4. Bağlantı ve Sağlık Kontrolünü Çalıştır
echo ""
echo "=============================================="
echo "🔍 3/4 Sağlık & Bağlantı Kontrolleri Yapılıyor"
echo "=============================================="
cd $BACKEND_DIR
source ../.venv/bin/activate
python scripts/check_connections.py
CHECK_STATUS=$?

echo ""
if [ $CHECK_STATUS -eq 0 ]; then
  echo "=============================================="
  echo "🎉 4/4 Her şey hazır! Log ekranına bağlanılıyor..."
  echo "ℹ️  (Çıkmak için: Ctrl+B sonra D | Durdurmak için: Ctrl+C)"
  echo "=============================================="
  sleep 2
  tmux attach -t $SESSION
else
  echo "=============================================="
  echo "⚠️ Bazı servislerde hata oluştu!"
  echo "👉 Detaylı hata loglarını görmek için:"
  echo "   tmux attach -t $SESSION"
  echo "=============================================="
fi