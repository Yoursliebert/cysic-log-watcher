```
git clone https://github.com/<username>/cysic-log-watcher.git
cd cysic-log-watcher
```

```
chmod +x install.sh
./install.sh
```
```
cd /opt/log_watcher
./bot.py
```
```
supervisorctl reread
supervisorctl update
supervisorctl restart log-watcher
```
```
supervisorctl status log-watcher
supervisorctl tail -f log-watcher
```
