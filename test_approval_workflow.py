"""
test_approval_workflow.py — Automated Test for Notifications + User Approval MVP
================================================================================

Tests:
1. Divergence of SELECT candidates into PENDING_APPROVAL status.
2. Verification that unapproved items never reach the Application Engine.
3. Rejecting an opportunity blocks it forever from submission.
4. Approving an opportunity promotes it to the Application Engine as APPROVED (no auto-submission).
5. Duplicate protection works cleanly against both approved and rejected items.
"""

import sys
import os
import time
import tempfile
import shutil
from engine.application_engine import ApplicationEngine
import engine.application_engine as app_eng_module
from notifications import STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING NOTIFICATIONS + USER APPROVAL MVP WORKFLOW                 ")
    print("======================================================================")

    temp_dir = tempfile.mkdtemp()
    app_eng_module.DATA_DIR = temp_dir
    import notifications.approval_manager as appr_mgr
    appr_mgr.DATA_DIR = temp_dir
    import proposals.proposal_generator as prop_gen
    prop_gen.DATA_DIR = temp_dir
    import models.opportunity as opp_model
    opp_model.DATA_DIR = temp_dir
    
    try:
        engine = ApplicationEngine()
        engine._ensure_files()
        manager = engine.approval_manager
        
        initial_apps_count = len(engine.get_applications())
        initial_appr_count = len(manager.get_all_approvals())
        
        print(f"\n[1/5] Simulating discovery of 2 new high-quality SELECT opportunities...")
        opp_reject = {
            "id": "test_opp_rej_101",
            "platform": "Superteam",
            "title": "[TEST] Solana DeFi Vulnerability Audit (To Be Rejected)",
            "url": "https://earn.superteam.fun/bounties/test-reject-101",
            "reward": 5000.0,
            "currency": "USDC",
            "reward_verified": True,
            "reward_evidence": "API field rewardAmount=5000 token=USDC"
        }
        proposal_reject = "I will perform a comprehensive fuzzing test and smart contract review on the DeFi protocol."
        
        opp_approve = {
            "id": "test_opp_appr_202",
            "platform": "GitHub",
            "title": "[TEST] $3000 Fix Memory Leak in RPC Engine (To Be Approved)",
            "url": "https://github.com/test-org/rpc-engine/issues/202",
            "reward": 3000.0,
            "currency": "USD",
            "reward_verified": True,
            "reward_evidence": "Amount found in title: 3000 USD"
        }
        proposal_approve = "I will trace memory allocations using heap snapshots and fix the leak cleanly."

        # Worker calls create_application_draft when AI evaluates SELECT
        res_1 = engine.create_application_draft(opp_reject, proposal_reject)
        res_2 = engine.create_application_draft(opp_approve, proposal_approve)

        assert res_1.get("approval_status") == STATUS_PENDING, f"Expected {STATUS_PENDING}, got {res_1}"
        assert res_2.get("approval_status") == STATUS_PENDING, f"Expected {STATUS_PENDING}, got {res_2}"
        print("  ✅ Both candidates diverted to PENDING_APPROVAL in approvals storage.")

        print("\n[2/5] Verifying separation from Application Engine (Only approved items may enter)...")
        current_apps = engine.get_applications()
        assert len(current_apps) == initial_apps_count, f"Application count should not have changed (expected {initial_apps_count}, got {len(current_apps)})!"
        print("  ✅ Confirmed: ZERO items reached the Application Engine while in PENDING_APPROVAL.")

        print("\n[3/5] Testing REJECT workflow on Opportunity 1...")
        rej_id = res_1["id"]
        manager.reject(rej_id)
        all_appr = {item["id"]: item for item in manager.get_all_approvals()}
        assert all_appr[rej_id]["approval_status"] == STATUS_REJECTED, "Item was not set to REJECTED!"
        
        # Try to forcibly promote the rejected item
        blocked_promo = engine.promote_approved_opportunity(all_appr[rej_id])
        assert blocked_promo == {}, "Safety violation: Rejected item was promoted!"
        assert len(engine.get_applications()) == initial_apps_count, "Rejected item leaked into applications!"
        print("  ✅ Confirmed: Rejected item status is REJECTED and is permanently blocked from reaching application engine.")

        print("\n[4/5] Testing APPROVE workflow on Opportunity 2...")
        appr_id = res_2["id"]
        manager.approve(appr_id, engine)
        all_appr = {item["id"]: item for item in manager.get_all_approvals()}
        assert all_appr[appr_id]["approval_status"] == STATUS_APPROVED, "Item was not set to APPROVED!"
        
        new_apps = engine.get_applications()
        assert len(new_apps) == initial_apps_count + 1, "Approved item was not promoted to application engine!"
        promoted_app = new_apps[-1]
        assert promoted_app["url"] == opp_approve["url"], "Promoted application URL mismatch!"
        assert promoted_app["status"] == "MANUAL_ACTION_REQUIRED", f"Promoted app status should be MANUAL_ACTION_REQUIRED, got {promoted_app['status']}!"
        assert promoted_app["submitted_at"] is None, "Safety violation: Application was automatically submitted!"
        print("  ✅ Confirmed: Approved item promoted to Application Engine in MANUAL_ACTION_REQUIRED status without automatic submission.")

        print("\n[5/5] Testing Duplicate Protection against Rejections and Approvals...")
        dup_1 = engine.create_application_draft(opp_reject, "new proposal")
        dup_2 = engine.create_application_draft(opp_approve, "new proposal")
        assert dup_1 == {}, "Duplicate created for rejected item!"
        assert dup_2 == {}, "Duplicate created for approved item!"
        print("  ✅ Confirmed: Duplicate protection blocked duplicate proposals for both items.")

        print("\n======================================================================")
        print("   🎉 ALL TESTS PASSED! NOTIFICATIONS + USER APPROVAL MVP WORKFLOW OK ")
        print("======================================================================")
        return 0
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    sys.exit(run_tests())
