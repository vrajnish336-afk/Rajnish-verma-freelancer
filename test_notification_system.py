"""
test_notification_system.py — Focused Tests for Notification System MVP (Telegram Provider)
=============================================================================================

Tests:
1. notification disabled (normal execution continues)
2. notification configured (sends alert without hardcoding or leaking secret tokens)
3. missing credentials (safe degradation without uncaught exceptions)
4. duplicate notification prevention (throttling against spam on repeated scan cycles)
5. payment notification correctness (never calls potential reward an earning; only PAYMENT_CONFIRMED uses confirmed earnings)
"""

import sys
import os
import json
import tempfile
import shutil
from notifications import (
    TelegramNotifier,
    EVENT_NEW_OPPORTUNITY,
    EVENT_APPROVAL_REQUIRED,
    EVENT_APPLICATION_SUBMITTED,
    EVENT_APPLICATION_ACCEPTED,
    EVENT_APPLICATION_REJECTED,
    EVENT_WORK_COMPLETED,
    EVENT_PAYMENT_PENDING,
    EVENT_PAYMENT_CONFIRMED,
    EVENT_SYSTEM_FAILURE
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING NOTIFICATION SYSTEM MVP (TELEGRAM PROVIDER & INTEGRITY)   ")
    print("======================================================================")

    temp_dir = tempfile.mkdtemp()
    cache_file = os.path.join(temp_dir, "test_sent_notifications.json")

    try:
        # 1. NOTIFICATION DISABLED
        print("\n[1/5] Testing Notification Disabled State...")
        notifier_dis = TelegramNotifier(enabled=False, cache_file=cache_file)
        res_dis = notifier_dis.notify(EVENT_NEW_OPPORTUNITY, {"id": "1", "title": "Test Job"})
        assert res_dis["sent"] is False, "Notification sent despite being disabled!"
        assert res_dis["success"] is False, "Flagged as success when disabled!"
        assert "disabled" in res_dis["reason"].lower() or "unconfigured" in res_dis["reason"].lower(), "Reason message mismatch!"
        print("  ✅ Passed: When notifications are disabled, normal execution continues silently without attempts to send.")

        # 2. NOTIFICATION CONFIGURED & SAFE TOKEN PROTECTION
        print("\n[2/5] Testing Notification Configured & Token Suppression...")
        os.environ["TELEGRAM_BOT_TOKEN"] = "secret_mock_bot_token_9999"
        os.environ["TELEGRAM_CHAT_ID"] = "-100123456789"
        
        notifier_conf = TelegramNotifier(cache_file=cache_file)
        assert notifier_conf.enabled is True, "Notifier failed to auto-enable upon finding valid environment variables!"

        def mock_telegram_api(url, payload):
            assert "secret_mock_bot_token_9999" in url, "Target API URL did not use token!"
            assert payload["chat_id"] == "-100123456789", "Chat ID mismatch!"
            # Return Telegram success payload
            return 200, {"ok": True, "result": {"message_id": 42}}

        res_conf = notifier_conf.notify(
            EVENT_APPROVAL_REQUIRED,
            {"id": "opp_appr_01", "title": "Solana Fuzzing", "platform": "Superteam", "reward": 4000.0, "currency": "USDC"},
            http_client=mock_telegram_api
        )
        assert res_conf["sent"] is True, f"Configured notification failed: {res_conf}"
        assert "secret_mock_bot_token_9999" not in str(res_conf["formatted_text"]), "Security fault: Bot token leaked into message output!"
        print("  ✅ Passed: Configured Telegram provider sends verified alerts while safeguarding secret tokens.")

        # 3. MISSING CREDENTIALS SAFE DEGRADATION
        print("\n[3/5] Testing Missing Credentials Safe Degradation...")
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
        
        notifier_nocred = TelegramNotifier(enabled=None, cache_file=cache_file)
        assert notifier_nocred.enabled is False, "Notifier enabled without credentials!"
        res_nocred = notifier_nocred.notify(EVENT_APPLICATION_SUBMITTED, {"id": "app_sub_01", "title": "GitHub Fix"})
        assert res_nocred["sent"] is False, "Sent without credentials!"
        assert "unconfigured or disabled" in res_nocred["reason"].lower(), f"Unexpected reason text: {res_nocred.get('reason')}"
        print("  ✅ Passed: Missing environment variables cleanly degrade without raising exceptions or breaking application flow.")

        # Re-establish environment tokens for remaining tests
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token_888"
        os.environ["TELEGRAM_CHAT_ID"] = "test_chat_id_777"
        notifier_active = TelegramNotifier(cache_file=cache_file)

        # 4. DUPLICATE NOTIFICATION PREVENTION (THROTTLING AGAINST SPAM)
        print("\n[4/5] Testing Duplicate Notification Prevention (Throttling against Spam)...")
        test_opp = {"id": "opp_throttle_001", "title": "Repeat Bounty Listing", "platform": "GitHub", "reward": 1000.0}
        
        # First send
        res_first = notifier_active.notify(EVENT_NEW_OPPORTUNITY, test_opp, http_client=lambda u, p: (200, {"ok": True}))
        assert res_first["sent"] is True and res_first["throttled"] is False, f"First alert failed: {res_first}"

        # Immediately send exact same item (simulating repeated scan cycle)
        res_dup = notifier_active.notify(EVENT_NEW_OPPORTUNITY, test_opp, http_client=lambda u, p: (200, {"ok": True}))
        assert res_dup["sent"] is False, "Duplicate notification sent! Throtling bypassed!"
        assert res_dup["throttled"] is True, "throttled flag not set to True!"
        assert "suppressed by throttle" in res_dup["reason"].lower(), f"Unexpected reason: {res_dup.get('reason')}"
        print("  ✅ Passed: Repeated scan cycles attempting to spam identical alerts are cleanly intercepted and throttled.")

        # 5. PAYMENT NOTIFICATION CORRECTNESS (TRUTH-IN-REPORTING)
        print("\n[5/5] Testing Payment Notification Correctness & Truth-in-Reporting...")
        # 1: Unconfirmed events must never describe potential rewards as earnings
        unconfirmed_events = [EVENT_NEW_OPPORTUNITY, EVENT_APPROVAL_REQUIRED, EVENT_APPLICATION_SUBMITTED, EVENT_WORK_COMPLETED, EVENT_PAYMENT_PENDING]
        for evt in unconfirmed_events:
            text_unconf = notifier_active._format_message(evt, {"title": f"Test {evt}", "reward": 5000.0, "currency": "USD", "platform": "GitHub"})
            assert "Confirmed Earnings" not in text_unconf and "confirmed earnings" not in text_unconf.lower(), f"Safety violation: Used 'confirmed earnings' in {evt} alert!\n{text_unconf}"
            assert "Earned Money" not in text_unconf, f"Safety violation: Used 'Earned Money' in {evt}!"
            
        # 2: PAYMENT_CONFIRMED must specifically describe the receipt as confirmed earnings
        conf_data = {
            "title": "Solana Vault Audit",
            "platform": "Superteam",
            "reward": 7500.0,
            "actual_amount_received": 7500.0,
            "currency": "USDC",
            "transaction_hash": "0x_real_telegram_tx_evidence_hash_999"
        }
        text_conf = notifier_active._format_message(EVENT_PAYMENT_CONFIRMED, conf_data)
        assert "Confirmed Earnings" in text_conf or "Confirmed Payment Received" in text_conf, f"Failed to use proper confirmation terminology in PAYMENT_CONFIRMED:\n{text_conf}"
        assert "0x_real_telegram_tx_evidence_hash_999" in text_conf, "Transaction evidence missing from confirmation alert!"
        print("  ✅ Passed: Payment notifications strictly distinguish potential/pending rewards from Confirmed Earnings.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n======================================================================")
    print("   🎉 ALL 5 NOTIFICATION SYSTEM MVP TESTS PASSED CLEANLY!             ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
