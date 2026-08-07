import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.adapters.github_adapter import GitHubAdapter
from engine.application_engine import ApplicationEngine, STATE_READY, STATE_SUBMITTED, STATE_MANUAL_ACTION_REQUIRED
import tempfile
import shutil
import engine.application_engine as app_eng_module
import notifications.approval_manager as appr_mgr
import proposals.proposal_generator as prop_gen
import models.opportunity as opp_model

class TestGitHubAdapter(unittest.TestCase):
    def setUp(self):
        # Create isolated temp dir for engine
        self.temp_dir = tempfile.mkdtemp()
        app_eng_module.DATA_DIR = self.temp_dir
        appr_mgr.DATA_DIR = self.temp_dir
        prop_gen.DATA_DIR = self.temp_dir
        opp_model.DATA_DIR = self.temp_dir
        self.engine = ApplicationEngine(dry_run=False)
        self.engine._ensure_files()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_valid_github_url_parsing(self):
        adapter = GitHubAdapter()
        parsed = adapter.parse_github_url("https://github.com/tenstorrent/tt-metal/issues/52328")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["owner"], "tenstorrent")
        self.assertEqual(parsed["repo"], "tt-metal")
        self.assertEqual(parsed["issue_number"], "52328")

    def test_invalid_github_url_parsing(self):
        adapter = GitHubAdapter()
        parsed = adapter.parse_github_url("https://earn.superteam.fun/bounties/abc")
        self.assertIsNone(parsed)

    @patch("engine.adapters.github_adapter.os.getenv")
    def test_missing_token_real_submission(self, mock_getenv):
        mock_getenv.return_value = None
        adapter = GitHubAdapter(dry_run=False)
        res = adapter.submit_proposal("https://github.com/org/repo/issues/1", "proposal")
        self.assertFalse(res["success"])
        self.assertEqual(res["mode"], "REAL")
        self.assertIn("GITHUB_TOKEN is required", res["error"])

    def test_dry_run_mode(self):
        adapter = GitHubAdapter(dry_run=True)
        res = adapter.submit_proposal("https://github.com/org/repo/issues/1", "Hello")
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "DRY_RUN")
        self.assertEqual(res["method"], "POST")
        self.assertEqual(res["payload"]["body"], "Hello")
        self.assertEqual(res["endpoint"], "https://api.github.com/repos/org/repo/issues/1/comments")

    @patch("engine.adapters.github_adapter.requests.post")
    @patch("engine.adapters.github_adapter.os.getenv")
    def test_successful_mocked_submission(self, mock_getenv, mock_post):
        mock_getenv.return_value = "ghp_fake_token"
        
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp
        
        adapter = GitHubAdapter(dry_run=False)
        res = adapter.submit_proposal("https://github.com/org/repo/issues/1", "Hello")
        
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "REAL")
        self.assertEqual(res["message"], "Real API submission successful")
        
        # Verify it was called with correct headers and payload
        mock_post.assert_called_once_with(
            "https://api.github.com/repos/org/repo/issues/1/comments",
            json={"body": "Hello"},
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "MEGA-Freelancer-Bot", "Authorization": "token ghp_fake_token"},
            timeout=15
        )

    @patch("engine.adapters.github_adapter.requests.post")
    @patch("engine.adapters.github_adapter.os.getenv")
    def test_failed_mocked_submission(self, mock_getenv, mock_post):
        mock_getenv.return_value = "ghp_fake_token"
        
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_post.return_value = mock_resp
        
        adapter = GitHubAdapter(dry_run=False)
        res = adapter.submit_proposal("https://github.com/org/repo/issues/1", "Hello")
        
        self.assertFalse(res["success"])
        self.assertIn("API Error 403", res["error"])

    def test_unapproved_submission_engine(self):
        # Should be blocked from entering engine
        opp = {
            "opportunity_id": "test_1",
            "platform": "GitHub",
            "url": "https://github.com/org/repo/issues/1",
            "approval_status": "PENDING_APPROVAL",
            "automation_allowed": True
        }
        res = self.engine.promote_approved_opportunity(opp)
        self.assertEqual(res, {})

    @patch("engine.adapters.github_adapter.requests.post")
    @patch("engine.adapters.github_adapter.os.getenv")
    def test_automation_allowed_false_engine(self, mock_getenv, mock_post):
        mock_getenv.return_value = "ghp_fake_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp
        
        opp = {
            "opportunity_id": "test_2",
            "platform": "GitHub",
            "url": "https://github.com/org/repo/issues/2",
            "approval_status": "APPROVED",
            "automation_allowed": False,
            "proposal": "Hello"
        }
        app = self.engine.promote_approved_opportunity(opp)
        self.assertEqual(app["status"], STATE_MANUAL_ACTION_REQUIRED)
        
        # Now try to submit via engine
        with patch.dict(os.environ, {"LIVE_SUBMISSION": "true"}):
            res = self.engine.submit_application(app["id"], dry_run=False)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], STATE_MANUAL_ACTION_REQUIRED)
        self.assertIn("MANUAL_ACTION_REQUIRED", res["error"])
        
        # Post should never be called
        mock_post.assert_not_called()

    @patch("engine.adapters.github_adapter.requests.post")
    def test_duplicate_submission_engine(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp
        
        opp = {
            "opportunity_id": "test_3",
            "platform": "GitHub",
            "url": "https://github.com/org/repo/issues/3",
            "approval_status": "APPROVED",
            "automation_allowed": True,
            "proposal": "Hello"
        }
        app = self.engine.promote_approved_opportunity(opp)
        self.assertEqual(app["status"], STATE_READY)
        
        # Submit once
        with patch.dict(os.environ, {"LIVE_SUBMISSION": "true", "GITHUB_TOKEN": "ghp_fake_token"}):
            res1 = self.engine.submit_application(app["id"], dry_run=False)
        self.assertTrue(res1["success"], f"Failed: {res1.get('error')}")
        self.assertEqual(res1["status"], STATE_SUBMITTED)
        self.assertEqual(mock_post.call_count, 1)
        
        # Submit again -> duplicate blocked
        with patch.dict(os.environ, {"LIVE_SUBMISSION": "true", "GITHUB_TOKEN": "ghp_fake_token"}):
            res2 = self.engine.submit_application(app["id"], dry_run=False)
        self.assertFalse(res2["success"])
        self.assertIn("Duplicate submission blocked", res2["error"])
        
        # Ensure it was not called again
        self.assertEqual(mock_post.call_count, 1)

if __name__ == '__main__':
    unittest.main()
