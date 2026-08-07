import os
import sys
import time
import json
import shutil
import tempfile
import unittest
import threading
from unittest.mock import patch, MagicMock

from daemon import MegaDaemon
from engine.application_engine import ApplicationEngine

class TestE2EDaemonIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch("daemon.DATA_DIR", self.temp_dir)
        self.patcher.start()
        
        self.patcher2 = patch("engine.application_engine.DATA_DIR", self.temp_dir)
        self.patcher2.start()
        
        self.patcher3 = patch("pipeline.worker.DATA_DIR", self.temp_dir)
        self.patcher3.start()
        
        self.patcher4 = patch("notifications.approval_manager.DATA_DIR", self.temp_dir)
        self.patcher4.start()
        
        # Patch DAEMON_LOCK inside the daemon module
        self.lock_patcher = patch("daemon.DAEMON_LOCK", os.path.join(self.temp_dir, "daemon.lock"))
        self.lock_patcher.start()
        
        # Patch pipeline worker lock
        self.worker_lock_patcher = patch("pipeline.worker.LOCK_FILE_PATH", os.path.join(self.temp_dir, "worker.lock"))
        self.worker_lock_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        self.patcher4.stop()
        self.lock_patcher.stop()
        self.worker_lock_patcher.stop()
        shutil.rmtree(self.temp_dir)

    @patch("daemon.subprocess.Popen")
    @patch("jobs.job_scanner.scan_all_jobs")
    @patch("pipeline.worker.LLMEvaluator")
    def test_e2e_daemon_flow(self, mock_evaluator_class, mock_scan_all, mock_popen):
        # 1. Setup Mocks
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        mock_scan_all.return_value = ([{
            "id": "e2e_job_1",
            "opportunity_id": "e2e_job_1",
            "platform": "GitHub",
            "url": "https://github.com/org/repo/issues/100",
            "title": "E2E Test Bug",
            "reward_verified": True
        }], {"GitHub": "OK"})
        
        mock_eval_instance = MagicMock()
        mock_eval_instance.evaluate_opportunity.return_value = {
            "id": "e2e_job_1",
            "opportunity_id": "e2e_job_1",
            "platform": "GitHub",
            "url": "https://github.com/org/repo/issues/100",
            "title": "E2E Test Bug",
            "reward_verified": True,
            "evaluation_decision": "SELECT",
            "proposal": "This is a mock proposal."
        }
        mock_evaluator_class.return_value = mock_eval_instance
        
        # We also need to patch out groq client instantiation so it uses the mocked LLMEvaluator
        # We will mock the whole LLMEvaluator class.
        
        # 2. Start Daemon
        # Using long intervals so they only run cycle 1 then wait.
        daemon = MegaDaemon(scheduler_interval_mins=60, worker_interval_secs=3600, start_dashboard=True)
        # Manually force the worker to use our mocked evaluator
        daemon.worker.evaluator = mock_eval_instance
        
        t = threading.Thread(target=daemon.start)
        t.daemon = True
        t.start()
        
        # 3. Wait for one full cycle to process
        time.sleep(2.0)
        
        # 4. Verifications
        # Verify 1 & 2: Started exactly once
        # (they run one cycle immediately, then wait for 1 hour)
        self.assertGreaterEqual(mock_scan_all.call_count, 1)
        mock_eval_instance.evaluate_opportunity.assert_called_once()
        
        # Verify 3: Dashboard started
        mock_popen.assert_called_once()
        
        # Verify 4: Scanner -> opportunities.json
        engine = ApplicationEngine()
        opps = engine._load(engine.opps_file)
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0]["id"], "e2e_job_1")
        
        # Verify 5 & 6: Worker -> proposal -> approvals.json (PENDING_APPROVAL)
        approvals_file = os.path.join(self.temp_dir, "approvals.json")
        with open(approvals_file, "r") as f:
            approvals = json.load(f)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["approval_status"], "PENDING_APPROVAL")
        self.assertIsInstance(approvals[0]["proposal"], str)
        self.assertGreater(len(approvals[0]["proposal"]), 0)
        
        # Verify 7 & 8: Duplicate not created. 
        # Force a second cycle
        daemon.scheduler.run_cycle(2)
        daemon.worker.run_cycle(2)
        
        opps_2 = engine._load(engine.opps_file)
        self.assertEqual(len(opps_2), 1)
        
        with open(approvals_file, "r") as f:
            approvals_2 = json.load(f)
        self.assertEqual(len(approvals_2), 1)
        
        # Verify 9: Application Engine remains blocked (no applications in applications.json)
        applications = engine.get_applications()
        self.assertEqual(len(applications), 0)
        
        # Verify 10: Earnings unchanged
        earnings_file = os.path.join(self.temp_dir, "earnings.json")
        if os.path.exists(earnings_file):
            with open(earnings_file, "r") as f:
                earnings = json.load(f)
            self.assertEqual(len(earnings), 0)
        else:
            self.assertTrue(True) # File not even created
            
        # Verify 11: Ctrl+C / graceful shutdown works
        daemon.stop()
        t.join(timeout=3.0)
        
        self.assertFalse(t.is_alive())
        mock_process.terminate.assert_called_once()

if __name__ == "__main__":
    unittest.main()
