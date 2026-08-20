#!/bin/bash

PROJECT_DIR=~/projects/ik-asistan
BACKEND_DIR=$PROJECT_DIR/backend
SESSION="ik-dev"

cd "$PROJECT_DIR"

echo "=============================================="
echo "🛑 Geliştirme Ortamı Kapatılıyor..."
echo "=============================================="


# ==========================================================
# TMUX + HONCHO KONTROLÜ
# ==========================================================

if tmux has-session -t "$SESSION" 2>/dev/null; then

  echo ""
  echo "[*] Aktif Celery görevleri kontrol ediliyor..."

  cd "$BACKEND_DIR"

  source ../.venv/bin/activate

  python scripts/check_active_tasks.py
  ACTIVE_STATUS=$?

  cd "$PROJECT_DIR"


  # --------------------------------------------------------
  # AKTİF GÖREV VARSA KULLANICIYA SOR
  # --------------------------------------------------------

  if [ $ACTIVE_STATUS -ne 0 ]; then

    echo ""
    read -p "⚠️  Şu an işlenen bir görev var. Yine de durdurulsun mu? [e/H]: " confirm

    if [[ ! "$confirm" =~ ^[eE]$ ]]; then
      echo ""
      echo "❌ İşlem iptal edildi."
      echo "   Görev(ler) bitene kadar bekleyip tekrar deneyebilirsin."
      exit 0
    fi

  fi


  # --------------------------------------------------------
  # HONCHO'YU DURDUR
  # --------------------------------------------------------

  echo ""
  echo "[*] Honcho servisleri (FastAPI, Celery, Next.js) durduruluyor..."

  # ÖNEMLİ:
  # Kullanıcı hangi tmux panelinde olursa olsun
  # Ctrl+C doğrudan SOL PANELDEKİ Honcho'ya gönderilir.
  tmux send-keys -t "$SESSION:0.0" C-c

  echo "[*] Servislerin düzgün kapanması bekleniyor..."
  sleep 15


  # --------------------------------------------------------
  # TMUX SESSION'I TAMAMEN KAPAT
  # --------------------------------------------------------

  tmux kill-session -t "$SESSION" 2>/dev/null

  echo "✅ Tmux oturumu ('$SESSION') kapatıldı."

else

  echo ""
  echo "ℹ️ '$SESSION' adında aktif bir tmux oturumu bulunamadı."

fi


# ==========================================================
# DOCKER SERVİSLERİNİ KAPAT
# ==========================================================

echo ""
echo "[*] Docker servisleri (Postgres & Redis) durduruluyor..."

docker compose down


# ==========================================================
# KAPATMA DOĞRULAMASI
# ==========================================================

echo ""
echo "=============================================="
echo "🔍 Kapatma Doğrulaması"
echo "=============================================="


# ----------------------------------------------------------
# DOCKER CONTAINER KONTROLÜ
# ----------------------------------------------------------

STILL_RUNNING=$(docker ps --filter "name=ik-asistan" --format "{{.Names}}")

if [ -z "$STILL_RUNNING" ]; then

  echo "✅ Docker container'ları tamamen kapandı."

else

  echo "⚠️ Hâlâ çalışan container(lar) var:"
  echo "$STILL_RUNNING"

fi


# ----------------------------------------------------------
# FASTAPI PORT KONTROLÜ
# ----------------------------------------------------------

if ss -tln 2>/dev/null | grep -q ':8000 '; then

  echo "⚠️ 8000 portu hâlâ dinleniyor (FastAPI tam kapanmamış olabilir)."

else

  echo "✅ 8000 portu boş (FastAPI kapandı)."

fi


# ----------------------------------------------------------
# NEXT.JS PORT KONTROLÜ
# ----------------------------------------------------------

if ss -tln 2>/dev/null | grep -q ':5300 '; then

  echo "⚠️ 5300 portu hâlâ dinleniyor (Next.js tam kapanmamış olabilir)."

else

  echo "✅ 5300 portu boş (Next.js kapandı)."

fi


# ----------------------------------------------------------
# TMUX KONTROLÜ
# ----------------------------------------------------------

if tmux has-session -t "$SESSION" 2>/dev/null; then

  echo "⚠️ '$SESSION' tmux oturumu hâlâ mevcut."

else

  echo "✅ Tmux oturumu temizlendi."

fi


# ==========================================================
# SON
# ==========================================================

echo ""
echo "=============================================="
echo "🎉 Kapatma işlemi tamamlandı!"
echo "=============================================="