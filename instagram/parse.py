def parse_reels_from_json(data: dict):
    reels = []

    try:
        edges = (
            data["data"]["user"]
            ["edge_owner_to_timeline_media"]["edges"]
        )
    except KeyError:
        return []

    for edge in edges:
        node = edge["node"]

        if not node.get("is_video"):
            continue

        # --- Engagement extraction (safe & realistic) ---
        play_count = node.get("play_count")
        video_views = node.get("video_view_count")
        like_count = node.get("edge_liked_by", {}).get("count", 0)
        comment_count = node.get("edge_media_to_comment", {}).get("count", 0)

        # Decide best metric
        views = (
            play_count
            or video_views
            or like_count  # fallback (VERY IMPORTANT)
        )

        reels.append({
            "url": f'https://www.instagram.com/reel/{node["shortcode"]}/',
            "views": views,
            "likes": like_count,
            "comments": comment_count,
            "caption": (
                node["edge_media_to_caption"]["edges"][0]["node"]["text"]
                if node["edge_media_to_caption"]["edges"]
                else ""
            )
        })

    return reels[:5]  # hard cap
