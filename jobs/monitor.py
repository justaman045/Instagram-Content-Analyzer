# jobs/monitor.py

import os
import time
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from dateutil.parser import isoparse

from instagram.fetch import fetch_reels
from db.supabase_client import supabase

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("monitor")

# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
for lib in ["httpx", "httpcore", "postgrest", "supabase", "urllib3"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

# ==========================
# CONFIG
# ==========================
DEV_MODE = os.getenv("ENV", "dev") != "prod"

SNAPSHOT_RETENTION = 6
MIN_VIEWS_PER_HOUR = 5

# Snapshot rules
MIN_VIEW_DELTA = 20
MAX_SNAPSHOT_INTERVAL_HOURS = 6

# 🔥 Pruning rules
MAX_INACTIVE_DAYS = 2
MAX_REEL_AGE_DAYS = 5
MIN_TOTAL_VIEWS = 100

FETCH_SLEEP_RANGE = (1.5, 3.0) if DEV_MODE else (6.0, 10.0)

# ==========================
# TIME HELPERS
# ==========================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_ts(ts: str) -> datetime:
    dt = isoparse(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

# ==========================
# USERNAME NORMALIZATION
# ==========================
def normalize_usernames(rows: List[dict]) -> List[str]:
    seen, result = set(), []
    for row in rows:
        for part in row.get("ig_username", "").split(","):
            u = part.strip().lstrip("@")
            if u and u not in seen:
                seen.add(u)
                result.append(u)
    return result

# ==========================
# SNAPSHOT HELPERS
# ==========================
def get_snapshots(project_id: str, reel_url: str, limit=2):
    return (
        supabase.table("reel_snapshots")
        .select("views, likes, comments, captured_at")
        .eq("project_id", project_id)
        .eq("reel_url", reel_url)
        .order("captured_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

def should_insert_snapshot(project_id: str, reel_url: str, reel: Dict) -> bool:
    snaps = get_snapshots(project_id, reel_url, limit=1)

    if not snaps:
        return True

    last = snaps[0]
    mins_since = (now_utc() - parse_ts(last["captured_at"])).total_seconds() / 60

    dv = reel["views"] - last["views"]
    dl = reel["likes"] - last["likes"]
    dc = reel["comments"] - last["comments"]

    if dv >= MIN_VIEW_DELTA or dl > 0 or dc > 0:
        return True

    if mins_since >= MAX_SNAPSHOT_INTERVAL_HOURS * 60:
        return True

    return False

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

    if len(rows) > SNAPSHOT_RETENTION:
        ids = [r["id"] for r in rows[SNAPSHOT_RETENTION:]]
        supabase.table("reel_snapshots").delete().in_("id", ids).execute()

# ==========================
# 🔥 PRUNING LOGIC (FIX)
# ==========================
def should_prune_reel(project_id: str, reel: dict) -> bool:
    reel_url = reel["reel_url"]

    snaps = get_snapshots(project_id, reel_url, limit=2)

    # Rule A — inactive for too long
    last_seen = parse_ts(reel["last_seen_at"])
    if now_utc() - last_seen > timedelta(days=MAX_INACTIVE_DAYS):
        log.info("🧹 Prune: inactive too long")
        return True

    # Rule B — low growth rate
    if len(snaps) >= 2:
        cur, prev = snaps
        hours = max(
            (parse_ts(cur["captured_at"]) - parse_ts(prev["captured_at"]))
            .total_seconds() / 3600,
            0.1,
        )
        vph = (cur["views"] - prev["views"]) / hours
        if vph < MIN_VIEWS_PER_HOUR:
            log.info("🧹 Prune: low growth rate")
            return True

    # Rule C — old + low total views
    age_days = (now_utc() - parse_ts(reel["last_seen_at"])).days
    if age_days >= MAX_REEL_AGE_DAYS and reel["views"] < MIN_TOTAL_VIEWS:
        log.info("🧹 Prune: old & underperforming")
        return True

    return False

# ==========================
# MAIN JOB
# ==========================
def run_monitor(project_id: Optional[str] = None):
    log.info("🛰️ Monitor job started")

    query = supabase.table("projects").select("*")
    query = query.eq("id", project_id) if project_id else query.eq("active", True)
    projects = query.execute().data or []

    total_reels = total_snaps = total_pruned = 0

    for project in projects:
        pid = project["id"]
        log.info(f"📁 Project: {project['name']}")

        rows = (
            supabase.table("monitored_accounts")
            .select("ig_username")
            .eq("project_id", pid)
            .execute()
            .data or []
        )

        usernames = normalize_usernames(rows)
        if not usernames:
            continue

        for username in usernames:
            try:
                log.info(f"🔍 Fetching {username}")
                reels = fetch_reels(username)
            except Exception:
                log.exception(f"Fetch failed @{username}")
                continue

            for reel in reels:
                now = now_utc().isoformat()
                reel_url = reel["url"]

                supabase.table("reels").upsert(
                    {
                        "project_id": pid,
                        "reel_url": reel_url,
                        "views": reel["views"],
                        "likes": reel["likes"],
                        "comments": reel["comments"],
                        "last_seen_at": now,
                    },
                    on_conflict="project_id,reel_url",
                ).execute()

                total_reels += 1

                if should_insert_snapshot(pid, reel_url, reel):
                    supabase.table("reel_snapshots").insert(
                        {
                            "project_id": pid,
                            "reel_url": reel_url,
                            "views": reel["views"],
                            "likes": reel["likes"],
                            "comments": reel["comments"],
                            "caption": reel["caption"],
                            "captured_at": now,
                        }
                    ).execute()
                    total_snaps += 1

                trim_snapshots(pid, reel_url)

            time.sleep(random.uniform(*FETCH_SLEEP_RANGE))

        # 🔥 FINAL PRUNE PASS (important!)
        all_reels = (
            supabase.table("reels")
            .select("*")
            .eq("project_id", pid)
            .execute()
            .data or []
        )

        for r in all_reels:
            if should_prune_reel(pid, r):
                supabase.table("reel_snapshots").delete() \
                    .eq("project_id", pid).eq("reel_url", r["reel_url"]).execute()

                supabase.table("reels").delete() \
                    .eq("project_id", pid).eq("reel_url", r["reel_url"]).execute()

                total_pruned += 1

    log.info(
        f"✅ Monitor finished | "
        f"Reels: {total_reels}, "
        f"Snapshots: {total_snaps}, "
        f"Pruned: {total_pruned}"
    )
