import os
import sys
import time
import signal
import logging
import threading
import subprocess
import traceback

from jobs.scheduler import ScanningScheduler
from pipeline.worker import LocalWorker

logger = logging.getLogger("mega.daemon")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DAEMON_LOCK = os.path.join(DATA_DIR, "daemon.lock")

try:
    import msvcrt
except ImportError:
    msvcrt = None

class DaemonLock:
    def __init__(self, lock_path=DAEMON_LOCK):
        self.lock_path = lock_path
        self.file_handle = None
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)

    def acquire(self) -> bool:
        try:
            self.file_handle = open(self.lock_path, "w")
            if msvcrt:
                msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            self.file_handle.write(f"PID: {os.getpid()}\n")
            self.file_handle.flush()
            return True
        except (IOError, OSError):
            if self.file_handle:
                try:
                    self.file_handle.close()
                except Exception:
                    pass
                self.file_handle = None
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

class MegaDaemon:
    def __init__(self, scheduler_interval_mins: int = 30, worker_interval_secs: int = 300, start_dashboard: bool = True):
        self.scheduler = ScanningScheduler(interval_minutes=scheduler_interval_mins)
        self.worker = LocalWorker(interval_seconds=worker_interval_secs)
        self.should_start_dashboard = start_dashboard
        self.dashboard_process = None
        self.stop_event = threading.Event()
        self.lock = DaemonLock()

    def _setup_signal_handlers(self):
        def handle_signal(signum, frame):
            logger.info("Daemon received termination signal. Initiating shutdown of all components...")
            self.stop()
        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, handle_signal)
        except ValueError:
            pass

    def _start_dashboard(self):
        if not self.should_start_dashboard:
            return
        try:
            logger.info("Starting Dashboard process...")
            env = os.environ.copy()
            self.dashboard_process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true"],
                env=env
            )
        except Exception as e:
            logger.error(f"Failed to start dashboard: {e}")

    def _start_scheduler(self):
        try:
            logger.info("Starting ScanningScheduler thread...")
            self.scheduler.start()
        except Exception as e:
            logger.error(f"ScanningScheduler failed: {e}")

    def _start_worker(self):
        try:
            logger.info("Starting LocalWorker thread...")
            self.worker.start()
        except Exception as e:
            logger.error(f"LocalWorker failed: {e}")

    def start(self) -> int:
        if not self.lock.acquire():
            logger.error("FATAL: Another Daemon instance is already running. Aborting startup.")
            return 1
            
        self._setup_signal_handlers()
        
        self.t_scheduler = threading.Thread(target=self._start_scheduler, daemon=True)
        self.t_worker = threading.Thread(target=self._start_worker, daemon=True)
        
        self.t_scheduler.start()
        self.t_worker.start()
        self._start_dashboard()
        
        logger.info("Mega Daemon successfully started all components. Press Ctrl+C to stop.")
        
        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(1.0)
        except KeyboardInterrupt:
            logger.info("Daemon received KeyboardInterrupt.")
            self.stop()
        except Exception as e:
            logger.error(f"Daemon encountered unexpected error: {e}\n{traceback.format_exc()}")
            self.stop()
        finally:
            self._shutdown_all()
            self.lock.release()
            
        return 0

    def stop(self):
        self.stop_event.set()
        
    def _shutdown_all(self):
        logger.info("Shutting down components...")
        self.scheduler.stop()
        self.worker.stop()
        
        if self.dashboard_process:
            logger.info("Terminating Dashboard process...")
            self.dashboard_process.terminate()
            try:
                self.dashboard_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.dashboard_process.kill()
                
        # Wait for threads to finish
        if hasattr(self, "t_scheduler") and self.t_scheduler.is_alive():
            self.t_scheduler.join(timeout=5)
        if hasattr(self, "t_worker") and self.t_worker.is_alive():
            self.t_worker.join(timeout=5)
            
        logger.info("All components cleanly shut down.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    daemon = MegaDaemon()
    sys.exit(daemon.start())
