# jobs/monitor.py

import time
import random
from datetime import datetime, timezone
from typing import List

from rich.console import Console
from dateutil.parser import isoparse  # 🔥 FIX

from instagram.fetch import fetch_reels
from db.supabase_client import supabase

console = Console()

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ======================================================
# CONFIG — FREE TIER SAFE
# ======================================================

DEV_MODE = True               # False in production
SNAPSHOT_RETENTION = 6        # max snapshots per reel
MIN_VIEWS_TO_KEEP = 10
MIN_VIEWS_PER_HOUR = 5

MIN_SNAPSHOT_INTERVAL_MIN = 90   # 🔥 CRITICAL
MIN_VIEW_DELTA = 20

DEV_SLEEP_RANGE = (1.5, 3.0)
PROD_SLEEP_RANGE = (8.0, 14.0)

# ======================================================
# TIME HELPERS (BULLETPROOF)
# ======================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    return now_utc().isoformat()


def parse_ts(ts: str) -> datetime:
    """
    Fully ISO-8601 compliant timestamp parser.
    Handles all Supabase formats safely.
    """
    dt = isoparse(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def safe_sleep():
    low, high = DEV_SLEEP_RANGE if DEV_MODE else PROD_SLEEP_RANGE
    time.sleep(random.uniform(low, high))


# ======================================================
# USERNAME NORMALIZATION
# ======================================================

def normalize_usernames(rows: List[dict]) -> List[str]:
    usernames = []
    for row in rows:
        raw = row.get("ig_username", "")
        for part in raw.split(","):
            u = part.strip().lstrip("@")
            if u:
                usernames.append(u)
    return list(dict.fromkeys(usernames))


# ======================================================
# SNAPSHOT RULES (🔥 STORAGE SAVER)
# ======================================================

def should_insert_snapshot(project_id: str, reel_url: str, reel: dict) -> bool:
    last = (
        supabase.table("reel_snapshots")
        .select("views, likes, comments, captured_at")
        .eq("project_id", project_id)
        .eq("reel_url", reel_url)
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    if not last:
        return True  # first snapshot

    last = last[0]

    mins_since = (
        now_utc() - parse_ts(last["captured_at"])
    ).total_seconds() / 60

    if mins_since < MIN_SNAPSHOT_INTERVAL_MIN:
        return False

    dv = reel["views"] - last["views"]
    dl = reel["likes"] - last["likes"]
    dc = reel["comments"] - last["comments"]

    return dv >= MIN_VIEW_DELTA or dl > 0 or dc > 0


# ======================================================
# SNAPSHOT MAINTENANCE
# ======================================================

def trim_snapshots(project_id: str, reel_url: str):
    rows = (
        supabase.table("reel_snapshots")
        .select("id")
        .eq("project_id", project_id)
        .eq("reel_url", reel_url)
        .order("captured_at", desc=True)
        .execute()
        .data or []
    )

    if len(rows) <= SNAPSHOT_RETENTION:
        return

    old_ids = [r["id"] for r in rows[SNAPSHOT_RETENTION:]]
    supabase.table("reel_snapshots").delete().in_("id", old_ids).execute()


def reel_is_dead(project_id: str, reel_url: str) -> bool:
    snaps = (
        supabase.table("reel_snapshots")
        .select("views, captured_at")
        .eq("project_id", project_id)
        .eq("reel_url", reel_url)
        .order("captured_at", desc=True)
        .limit(2)
        .execute()
        .data or []
    )

    if len(snaps) < 2:
        return False

    cur, prev = snaps[0], snaps[1]

    hours = max(
        (parse_ts(cur["captured_at"]) - parse_ts(prev["captured_at"]))
        .total_seconds() / 3600,
        0.01,
    )

    vph = (cur["views"] - prev["views"]) / hours

    return cur["views"] < MIN_VIEWS_TO_KEEP and vph < MIN_VIEWS_PER_HOUR


# ======================================================
# MAIN JOB
# ======================================================

def run_monitor():
    console.print("\n[bold cyan]🛰️ Monitor Job Started[/bold cyan]\n")

    projects = supabase.table("projects").select("*").execute().data or []

    total_reels = 0
    total_snapshots = 0
    total_pruned = 0

    for project in projects:
        project_id = project["id"]
        console.print(f"[yellow]📁 Project:[/yellow] {project['name']}")

        rows = (
            supabase.table("monitored_accounts")
            .select("ig_username")
            .eq("project_id", project_id)
            .execute()
            .data or []
        )

        usernames = normalize_usernames(rows)

        if not usernames:
            console.print("[dim]No monitored accounts[/dim]")
            continue

        for username in usernames:
            log(f"🔍 Fetching @{username}")

            try:
                reels = fetch_reels(username)
            except Exception as e:
                console.print(f"[red]❌ Fetch failed @{username}: {e}[/red]")
                continue

            for reel in reels:
                reel_url = reel["url"]
                now = now_utc_iso()

                # 🔥 AUTHORITATIVE STATE
                supabase.table("reels").upsert(
                    {
                        "project_id": project_id,
                        "reel_url": reel_url,
                        "views": reel["views"],
                        "likes": reel["likes"],
                        "comments": reel["comments"],
                        "last_seen_at": now,
                    },
                    on_conflict="project_id,reel_url",
                ).execute()

                total_reels += 1

                # 🔥 SNAPSHOT (SMART)
                if should_insert_snapshot(project_id, reel_url, reel):
                    supabase.table("reel_snapshots").insert(
                        {
                            "project_id": project_id,
                            "reel_url": reel_url,
                            "views": reel["views"],
                            "likes": reel["likes"],
                            "comments": reel["comments"],
                            "captured_at": now,
                        }
                    ).execute()
                    total_snapshots += 1

                trim_snapshots(project_id, reel_url)

                if reel_is_dead(project_id, reel_url):
                    console.print("[dim red]🧹 Removing dead reel[/dim red]")
                    supabase.table("reel_snapshots").delete() \
                        .eq("project_id", project_id) \
                        .eq("reel_url", reel_url) \
                        .execute()

                    supabase.table("reels").delete() \
                        .eq("project_id", project_id) \
                        .eq("reel_url", reel_url) \
                        .execute()

                    total_pruned += 1

            safe_sleep()

    log(
        f"""
[bold green]✅ Monitor Completed[/bold green]
• Reels updated     : {total_reels}
• Snapshots written : {total_snapshots}
• Reels pruned      : {total_pruned}
"""
    )
