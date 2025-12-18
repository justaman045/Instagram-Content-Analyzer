import requests
from instagram.parse import parse_reels_from_json

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 9; GM1903 Build/PKQ1.190110.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/75.0.3770.143 Mobile Safari/537.36 Instagram 103.1.0.15.119 Android (28/9; 420dpi; 1080x2260; OnePlus; GM1903; OnePlus7; qcom; sv_SE; 164094539)",
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
        print(res.content)
        return []

    try:
        data = res.json()
    except Exception:
        print("⚠️ Invalid JSON response")
        return []

    return parse_reels_from_json(data)
