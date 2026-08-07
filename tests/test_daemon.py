import os
import sys
import time
import shutil
import tempfile
import unittest
import threading
from unittest.mock import patch, MagicMock

from daemon import MegaDaemon

class TestMegaDaemon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch("daemon.DATA_DIR", self.temp_dir)
        self.patcher.start()
        # Patch DAEMON_LOCK inside the daemon module
        self.lock_patcher = patch("daemon.DAEMON_LOCK", os.path.join(self.temp_dir, "daemon.lock"))
        self.lock_patcher.start()
        
    def tearDown(self):
        self.patcher.stop()
        self.lock_patcher.stop()
        shutil.rmtree(self.temp_dir)

    @patch("daemon.subprocess.Popen")
    @patch("daemon.ScanningScheduler.start")
    @patch("daemon.LocalWorker.start")
    def test_daemon_startup_and_shutdown(self, mock_worker_start, mock_scheduler_start, mock_popen):
        # Mock Popen
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        daemon = MegaDaemon(start_dashboard=True)
        
        # Start daemon in background thread
        t = threading.Thread(target=daemon.start)
        t.daemon = True
        t.start()
        
        # Give it a moment to initialize
        time.sleep(0.5)
        
        # Check components started
        mock_worker_start.assert_called_once()
        mock_scheduler_start.assert_called_once()
        mock_popen.assert_called_once()
        
        # Trigger stop
        daemon.stop()
        t.join(timeout=2.0)
        
        # Verify clean shutdown
        self.assertFalse(t.is_alive())
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()

    @patch("daemon.subprocess.Popen")
    @patch("daemon.ScanningScheduler.start")
    @patch("daemon.LocalWorker.start")
    def test_duplicate_start_prevention(self, mock_worker_start, mock_scheduler_start, mock_popen):
        daemon1 = MegaDaemon(start_dashboard=False)
        daemon2 = MegaDaemon(start_dashboard=False)
        
        # Start daemon1
        t1 = threading.Thread(target=daemon1.start)
        t1.daemon = True
        t1.start()
        
        time.sleep(0.5)
        
        # Try to start daemon2
        res = daemon2.start()
        
        # It should exit with 1 (failed lock)
        self.assertEqual(res, 1)
        
        # Stop daemon1
        daemon1.stop()
        t1.join(timeout=2.0)
        
if __name__ == "__main__":
    unittest.main()
