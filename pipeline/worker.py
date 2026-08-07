"""
pipeline/worker.py — Controlled Windows Background Worker
=========================================================

Runs continuous scan and evaluation cycles in the background with:
  - Configurable scan intervals
  - Graceful shutdown via threading.Event and signal handlers
  - No uncontrolled 'while True' loops
  - Start / end / error telemetry logging
  - Windows file lock (msvcrt) to prevent overlapping scan executions
"""

import os
import sys
import time
import signal
import logging
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

try:
    import msvcrt
except ImportError:
    msvcrt = None

from dotenv import load_dotenv
from groq import Groq

from jobs.job_scanner import JobScanner
from evaluator.llm_evaluator import LLMEvaluator
from engine.application_engine import ApplicationEngine
from models.opportunity import Opportunity

logger = logging.getLogger("mega.worker")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LOCK_FILE_PATH = os.path.join(DATA_DIR, "worker.lock")


class WorkerLock:
    """Windows filesystem lock to prevent overlapping worker instances."""
    def __init__(self, lock_path: str = LOCK_FILE_PATH):
        self.lock_path = lock_path
        self.file_handle = None
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)

    def acquire(self) -> bool:
        try:
            self.file_handle = open(self.lock_path, "w")
            if msvcrt:
                msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            self.file_handle.write(f"PID: {os.getpid()}\nStarted: {datetime.now(timezone.utc).isoformat()}\n")
            self.file_handle.flush()
            return True
        except (IOError, OSError):
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None
            logger.warning(f"Could not acquire worker lock ({self.lock_path}): another instance is already running.")
            return False

    def release(self):
        if self.file_handle:
            try:
                if msvcrt:
                    msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
            finally:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                if os.path.exists(self.lock_path):
                    try:
                        os.remove(self.lock_path)
                    except (IOError, OSError):
                        pass
                self.file_handle = None


