git clone https://github.com/Yoursliebert/cysic-log-watcher.git
cd cysic-log-watcher
cp .env.example .env   # isi TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_FILES
chmod +x install.sh
./install.sh




supervisorctl status log-watcher
supervisorctl tail -f log-watcher
