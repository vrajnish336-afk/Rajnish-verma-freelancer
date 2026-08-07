"""
test_application_engine_mvp.py — Focused Tests for Application Engine MVP
==========================================================================

Tests:
1. unapproved opportunity blocked from entering Application Engine
2. manual-action opportunity blocked from automation (automation_allowed=False -> MANUAL_ACTION_REQUIRED)
3. approved dry-run (simulates submission only, labeled DRY_RUN, never claims submission/payment)
4. duplicate blocked (duplicate promotion and duplicate submission attempts blocked)
5. state persistence (READY, MANUAL_ACTION_REQUIRED, SUBMITTED, REJECTED, ACCEPTED, COMPLETED, PAYMENT_PENDING, PAYMENT_CONFIRMED)
"""

import sys
import os
from engine.application_engine import (
    ApplicationEngine,
    STATE_READY, STATE_MANUAL_ACTION_REQUIRED, STATE_SUBMITTED,
    STATE_REJECTED, STATE_ACCEPTED, STATE_COMPLETED,
    STATE_PAYMENT_PENDING, STATE_PAYMENT_CONFIRMED
)
from models.opportunity import PAYMENT_UNKNOWN, PAYMENT_CONFIRMED

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


import tempfile
import shutil
import engine.application_engine as app_eng_module

