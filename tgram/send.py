# telegram/send.py
import requests

def send_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
