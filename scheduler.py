import threading
import time
import signal
import logging
from datetime import datetime, timedelta

from jobs.monitor import run_monitor
from jobs.analyze import run_analyze
from jobs.deliver import run_deliver

# ==========================
# CONFIG
# ==========================
MONITOR_INTERVAL = 3 * 60 * 60      # 3 hours
DELIVERY_CHECK_INTERVAL = 60        # 1 minute

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
# CONTROL
# ==========================
stop_event = threading.Event()
monitor_lock = threading.Lock()


def sleep_until(next_run: datetime):
    """Sleep in small chunks so we can exit cleanly."""
    while not stop_event.is_set():
        remaining = (next_run - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5))


# ==========================
# LOOP 1 — MONITOR + ANALYZE
# ==========================
def monitor_loop():
    log.info("🛰️ Monitor loop started")

    next_run = datetime.now()

    while not stop_event.is_set():
        next_run += timedelta(seconds=MONITOR_INTERVAL)

        with monitor_lock:
            try:
                log.info("🛰️ Monitor started")
                run_monitor()

                log.info("📊 Analyzer started")
                run_analyze(preview=False)

                log.info("✅ Monitor + Analyze finished")

            except Exception:
                log.exception("❌ Monitor/Analyze crashed")

        sleep_until(next_run)


# ==========================
# LOOP 2 — DELIVERY WATCHER
# ==========================
def delivery_loop():
    log.info("📦 Delivery loop started")

    while not stop_event.is_set():
        try:
            sent = run_deliver()
            if sent:
                log.info(f"📤 Delivered {sent} reel(s)")

        except Exception:
            log.exception("❌ Delivery crashed")

        stop_event.wait(DELIVERY_CHECK_INTERVAL)


# ==========================
# SHUTDOWN HANDLING
# ==========================
def shutdown(signum, frame):
    log.warning("🛑 Shutdown signal received")
    stop_event.set()


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    log.info("🚀 Instagram Automation Engine started")

    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=delivery_loop, daemon=True).start()

    while not stop_event.is_set():
        time.sleep(1)

    log.info("👋 Scheduler stopped cleanly")
