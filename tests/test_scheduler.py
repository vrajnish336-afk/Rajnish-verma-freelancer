import os
import sys
import time
import shutil
import tempfile
import unittest
import threading
from unittest.mock import patch, MagicMock

from jobs.scheduler import ScanningScheduler
from engine.application_engine import ApplicationEngine

class TestScanningScheduler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create empty opportunities file so it doesn't crash
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(os.path.join(self.temp_dir, "opportunities.json"), "w") as f:
            f.write("[]")
            
        self.patcher = patch("engine.application_engine.DATA_DIR", self.temp_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.temp_dir)

    @patch("jobs.job_scanner.scan_all_jobs")
    def test_single_scan_cycle(self, mock_scan):
        # Mock scanner to return 2 jobs, one verified, one unverified
        mock_jobs = [
            {
                "id": "test_1",
                "opportunity_id": "test_1",
                "platform": "GitHub",
                "url": "https://github.com/org/repo/issues/1",
                "title": "Bug fix",
                "reward_verified": True
            },
            {
                "id": "test_2",
                "opportunity_id": "test_2",
                "platform": "Superteam",
                "url": "https://earn.superteam.fun/bounties/1",
                "title": "Write content",
                "reward_verified": False
            }
        ]
        mock_health = {"GitHub": "OK", "Superteam": "OK"}
        mock_scan.return_value = (mock_jobs, mock_health)
        
        scheduler = ScanningScheduler(interval_minutes=30)
        
        # Run one cycle
        scheduler.run_cycle(1)
        
        # Check that both opportunities were saved (both verified and unverified)
        engine = ApplicationEngine()
        opps = engine._load(engine.opps_file)
        self.assertEqual(len(opps), 2)
        
        # Run second cycle with same jobs
        scheduler.run_cycle(2)
        
        # No new jobs should be saved due to deduplication
        opps2 = engine._load(engine.opps_file)
        self.assertEqual(len(opps2), 2)
        
    @patch("jobs.scheduler.JobScanner.scan_for_opportunities")
    def test_graceful_shutdown(self, mock_scan):
        mock_scan.return_value = []
        scheduler = ScanningScheduler(interval_minutes=30)
        
        # Run in a thread
        t = threading.Thread(target=scheduler.start)
        t.daemon = True
        t.start()
        
        # Give it a second to start
        time.sleep(0.5)
        
        # Signal stop
        scheduler.stop()
        
        # Wait for thread to finish cleanly
        t.join(timeout=2.0)
        self.assertFalse(t.is_alive(), "Scheduler thread did not shut down cleanly")

    @patch("jobs.scheduler.JobScanner.scan_for_opportunities")
    def test_overlapping_prevented(self, mock_scan):
        # Make the scan block
        scan_event = threading.Event()
        resume_event = threading.Event()
        
        def blocking_scan():
            scan_event.set()
            resume_event.wait(timeout=2.0)
            return []
            
        mock_scan.side_effect = blocking_scan
        
        scheduler = ScanningScheduler(interval_minutes=30)
        
        # Start cycle 1 in background
        t1 = threading.Thread(target=scheduler.run_cycle, args=(1,))
        t1.start()
        
        # Wait until it enters the scan
        scan_event.wait(timeout=1.0)
        
        # Try to run cycle 2 concurrently
        scheduler.run_cycle(2)
        
        # The second cycle should have skipped.
        # Now let cycle 1 finish
        resume_event.set()
        t1.join(timeout=1.0)
        
        # Mock scan should only be called once
        self.assertEqual(mock_scan.call_count, 1)

if __name__ == "__main__":
    unittest.main()
