import os
import sys
import time
import signal
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Dict, Any

from jobs.job_scanner import JobScanner
from engine.application_engine import ApplicationEngine
from models.opportunity import Opportunity

logger = logging.getLogger("mega.scheduler")

class ScanningScheduler:
    def __init__(self, interval_minutes: int = 30):
        self.interval_seconds = interval_minutes * 60
        self.stop_event = threading.Event()
        self.cycle_lock = threading.Lock()
        self.engine = ApplicationEngine()
        self.scanner = JobScanner()
        self.is_scanning = False
        
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

    def _setup_signal_handlers(self):
        def handle_signal(signum, frame):
            logger.info("Scheduler: Received termination signal. Initiating graceful shutdown...")
            self.stop()
        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, handle_signal)
        except ValueError:
            pass

    def stop(self):
        self.stop_event.set()

    def run_cycle(self, cycle: int):
        with self.cycle_lock:
            if self.is_scanning:
                logger.warning(f"[Cycle {cycle}] Overlapping scan prevented. Previous cycle is still running.")
                return
            self.is_scanning = True
            
        try:
            logger.info(f"=== [Cycle {cycle}] Starting scan cycle ===")
            start_time = time.time()
            
            raw_jobs = self.scanner.scan_for_opportunities()
            
            # Deduplicate and save
            existing_opps = self.engine._load(self.engine.opps_file)
            existing_keys = {
                (o.get("platform"), o.get("url") or o.get("opportunity_id") or o.get("title")): True
                for o in existing_opps
            }
            
            new_count = 0
            skipped_count = 0
            
            for job in raw_jobs:
                # Store unconditionally if it's new (verified or unverified)
                key = (job.get("platform"), job.get("url") or job.get("opportunity_id") or job.get("title"))
                if key in existing_keys:
                    skipped_count += 1
                    continue
                    
                # Store persistently
                opp = Opportunity.from_dict(job)
                self.engine.save_opportunity(opp)
                existing_keys[key] = True
                new_count += 1
                
            duration = round(time.time() - start_time, 2)
            logger.info(f"=== [Cycle {cycle}] Finished in {duration}s | Found: {len(raw_jobs)} | New: {new_count} | Skipped: {skipped_count} ===")
            
        except Exception as e:
            logger.error(f"[Cycle {cycle}] Scanner failed: {e}\n{traceback.format_exc()}")
        finally:
            with self.cycle_lock:
                self.is_scanning = False

    def start(self):
        self._setup_signal_handlers()
        self.stop_event.clear()
        cycle = 0
        
        logger.info(f"Starting 24/7 Scanning Scheduler (Interval: {self.interval_seconds}s)")
        
        while not self.stop_event.is_set():
            cycle += 1
            self.run_cycle(cycle)
            
            if not self.stop_event.is_set():
                logger.info(f"Waiting {self.interval_seconds}s until next scan cycle...")
                self.stop_event.wait(self.interval_seconds)
                
        logger.info("Scanning Scheduler cleanly shut down.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    scheduler = ScanningScheduler()
    scheduler.start()
