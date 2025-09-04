#!/usr/bin/env python3
"""
bot.py - Log Watcher -> Telegram

Fitur:
- Startup: kirim 'online' + 1 baris terakhir log.
- Trigger A (KEYWORDS): contoh 'start prepare task: <angka>' → kirim pesan dengan judul '*Received Task*'
  lalu BLACKOUT selama BLACKOUT_SECONDS.
- Trigger B (RAW_ONLY_PATTERNS): contoh 'submit taskData ...' / 'process submitProofData finish'
  → forward baris mentah TANPA judul dan TANPA blackout.
- Token & Chat ID: bisa diambil dari env, atau jika kosong diminta input lalu disimpan ke /opt/log_watcher/.env

Env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  LOG_FILES
  KEYWORDS
  RAW_ONLY_PATTERNS
  BLACKOUT_SECONDS
"""

import os, re, sys, time, signal, atexit, logging, selectors, subprocess
import urllib.parse, urllib.request
from pathlib import Path

# === Load/save env file ===
ENV_FILE = Path("/opt/log_watcher/.env")

def load_env_file():
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v.strip('"'))

def ensure_token_chat():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(">> Konfigurasi Telegram belum ada, masukkan sekarang.")
        token = input("Masukkan TELEGRAM_BOT_TOKEN: ").strip()
        chat_id = input("Masukkan TELEGRAM_CHAT_ID: ").strip()
        with open(ENV_FILE, "w") as f:
            f.write(f'TELEGRAM_BOT_TOKEN="{token}"\n')
            f.write(f'TELEGRAM_CHAT_ID="{chat_id}"\n')
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        print(f"[+] Token & Chat ID disimpan ke {ENV_FILE}")

# === Inisialisasi ===
load_env_file()
ensure_token_chat()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
LOG_FILES = [p.strip() for p in os.getenv("LOG_FILES", "").split(",") if p.strip()]

DEFAULT_KEYWORDS = r"re:start prepare task:\s*\d+"
KEYWORDS  = [p.strip() for p in os.getenv("KEYWORDS", DEFAULT_KEYWORDS).split(",") if p.strip()]

DEFAULT_RAW_ONLY = ",".join([
    r"re:submit\s+taskData,\s*task:\s*\d+.*",
    r"re:task:\s*\d+\s+process\s+submitProofData\s+finish"
])
RAW_ONLY_PATTERNS = [p.strip() for p in os.getenv("RAW_ONLY_PATTERNS", DEFAULT_RAW_ONLY).split(",") if p.strip()]

BLACKOUT_SECONDS = int(os.getenv("BLACKOUT_SECONDS", "300"))

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Error: TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID wajib di-set.")
    sys.exit(1)
if not LOG_FILES:
    print("Error: LOG_FILES wajib di-set.")
    sys.exit(1)

# === Compile regex ===
def compile_list(patterns):
    out = []
    for it in patterns:
        if it.lower().startswith("re:"):
            out.append(re.compile(it[3:], re.IGNORECASE))
        else:
            out.append(re.compile(re.escape(it), re.IGNORECASE))
    return out

PAT_KEYWORDS = compile_list(KEYWORDS)
PAT_RAW_ONLY = compile_list(RAW_ONLY_PATTERNS)

# === Telegram helper ===
MDV2_ESC = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")
def mdv2_escape(s: str) -> str:
    return MDV2_ESC.sub(r"\\\1", s)

def tg_send(text: str):
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "MarkdownV2", "disable_web_page_preview": True}
    data = urllib.parse.urlencode(payload).encode()
    with urllib.request.urlopen(base, data, timeout=10) as resp:
        if resp.status != 200:
            logging.warning("Telegram status %s", resp.status)

# === Tail setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

sel = selectors.DefaultSelector()
procs = {}
def start_tail(path: str):
    cmd = ["tail", "-n", "0", "-F", path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    procs[path] = proc
    sel.register(proc.stdout, selectors.EVENT_READ, (path, "out"))
    sel.register(proc.stderr, selectors.EVENT_READ, (path, "err"))
    logging.info("Watching %s", path)

def stop_all():
    for p in procs.values():
        try: p.terminate()
        except: pass
    for p in procs.values():
        try: p.wait(timeout=2)
        except: pass
atexit.register(stop_all)

for path in LOG_FILES:
    start_tail(path)

# === Startup notif ===
try:
    tg_send("*Log Watcher is online*\n*Files:* " + mdv2_escape(", ".join(LOG_FILES)))
    try:
        first_log = LOG_FILES[0]
        with open(first_log, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            if lines:
                last_line = lines[-1].strip()
                if last_line:
                    tg_send("*Last log line:*\n" + mdv2_escape(last_line))
    except Exception as e:
        logging.warning("Tidak bisa ambil baris terakhir: %s", e)
except Exception as e:
    logging.error("Startup send failed: %s", e)

# === Main loop ===
RUNNING = True
NEXT_READ_ALLOWED_TS = 0.0

def handle_sig(signum, frame):
    global RUNNING
    RUNNING = False
    logging.info("Shutting down...")
signal.signal(signal.SIGINT, handle_sig)
signal.signal(signal.SIGTERM, handle_sig)

def any_match(line: str, patterns):
    for p in patterns:
        m = p.search(line)
        if m:
            return p, m
    return None, None

def now_ts(): return time.time()

while RUNNING and procs:
    events = sel.select(timeout=1.0)
    in_blackout = now_ts() < NEXT_READ_ALLOWED_TS
    for key, _ in events:
        path, stream = key.data
        line = key.fileobj.readline()
        if not line:
            continue
        line = line.rstrip("\n")

        # RAW_ONLY → forward mentah, tanpa blackout
        p_raw, _ = any_match(line, PAT_RAW_ONLY)
        if p_raw:
            try: tg_send(mdv2_escape(line))
            except Exception as e: logging.error("Send RAW_ONLY failed: %s", e)
            continue

        if in_blackout:
            continue

        # KEYWORDS → "Received Task" + blackout
        p_kw, _ = any_match(line, PAT_KEYWORDS)
        if not p_kw:
            continue

        msg = f"*Received Task*\n{mdv2_escape(line)}"
        try:
            tg_send(msg)
            NEXT_READ_ALLOWED_TS = now_ts() + BLACKOUT_SECONDS
            logging.info("Trigger! Blackout %s detik", BLACKOUT_SECONDS)
        except Exception as e:
            logging.error("Send failed: %s", e)

logging.info("Exited.")
