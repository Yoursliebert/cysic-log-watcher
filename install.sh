#!/bin/bash
set -euo pipefail

# baca .env kalau ada
if [[ -f .env ]]; then
  echo "[*] Loading .env"
  set -a
  source .env
  set +a
fi

# cek variabel penting
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN belum di-set (lihat .env.example)}"
: "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID belum di-set (lihat .env.example)}"
: "${LOG_FILES:?LOG_FILES belum di-set (path log, bisa koma-separated)}"

# default opsional
KEYWORDS="${KEYWORDS:-re:start prepare task:\s*\d+}"
RAW_ONLY_PATTERNS="${RAW_ONLY_PATTERNS:-re:submit\s+taskData,\s*task:\s*\d+.*,re:task:\s*\d+\s+process\s+submitProofData\s+finish}"
BLACKOUT_SECONDS="${BLACKOUT_SECONDS:-300}"

echo "[*] Installing deps..."
sudo apt update
sudo apt install -y python3 coreutils supervisor

echo "[*] Deploying bot.py..."
sudo mkdir -p /opt/log_watcher
sudo cp bot.py /opt/log_watcher/bot.py
sudo chmod 755 /opt/log_watcher/bot.py

echo "[*] Writing supervisor config..."
sudo mkdir -p /etc/supervisor/conf.d
sudo bash -c "cat > /etc/supervisor/conf.d/log-watcher.conf" <<EOF
[program:log-watcher]
command=/usr/bin/python3 /opt/log_watcher/bot.py
directory=/opt/log_watcher
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/supervisor/log-watcher-out.log
environment=TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}",TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID}",LOG_FILES="${LOG_FILES}",KEYWORDS="${KEYWORDS}",RAW_ONLY_PATTERNS="${RAW_ONLY_PATTERNS}",BLACKOUT_SECONDS="${BLACKOUT_SECONDS}"
EOF

echo "[*] Reloading supervisor..."
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart log-watcher || sudo supervisorctl start log-watcher

echo "[*] Done."
echo "Check status:  supervisorctl status log-watcher"
echo "Tail logs:     supervisorctl tail -f log-watcher"
