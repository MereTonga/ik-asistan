#!/bin/bash
# Docker modunda canli izleme paneli: eski Honcho/tmux panelinin (run_dev.sh) compose karsiligi.
#   bash docker_panel.sh        -> tmux oturumu acar / varsa ona baglanir
#   Ctrl+B, D                   -> oturumdan ayril (loglar akmaya devam eder)
#   tmux kill-session -t ik-docker -> paneli kapat (container'lara dokunmaz)
#
# Paneller: sol = worker + beat (RAG, OCR, e-posta isleme), sag ust = api + frontend, sag alt = psql.

SESSION="ik-docker"
cd "$(dirname "$0")" || exit 1

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux attach -t "$SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -n izleme "docker compose logs -f --tail=100 worker beat"
WORKER_PANE=$(tmux display-message -p -t "$SESSION" '#{pane_id}')

API_PANE=$(tmux split-window -h -t "$WORKER_PANE" -P -F '#{pane_id}' "docker compose logs -f --tail=50 api frontend")
PSQL_PANE=$(tmux split-window -v -t "$API_PANE" -P -F '#{pane_id}' "docker compose exec postgres psql -U ik_asistan -d ik_asistan_db")

tmux set-option -t "$SESSION" pane-border-status top
tmux select-pane -t "$WORKER_PANE" -T "worker + beat (RAG / OCR / e-posta)"
tmux select-pane -t "$API_PANE" -T "api + frontend"
tmux select-pane -t "$PSQL_PANE" -T "PostgreSQL (psql)"
tmux select-pane -t "$WORKER_PANE"

tmux attach -t "$SESSION"
