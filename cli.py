import argparse
import logging
import sys
from typing import List, Dict

from db.supabase_client import supabase
from jobs.monitor import run_monitor
from jobs.analyze import run_analyze
from jobs.deliver import run_deliver
from setup.setup import run_setup   # 👈 ADD THIS

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cli")


# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ==========================
# PROJECT HELPERS
# ==========================
def list_projects() -> List[Dict]:
    projects = (
        supabase.table("projects")
        .select("id,name,created_at")
        .eq("active", True)
        .order("created_at")
        .execute()
        .data or []
    )

    if not projects:
        log.warning("No active projects found")
        sys.exit(1)

    return projects


def prompt_project_selection(projects: List[Dict]) -> str:
    print("\nSelect a project to run:\n")

    for idx, p in enumerate(projects, start=1):
        print(f"{idx}. {p['name']}")

    while True:
        choice = input("\nEnter project number: ").strip()

        try:
            idx = int(choice)
            if 1 <= idx <= len(projects):
                return projects[idx - 1]["id"]
        except ValueError:
            pass

        print("❌ Invalid selection, try again.")



# ==========================
# CLI
# ==========================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Instagram Automation Worker"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # ---- setup ----
    sub.add_parser(
        "setup",
        help="Run interactive project setup wizard"
    )

    # ---- monitor ----
    monitor = sub.add_parser("monitor", help="Run monitor job")
    monitor.add_argument(
        "--project",
        type=int,
        help="Project number (use list order)"
    )

    # ---- analyze ----
    analyze = sub.add_parser("analyze", help="Run analyze job")
    analyze.add_argument(
        "--inspect",
        action="store_true",
        help="Preview analysis without persisting results"
    )
    analyze.add_argument(
        "--project",
        type=int,
        help="Project number (use list order)"
    )


    # ---- deliver ----
    sub.add_parser("deliver", help="Run delivery job")

    args = parser.parse_args()

    try:
        if args.command == "setup":
            run_setup()

        elif args.command == "monitor":
            projects = list_projects()

            if args.project:
                idx = args.project - 1
                if idx < 0 or idx >= len(projects):
                    raise ValueError("Invalid project number")

                project_id = projects[idx]["id"]

            else:
                if len(projects) == 1:
                    project_id = projects[0]["id"]
                    log.info(
                        f"Only one project found, running: {projects[0]['name']}"
                    )
                else:
                    project_id = prompt_project_selection(projects)

            run_monitor(project_id=project_id)

        elif args.command == "analyze":
            projects = list_projects()

            # ---- explicit project ----
            if args.project:
                idx = args.project - 1
                if idx < 0 or idx >= len(projects):
                    raise ValueError("Invalid project number")

                project_id = projects[idx]["id"]

            # ---- interactive selection ----
            else:
                if len(projects) == 1:
                    project_id = projects[0]["id"]
                    log.info(
                        f"Only one project found, analyzing: {projects[0]['name']}"
                    )
                else:
                    project_id = prompt_project_selection(projects)

            run_analyze(
                preview=args.inspect,
                project_id=project_id
            )


        elif args.command == "deliver":
            run_deliver()

        return 0

    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130

    except Exception:
        log.exception("❌ Job failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
