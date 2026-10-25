import os
import threading
import time

import cv2
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COOLDOWN = 30  # minimum seconds between alerts, so you are not spammed

_last_sent = 0


def _post(jpg_bytes, caption):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": ("alert.jpg", jpg_bytes, "image/jpeg")},
            timeout=15,
        )
        if not resp.ok:
            print("Telegram error:", resp.status_code, resp.text)
    except Exception as e:
        print("Telegram error:", e)


def send_alert(frame, caption):
    """Send a photo with a caption without freezing the detector."""
    global _last_sent
    if not TOKEN or not CHAT_ID:
        print("Telegram not configured: check detector/.env")
        return False
    now = time.time()
    if now - _last_sent < COOLDOWN:
        return False
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        return False
    _last_sent = now
    threading.Thread(target=_post, args=(buf.tobytes(), caption), daemon=True).start()
    return True