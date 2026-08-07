"""
test_monitoring_system.py — Focused Tests for Daily Summary & System Health Monitoring MVP
=============================================================================================

Tests:
1. daily summary calculation (accurate aggregation across all 10 required metric categories)
2. zero activity day (clean reporting of zeroed statistics without errors or crashes)
3. confirmed earnings calculation (strictly counts only confirmed payments with real evidence)
4. component failure detection (never reports healthy unless last check actually succeeded)
5. repeated failure alert prevention (suppression of duplicate spam for identical failure alerts)
6. notification failure (safe, graceful handling of broken or offline notification services)
"""

import sys
import os
import json
import shutil
import tempfile
from monitoring import DailySummaryGenerator, SystemHealthTracker, STATUS_HEALTHY, STATUS_UNHEALTHY, STATUS_UNKNOWN

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class MockWorkingNotifier:
    def __init__(self):
        self.sent_alerts = []

    def notify(self, event_type, item_data, message_override=None, deduplication_key=None, http_client=None):
        self.sent_alerts.append({"event": event_type, "data": item_data, "text": message_override, "key": deduplication_key})
        return {"success": True, "sent": True, "throttled": False}


class MockBrokenNotifier:
    def notify(self, *args, **kwargs):
        raise RuntimeError("Intended test exception: Telegram API offline / connection timed out.")


