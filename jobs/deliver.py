# jobs/deliver.py

from datetime import datetime, timezone
import pytz, os
from rich import print

from db.supabase_client import supabase
from telegram.send import send_message

DEV_MODE = False
DELIVERY_WINDOW_MIN = 5


def utc_now():
    return datetime.now(timezone.utc)


def already_sent_today(project_id: str) -> bool:
    today = utc_now().date().isoformat()
    rows = (
        supabase
        .table("sent_reels")
        .select("id")
        .eq("project_id", project_id)
        .gte("sent_at", today)
        .execute()
        .data
    )
    return bool(rows)


def run_deliver():
    # print("\n[bold cyan]🚀 Deliver Job Started[/bold cyan]\n")

    projects = supabase.table("projects").select("*").execute().data or []

    for project in projects:
        pid = project["id"]
        uid = project["user_id"]

        # print(f"[yellow]📁 Project:[/yellow] {project['name']}")

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
            print("[dim]No delivery settings[/dim]")
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
            print("[red]Telegram not configured[/red]")
            continue

        # =============================
        # TIME GATE (PRODUCTION)
        # =============================
        if not DEV_MODE:
            # tz = pytz.timezone(settings["timezone"])
            now_local = utc_now()

            target_minutes = settings["send_hour"] * 60
            now_minutes = now_local.hour * 60 + now_local.minute

            if abs(now_minutes - target_minutes) > DELIVERY_WINDOW_MIN:
                print("[dim]⏳ Outside delivery window[/dim]")
                continue

            if already_sent_today(pid):
                print("[dim]Already sent today[/dim]")
                continue
        else:
            print("[bold yellow]⚠ DEV MODE: Bypassing time check[/bold yellow]")

        # =============================
        # PICK ANALYZER-APPROVED REEL
        # =============================
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
            print("[dim]No recommended reel[/dim]")
            continue

        reel = reel[0]

        message = (
            f"<b>🔥 Trending Reel</b>\n\n"
            f"{reel['reel_url']}\n\n"
            f"👁 {reel['views']} | ❤️ {reel['likes']} | 💬 {reel['comments']}\n"
            f"📈 {reel['trend']}"
        )

        send_message(
            os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram["chat_id"],
            message
        )

        supabase.table("sent_reels").insert({
            "project_id": pid,
            "reel_url": reel["reel_url"],
            "sent_at": utc_now().isoformat()
        }).execute()

        print(f"[green]✅ Delivered[/green] {reel['reel_url']}")

    # print("\n[bold green]🎉 Deliver job completed[/bold green]")
