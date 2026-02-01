import logging
import sys
import os
from typing import List, Dict

from db.supabase_client import supabase
from jobs.monitor import run_monitor
from jobs.analyze import run_analyze
from jobs.deliver import run_deliver

# ==========================
# CONFIG
# ==========================
log = logging.getLogger("batch-runner")

def get_active_projects() -> List[Dict]:
    target_pid = os.getenv("PROJECT_ID")
    
    query = supabase.table("projects").select("id,name").eq("active", True)
    
    if target_pid:
        log.info(f"🎯 Target Project ID set: {target_pid}")
        query = query.eq("id", target_pid)
        
    projects = query.execute().data or []
    return projects


def run_batch():
    log.info("🚀 Starting Core Analysis Batch (GHA)")

    projects = get_active_projects()
    if not projects:
        log.warning("⚠️ No active projects found. Exiting.")
        return

    log.info(f"Found {len(projects)} active project(s). Processing sequentially.")

    for p in projects:
        pid = p["id"]
        pname = p["name"]
        
        log.info(f"👉 Processing Project: {pname} ({pid})")
        
        try:
            # 1. Monitor
            log.info("   • Running Monitor...")
            run_monitor(project_id=pid)
            
            # 2. Analyze
            log.info("   • Running Analyzer...")
            run_analyze(preview=False, project_id=pid)
            
            # 3. Deliver
            log.info("   • Running Delivery...")
            sent = run_deliver(project_id=pid)
            if sent:
                log.info(f"   • 📤 Delivered {sent} reels")
                
        except Exception:
            log.exception(f"❌ Failed processing project: {pname}")

    log.info("✅ Batch completed")
