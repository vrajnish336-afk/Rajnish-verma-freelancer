"""
test_payment_tracking.py — Focused Tests for Payment Tracking and Earnings Integrity MVP
========================================================================================

Tests:
1. unknown payment -> earnings unchanged
2. pending payment -> earnings unchanged
3. confirmed payment -> earnings increases once
4. duplicate confirmation -> no double counting
5. partial payment (without incorrectly marking the full reward as received)
6. missing transaction evidence (remains PAYMENT_UNKNOWN / PAYMENT_PENDING, hash remains null)
"""

import sys
import os
import json
from payments import PaymentTracker, PAYMENT_UNKNOWN, PAYMENT_PENDING, PAYMENT_CONFIRMED

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING PAYMENT TRACKING AND EARNINGS INTEGRITY MVP                ")
    print("======================================================================")
    
    # Initialize tracker and wipe payments_log for clean isolated testing
    tracker = PaymentTracker()
    with open(tracker.payments_file, "w", encoding="utf-8") as fh:
        json.dump({"records": [], "confirmed_tx_hashes": []}, fh)

    # 1. UNKNOWN PAYMENT -> EARNINGS UNCHANGED
    print("\n[1/6] Testing PAYMENT_UNKNOWN (Earnings Unchanged)...")
    app_id_1 = "app_test_unknown_001"
    tracker.register_expected_reward(app_id_1, expected_amount=5000.0, currency="USDC", source="Superteam", initial_status=PAYMENT_UNKNOWN)
    
    summary1 = tracker.get_financial_summary()
    confirmed_usdc = summary1["confirmed_earnings"].get("USDC", 0.0)
    assert confirmed_usdc == 0.0, f"Safety violation: PAYMENT_UNKNOWN increased confirmed earnings to {confirmed_usdc}!"
    print("  ✅ Passed: expected reward registered under PAYMENT_UNKNOWN leaves confirmed earnings untouched at 0.0.")

    # 2. PENDING PAYMENT -> EARNINGS UNCHANGED
    print("\n[2/6] Testing PAYMENT_PENDING (Earnings Unchanged)...")
    tracker.set_payment_status(app_id_1, PAYMENT_PENDING)
    summary2 = tracker.get_financial_summary()
    confirmed_usdc2 = summary2["confirmed_earnings"].get("USDC", 0.0)
    assert confirmed_usdc2 == 0.0, f"Safety violation: PAYMENT_PENDING increased confirmed earnings to {confirmed_usdc2}!"
    print("  ✅ Passed: transitioning to PAYMENT_PENDING leaves confirmed earnings unchanged at 0.0.")

    # 3. CONFIRMED PAYMENT -> EARNINGS INCREASES ONCE
    print("\n[3/6] Testing PAYMENT_CONFIRMED (Earnings Increases Once)...")
    tx_hash_real = "0x9a8b7c6d5e4f3a2b1c_real_evidence_hash"
    res_conf = tracker.record_payment(app_id_1, amount_received=5000.0, currency="USDC", source="Superteam", transaction_hash=tx_hash_real)
    assert res_conf["success"] is True, f"Failed to confirm valid payment: {res_conf}"
    assert res_conf["status"] == PAYMENT_CONFIRMED, f"Expected {PAYMENT_CONFIRMED}, got {res_conf['status']}!"
    
    summary3 = tracker.get_financial_summary()
    confirmed_usdc3 = summary3["confirmed_earnings"].get("USDC", 0.0)
    assert confirmed_usdc3 == 5000.0, f"Expected 5000.0 USDC confirmed, got {confirmed_usdc3}!"
    print(f"  ✅ Passed: PAYMENT_CONFIRMED with verified hash '{tx_hash_real}' cleanly increased earnings by exactly 5000.0 USDC.")

    # 4. DUPLICATE CONFIRMATION -> NO DOUBLE COUNTING
    print("\n[4/6] Testing Duplicate Payment Confirmation (No Double Counting)...")
    res_dup = tracker.record_payment(app_id_1, amount_received=5000.0, currency="USDC", source="Superteam", transaction_hash=tx_hash_real)
    assert res_dup["success"] is False, "Duplicate payment confirmation was allowed!"
    assert res_dup.get("duplicate_blocked") is True, "duplicate_blocked flag not returned!"
    
    summary4 = tracker.get_financial_summary()
    confirmed_usdc4 = summary4["confirmed_earnings"].get("USDC", 0.0)
    assert confirmed_usdc4 == 5000.0, f"Safety violation: Duplicate hash double counted! Earnings jumped to {confirmed_usdc4}!"
    print("  ✅ Passed: Duplicate payment attempts with existing transaction hash are blocked; no double counting occurs.")

    # 5. PARTIAL PAYMENT (NO FALSE FULL COMPLETION)
    print("\n[5/6] Testing Partial Payment Tracking (Without Marking Full Reward Received)...")
    app_id_partial = "app_test_partial_002"
    expected_full = 10000.0
    partial_received = 3500.0
    tx_hash_partial = "0xpartial_receipt_hash_555"
    
    tracker.register_expected_reward(app_id_partial, expected_amount=expected_full, currency="USD", source="GitHub")
    res_part = tracker.record_payment(
        app_id_partial,
        amount_received=partial_received,
        currency="USD",
        source="GitHub",
        transaction_hash=tx_hash_partial,
        is_partial=True,
        expected_amount=expected_full
    )
    assert res_part["success"] is True, f"Partial payment failed: {res_part}"
    assert res_part["is_partial"] is True, "is_partial flag not set!"
    assert res_part["amount_received"] == 3500.0, f"Expected 3500.0, got {res_part['amount_received']}"
    assert res_part["expected_amount"] == 10000.0, "Lost track of full expected reward!"
    
    # Check that confirmed USD earnings equal ONLY the partial amount received (3500.0), not the full 10000.0!
    summary5 = tracker.get_financial_summary()
    confirmed_usd5 = summary5["confirmed_earnings"].get("USD", 0.0)
    assert confirmed_usd5 == 3500.0, f"Safety violation: Expected confirmed earnings of exactly 3500.0 USD, got {confirmed_usd5}!"
    print("  ✅ Passed: Partial payment of $3,500 recorded accurately; full $10,000 expected reward is not marked as fully received.")

    # 6. MISSING TRANSACTION EVIDENCE (NO FAKE HASHES / REMAINS PENDING/UNKNOWN)
    print("\n[6/6] Testing Missing Transaction Evidence (Hash Remains Null, No Earnings Jump)...")
    app_id_no_hash = "app_test_nohash_003"
    tracker.register_expected_reward(app_id_no_hash, expected_amount=1200.0, currency="USD", source="GitHub", initial_status=PAYMENT_PENDING)
    
    # Try to record payment with missing/empty transaction hash
    res_nohash = tracker.record_payment(app_id_no_hash, amount_received=1200.0, currency="USD", source="GitHub", transaction_hash=None)
    assert res_nohash["success"] is False, f"Payment confirmed without transaction hash: {res_nohash}"
    assert res_nohash["status"] == PAYMENT_PENDING, f"Status improperly changed to {res_nohash['status']}!"
    
    # Confirm hash remained null in disk database
    records = tracker.get_records()
    target_rec = [r for r in records if r["app_id"] == app_id_no_hash][0]
    assert target_rec["transaction_hash"] is None, f"Safety violation: Fake transaction hash generated ({target_rec['transaction_hash']})!"
    assert target_rec["status"] != PAYMENT_CONFIRMED, "Status changed to PAYMENT_CONFIRMED without real evidence!"
    
    summary6 = tracker.get_financial_summary()
    confirmed_usd6 = summary6["confirmed_earnings"].get("USD", 0.0)
    assert confirmed_usd6 == 3500.0, f"Safety violation: Earnings increased without valid transaction evidence!"
    print("  ✅ Passed: Missing transaction evidence prevents PAYMENT_CONFIRMED transition, transaction_hash stays null, and earnings remain untouched.")

    print("\n======================================================================")
    print("   🎉 ALL 6 PAYMENT TRACKING AND EARNINGS INTEGRITY TESTS PASSED!     ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
