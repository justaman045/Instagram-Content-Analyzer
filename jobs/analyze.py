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
# Trend detection (UNCHANGED)
# =========================================================
def detect_trend(rate_vph, score, prev_score):
    if rate_vph >= 300 and score >= prev_score * 0.9:
        return "PEAK 🔥"
    if rate_vph >= 80 and score > prev_score:
        return "RISING 🚀"
    if rate_vph <= 20 and score < prev_score:
        return "DYING 💤"
    return "STABLE ⚖️"


# =========================================================
# Analyzer job
# =========================================================
def run_analyze(
    preview: bool = False,
    project_id: Optional[str] = None,
):
    log.info("📊 Analyze job started")
    log.info("[bold cyan]📊 Analyze Job – Momentum Engine[/bold cyan]\n")

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

        log.info(
            f"\n[bold underline]📁 Project: {pname}[/bold underline]"
        )

        try:
            reels = (
                supabase
                .table("reels")
                .select("reel_url")
                .eq("project_id", pid)
                .execute()
                .data or []
            )

            ranked = []

            for r in reels:
                url = r["reel_url"]

                snaps = (
                    supabase
                    .table("reel_snapshots")
                    .select("views, likes, comments, captured_at")
                    .eq("project_id", pid)
                    .eq("reel_url", url)
                    .order("captured_at", desc=True)
                    .limit(2)
                    .execute()
                    .data or []
                )

                if len(snaps) < 2:
                    continue

                cur, prev = snaps
                hrs = hours_between(
                    prev["captured_at"],
                    cur["captured_at"],
                )

                dv = cur["views"] - prev["views"]
                dl = cur["likes"] - prev["likes"]
                dc = cur["comments"] - prev["comments"]

                rate_vph = dv / hrs
                engagement = (dl / hrs) * 1.5 + (dc / hrs) * 2.0
                score = (rate_vph * 1.2) + engagement
                prev_score = max(prev["views"] / hrs, 1)

                ranked.append(
                    {
                        "url": url,
                        "age": f"{int(hrs * 60)} min",
                        "dv": dv,
                        "dl": dl,
                        "dc": dc,
                        "rate": round(rate_vph, 2),
                        "score": round(score, 2),
                        "trend": detect_trend(
                            rate_vph, score, prev_score
                        ),
                    }
                )

            if not ranked:
                log.info("[dim]No analyzable reels[/dim]")
                continue

            ranked.sort(key=lambda x: x["score"], reverse=True)

            # =========================
            # PREVIEW MODE
            # =========================
            if preview:
                table = Table(show_lines=False)
                table.add_column("Rank")
                table.add_column("Reel")
                table.add_column("Age")
                table.add_column("ΔV")
                table.add_column("ΔL")
                table.add_column("ΔC")
                table.add_column("V/hr")
                table.add_column("Score")
                table.add_column("Trend")

                for i, r in enumerate(ranked, 1):
                    table.add_row(
                        str(i),
                        r["url"],
                        r["age"],
                        str(r["dv"]),
                        str(r["dl"]),
                        str(r["dc"]),
                        str(r["rate"]),
                        str(r["score"]),
                        r["trend"],
                    )

                log.info(table)
                continue

            # =========================
            # PROD MODE
            # =========================
            best = ranked[0]

            supabase.table("reels").update(
                {"is_recommended": False}
            ).eq("project_id", pid).execute()

            supabase.table("reels").update(
                {
                    "score": best["score"],
                    "trend": best["trend"],
                    "is_recommended": True,
                    "analyzed_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }
            ).eq("project_id", pid).eq(
                "reel_url", best["url"]
            ).execute()

            log.info(
                f"[green]⭐ Recommended[/green] {best['url']} ({best['trend']})"
            )

        except Exception:
            log.exception(f"Analyze failed for project: {pname}")

    log.info("\n[bold green]✅ Analyze job finished[/bold green]")
