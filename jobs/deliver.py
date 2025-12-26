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


def get_last_delivery_attempt(project_id: str) -> Optional[datetime]:
    """
    Returns the last time the delivery job successfully ran for this project.
    """
    row = (
        supabase
        .table("sent_reels")
        .select("sent_at")
        .eq("project_id", project_id)
        .order("sent_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if not row:
        return None

    return datetime.fromisoformat(row[0]["sent_at"])


def is_batch_responsible(settings: dict, last_run: Optional[datetime]) -> bool:
    """
    Send ONLY if this batch is the FIRST batch AFTER scheduled time.

    Rule:
        last_run < scheduled_time <= now
    """
    tz = pytz.timezone(settings["timezone"])
    now_local = utc_now().astimezone(tz)

    scheduled_time = now_local.replace(
        hour=settings["send_hour"],
        minute=settings.get("send_minute", 0),
        second=0,
        microsecond=0,
    )

    if last_run:
        last_run = last_run.astimezone(tz)
    else:
        # First ever run → allow if already past scheduled time
        return now_local >= scheduled_time

    log.info(f"Last run       : {last_run}")
    log.info(f"Scheduled time : {scheduled_time}")
    log.info(f"Now            : {now_local}")

    return last_run < scheduled_time <= now_local


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
    delivered_count = 0

    query = supabase.table("projects").select("*")
    query = query.eq("id", project_id) if project_id else query.eq("active", True)

    projects = query.execute().data or []
    if not projects:
        log.warning("No projects found")
        return 0

    for project in projects:
        pid = project["id"]
        uid = project["user_id"]

        log.info(f"📦 Delivery check → {project['name']}")

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
            continue

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
            continue

        if not DEV_MODE:
            last_run = get_last_delivery_attempt(pid)

            if not is_batch_responsible(settings, last_run):
                log.info("⏭ Batch not responsible for this delivery")
                continue

            if already_sent_today(pid):
                log.info("📭 Already sent today")
                continue

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
            continue

        reel = reel[0]
        caption = fetch_latest_caption(pid, reel["reel_url"])
        caption_block = f"\n\n📝 <b>Caption</b>\n{caption}" if caption else ""

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

        supabase.table("sent_reels").insert(
            {
                "project_id": pid,
                "reel_url": reel["reel_url"],
                "sent_at": utc_now().isoformat(),
            }
        ).execute()

        delivered_count += 1
        log.info(f"✅ Delivered {reel['reel_url']}")

    return delivered_count
