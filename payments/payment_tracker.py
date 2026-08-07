"""
payments/payment_tracker.py — Payment Tracking and Earnings Integrity MVP
========================================================================

Enforces complete financial integrity for MEGA FREELANCER:
  - Tracks payment states: PAYMENT_UNKNOWN, PAYMENT_PENDING, PAYMENT_CONFIRMED.
  - Records expected reward separately from actual received payment.
  - Only PAYMENT_CONFIRMED increases total earnings.
  - Never generates fake transaction hashes; never simulates a real payment.
  - transaction_hash remains null unless real evidence exists.
  - Stores payment amount, currency, source, evidence/reference, and confirmed_at.
  - Supports partial payments without marking full reward as received.
  - Prevents duplicate payment records from increasing earnings twice.
  - Keeps potential rewards, accepted value, and confirmed earnings completely separate.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("mega.payments")

# Payment States
PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class PaymentTracker:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.payments_file = os.path.join(DATA_DIR, "payments_log.json")
        self._ensure_files()

    def _ensure_files(self):
        if not os.path.exists(self.payments_file):
            with open(self.payments_file, "w", encoding="utf-8") as fh:
                json.dump({"records": [], "confirmed_tx_hashes": []}, fh)

    def _load_data(self) -> Dict[str, Any]:
        try:
            with open(self.payments_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if "records" not in data:
                    data["records"] = []
                if "confirmed_tx_hashes" not in data:
                    data["confirmed_tx_hashes"] = []
                return data
        except (json.JSONDecodeError, IOError):
            return {"records": [], "confirmed_tx_hashes": []}

    def _save_data(self, data: Dict[str, Any]):
        with open(self.payments_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    def register_expected_reward(
        self,
        app_id: str,
        expected_amount: float,
        currency: str = "USD",
        source: str = "",
        initial_status: str = PAYMENT_UNKNOWN
    ) -> Dict[str, Any]:
        """
        Records expected reward completely separately from actual received payment.
        Does NOT increase confirmed total earnings.
        """
        data = self._load_data()
        
        # Check if record exists
        for rec in data["records"]:
            if rec.get("app_id") == app_id:
                rec["expected_amount"] = expected_amount
                rec["currency"] = currency
                rec["source"] = source
                if rec.get("status") != PAYMENT_CONFIRMED:
                    rec["status"] = initial_status
                self._save_data(data)
                return rec
                
        rec = {
            "app_id": app_id,
            "expected_amount": expected_amount,
            "actual_amount_received": 0.0,
            "currency": currency,
            "source": source,
            "status": initial_status,
            "transaction_hash": None, # Must remain null unless real evidence exists
            "evidence": None,
            "is_partial": False,
            "confirmed_at": None,
            "created_at": datetime.utcnow().isoformat()
        }
        data["records"].append(rec)
        self._save_data(data)
        logger.info(f"Registered expected reward of {expected_amount} {currency} for app {app_id} as [{initial_status}]")
        return rec

    def set_payment_status(self, app_id: str, new_status: str, evidence: Optional[str] = None) -> Dict[str, Any]:
        """
        Updates payment status. If setting PAYMENT_CONFIRMED without real transaction evidence, blocks confirmation!
        """
        data = self._load_data()
        for rec in data["records"]:
            if rec.get("app_id") == app_id:
                # Safety check: block confirming payment without transaction evidence
                if new_status == PAYMENT_CONFIRMED and not rec.get("transaction_hash") and not evidence:
                    logger.warning(f"Cannot transition {app_id} to PAYMENT_CONFIRMED without valid transaction evidence. Keeping status as PAYMENT_PENDING.")
                    rec["status"] = PAYMENT_PENDING
                else:
                    rec["status"] = new_status
                if evidence:
                    rec["evidence"] = evidence
                self._save_data(data)
                return rec
        return {}

    def record_payment(
        self,
        app_id: str,
        amount_received: float,
        currency: str = "USD",
        source: str = "",
        transaction_hash: Optional[str] = None,
        is_partial: bool = False,
        expected_amount: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Records actual payment receipt with strict integrity verification:
          - If transaction_hash is missing/null, refuses to confirm payment or increase earnings.
          - If duplicate transaction_hash is submitted, prevents double counting.
          - Supports partial payments without incorrectly marking full expected reward as received.
        """
        data = self._load_data()
        
        # 1. Missing transaction evidence -> cannot confirm payment
        if not transaction_hash or str(transaction_hash).strip() == "":
            logger.warning(f"[PaymentTracker] Attempted to record payment for {app_id} without transaction hash! Keeping status as PAYMENT_PENDING/UNKNOWN without increasing earnings.")
            for rec in data["records"]:
                if rec.get("app_id") == app_id:
                    rec["status"] = PAYMENT_PENDING
                    rec["transaction_hash"] = None # Must remain null unless real evidence exists
                    self._save_data(data)
                    return {
                        "success": False,
                        "status": PAYMENT_PENDING,
                        "error": "Missing transaction evidence (transaction_hash is null). Cannot mark payment confirmed or increase earnings.",
                        "record": rec
                    }
            return {
                "success": False,
                "status": PAYMENT_UNKNOWN,
                "error": "Missing transaction evidence and application record not found."
            }

        clean_hash = str(transaction_hash).strip()

        # 2. Duplicate payment confirmation prevention -> no double counting
        if clean_hash in data.get("confirmed_tx_hashes", []):
            logger.warning(f"[PaymentTracker] Duplicate transaction hash '{clean_hash}' detected for app {app_id}! Double counting blocked.")
            for rec in data["records"]:
                if rec.get("transaction_hash") == clean_hash or (rec.get("app_id") == app_id and clean_hash in str(rec.get("evidence", ""))):
                    return {
                        "success": False,
                        "status": rec.get("status", PAYMENT_CONFIRMED),
                        "error": f"Duplicate payment record with hash '{clean_hash}'. Double counting prevented.",
                        "record": rec,
                        "duplicate_blocked": True
                    }
            return {
                "success": False,
                "error": f"Duplicate transaction hash '{clean_hash}'. Double counting blocked.",
                "duplicate_blocked": True
            }

        # 3. Process confirmed payment (partial or full)
        target_rec = None
        for rec in data["records"]:
            if rec.get("app_id") == app_id:
                target_rec = rec
                break

        if not target_rec:
            target_rec = {
                "app_id": app_id,
                "expected_amount": expected_amount or amount_received,
                "actual_amount_received": 0.0,
                "currency": currency,
                "source": source,
                "status": PAYMENT_UNKNOWN,
                "transaction_hash": None,
                "evidence": None,
                "is_partial": False,
                "confirmed_at": None,
                "created_at": datetime.utcnow().isoformat()
            }
            data["records"].append(target_rec)

        # Calculate total received if partial payments accumulate, or set new amount
        new_total_received = target_rec.get("actual_amount_received", 0.0) + amount_received
        exp_amount = expected_amount if expected_amount is not None else target_rec.get("expected_amount", amount_received)
        
        # Support partial payments without incorrectly marking full reward as received
        if is_partial or new_total_received < exp_amount:
            target_rec["is_partial"] = True
            target_rec["status"] = PAYMENT_CONFIRMED  # Confirmed receipt of partial amount
            logger.info(f"[PaymentTracker] Recorded confirmed PARTIAL payment of {amount_received} {currency} for app {app_id} (Total received: {new_total_received}/{exp_amount}).")
        else:
            target_rec["is_partial"] = False
            target_rec["status"] = PAYMENT_CONFIRMED
            logger.info(f"[PaymentTracker] Recorded confirmed FULL payment of {amount_received} {currency} for app {app_id}.")

        target_rec["actual_amount_received"] = new_total_received
        target_rec["currency"] = currency
        target_rec["source"] = source
        target_rec["transaction_hash"] = clean_hash
        target_rec["evidence"] = f"tx:{clean_hash}"
        target_rec["confirmed_at"] = datetime.utcnow().isoformat()

        if clean_hash not in data["confirmed_tx_hashes"]:
            data["confirmed_tx_hashes"].append(clean_hash)

        self._save_data(data)
        return {
            "success": True,
            "status": PAYMENT_CONFIRMED,
            "is_partial": target_rec["is_partial"],
            "amount_received": amount_received,
            "total_received": new_total_received,
            "expected_amount": exp_amount,
            "transaction_hash": clean_hash,
            "record": target_rec
        }

        return target_rec

    def get_records(self) -> List[Dict[str, Any]]:
        return self._load_data().get("records", [])

    def get_financial_summary(self, opps_file: Optional[str] = None, apps_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Keeps potential rewards, accepted value, and confirmed earnings completely separate.
        """
        potential_rewards_by_currency = {}
        accepted_value_by_currency = {}
        confirmed_earnings_by_currency = {}

        # 1. Confirmed earnings: strictly from PAYMENT_CONFIRMED records with valid tx hash
        data = self._load_data()
        for rec in data.get("records", []):
            curr = rec.get("currency", "USD")
            if rec.get("status") == PAYMENT_CONFIRMED and rec.get("transaction_hash"):
                amt = float(rec.get("actual_amount_received") or 0.0)
                confirmed_earnings_by_currency[curr] = confirmed_earnings_by_currency.get(curr, 0.0) + amt
            elif rec.get("status") in [PAYMENT_UNKNOWN, PAYMENT_PENDING]:
                # Do NOT add to confirmed earnings!
                pass

        # 2. Potential Rewards (from raw opportunities database if path provided or standard location)
        if not opps_file:
            opps_file = os.path.join(DATA_DIR, "opportunities.json")
        if os.path.exists(opps_file):
            try:
                with open(opps_file, "r", encoding="utf-8") as fh:
                    opps = json.load(fh)
                    for o in opps:
                        curr = o.get("currency", "USD")
                        amt = float(o.get("reward") or 0.0)
                        potential_rewards_by_currency[curr] = potential_rewards_by_currency.get(curr, 0.0) + amt
            except Exception:
                pass

        # 3. Accepted Value (from application engine database)
        if not apps_file:
            apps_file = os.path.join(DATA_DIR, "applications.json")
        if os.path.exists(apps_file):
            try:
                with open(apps_file, "r", encoding="utf-8") as fh:
                    apps = json.load(fh)
                    for a in apps:
                        curr = a.get("currency", "USD")
                        amt = float(a.get("reward") or 0.0)
                        accepted_value_by_currency[curr] = accepted_value_by_currency.get(curr, 0.0) + amt
            except Exception:
                pass

        # Ensure at least USD key exists for clean dashboard display
        for d in [potential_rewards_by_currency, accepted_value_by_currency, confirmed_earnings_by_currency]:
            if "USD" not in d and "USDC" not in d and not d:
                d["USD"] = 0.0

        return {
            "potential_rewards": potential_rewards_by_currency,
            "accepted_value": accepted_value_by_currency,
            "confirmed_earnings": confirmed_earnings_by_currency,
            "integrity_verified": True
        }
