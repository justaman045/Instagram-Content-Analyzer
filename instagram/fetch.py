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

# ==========================
# USER AGENT ROTATION
# ==========================
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Build/SD1A.210817.036; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/94.0.4606.71 Mobile Safari/537.36",
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "X-IG-App-ID": "936619743392459",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

HEADERS = get_headers()

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

    # Rotate headers per request for better stealth
    headers = get_headers()

    try:
        # Use a fresh session or the global one? 
        # For rotation to work effectively with keep-alive, we might want requests.get 
        # but SESSION reuses connection pool which is faster. 
        # Let's clean header update.
        SESSION.headers.update(headers)
        res = SESSION.get(url, timeout=10)
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
