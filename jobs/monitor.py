# jobs/monitor.py

import time
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set

from dateutil.parser import isoparse

from instagram.fetch import fetch_reels
from db.supabase_client import supabase

# ======================================================
# LOGGING
# ======================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("monitor")

# Silence noisy libs
for lib in ("httpx", "httpcore", "postgrest", "supabase", "urllib3"):
    logging.getLogger(lib).setLevel(logging.WARNING)

# ======================================================
# SAFETY LIMITS
# ======================================================
MAX_REQUESTS_PER_HOUR = 120
BATCH_SIZE = 5
BATCH_COOLDOWN_RANGE = (900, 1800)       # 15–30 min
SESSION_COOLDOWN_RANGE = (3600, 7200)    # 1–2 hours
MAX_PROJECT_RUNTIME_MIN = 45

# ======================================================
# SNAPSHOT / PRUNE CONFIG
# ======================================================
SNAPSHOT_RETENTION = 6

MIN_VIEW_DELTA = 20
MIN_VIEWS_PER_HOUR = 5

MAX_INACTIVE_DAYS = 2
MAX_REEL_AGE_DAYS = 5
MIN_TOTAL_VIEWS = 100

MAX_MISSING_RUNS = 3        # 🚨 deletion confirmation
HARD_STALE_DAYS = 3         # 🚨 hard kill even if exists

