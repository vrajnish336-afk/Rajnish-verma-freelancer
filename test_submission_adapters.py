"""
test_submission_adapters.py — Focused Tests for Application Submission Adapters MVP Layer
==========================================================================================

Tests:
1. unapproved submission blocked
2. missing credentials (safe failure without exception)
3. unsupported platform -> MANUAL_ACTION_REQUIRED
4. successful adapter response (stores external application ID/reference)
5. failed submission (never invents a successful submission or ID)
6. DRY_RUN (simulates without network requests)
"""

import sys
import os
from datetime import datetime
from submission import SubmissionManager

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING APPLICATION SUBMISSION ADAPTERS MVP LAYER                  ")
    print("======================================================================")
    
    manager = SubmissionManager()

    # 1. UNAPPROVED SUBMISSION BLOCKED
    print("\n[1/6] Testing Unapproved Submission Blocking...")
    unapproved_app = {
        "id": "test_app_unappr_01",
        "platform": "GitHub",
        "title": "[TEST] Unapproved Job",
        "url": "https://github.com/org/repo/issues/10",
        "proposal": "Here is my proposed bugfix.",
        "approval_status": "PENDING_APPROVAL",  # Not approved!
        "automation_allowed": True
    }
    res_unapproved = manager.submit_application(unapproved_app, dry_run=True)
    assert res_unapproved["success"] is False, f"Submission succeeded on unapproved app: {res_unapproved}"
    assert res_unapproved["status"] == "BLOCKED", f"Expected BLOCKED status, got {res_unapproved['status']}"
    assert "must have APPROVED status" in res_unapproved["error"], f"Unexpected error message: {res_unapproved['error']}"
    print("  ✅ Passed: Unapproved application submission completely blocked during preflight check.")

    # 2. MISSING CREDENTIALS (SAFE FAILURE)
    print("\n[2/6] Testing Missing Credentials Safe Failure...")
    # Clean environment token for test isolation
    orig_token = os.environ.pop("GITHUB_TOKEN", None)
    try:
        approved_app_no_token = {
            "id": "test_app_notoken_02",
            "platform": "GitHub",
            "title": "[TEST] Approved Job No Credentials",
            "url": "https://github.com/org/repo/issues/22",
            "proposal": "Fixing leak cleanly.",
            "approval_status": "APPROVED",
            "automation_allowed": True
        }
        res_no_cred = manager.submit_application(approved_app_no_token, dry_run=False)
        assert res_no_cred["success"] is False, f"Succeeded without credentials! {res_no_cred}"
        assert res_no_cred["status"] == "FAILED", f"Expected FAILED status, got {res_no_cred['status']}"
        assert "Missing API credentials" in res_no_cred["error"], f"Unexpected error text: {res_no_cred['error']}"
        print("  ✅ Passed: Missing credentials cleanly return FAILED status without raising uncaught exceptions.")
    finally:
        if orig_token is not None:
            os.environ["GITHUB_TOKEN"] = orig_token

    # 3. UNSUPPORTED PLATFORM -> MANUAL_ACTION_REQUIRED
    print("\n[3/6] Testing Unsupported Platform (Superteam / Web3) -> MANUAL_ACTION_REQUIRED...")
    app_unsupported = {
        "id": "test_app_superteam_03",
        "platform": "Superteam",
        "title": "[TEST] Superteam Solana Bounty",
        "url": "https://earn.superteam.fun/bounties/test-bounty-03",
        "proposal": "Auditing protocol.",
        "approval_status": "APPROVED",
        "automation_allowed": True
    }
    res_unsupported = manager.submit_application(app_unsupported, dry_run=False)
    assert res_unsupported["success"] is False, "Succeeded on unsupported open API platform!"
    assert res_unsupported["status"] == "MANUAL_ACTION_REQUIRED", f"Expected MANUAL_ACTION_REQUIRED, got {res_unsupported['status']}!"
    assert "MANUAL_ACTION_REQUIRED" in res_unsupported["error"] or "MANUAL_ACTION_REQUIRED" in res_unsupported.get("message", ""), "Reason text missing!"
    print("  ✅ Passed: Unsupported platform correctly defaults to MANUAL_ACTION_REQUIRED without attempting CAPTCHA or browser bypass.")

    # 4. SUCCESSFUL ADAPTER RESPONSE
    print("\n[4/6] Testing Successful Adapter Response (Store external ID & Timestamp)...")
    app_success_test = {
        "id": "test_app_git_04",
        "platform": "GitHub",
        "title": "[TEST] GitHub Bug Bounty",
        "url": "https://github.com/test-org/test-repo/issues/404",
        "proposal": "Resolving memory leak with heap dump verification.",
        "approval_status": "APPROVED",
        "automation_allowed": True,
        "github_token": "ghp_test_token_val_12345"
    }
    
    def mock_http_client_success(url, headers, payload):
        assert "test-org/test-repo/issues/404/comments" in url, f"Wrong target API URL: {url}"
        assert headers["Authorization"] == "token ghp_test_token_val_12345", "Auth header mismatch!"
        return 201, {"id": 9876543210, "html_url": "https://github.com/test-org/test-repo/issues/404#issuecomment-9876543210"}

    res_success = manager.submit_application(app_success_test, dry_run=False, http_client=mock_http_client_success)
    assert res_success["success"] is True, f"Expected success, got {res_success}"
    assert res_success["status"] == "SUBMITTED", f"Expected SUBMITTED, got {res_success['status']}"
    assert res_success["external_reference"] == "9876543210", f"Expected ID 9876543210, got {res_success['external_reference']}"
    assert res_success["timestamp"] is not None, "Missing execution timestamp!"
    print("  ✅ Passed: Successful API response records exact timestamp and stores returned external reference ID.")

    # 5. FAILED SUBMISSION (NEVER INVENT SUCCESS)
    print("\n[5/6] Testing Failed Submission (Never Invent Success or ID)...")
    def mock_http_client_failure(url, headers, payload):
        return 403, {"message": "Resource strictly protected by anti-bot rules or closed repository."}

    res_fail = manager.submit_application(app_success_test, dry_run=False, http_client=mock_http_client_failure)
    assert res_fail["success"] is False, "Failed API call flagged as success!"
    assert res_fail["status"] == "FAILED", f"Expected FAILED, got {res_fail['status']}"
    assert res_fail["external_reference"] is None, f"Safety violation: Invented external reference {res_fail['external_reference']} on failure!"
    assert "protected by anti-bot rules" in res_fail["error"], "Error details not accurately recorded!"
    assert res_fail["timestamp"] is not None, "Missing execution timestamp!"
    print("  ✅ Passed: Failed submission accurately records failure without inventing success or external reference IDs.")

    # 6. DRY_RUN
    print("\n[6/6] Testing DRY_RUN Mode (No External Requests)...")
    def mock_http_client_crash_if_called(url, headers, payload):
        raise RuntimeError("Safety violation: HTTP network client was invoked during DRY_RUN!")

    res_dry = manager.submit_application(app_success_test, dry_run=True, http_client=mock_http_client_crash_if_called)
    assert res_dry["success"] is True, f"DRY_RUN failed: {res_dry}"
    assert res_dry["mode"] == "DRY_RUN", f"Expected DRY_RUN mode, got {res_dry['mode']}"
    assert res_dry["external_reference"] is None, "Safety violation: Invented external ID during DRY_RUN simulation!"
    assert "without sending network request" in res_dry["message"], f"Unexpected confirmation message: {res_dry['message']}"
    print("  ✅ Passed: DRY_RUN mode safely simulates submission without executing external network requests or inventing IDs.")

    print("\n======================================================================")
    print("   🎉 ALL 6 APPLICATION SUBMISSION ADAPTER TESTS PASSED CLEANLY!      ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
