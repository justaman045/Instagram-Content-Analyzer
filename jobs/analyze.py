# jobs/analyze.py

import logging
from datetime import datetime, timezone
from typing import Optional

from rich.table import Table
from rich.console import Console
from rich import print
from dateutil.parser import isoparse

from db.supabase_client import supabase

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("analyze")

# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

console = Console()

# =========================================================
# Time helpers
# =========================================================
def parse_ts(ts: str):
    dt = isoparse(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hours_between(t1: str, t2: str) -> float:
    return max(
        (parse_ts(t2) - parse_ts(t1)).total_seconds() / 3600,
        0.01,
    )


# =========================================================
# Trend detection
# =========================================================
def detect_trend(velocity, acceleration, score):
    """
    Classifies the growth trajectory based on velocity (VPH) and acceleration (ΔVPH/hr).
    """
    if velocity > 250 and acceleration > 50:
        return "VIRAL 🦄"
    
    if acceleration > 20:
        return "EXPLODING 🧨"
    
    if acceleration > 5:
        return "HEATING UP 🔥"
    
    if -5 <= acceleration <= 5:
        return "STEADY 📈"
    
    if acceleration < -5:
        return "COOLING ❄️"
        
    return "STABLE ⚖️"


# =========================================================
# Analyzer job
# =========================================================
def run_analyze(
    preview: bool = False,
    project_id: Optional[str] = None,
):
    log.info("📊 Analyze job started")
    log.info("[bold cyan]📊 Analyze Job – Momentum Engine (v2)[/bold cyan]\n")

    # -------------------------
    # Fetch projects
    # -------------------------
    query = supabase.table("projects").select("id, name").eq("active", True)

    if project_id:
        query = query.eq("id", project_id)

    projects = query.execute().data or []

    if not projects:
        log.warning("No projects found to analyze")
        return

    for project in projects:
        pid = project["id"]
        pname = project["name"]

        log.info(f"\n[bold underline]📁 Project: {pname}[/bold underline]")

        try:
            # -------------------------
            # Fetch already sent reels
            # -------------------------
            sent_rows = (
                supabase
                .table("sent_reels")
                .select("reel_url")
                .eq("project_id", pid)
                .execute()
                .data or []
            )

            sent_urls = {r["reel_url"] for r in sent_rows}

            # -------------------------
            # Fetch all reels
            # -------------------------
            reels = (
                supabase
                .table("reels")
                .select("reel_url, owner_handle, created_at, views, likes, comments")
                .eq("project_id", pid)
                .execute()
                .data or []
            )

            ranked = []

            for r in reels:
                url = r["reel_url"]

                # ⛔ Skip reels already sent
                if url in sent_urls:
                    continue

                age = hours_between(
                    r["created_at"],
                    datetime.now(timezone.utc).isoformat(),
                )

                # Fetch MORE snapshots to calculate acceleration
                snaps = (
                    supabase
                    .table("reel_snapshots")
                    .select("views, likes, comments, captured_at")
                    .eq("project_id", pid)
                    .eq("reel_url", url)
                    .order("captured_at", desc=True)
                    .limit(3)  # Need 3 points for acceleration (current, prev, prev_prev)
                    .execute()
                    .data or []
                )

                if len(snaps) < 2:
                    continue

                # -------------------------
                # METRICS CALCULATION
                # -------------------------
                cur = snaps[0]
                prev = snaps[1]
                
                # Interval 1 (Most Recent)
                h1 = hours_between(prev["captured_at"], cur["captured_at"])
                d_views_1 = cur["views"] - prev["views"]
                velocity_1 = d_views_1 / h1  # Current Velocity

                # Interval 2 (Previous) - Optional (if 3rd snap exists)
                velocity_2 = 0
                acceleration = 0

                if len(snaps) >= 3:
                    prev_2 = snaps[2]
                    h2 = hours_between(prev_2["captured_at"], prev["captured_at"])
                    d_views_2 = prev["views"] - prev_2["views"]
                    velocity_2 = d_views_2 / h2
                    
                    # Acceleration: Change in velocity per hour
                    # (v_current - v_old) / time_between_midpoints roughly
                    # Simplified: just delta velocity
                    acceleration = (velocity_1 - velocity_2)

                # Engagement Quality (safe division)
                # Likes/Views ratio + Comments/Views ratio
                # We use current total stats for this quality check
                safe_views = max(r["views"], 1)
                eng_quality = ((r["likes"] / safe_views) * 100) + ((r["comments"] / safe_views) * 200)

                # -------------------------
                # SCORING FORMULA
                # -------------------------
                # Score = (Velocity * 1.0) + (Acceleration * 2.0) + (EngagementQuality * 5.0)
                # Acceleration is heavily weighted to catch "Exploding" trends early
                score = (velocity_1 * 1.0) + (acceleration * 2.0) + (eng_quality * 5.0)

                trend_label = detect_trend(velocity_1, acceleration, score)

                ranked.append(
                    {
                        "url": url,
                        "owner_handle": r.get("owner_handle"), # Pass handle for feedback loop
                        "age": f"{int(age * 60)}m",
                        "velocity": round(velocity_1, 1),
                        "accel": round(acceleration, 1),
                        "eng_q": round(eng_quality, 1),
                        "score": round(score, 1),
                        "trend": trend_label,
                        "d_views": d_views_1,
                    }
                )

            if not ranked:
                log.info("[dim]No new reels available to recommend[/dim]")
                continue

            # Sort by Score DESC
            ranked.sort(key=lambda x: x["score"], reverse=True)

            # =========================
            # PREVIEW MODE
            # =========================
            if preview:
                table = Table(show_lines=False)
                table.add_column("Rank")
                table.add_column("Reel")
                table.add_column("Age")
                table.add_column("ΔV (curr)")
                table.add_column("Vel (v/h)")
                table.add_column("Accel")
                table.add_column("Eng%")
                table.add_column("Score")
                table.add_column("Trend", style="bold")

                for i, r in enumerate(ranked, 1):
                    table.add_row(
                        str(i),
                        r["url"],
                        r["age"],
                        str(r["d_views"]),
                        str(r["velocity"]),
                        f"[green]{r['accel']}[/green]" if r['accel'] > 0 else f"[red]{r['accel']}[/red]",
                        str(r["eng_q"]),
                        str(r["score"]),
                        r["trend"],
                    )

                print(table)
                continue

            # =========================
            # PROD MODE
            # =========================
            best = ranked[0]

            # Reset previous recommendations
            supabase.table("reels").update(
                {"is_recommended": False}
            ).eq("project_id", pid).execute()

            # Set new recommendation
            supabase.table("reels").update(
                {
                    "score": best["score"],
                    "trend": best["trend"],
                    "is_recommended": True,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("project_id", pid).eq(
                "reel_url", best["url"]
            ).execute()

            log.info(
                f"[green]⭐ Recommended[/green] {best['url']} "
                f"(Score: {best['score']} | {best['trend']})"
            )
            
            # =========================
            # FEEDBACK LOOP (ADAPTIVE-V3)
            # =========================
            # 1. Aggregate Max Score per User
            user_max_scores = {}
            for r in ranked:
                u = r.get("owner_handle")
                if not u:
                    continue
                
                # Keep the highest score seen for this user
                if u not in user_max_scores or r["score"] > user_max_scores[u]:
                    user_max_scores[u] = r["score"]

            # 2. Update Monitored Accounts
            updates_count = 0
            for handle, max_score in user_max_scores.items():
                # Logic: Map Score -> Priority/Freq
                # Score > 2.0 (Viral) -> 1h, Prio 3.0
                # Score > 1.0 (Heating) -> 2h, Prio 1.5
                # Score < 0 (Cooling) -> 12h, Prio 0.5
                
                new_freq = 6  # Default
                new_prio = 1.0
                
                if max_score >= 2.0:
                    new_freq = 1
                    new_prio = 3.0
                elif max_score >= 1.0:
                    new_freq = 2
                    new_prio = 1.5
                elif max_score < 0:
                    new_freq = 12
                    new_prio = 0.5
                else: 
                    # 0.0 - 0.9 (Steady)
                    new_freq = 6
                    new_prio = 1.0

                try:
                    # Update DB
                    supabase.table("monitored_accounts").update({
                        "check_frequency": new_freq,
                        "priority_score": new_prio
                    }).eq("project_id", pid).eq("ig_username", handle).execute()
                    updates_count += 1
                except Exception:
                    log.warning(f"Failed to update priority for @{handle}")

            log.info(f"🔄 Adaptive Feedback: Updated {updates_count} accounts")
 

        except Exception:
            log.exception(f"Analyze failed for project: {pname}")

    log.info("\n[bold green]✅ Analyze job finished[/bold green]")
