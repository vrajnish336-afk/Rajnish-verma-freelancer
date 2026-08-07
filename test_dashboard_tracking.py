"""
test_dashboard_tracking.py — Focused Tests for MVP Dashboard & End-to-End Tracking Layer
========================================================================================

Tests:
1. correct status display (separation of job status vs payment status, formatting of all required attributes)
2. confirmed earnings calculation (comes strictly ONLY from PAYMENT_CONFIRMED records)
3. pending payment not counted as earnings (potential/expected/pending never counted as earned money)
4. filtering (by platform and status)
5. missing data (graceful handling of missing or corrupted data files without exceptions)
"""

import sys
import os
import json
import shutil
import tempfile
from dashboard import DashboardTrackingLayer

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING MVP DASHBOARD & END-TO-END TRACKING LAYER                  ")
    print("======================================================================")
    
    # 1. CORRECT STATUS DISPLAY & ATTRIBUTE NORMALIZATION
    print("\n[1/5] Testing Correct Status Display & Attribute Normalization...")
    tracker = DashboardTrackingLayer()
    raw_item = {
        "id": "item_001",
        "platform": "Superteam",
        "title": "[TEST] Solana DeFi Audit",
        "url": "https://earn.superteam.fun/audit-001",
        "reward": "4500.0",
        "currency": "USDC",
        "reward_verified": True,
        "status": "ACCEPTED",
        "payment_status": "PAYMENT_PENDING",
        "deadline": "2026-11-30",
        "profit_score": 88.5,
        "created_at": "2026-08-01T10:00:00Z"
    }
    normalized = tracker.normalize_item(raw_item)
    assert normalized["platform"] == "Superteam", "Platform mismatch!"
    assert normalized["title"] == "[TEST] Solana DeFi Audit", "Title mismatch!"
    assert normalized["reward"] == 4500.0, f"Reward not converted to float: {normalized['reward']}"
    assert normalized["reward_verified"] is True, "Reward verification flag mismatch!"
    assert normalized["status"] == "ACCEPTED", f"Job status mismatch: {normalized['status']}"
    assert normalized["payment_status"] == "PAYMENT_PENDING", f"Payment status mismatch: {normalized['payment_status']}"
    assert normalized["deadline"] == "2026-11-30", "Deadline mismatch!"
    assert normalized["profit_score"] == 88.5, "Profit score mismatch!"
    assert normalized["created_at"] == "2026-08-01T10:00:00Z", "Timestamp mismatch!"
    print("  ✅ Passed: All attributes cleanly exposed; job status and payment status remain explicitly separated.")

    # 2. CONFIRMED EARNINGS CALCULATION (STRICTLY FROM PAYMENT_CONFIRMED)
    print("\n[2/5] Testing Confirmed Earnings Calculation...")
    mock_sections_confirmed = {
        "New Opportunities": [],
        "Pending Approval": [],
        "Applications": [],
        "Accepted Work": [],
        "Work Completed": [],
        "Pending Payments": [],
        "Confirmed Earnings": [
            {
                "id": "conf_01",
                "reward": 5000.0,
                "actual_amount_received": 5000.0,
                "status": "COMPLETED",
                "payment_status": "PAYMENT_CONFIRMED",
                "transaction_hash": "0xtx_real_hash_111"
            }
        ]
    }
    metrics = tracker.get_financial_metrics(mock_sections_confirmed)
    assert metrics["Confirmed Earnings"] == 5000.0, f"Expected 5000.0 Confirmed Earnings, got {metrics['Confirmed Earnings']}!"
    assert metrics["Owner Confirmed Earnings"] == 3500.0, f"Expected 3500.0 Owner Confirmed Earnings, got {metrics['Owner Confirmed Earnings']}!"
    assert metrics["Agent Confirmed Earnings"] == 1500.0, f"Expected 1500.0 Agent Confirmed Earnings, got {metrics['Agent Confirmed Earnings']}!"
    print("  ✅ Passed: Confirmed Earnings accurately calculated strictly from PAYMENT_CONFIRMED records, with exact 70/30 split.")

    # 3. PENDING PAYMENT & POTENTIAL REWARDS NOT COUNTED AS EARNINGS
    print("\n[3/5] Testing Pending & Potential Rewards Never Counted as Earnings...")
    mock_sections_unconfirmed = {
        "New Opportunities": [{"id": "opp_1", "reward": 15000.0, "status": "NEW", "payment_status": "PAYMENT_UNKNOWN"}],
        "Pending Approval": [{"id": "appr_1", "reward": 8000.0, "status": "PENDING_APPROVAL", "payment_status": "PAYMENT_UNKNOWN"}],
        "Applications": [{"id": "app_1", "reward": 3000.0, "status": "SUBMITTED", "payment_status": "PAYMENT_UNKNOWN"}],
        "Accepted Work": [{"id": "acc_1", "reward": 7000.0, "status": "ACCEPTED", "payment_status": "PAYMENT_UNKNOWN"}],
        "Work Completed": [],
        "Pending Payments": [{"id": "pay_1", "reward": 12000.0, "status": "COMPLETED", "payment_status": "PAYMENT_PENDING"}],
        "Confirmed Earnings": []
    }
    metrics_unconf = tracker.get_financial_metrics(mock_sections_unconfirmed)
    assert metrics_unconf["Potential Rewards"] == 23000.0, f"Potential mismatch: {metrics_unconf['Potential Rewards']}"
    assert metrics_unconf["Applied Value"] == 3000.0, f"Applied mismatch: {metrics_unconf['Applied Value']}"
    assert metrics_unconf["Accepted Value"] == 7000.0, f"Accepted mismatch: {metrics_unconf['Accepted Value']}"
    assert metrics_unconf["Confirmed Earnings"] == 0.0, f"Safety violation: Confirmed Earnings jumped to {metrics_unconf['Confirmed Earnings']} without verified confirmation!"
    print("  ✅ Passed: Potential rewards, applied value, accepted work, and pending payments are NEVER counted as Confirmed Earnings.")

    # 4. FILTERING BY PLATFORM AND STATUS
    print("\n[4/5] Testing Dashboard Filtering (Platform & Status)...")
    test_items = [
        {"id": "1", "platform": "GitHub", "status": "SUBMITTED", "title": "Job A"},
        {"id": "2", "platform": "Superteam", "status": "ACCEPTED", "title": "Job B"},
        {"id": "3", "platform": "GitHub", "status": "ACCEPTED", "title": "Job C"},
        {"id": "4", "platform": "Upwork", "status": "SUBMITTED", "title": "Job D"},
    ]
    f1 = tracker.filter_items(test_items, platform_filter="GitHub", status_filter="All")
    assert len(f1) == 2 and all(i["platform"] == "GitHub" for i in f1), "Platform filtering failed!"
    
    f2 = tracker.filter_items(test_items, platform_filter="All", status_filter="ACCEPTED")
    assert len(f2) == 2 and all(i["status"] == "ACCEPTED" for i in f2), "Status filtering failed!"

    f3 = tracker.filter_items(test_items, platform_filter="GitHub", status_filter="ACCEPTED")
    assert len(f3) == 1 and f3[0]["id"] == "3", f"Combined filtering failed: {f3}"
    print("  ✅ Passed: Multi-dimension filtering by platform and job status functions accurately.")

    # 5. GRACEFUL MISSING & CORRUPTED DATA HANDLING
    print("\n[5/5] Testing Graceful Missing & Corrupted Data Handling...")
    temp_dir = tempfile.mkdtemp()
    try:
        corrupted_tracker = DashboardTrackingLayer(data_dir=temp_dir)
        # 1. Test completely missing files (should not crash, return empty lists/sections)
        sections_empty = corrupted_tracker.get_dashboard_sections()
        for sec_name, sec_list in sections_empty.items():
            assert sec_list == [], f"Expected empty list for missing data in {sec_name}, got {sec_list}"

        # 2. Test corrupted / invalid syntax JSON files
        bad_file = os.path.join(temp_dir, "opportunities.json")
        with open(bad_file, "w") as fh:
            fh.write("}{INVALID_JSON_CORRUPTED_FILE!!![[@#")
        
        # Load sections again; should intercept JSONDecodeError gracefully and return []
        sections_corrupted = corrupted_tracker.get_dashboard_sections()
        assert sections_corrupted["New Opportunities"] == [], "Failed to handle corrupted JSON gracefully!"
        metrics_corrupt = corrupted_tracker.get_financial_metrics(sections_corrupted)
        assert metrics_corrupt["Confirmed Earnings"] == 0.0, "Metrics calculation failed on empty/corrupted data!"
        print("  ✅ Passed: Missing and corrupted JSON files handled cleanly without throwing uncaught exceptions.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n======================================================================")
    print("   🎉 ALL 5 MVP DASHBOARD & TRACKING LAYER TESTS PASSED CLEANLY!      ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
