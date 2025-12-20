import time
import random
import requests
import threading
from instagram.parse import parse_reels_from_json
import logging

# ==========================
# Request Blocking Helpers
# ==========================
_response_blocked = False
_block_lock = threading.Lock()

def is_blocked() -> bool:
    with _block_lock:
        return _response_blocked

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cli")


# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ==========================
# GLOBAL RATE LIMITER
# ==========================
MAX_REQUESTS_PER_HOUR = 150
SECONDS_PER_HOUR = 3600

_request_times = []
_lock = threading.Lock()

def rate_limit():
    with _lock:
        now = time.time()

        # Remove old requests
        while _request_times and now - _request_times[0] > SECONDS_PER_HOUR:
            _request_times.pop(0)

        if len(_request_times) >= MAX_REQUESTS_PER_HOUR:
            sleep_for = SECONDS_PER_HOUR - (now - _request_times[0]) + random.uniform(5, 15)
            log.info(f"⏳ Rate limit reached, sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)

        _request_times.append(time.time())


# ==========================
# SESSION
# ==========================
SESSION = requests.Session()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/119.0.0.0 Mobile Safari/537.36 "
        "Instagram 312.0.0.33.111 Android"
    ),
    "Accept": "application/json",
    "X-IG-App-ID": "936619743392459",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ==========================
# FETCH
# ==========================
def fetch_reels(username: str):
    global _response_blocked

    # 🚫 If already blocked, do NOTHING
    with _block_lock:
        if _response_blocked:
            return None  # important: None means "skipped"

    rate_limit()
    time.sleep(random.uniform(1.2, 3.8))

    url = (
        "https://www.instagram.com/api/v1/users/"
        f"web_profile_info/?username={username}"
    )

    try:
        res = SESSION.get(url, headers=HEADERS, timeout=10)
    except requests.RequestException:
        log.warning(f"⚠️ Network error @{username}")
        return []

    # 🚨 FIRST HARD BLOCK
    if res.status_code in (401, 403, 429):
        with _block_lock:
            _response_blocked = True

        log.error(
            f"🚫 BLOCKED by Instagram ({res.status_code}) "
            f"@{username} — future requests will be skipped"
        )
        return None

    if res.status_code != 200:
        log.warning(f"⚠️ Failed @{username} ({res.status_code})")
        return []

    try:
        data = res.json()
    except Exception:
        log.warning("⚠️ Invalid JSON — possible soft block")
        return []

    return parse_reels_from_json(data)
