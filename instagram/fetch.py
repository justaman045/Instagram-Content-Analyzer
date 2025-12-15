import requests
from instagram.parse import parse_reels_from_json

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "X-IG-App-ID": "936619743392459"  # public web app id
}

def fetch_reels(username: str):
    url = (
        "https://www.instagram.com/api/v1/users/"
        f"web_profile_info/?username={username}"
    )

    res = requests.get(url, headers=HEADERS, timeout=10)

    if res.status_code != 200:
        print(f"⚠️ Failed to fetch @{username} ({res.status_code})")
        return []

    try:
        data = res.json()
    except Exception:
        print("⚠️ Invalid JSON response")
        return []

    return parse_reels_from_json(data)