# ======================================================
# TIME HELPERS
# ======================================================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_ts(ts: str) -> datetime:
    dt = isoparse(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

# ======================================================
# USERNAME NORMALIZATION
# ======================================================
def normalize_usernames(rows: List[dict]) -> List[str]:
    seen, result = set(), []
    for row in rows:
        for part in row.get("ig_username", "").split(","):
            u = part.strip().lstrip("@")
            if u and u not in seen:
                seen.add(u)
                result.append(u)
    return result

# ======================================================
# SNAPSHOT HELPERS
# ======================================================
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

    # 1. Capture significant delta
    if dv >= MIN_VIEW_DELTA or dl > 0 or dc > 0:
        return True

    # 2. Adaptive: If moving fast (> 50 VPH), capture at least hourly
    # (Even if delta < MIN_VIEW_DELTA, which is rare, but safe fallback)
    hours = max(mins_since / 60, 0.01)
    vph = dv / hours
    if vph > 50 and mins_since >= 60:
        return True

    # 3. Fallback: Catch-up every 6 hours
    if mins_since >= 360:
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

# ======================================================
# PRUNE LOGIC
# ======================================================
def should_prune_reel(project_id: str, reel: dict) -> bool:
    reel_url = reel["reel_url"]
    snaps = get_snapshots(project_id, reel_url, limit=2)

    # 🚨 Hard stale kill
    if now_utc() - parse_ts(reel["last_seen_at"]) > timedelta(days=HARD_STALE_DAYS):
        return True

    # A — inactive
    if now_utc() - parse_ts(reel["last_seen_at"]) > timedelta(days=MAX_INACTIVE_DAYS):
        return True

    # B — flat or weak growth
    if len(snaps) >= 2:
        cur, prev = snaps
        if cur["views"] <= prev["views"]:
            return True

        hours = max(
            (parse_ts(cur["captured_at"]) - parse_ts(prev["captured_at"]))
            .total_seconds() / 3600,
            0.1,
        )
        vph = (cur["views"] - prev["views"]) / hours
        if vph < MIN_VIEWS_PER_HOUR:
            return True

    # C — old & weak
    age_days = (now_utc() - parse_ts(reel["last_seen_at"])).days
    if age_days >= MAX_REEL_AGE_DAYS and reel["views"] < MIN_TOTAL_VIEWS:
        return True

    return False

# ======================================================
# DELETED REEL RECONCILIATION
# ======================================================
def reconcile_missing_reels(project_id: str, seen_reels: Set[str]):
    rows = (
        supabase.table("reels")
        .select("reel_url, missing_count")
        .eq("project_id", project_id)
        .execute()
        .data or []
    )

    for r in rows:
        if r["reel_url"] not in seen_reels:
            misses = (r.get("missing_count") or 0) + 1

            if misses >= MAX_MISSING_RUNS:
                log.warning(f"🗑️ Deleting missing reel {r['reel_url']}")

                supabase.table("reel_snapshots").delete() \
                    .eq("project_id", project_id) \
                    .eq("reel_url", r["reel_url"]).execute()

                supabase.table("reels").delete() \
                    .eq("project_id", project_id) \
                    .eq("reel_url", r["reel_url"]).execute()
            else:
                supabase.table("reels").update(
                    {"missing_count": misses}
                ).eq(
                    "project_id", project_id
                ).eq(
                    "reel_url", r["reel_url"]
                ).execute()

# ======================================================
# MAIN MONITOR
# ======================================================
def run_monitor(project_id: Optional[str] = None):
    start_time = time.time()
    requests_this_run = 0
    blocked = False

    log.info("🛰️ Monitor job started")

    query = supabase.table("projects").select("*")
    query = query.eq("id", project_id) if project_id else query.eq("active", True)
    projects = query.execute().data or []

    total_reels = total_snaps = total_pruned = 0

    for project in projects:
        if (time.time() - start_time) / 60 > MAX_PROJECT_RUNTIME_MIN:
            log.warning("⏹️ Max runtime reached — stopping")
            break

        pid = project["id"]
        log.info(f"📁 Project: {project['name']}")

        # 1. Fetch ALL monitored accounts (Metadata is small, ~5000 rows = ~500KB, fine to fetch)
        rows = (
            supabase.table("monitored_accounts")
            .select("id, ig_username, last_checked_at, check_frequency, priority_score")
            .eq("project_id", pid)
            .eq("is_active", True)
            .execute()
            .data or []
        )

        if not rows:
            log.info("ℹ️ No active accounts.")
            continue

        # 2. Filter: Who needs checking?
        # Criteria: now > last_checked + frequency
        queue = []
        now = now_utc()
        
        for r in rows:
            # Parse last_checked (handle None as 'Never')
            if r.get("last_checked_at"):
                last_check = parse_ts(r["last_checked_at"])
            else:
                last_check = datetime.min.replace(tzinfo=timezone.utc)
            
            # Default freq 6h if missing
            freq_hours = r.get("check_frequency") or 6
            next_check = last_check + timedelta(hours=freq_hours)
            
            if now >= next_check:
                # Add to queue
                priority = r.get("priority_score") or 1.0
                queue.append({
                    "row_id": r["id"],
                    "username": r.get("ig_username", "").strip().lstrip("@"),
                    "score": priority,
                    "overdue_by": (now - next_check).total_seconds()
                })

        # 3. Sort Queue
        # Primary: Priority Score (Desc), Secondary: Overdue Amount (Desc)
        queue.sort(key=lambda x: (x["score"], x["overdue_by"]), reverse=True)

        log.info(f"📊 Queue status: {len(queue)} pending / {len(rows)} total")

        # 4. Cap Batch Size (Human-Like Safety)
        # To fetch 50 users with ~60s delays takes ~50 minutes.
        # This fits the GHA timeout of 60m.
        SAFE_BATCH_LIMIT = 50
        batch = queue[:SAFE_BATCH_LIMIT]
        
        if not batch:
            log.info(f"✅ All accounts are up to date (Queue: {len(queue)})")
            continue
            
        usernames = [x["username"] for x in batch]
        
        seen_reels_this_run: Set[str] = set()
        requests_count = 0

        for i, username in enumerate(usernames):
            # 5. Human-Like Delays
            # Sleep SIGNIFICANTLY between profiles.
            # 30s to 90s is safe for "browsing".
            if i > 0:
                sleep_time = random.uniform(30, 90)
                log.info(f"☕ " + f"Reading content... ({sleep_time:.0f}s delay)")
                time.sleep(sleep_time)

            if requests_this_run >= MAX_REQUESTS_PER_HOUR:
                # ... existing break logic ...
                log.warning(f"🛑 Hour cap hit")
                blocked = True
                break

            try:
                log.info(f"🔍 Fetching @{username}")
                reels = fetch_reels(username)

                if reels is None:
                    log.warning(f"⏭️ skipped @{username} (blocked by IG)")
                    blocked = True
                    break

                if reels == []:
                    log.info(f"ℹ️ No reels @{username}")
                else:
                    time.sleep(60)

                requests_this_run += 1
                requests_count += 1
                
                # Mark as checked
                # Find row_id from batch list (inefficient look up but list is small <200)
                row_id = next((x["row_id"] for x in batch if x["username"] == username), None)
                if row_id:
                    supabase.table("monitored_accounts").update({
                        "last_checked_at": now_utc().isoformat()
                    }).eq("id", row_id).execute()

            except Exception:
                log.exception(f"Fetch failed @{username}")
                continue

            for reel in reels:
                now = now_utc().isoformat()
                reel_url = reel["url"]
                seen_reels_this_run.add(reel_url)

                supabase.table("reels").upsert(
                    {
                        "project_id": pid,
                        "reel_url": reel_url,
                        "owner_handle": username, # Linked for Analyzer
                        "views": reel["views"],
                        "likes": reel["likes"],
                        "comments": reel["comments"],
                        "last_seen_at": now,
                        "missing_count": 0,
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

        if blocked:
            log.error("🚫 Instagram blocked — stopping safely")
            break

        # 🔥 Deleted reel cleanup
        reconcile_missing_reels(pid, seen_reels_this_run)

        # 🔥 Final prune
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