def run_tests():
    print("======================================================================")
    print("   TESTING DAILY SUMMARY & SYSTEM HEALTH MONITORING MVP               ")
    print("======================================================================")

    temp_dir = tempfile.mkdtemp()
    try:
        # Create mock data files in temporary folder to verify summary aggregation
        opps_data = [
            {"id": "o1", "timestamp": "2026-08-06T10:00:00Z", "reward": "1000", "reward_verified": True},
            {"id": "o2", "timestamp": "2026-08-06T11:00:00Z", "reward": "2000", "reward_verified": True},
            {"id": "o3", "timestamp": "2026-08-06T12:00:00Z", "reward": "500", "reward_verified": False},
        ]
        apps_data = [
            {"id": "a1", "timestamp": "2026-08-06T13:00:00Z", "status": "SUBMITTED", "reward": 1000, "payment_status": "PAYMENT_UNKNOWN"},
            {"id": "a2", "timestamp": "2026-08-06T14:00:00Z", "status": "ACCEPTED", "reward": 3000, "payment_status": "PAYMENT_UNKNOWN"},
            {"id": "a3", "timestamp": "2026-08-06T15:00:00Z", "status": "REJECTED", "reward": 1500, "payment_status": "PAYMENT_UNKNOWN"},
            {"id": "a4", "timestamp": "2026-08-06T16:00:00Z", "status": "COMPLETED", "reward": 8000, "payment_status": "PAYMENT_PENDING"},
            {"id": "a5", "timestamp": "2026-08-06T17:00:00Z", "status": "COMPLETED", "reward": 5000, "actual_amount_received": 5000, "payment_status": "PAYMENT_CONFIRMED", "transaction_hash": "0x_confirmed_tx_888"},
        ]
        with open(os.path.join(temp_dir, "opportunities.json"), "w") as f: json.dump(opps_data, f)
        with open(os.path.join(temp_dir, "applications.json"), "w") as f: json.dump(apps_data, f)
        with open(os.path.join(temp_dir, "payments_log.json"), "w") as f: json.dump({"records": []}, f)
        with open(os.path.join(temp_dir, "approvals.json"), "w") as f: json.dump([], f)

        summary_gen = DailySummaryGenerator(data_dir=temp_dir)

        # 1. DAILY SUMMARY CALCULATION
        print("\n[1/6] Testing Daily Summary Calculation (10 Core Metrics)...")
        res_sum = summary_gen.generate_summary(target_date="2026-08-06")
        assert res_sum["opportunities_discovered"] == 3, f"Opps discovered mismatch: {res_sum['opportunities_discovered']}"
        assert res_sum["verified_paid_opportunities"] == 2, f"Verified opps mismatch: {res_sum['verified_paid_opportunities']}"
        assert res_sum["applications_submitted"] == 1, "Submitted mismatch!"
        assert res_sum["applications_accepted"] == 1, "Accepted mismatch!"
        assert res_sum["applications_rejected"] == 1, "Rejected mismatch!"
        assert res_sum["active_work"] == 1, "Active work mismatch!"
        assert res_sum["completed_work"] == 2, f"Completed mismatch: {res_sum['completed_work']}"
        assert res_sum["pending_payments"] == 1, "Pending payments mismatch!"
        assert res_sum["confirmed_payments"] == 1, "Confirmed payments mismatch!"
        assert res_sum["confirmed_earnings"] == 5000.0, f"Confirmed earnings mismatch: {res_sum['confirmed_earnings']}"
        print("  ✅ Passed: All 10 daily operational and financial summary statistics aggregated accurately.")

        # 2. ZERO ACTIVITY DAY
        print("\n[2/6] Testing Zero Activity Day Handling...")
        res_zero = summary_gen.generate_summary(target_date="2099-01-01")
        assert res_zero["opportunities_discovered"] == 0
        assert res_zero["confirmed_payments"] == 0
        assert res_zero["confirmed_earnings"] == 0.0
        print("  ✅ Passed: Zero activity dates return clean zeroed totals without raising errors.")

        # 3. CONFIRMED EARNINGS CALCULATION INTEGRITY
        print("\n[3/6] Testing Confirmed Earnings Calculation & Isolation...")
        # Notice total expected value in dataset exceeds $18,000, but ONLY the verified $5,000 receipt is counted
        assert res_sum["confirmed_earnings"] == 5000.0, "Potential or pending rewards incorrectly added to earnings!"
        report_msg = summary_gen.format_report_text(res_sum)
        assert "$5,000.00" in report_msg and "strictly verified receipts with transaction hash evidence" in report_msg
        print("  ✅ Passed: Confirmed earnings strictly restrict accounting to verified PAYMENT_CONFIRMED records.")

        # 4. COMPONENT FAILURE DETECTION
        print("\n[4/6] Testing Component Failure Detection & Status Rules...")
        health_file = os.path.join(temp_dir, "test_health.json")
        tracker = SystemHealthTracker(cache_file=health_file)
        
        # Initial check
        assert tracker.get_health_status("cloud_scanner")["current_status"] == STATUS_UNKNOWN
        
        # Record failure
        f_rec1 = tracker.record_failure("cloud_scanner", "Connection timed out to GitHub API", threshold=2)
        assert f_rec1["current_status"] == STATUS_UNHEALTHY, "Status did not transition immediately to UNHEALTHY!"
        assert f_rec1["last_failure"] is not None, "Last failure timestamp omitted!"
        assert tracker.get_health_status("cloud_scanner")["current_status"] == STATUS_UNHEALTHY, "Failed component falsely reported as healthy!"
        print("  ✅ Passed: Failed components immediately transition to UNHEALTHY; never reported healthy unless check succeeds.")

        # 5. REPEATED FAILURE ALERT PREVENTION (SUPPRESSION)
        print("\n[5/6] Testing Repeated Failure Alert Prevention (Deduplication)...")
        working_notifier = MockWorkingNotifier()
        
        # Second failure (reaches threshold=2, should trigger alert)
        f_rec2 = tracker.record_failure("cloud_scanner", "Connection timed out to GitHub API", notifier=working_notifier, threshold=2)
        assert f_rec2["consecutive_failures"] == 2
        assert f_rec2["alert_info"]["triggered"] is True, f"Failed to trigger alert on threshold breach! {f_rec2['alert_info']}"
        assert len(working_notifier.sent_alerts) == 1, "Alert not sent via notifier!"
        
        # Third and Fourth failure with exact same error message (should NOT trigger extra alerts)
        f_rec3 = tracker.record_failure("cloud_scanner", "Connection timed out to GitHub API", notifier=working_notifier, threshold=2)
        f_rec4 = tracker.record_failure("cloud_scanner", "Connection timed out to GitHub API", notifier=working_notifier, threshold=2)
        assert f_rec4["alert_info"]["triggered"] is False, "Duplicate repeat alert was sent! Suppression failed!"
        assert len(working_notifier.sent_alerts) == 1, f"Repeated alerts flooded notifier! Total alerts sent: {len(working_notifier.sent_alerts)}"
        assert "suppressed" in f_rec4["alert_info"]["reason"].lower() or "already notified" in f_rec4["alert_info"]["reason"].lower()
        print("  ✅ Passed: Threshold breach triggers alert once; subsequent repeat failures with identical error are cleanly suppressed.")

        # 6. NOTIFICATION FAILURE GRACEFUL HANDLING
        print("\n[6/6] Testing Graceful Handling of Notification Service Failure...")
        broken_notifier = MockBrokenNotifier()
        
        # Test sending daily summary through crashing notifier
        sum_res = summary_gen.send_daily_summary(notifier=broken_notifier, target_date="2026-08-06")
        assert sum_res["success"] is False, "Did not report send failure!"
        assert sum_res["sent"] is False, "Reported sent despite crashing notifier!"
        assert "Intended test exception" in sum_res.get("error", "") or "Telegram API offline" in str(sum_res), "Error string not caught!"
        
        # Test recording subsystem threshold failure through crashing notifier
        health_res = tracker.record_failure("local_worker", "Disk quota exceeded", notifier=broken_notifier, threshold=1)
        assert health_res["current_status"] == STATUS_UNHEALTHY, "Health status failed to record when notifier crashed!"
        assert "graceful" in health_res["alert_info"]["reason"].lower() or "handled" in health_res["alert_info"]["reason"].lower(), f"Unexpected alert reason: {health_res['alert_info']}"
        print("  ✅ Passed: Crashing or offline notification providers are caught gracefully without raising uncaught exceptions.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n======================================================================")
    print("   🎉 ALL 6 DAILY SUMMARY & HEALTH MONITORING TESTS PASSED CLEANLY!  ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
