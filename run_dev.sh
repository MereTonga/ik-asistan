#!/bin/bash

PROJECT_DIR=~/projects/ik-asistan
BACKEND_DIR=$PROJECT_DIR/backend
SESSION="ik-dev"

# Maksimum bekleme süresi (saniye)
TIMEOUT=60

cd "$PROJECT_DIR"


# ==========================================================
# RENK / MESAJ YARDIMCILARI
# ==========================================================

print_step() {
  echo ""
  echo "=============================================="
  echo "$1"
  echo "=============================================="
}

wait_for() {
  local description="$1"
  local check_command="$2"
  local timeout="$3"

  echo -n "⏳ $description"

  local elapsed=0

  while ! eval "$check_command" >/dev/null 2>&1; do

    if [ "$elapsed" -ge "$timeout" ]; then
      echo ""
      echo "❌ Zaman aşımı: $description"
      return 1
    fi

    echo -n " "
    sleep 1
    elapsed=$((elapsed + 1))

  done

  echo " ✅"
  return 0
}


# ==========================================================
# 1. DOCKER
# ==========================================================

print_step "🚀 1/4 Docker servisleri başlatılıyor..."

docker compose up -d

if [ $? -ne 0 ]; then
  echo "❌ Docker servisleri başlatılamadı."
  exit 1
fi

echo "✅ Docker container'ları başlatıldı."


# ==========================================================
# 2. POSTGRESQL HAZIRLIK KONTROLÜ
# ==========================================================

echo ""
echo "[*] PostgreSQL bağlantısı bekleniyor..."

wait_for \
  "PostgreSQL hazır." \
  "docker exec ik-asistan-postgres-1 pg_isready -U ik_asistan -d ik_asistan_db" \
  "$TIMEOUT"

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ PostgreSQL hazır değil."
  echo ""
  echo "Detaylı bilgi için:"
  echo "  docker logs ik-asistan-postgres-1"
  exit 1
fi


# ==========================================================
# 3. REDIS HAZIRLIK KONTROLÜ
# ==========================================================

echo ""
echo "[*] Redis bağlantısı bekleniyor..."

# Redis container adını bul
REDIS_CONTAINER=$(docker ps \
  --filter "name=ik-asistan-redis" \
  --format "{{.Names}}" \
  | head -n 1)

if [ -z "$REDIS_CONTAINER" ]; then
  echo "❌ Redis container'ı bulunamadı."
  echo ""
  echo "Çalışan container'ları kontrol etmek için:"
  echo "  docker ps"
  exit 1
fi

wait_for \
  "Redis hazır." \
  "docker exec $REDIS_CONTAINER redis-cli ping | grep -q PONG" \
  "$TIMEOUT"

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Redis hazır değil."
  echo ""
  echo "Detaylı bilgi için:"
  echo "  docker logs $REDIS_CONTAINER"
  exit 1
fi


# ==========================================================
# TMUX SESSION
# ==========================================================

print_step "🚀 2/4 Honcho + Tmux ortamı hazırlanıyor..."

if ! tmux has-session -t "$SESSION" 2>/dev/null; then

  # --------------------------------------------------------
  # PANEL 0 - SOL
  # HONCHO
  # --------------------------------------------------------

  tmux new-session -d \
    -s "$SESSION" \
    -c "$PROJECT_DIR" \
    "source .venv/bin/activate && honcho start -f Procfile.dev"

  # İlk panelin ID'sini al
  HONCHO_PANE=$(tmux display-message \
    -p \
    -t "$SESSION" \
    '#{pane_id}')


  # --------------------------------------------------------
  # PANEL 1 - SAĞ TARAF
  # --------------------------------------------------------

  POSTGRES_PANE=$(tmux split-window \
    -h \
    -t "$HONCHO_PANE" \
    -c "$PROJECT_DIR" \
    -P \
    -F '#{pane_id}')


  # --------------------------------------------------------
  # PANEL 2 - SAĞ ALT
  # --------------------------------------------------------

  TERMINAL_PANE=$(tmux split-window \
    -v \
    -t "$POSTGRES_PANE" \
    -c "$PROJECT_DIR" \
    -P \
    -F '#{pane_id}')


  # --------------------------------------------------------
  # POSTGRESQL PANELİ
  # --------------------------------------------------------

  tmux send-keys \
    -t "$POSTGRES_PANE" \
    "clear; echo '================================'; echo '🐘 PostgreSQL'; echo '================================'; echo ''; docker exec -it ik-asistan-postgres-1 psql -U ik_asistan -d ik_asistan_db" \
    C-m


  # --------------------------------------------------------
  # UBUNTU TERMINAL PANELİ
  # --------------------------------------------------------

  tmux send-keys \
    -t "$TERMINAL_PANE" \
    "clear; echo '================================'; echo '🖥️  Ubuntu Terminal'; echo '================================'; echo ''; echo 'FastAPI link: http://localhost:8000/docs'; echo 'Next.js link: http://localhost:5300'; echo '';echo ''" \
    C-m


  # --------------------------------------------------------
  # TMUX AYARLARI
  # --------------------------------------------------------

  # Mouse desteği
  # tmux set-option -t "$SESSION" mouse on

  # Panel başlıklarını göster
  tmux set-option -t "$SESSION" pane-border-status top

  # Panel isimleri
  tmux select-pane -t "$HONCHO_PANE" -T "HONCHO LOGS"
  tmux select-pane -t "$POSTGRES_PANE" -T "PostgreSQL"
  tmux select-pane -t "$TERMINAL_PANE" -T "Ubuntu Terminal"

  # Başlangıçta Honcho paneli aktif olsun
  tmux select-pane -t "$HONCHO_PANE"

  echo ""
  echo "✅ Honcho paneli oluşturuldu."
  echo "✅ PostgreSQL paneli oluşturuldu."
  echo "✅ Ubuntu terminal paneli oluşturuldu."