class LocalWorker:
    def __init__(self, interval_seconds: int = 300, max_cycles: int = 0):
        """
        :param interval_seconds: Time in seconds to wait between scan cycles.
        :param max_cycles: Maximum cycles to run before exiting (0 = infinite until shutdown).
        """
        self.interval_seconds = interval_seconds
        self.max_cycles = max_cycles
        self.stop_event = threading.Event()
        self.cycle_lock = threading.Lock()
        self.lock = WorkerLock()
        
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY missing in environment; AI evaluation will fall back to default review state.")
            self.groq_client = None
        else:
            self.groq_client = Groq(api_key=api_key)

        self.engine = ApplicationEngine()
        self.scanner = JobScanner()
        self.evaluator = LLMEvaluator(groq_client=self.groq_client) if self.groq_client else None
        
        # Configure stdout for UTF-8 on Windows consoles
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

    def _setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        def handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
            logger.info(f"Received signal {sig_name} ({signum}). Initiating graceful shutdown...")
            self.stop()

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            if hasattr(signal, "SIGBREAK"):  # Windows Ctrl+Break
                signal.signal(signal.SIGBREAK, handle_signal)
        except (ValueError, OSError) as e:
            logger.debug(f"Could not register all signal handlers (likely running outside main thread): {e}")

    def stop(self):
        """Signal the worker to terminate gracefully."""
        self.stop_event.set()

    def run_cycle(self, cycle_num: int) -> Dict[str, Any]:
        """Execute a single scan and evaluation cycle with error handling and telemetry."""
        with self.cycle_lock:
            start_time = time.time()
            logger.info(f"=== [Cycle {cycle_num}] Starting worker cycle ===")
            stats = {"cycle": cycle_num, "scanned": 0, "evaluated": 0, "drafted": 0, "errors": []}

            try:
                # 1. Scan live sources
                logger.info(f"[Cycle {cycle_num}] [1/3] Scanning opportunity sources...")
                raw_jobs = self.scanner.scan_for_opportunities()
                stats["scanned"] = len(raw_jobs)
                if not raw_jobs:
                    logger.info(f"[Cycle {cycle_num}] No opportunities found or scanners failed.")
                    return stats

                logger.info(f"[Cycle {cycle_num}] Found {len(raw_jobs)} raw opportunities.")

                # 2. Evaluate & Filter
                logger.info(f"[Cycle {cycle_num}] [2/3] Evaluating and filtering opportunities...")
                existing_opps = {
                    opp.get("url") or f"{opp.get('platform')}:{opp.get('title')}": opp 
                    for opp in self.engine._load(self.engine.opps_file)
                }
                evaluated_jobs = []

                for idx, job in enumerate(raw_jobs, 1):
                    if self.stop_event.is_set():
                        logger.info(f"[Cycle {cycle_num}] Stop requested during evaluation; aborting cycle early.")
                        break

                    if not job.get("reward_verified"):
                        continue  # Skip unverified for MVP strict mode

                    url = job.get("url")
                    platform = job.get("platform")
                    title = job.get("title", "Untitled")
                    key = url or f"{platform}:{title}"
                    short_title = title[:45].encode("ascii", errors="replace").decode("ascii", errors="replace")

                    # Duplicate protection: skip if already applied/drafted
                    if self.engine.has_applied(platform, url):
                        continue

                    # Reuse evaluation if already processed previously to avoid repeated LLM calls
                    if key in existing_opps and existing_opps[key].get("evaluation_decision"):
                        evaluated = existing_opps[key]
                    elif self.evaluator:
                        logger.info(f"[Cycle {cycle_num}]   Analyzing [{idx}/{len(raw_jobs)}]: {short_title}...")
                        evaluated = self.evaluator.evaluate_opportunity(job)
                        stats["evaluated"] += 1
                    else:
                        evaluated = job

                    if evaluated.get("evaluation_decision") == "SELECT":
                        evaluated_jobs.append(evaluated)

                # 3. Generate Draft Applications
                logger.info(f"[Cycle {cycle_num}] [3/3] Processing {len(evaluated_jobs)} SELECT candidates...")
                for job in evaluated_jobs:
                    if self.stop_event.is_set():
                        break
                    opp = Opportunity.from_dict(job)
                    self.engine.save_opportunity(opp)

                    proposal = job.get("proposal", "")
                    if proposal:
                        draft = self.engine.create_application_draft(job, proposal)
                        if draft:
                            short_title = job.get("title", "Untitled")[:30].encode("ascii", errors="replace").decode("ascii", errors="replace")
                            logger.info(f"[Cycle {cycle_num}]   -> Created DRAFT application for: {short_title}")
                            stats["drafted"] += 1

            except Exception as e:
                msg = f"Error during worker cycle {cycle_num}: {e}"
                logger.error(f"{msg}\n{traceback.format_exc()}")
                stats["errors"].append(msg)

            duration = round(time.time() - start_time, 2)
            stats["duration"] = duration
            logger.info(f"=== [Cycle {cycle_num}] Finished in {duration}s | Scanned: {stats['scanned']} | Evaluated: {stats['evaluated']} | Drafted: {stats['drafted']} ===")
            return stats

    def start(self) -> int:
        """Start the controlled background worker loop."""
        logger.info(f"Starting MEGA Freelancer Local Worker (interval: {self.interval_seconds}s, max_cycles: {self.max_cycles or 'unlimited'}).")
        
        # Prevent overlapping scans using Windows lock
        if not self.lock.acquire():
            logger.error("FATAL: Another local worker instance is already running (worker.lock acquired). Aborting startup.")
            return 1

        self._setup_signal_handlers()
        self.stop_event.clear()

        cycle = 0
        try:
            while not self.stop_event.is_set():
                cycle += 1
                self.run_cycle(cycle)

                # Check if we reached max_cycles
                if self.max_cycles > 0 and cycle >= self.max_cycles:
                    logger.info(f"Reached configured maximum of {self.max_cycles} cycle(s). Worker stopping.")
                    break

                if not self.stop_event.is_set():
                    logger.info(f"Waiting {self.interval_seconds}s until next cycle (Press Ctrl+C to initiate graceful shutdown)...")
                    # Using stop_event.wait instead of sleep avoids uncontrolled blocking & allows instant shutdown
                    self.stop_event.wait(timeout=self.interval_seconds)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Shutting down worker...")
            self.stop()
        except Exception as e:
            logger.error(f"Unexpected fatal error in worker loop: {e}\n{traceback.format_exc()}")
        finally:
            self.lock.release()
            logger.info("Local Worker cleanly shut down and lock released.")

        return 0