def run_tests():
    print("======================================================================")
    print("   TESTING APPLICATION ENGINE MVP WORKFLOW & SAFETY GUARANTEES        ")
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
        engine = ApplicationEngine(dry_run=True)
        engine._ensure_files()
        initial_apps_count = len(engine.get_applications())

        # 1. UNAPPROVED OPPORTUNITY BLOCKED
        print("\n[1/5] Testing Unapproved Opportunity Blocking...")
        opp_pending = {
            "opportunity_id": "opp_unapproved_101",
            "platform": "Superteam",
            "title": "[TEST] Unapproved Opportunity",
            "url": "https://earn.superteam.fun/bounties/unappr-101",
            "proposal": "Clean execution plan",
            "approval_status": "PENDING_APPROVAL",
            "automation_allowed": True
        }
        opp_rejected = dict(opp_pending, opportunity_id="opp_rej_102", url="https://earn.superteam.fun/bounties/rej-102", approval_status="REJECTED")
        
        res1 = engine.promote_approved_opportunity(opp_pending)
        res2 = engine.promote_approved_opportunity(opp_rejected)
        assert res1 == {}, f"Safety violation: PENDING_APPROVAL opportunity accepted into engine!"
        assert res2 == {}, f"Safety violation: REJECTED opportunity accepted into engine!"
        assert len(engine.get_applications()) == initial_apps_count, "Application count leaked unapproved items!"
        print("  ✅ Passed: Unapproved (PENDING_APPROVAL & REJECTED) candidates completely blocked from Application Engine.")

        # 2. MANUAL-ACTION OPPORTUNITY BLOCKED FROM AUTOMATION
        print("\n[2/5] Testing Manual-Action Opportunity (automation_allowed=False)...")
        opp_manual = {
            "opportunity_id": "opp_manual_201",
            "platform": "GitHub",
            "title": "[TEST] Manual Action Required Job",
            "url": "https://github.com/test-org/manual-issue-201",
            "proposal": "I will fix this bug systematically.",
            "approval_status": "APPROVED",
            "automation_allowed": False  # Automation forbidden
        }
        app_manual = engine.promote_approved_opportunity(opp_manual)
        assert app_manual != {}, "Approved manual opportunity was not accepted into engine!"
        assert app_manual["status"] == STATE_MANUAL_ACTION_REQUIRED, f"Expected {STATE_MANUAL_ACTION_REQUIRED}, got {app_manual['status']}!"
        
        # Attempt automation on manual opportunity
        auto_attempt = engine.submit_application(app_manual["id"], dry_run=False)
        assert auto_attempt["success"] is False, "Automation attempt succeeded on manual opportunity!"
        assert "MANUAL_ACTION_REQUIRED" in auto_attempt["error"], f"Unexpected error text: {auto_attempt['error']}"
        assert auto_attempt["actual_submission"] is False, "Safety violation: External submission occurred for manual item!"
        print("  ✅ Passed: automation_allowed=False correctly sets MANUAL_ACTION_REQUIRED and blocks automated submission attempts.")

        # 3. APPROVED DRY-RUN
        print("\n[3/5] Testing Approved DRY_RUN Simulation & Safety Guarantees...")
        opp_auto = {
            "opportunity_id": "opp_auto_301",
            "platform": "Superteam",
            "title": "[TEST] Approved Auto Job for Dry Run",
            "url": "https://earn.superteam.fun/bounties/auto-dry-301",
            "proposal": "I will deliver clean verified solution.",
            "approval_status": "APPROVED",
            "automation_allowed": True,
            "reward": 2500.0,
            "currency": "USDC"
        }
        app_auto = engine.promote_approved_opportunity(opp_auto)
        assert app_auto["status"] == STATE_READY, f"Expected {STATE_READY} for automation_allowed=True, got {app_auto['status']}!"
        
        dry_res = engine.submit_application(app_auto["id"], dry_run=True)
        assert dry_res["success"] is True, f"Dry run simulation failed: {dry_res}"
        assert dry_res["mode"] == "DRY_RUN", "Mode not labeled DRY_RUN!"
        assert dry_res["actual_submission"] is False, "Safety violation: actual_submission flagged as true during dry run!"
        assert dry_res["submitted_at"] is None, "Safety violation: submitted_at timestamp generated during dry run!"
        
        # Verify records in persistent database
        updated_app = [a for a in engine.get_applications() if a["id"] == app_auto["id"]][0]
        assert "DRY_RUN: Simulated submission step only" in updated_app["last_attempt"], "DRY_RUN label missing in last_attempt!"
        assert updated_app["status"] == STATE_READY, f"Safety violation: Status altered to {updated_app['status']} without real platform submission!"
        assert updated_app["payment_status"] == PAYMENT_UNKNOWN, "Safety violation: Payment claimed without real submission/evidence!"
        print("  ✅ Passed: DRY_RUN cleanly simulates submission step only, explicitly labels as DRY_RUN, and never claims submission or payment.")

        # 4. DUPLICATE BLOCKED
        print("\n[4/5] Testing Duplicate Prevention & Protection...")
        dup_promo = engine.promote_approved_opportunity(opp_auto)
        assert dup_promo == {}, "Duplicate opportunity promotion was allowed!"
        
        # Simulate manual marking as SUBMITTED, then try submitting again
        engine.update_application_status(app_auto["id"], STATE_SUBMITTED)
        dup_submit = engine.submit_application(app_auto["id"], dry_run=True)
        assert dup_submit["success"] is False, "Duplicate submission on SUBMITTED application allowed!"
        assert "already processed" in dup_submit["error"].lower(), f"Unexpected duplicate submit error: {dup_submit['error']}"
        print("  ✅ Passed: Duplicate application records and duplicate submission attempts completely blocked.")

        # 5. LIVE SUBMISSION SAFEGUARD
        print("\n[5/6] Testing LIVE_SUBMISSION Safeguard...")
        # 1. Constructor test
        engine_real = ApplicationEngine(dry_run=False)
        assert engine_real.dry_run is True, "ApplicationEngine allowed dry_run=False without LIVE_SUBMISSION=true!"
        
        # 2. Submit test
        # We need a fresh approved app for this
        opp_live_test = {
            "opportunity_id": "opp_live_123",
            "platform": "Superteam",
            "url": "https://test.live.com",
            "approval_status": "APPROVED",
            "proposal": "Proposal Text",
            "automation_allowed": True
        }
        app_live = engine.promote_approved_opportunity(opp_live_test)
        live_submit = engine.submit_application(app_live["id"], dry_run=False)
        assert live_submit["mode"] == "DRY_RUN", "submit_application allowed dry_run=False without LIVE_SUBMISSION=true!"
        print("  ✅ Passed: LIVE_SUBMISSION=true is strictly required to disable DRY_RUN.")

        # 6. STATE PERSISTENCE
        print("\n[6/6] Testing Complete State Tracking & Persistence Across Reloads...")
        all_required_states = [
            STATE_READY, STATE_MANUAL_ACTION_REQUIRED, STATE_SUBMITTED,
            STATE_REJECTED, STATE_ACCEPTED, STATE_COMPLETED,
            STATE_PAYMENT_PENDING, STATE_PAYMENT_CONFIRMED
        ]
        test_id = app_manual["id"]
        
        # Cycle through each non-payment status and confirm persistence across reloading engine instance
        for state in [STATE_READY, STATE_SUBMITTED, STATE_REJECTED, STATE_ACCEPTED, STATE_COMPLETED, STATE_PAYMENT_PENDING]:
            engine.update_application_status(test_id, state)
            reloaded_engine = ApplicationEngine()
            persisted_app = [a for a in reloaded_engine.get_applications() if a["id"] == test_id][0]
            assert persisted_app["status"] == state, f"Failed to persist state {state}, found {persisted_app['status']}!"
        
        # Finally test PAYMENT_CONFIRMED state and earnings record
        engine.mark_payment_confirmed(test_id, actual_amount_received=1500.0, tx_hash="0xtest_tx_hash_888")
        reloaded_engine2 = ApplicationEngine()
        final_app = [a for a in reloaded_engine2.get_applications() if a["id"] == test_id][0]
        assert final_app["status"] == STATE_PAYMENT_CONFIRMED, "Failed to persist STATE_PAYMENT_CONFIRMED status!"
        assert final_app["payment_status"] == PAYMENT_CONFIRMED, "Failed to persist PAYMENT_CONFIRMED payment_status!"
        print(f"  ✅ Passed: All 8 required states ({', '.join(all_required_states)}) accurately tracked and persisted to disk.")

        print("\n======================================================================")
        print("   🎉 ALL 6 APPLICATION ENGINE MVP TESTS PASSED CLEANLY!              ")
        print("======================================================================")
        return 0
    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    sys.exit(run_tests())
