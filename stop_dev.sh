#!/bin/bash

PROJECT_DIR=~/projects/ik-asistan
BACKEND_DIR=$PROJECT_DIR/backend
SESSION="ik-dev"

cd $PROJECT_DIR

echo "=============================================="
echo "🛑 Geliştirme Ortamı Kapatılıyor..."
echo "=============================================="

if tmux has-session -t $SESSION 2>/dev/null; then

  echo ""
  echo "[*] Aktif Celery görevleri kontrol ediliyor..."
  cd $BACKEND_DIR
  source ../.venv/bin/activate
  python scripts/check_active_tasks.py
  ACTIVE_STATUS=$?
  cd $PROJECT_DIR

  if [ $ACTIVE_STATUS -ne 0 ]; then
    echo ""
    read -p "⚠️  Şu an işlenen bir görev var. Yine de durdurulsun mu? [e/H]: " confirm
    if [[ ! "$confirm" =~ ^[eE]$ ]]; then
      echo "İşlem iptal edildi. Görev(ler) bitene kadar bekleyip tekrar deneyebilirsin."
      exit 0
    fi
  fi

  echo "[*] Honcho ve Python servisleri (FastAPI, Celery) durduruluyor..."
  tmux send-keys -t $SESSION C-c
  sleep 5
  tmux kill-session -t $SESSION 2>/dev/null
  echo "✅ Tmux oturumu ('$SESSION') kapatıldı."
else
  echo "ℹ️ '$SESSION' adında aktif bir tmux oturumu bulunamadı."
fi

echo ""
echo "[*] Docker servisleri (Postgres & Redis) durduruluyor..."
docker compose down

echo ""
echo "=============================================="
echo "🔍 Kapatma Doğrulaması"
echo "=============================================="

STILL_RUNNING=$(docker ps --filter "name=ik-asistan" --format "{{.Names}}")
if [ -z "$STILL_RUNNING" ]; then
  echo "✅ Docker container'ları tamamen kapandı."
else
  echo "⚠️ Hâlâ çalışan container(lar) var: $STILL_RUNNING"
fi

if ss -tln 2>/dev/null | grep -q ':8000 '; then
  echo "⚠️ 8000 portu hâlâ dinleniyor (FastAPI tam kapanmamış olabilir)."
else
  echo "✅ 8000 portu boş (FastAPI kapandı)."
fi

if tmux has-session -t $SESSION 2>/dev/null; then
  echo "⚠️ '$SESSION' tmux oturumu hâlâ mevcut."
else
  echo "✅ Tmux oturumu temizlendi."
fi

echo ""
echo "=============================================="
echo "🎉 Kapatma işlemi tamamlandı!"
echo "=============================================="