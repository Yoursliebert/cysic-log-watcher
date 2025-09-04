```
git clone https://github.com/Yoursliebert/cysic-log-watcher.git
cd cysic-log-watcher
cp .env.example .env 
chmod +x install.sh
./install.sh
```


```
supervisorctl status log-watcher
supervisorctl tail -f log-watcher
```
```
 supervisorctl restart log-watcher
```
