# jobs/deliver.py

from datetime import datetime, timezone
from typing import Optional
import os
import logging
import pytz

from rich import print

from db.supabase_client import supabase
from tgram.send import send_message

# ==========================
# CONFIG
# ==========================
DEV_MODE = False  # set True only for local testing

# ==========================
# LOGGING
# ==========================
log = logging.getLogger("deliver")

# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ==========================
# TIME HELPERS
# ==========================
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_delivery_due(settings: dict) -> bool:
    """
    Delivery is allowed if current local time is AFTER send_hour.
    Safe even if scheduler runs late.
    """
    tz = pytz.timezone(settings["timezone"])
    now_local = utc_now().astimezone(tz)

    delivery_time = now_local.replace(
        hour=settings["send_hour"],
        minute=0,
        second=0,
        microsecond=0,
    )

    return now_local >= delivery_time


def already_sent_today(project_id: str) -> bool:
    """
    Prevent duplicate deliveries per UTC day.
    """
    start_of_today = utc_now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    rows = (
        supabase
        .table("sent_reels")
        .select("id")
        .eq("project_id", project_id)
        .gte("sent_at", start_of_today)
        .limit(1)
        .execute()
        .data
    )

    return bool(rows)


def fetch_latest_caption(project_id: str, reel_url: str) -> str:
    """
    Fetch caption from latest reel snapshot.
    """
    snap = (
        supabase
        .table("reel_snapshots")
        .select("caption")
        .eq("project_id", project_id)
        .eq("reel_url", reel_url)
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if snap and snap[0].get("caption"):
        return snap[0]["caption"].strip()

    return ""


# ==========================
# MAIN JOB
# ==========================
def run_deliver(project_id: Optional[str] = None) -> int:
    """
    Delivers ONE recommended reel per project per day.
    Returns number of reels delivered.
    """
    delivered_count = 0

    # -------------------------
    # Resolve projects
    # -------------------------
    query = supabase.table("projects").select("*")

    if project_id:
        query = query.eq("id", project_id)
    else:
        query = query.eq("active", True)

    projects = query.execute().data or []

    if not projects:
        log.warning("No projects found for delivery")
        return 0

    # -------------------------
    # Process projects
    # -------------------------
    for project in projects:
        pid = project["id"]
        uid = project["user_id"]

        log.info(f"📦 Delivery check → {project['name']}")

        # -------------------------
        # Delivery settings
        # -------------------------
        settings = (
            supabase
            .table("delivery_settings")
            .select("*")
            .eq("project_id", pid)
            .single()
            .execute()
            .data
        )

        if not settings:
            log.warning("No delivery settings")
            continue

        # -------------------------
        # Telegram config
        # -------------------------
        telegram = (
            supabase
            .table("telegram_accounts")
            .select("chat_id")
            .eq("user_id", uid)
            .single()
            .execute()
            .data
        )

        if not telegram:
            log.warning("Telegram not configured")
            continue

        # -------------------------
        # Time gate
        # -------------------------
        if not DEV_MODE:
            if not is_delivery_due(settings):
                log.info("⏳ Delivery time not reached")
                continue

            if already_sent_today(pid):
                log.info("📭 Already delivered today")
                continue
        else:
            log.warning("⚠ DEV MODE: bypassing time checks")

        # -------------------------
        # Recommended reel
        # -------------------------
        reel = (
            supabase
            .table("reels")
            .select("*")
            .eq("project_id", pid)
            .eq("is_recommended", True)
            .limit(1)
            .execute()
            .data
        )

        if not reel:
            log.info("No recommended reel")
            continue

        reel = reel[0]

        # -------------------------
        # Fetch caption from snapshot
        # -------------------------
        caption = fetch_latest_caption(pid, reel["reel_url"])

        caption_block = f"\n\n📝 <b>Caption</b>\n{caption}" if caption else ""

        # -------------------------
        # Send message
        # -------------------------
        message = (
            "<b>🔥 Trending Reel</b>\n\n"
            f"{reel['reel_url']}\n"
            f"👁 {reel['views']} | ❤️ {reel['likes']} | 💬 {reel['comments']}\n"
            f"📈 {reel['trend']}"
            f"{caption_block}"
        )

        send_message(
            os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram["chat_id"],
            message,
        )

        # -------------------------
        # Record delivery
        # -------------------------
        supabase.table("sent_reels").insert(
            {
                "project_id": pid,
                "reel_url": reel["reel_url"],
                "sent_at": utc_now().isoformat(),
            }
        ).execute()

        delivered_count += 1
        print(f"[green]✅ Delivered[/green] {reel['reel_url']}")

    return delivered_count