else

  echo "ℹ️ '$SESSION' oturumu zaten çalışıyor."

fi


# ==========================================================
# UYGULAMA SERVİSLERİNİ BEKLE
# ==========================================================

echo ""
echo "[*] Uygulama servislerinin hazır olması bekleniyor..."


# ----------------------------------------------------------
# FASTAPI :8000
# ----------------------------------------------------------

wait_for \
  "FastAPI :8000 hazır." \
  "curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000 | grep -Eq '^[1-4][0-9][0-9]$'" \
  "$TIMEOUT"

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ FastAPI zamanında hazır olmadı."
  echo ""
  echo "Honcho loglarını görmek için:"
  echo "  tmux attach -t $SESSION"
  exit 1
fi


# ----------------------------------------------------------
# NEXT.JS :5300
# ----------------------------------------------------------

wait_for \
  "Next.js :5300 hazır." \
  "curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:5300 | grep -Eq '^[1-4][0-9][0-9]$'" \
  "$TIMEOUT"

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Next.js zamanında hazır olmadı."
  echo ""
  echo "Honcho loglarını görmek için:"
  echo "  tmux attach -t $SESSION"
  exit 1
fi


# ----------------------------------------------------------
# CELERY WORKER
# ----------------------------------------------------------

wait_for \
  "Celery Worker hazır." \
  "cd '$BACKEND_DIR' && ../.venv/bin/python -c \"from app.celery_app import celery_app; raise SystemExit(0 if celery_app.control.inspect(timeout=1.0).ping() else 1)\"" \
  "$TIMEOUT"

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Celery Worker zamanında hazır olmadı."
  echo ""
  echo "Honcho loglarını görmek için:"
  echo "  tmux attach -t $SESSION"
  exit 1
fi


# ==========================================================
# 3. SAĞLIK KONTROLÜ
# ==========================================================

print_step "🔍 3/4 Sağlık & Bağlantı Kontrolleri Yapılıyor"

cd "$BACKEND_DIR"

source ../.venv/bin/activate

python scripts/check_connections.py
CHECK_STATUS=$?


# ==========================================================
# 4. SONUÇ
# ==========================================================

echo ""

if [ $CHECK_STATUS -eq 0 ]; then

  print_step "🎉 4/4 Her şey hazır!"

  echo ""
  echo "🖥️  Tmux ekranına bağlanılıyor..."
  echo ""
  echo "┌──────────────────────────────────────────────┐"
  echo "│ Ctrl+B → o       : Panel değiştir            │"
  echo "│ Ctrl+B → ←/→     : Sol / sağ panel           │"
  echo "│ Ctrl+B → ↑/↓     : Üst / alt panel           │"
  echo "│ Ctrl+B → d       : Tmux'tan ayrıl            │"
  echo "│ Mouse             : Panel seç / boyutlandır  │"
  echo "└──────────────────────────────────────────────┘"
  echo ""

  sleep 2

  tmux attach-session -t "$SESSION"

else

  echo "=============================================="
  echo "⚠️ Sağlık kontrolünde hata oluştu!"
  echo "=============================================="

  echo ""
  echo "Detaylı logları görmek için:"
  echo ""
  echo "  tmux attach -t $SESSION"
  echo ""

fi