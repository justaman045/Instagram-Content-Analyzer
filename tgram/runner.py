# tgram/runner.py
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta

from tgram.handlers import setup_bot

# ==========================
# CONFIG
# ==========================
# Defaults to 15 minutes for "Mailbox" mode
# Can be overridden by env var (e.g., from GHA inputs)
DEFAULT_RUNTIME_MINUTES = 15

log = logging.getLogger("bot-runner")

# ==========================
# MAIN RUNNER
# ==========================
async def run_bot():
    log.info("🤖 Starting Manager Bot")
    
    # Setup Telegram Bot (Main Async Loop)
    app = setup_bot()
    
    log.info("✅ Bot initialized. Starting polling...")
    
    await app.initialize()
    await app.start()
    
    # Start receiving updates
    await app.updater.start_polling()
    
    # Calculate Runtime
    try:
        runtime_min = int(os.getenv("RUNTIME_MINUTES", DEFAULT_RUNTIME_MINUTES))
    except ValueError:
        runtime_min = DEFAULT_RUNTIME_MINUTES

    log.info(f"⏱️ Bot configured to run for {runtime_min} minutes")
    
    start_time = time.time()
    end_time = start_time + (runtime_min * 60)
    
    log.info(f"⏳ Bot will run until {datetime.fromtimestamp(end_time)}")

    try:
        while time.time() < end_time:
            await asyncio.sleep(10) 
            # Heartbeat (faster checks for short runs)
    except asyncio.CancelledError:
        log.info("🛑 Async cancelled")
    finally:
        log.info("🛑 Time limit reached or stopping...")
        
        # Stop Telegram
        if app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()
            
    log.info("👋 Manager Bot exiting cleanly")
