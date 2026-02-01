# scheduler.py

import threading
import time
import signal
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from jobs.monitor import run_monitor
from jobs.analyze import run_analyze
from jobs.deliver import run_deliver
from cli import list_projects, prompt_project_selection

# ==========================
# CONFIG
# ==========================
MONITOR_INTERVAL = 3 * 60 * 60
DELIVERY_CHECK_INTERVAL = 60 * 60

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")



# ==========================
# SILENCE NOISY LIBRARIES
# ==========================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)



# Silence noisy libs
for name in ("httpx", "httpcore", "postgrest", "supabase", "urllib3"):
    logging.getLogger(name).setLevel(logging.WARNING)

# ==========================
# CONTROL
# ==========================
stop_event = threading.Event()
monitor_lock = threading.Lock()


def sleep_until(next_run: datetime):
    while not stop_event.is_set():
        remaining = (next_run - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        stop_event.wait(min(remaining, 1))


# ==========================
# PROJECT SELECTION
# ==========================
def resolve_project_id() -> str:
    env_pid = os.getenv("PROJECT_ID")
    if env_pid:
        log.info(f"Using PROJECT_ID from env: {env_pid}")
        return env_pid

    projects = list_projects()

    if len(projects) == 1:
        log.info(f"Only one project found, running: {projects[0]['name']}")
        return projects[0]["id"]

    return prompt_project_selection(projects)


# ==========================
# WORKER LOOPS
# ==========================
def monitor_loop(project_id: str):
    log.info(f"🛰️ Monitor loop started (project={project_id})")
    next_run = datetime.now()

    while not stop_event.is_set():
        next_run += timedelta(seconds=MONITOR_INTERVAL)

        with monitor_lock:
            if stop_event.is_set():
                break

            try:
                log.info("🛰️ Monitor started")
                run_monitor(project_id=project_id)

                log.info("📊 Analyzer started")
                run_analyze(preview=False, project_id=project_id)

                log.info("✅ Monitor + Analyze finished")

            except Exception:
                log.exception("❌ Monitor/Analyze crashed")

        sleep_until(next_run)

    log.info("🛰️ Monitor loop exited")


def delivery_loop(project_id: str):
    log.info(f"📦 Delivery loop started (project={project_id})")

    while not stop_event.is_set():
        try:
            sent = run_deliver(project_id=project_id)
            if sent:
                log.info(f"📤 Delivered {sent} reel(s)")

        except Exception:
            log.exception("❌ Delivery crashed")

        stop_event.wait(DELIVERY_CHECK_INTERVAL)

    log.info("📦 Delivery loop exited")


# ==========================
# SHUTDOWN HANDLING
# ==========================
def shutdown(signum, frame):
    log.warning("🛑 Shutdown signal received")
    stop_event.set()


# ==========================
# FACTORY
# ==========================
def start_scheduler_threads(project_id: str):
    log.info(f"🚀 Starting scheduler threads for project: {project_id}")

    monitor_thread = threading.Thread(
        target=monitor_loop,
        args=(project_id,),
        name="monitor-thread",
    )

    delivery_thread = threading.Thread(
        target=delivery_loop,
        args=(project_id,),
        name="delivery-thread",
    )

    monitor_thread.start()
    delivery_thread.start()

    return monitor_thread, delivery_thread, stop_event

