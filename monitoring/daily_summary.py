"""
monitoring/daily_summary.py — Daily Summary and Operational Metrics MVP
========================================================================

Aggregates operational activity and financial progress without modifying core engines:
  - Tracks 10 core metrics:
      1. opportunities discovered
      2. verified paid opportunities
      3. applications submitted
      4. applications accepted
      5. applications rejected
      6. active work
      7. completed work
      8. pending payments
      9. confirmed payments
      10. confirmed earnings (STRICTLY from PAYMENT_CONFIRMED records with verified transaction evidence)
  - Sends daily summary reports through the existing Telegram notification provider.
  - Gracefully handles missing data and unavailable services without raising exceptions.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("mega.monitoring.summary")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class DailySummaryGenerator:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.opps_file = os.path.join(self.data_dir, "opportunities.json")
        self.apps_file = os.path.join(self.data_dir, "applications.json")
        self.pay_file = os.path.join(self.data_dir, "payments_log.json")
        self.appr_file = os.path.join(self.data_dir, "approvals.json")

    def _load_json(self, filepath: str) -> List[Dict[str, Any]]:
        """Gracefully loads data files, returning empty list if missing or corrupted."""
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("records", data.get("approvals", []))
                return []
        except (json.JSONDecodeError, IOError, Exception) as e:
            logger.warning(f"[DailySummary] Gracefully handled unreadable/missing file at {filepath}: {e}")
            return []

    def _matches_date(self, item: Dict[str, Any], target_date: str) -> bool:
        """
        Checks if item timestamp matches target YYYY-MM-DD date.
        If target_date is 'ALL' or empty, treats as general operational activity summary.
        """
        if not target_date or target_date.upper() == "ALL":
            return True
        ts = str(item.get("confirmed_at") or item.get("submitted_at") or item.get("created_at") or item.get("timestamp") or "")
        return ts.startswith(target_date)

    def generate_summary(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates all 10 mandatory summary operational and financial metrics.
        Never calls potential or pending rewards confirmed earnings!
        """
        if not target_date:
            target_date = datetime.utcnow().strftime("%Y-%m-%d")

        opps = self._load_json(self.opps_file)
        apprs = self._load_json(self.appr_file)
        apps = self._load_json(self.apps_file)
        pays = self._load_json(self.pay_file)

        opps_discovered = 0
        verified_opps = 0
        for o in opps:
            if self._matches_date(o, target_date):
                opps_discovered += 1
                if o.get("reward_verified") or (float(o.get("reward") or 0) > 0 and o.get("reward_evidence")):
                    verified_opps += 1

        apps_submitted = 0
        apps_accepted = 0
        apps_rejected = 0
        active_work = 0
        completed_work = 0
        pending_payments = 0
        confirmed_payments = 0
        confirmed_earnings_usd = 0.0

        # Track evaluated IDs to avoid overlap between application states
        evaluated_app_ids = set()
        for a in apps:
            if not self._matches_date(a, target_date):
                continue
            a_id = a.get("id") or a.get("opportunity_id")
            if a_id in evaluated_app_ids:
                continue
            evaluated_app_ids.add(a_id)

            status = str(a.get("status") or "").upper()
            payment_status = str(a.get("payment_status") or "").upper()

            if status in ["SUBMITTED"]:
                apps_submitted += 1
            elif status in ["ACCEPTED"]:
                apps_accepted += 1
                active_work += 1
            elif status in ["COMPLETED"]:
                completed_work += 1
            elif status in ["REJECTED"]:
                apps_rejected += 1

            if payment_status == "PAYMENT_PENDING":
                pending_payments += 1
            elif payment_status == "PAYMENT_CONFIRMED" and a.get("transaction_hash"):
                confirmed_payments += 1
                try:
                    confirmed_earnings_usd += float(a.get("actual_amount_received") or a.get("reward") or 0.0)
                except (ValueError, TypeError):
                    pass

        # Check explicit payments log for payment activity not captured in apps list
        for p in pays:
            if not self._matches_date(p, target_date):
                continue
            p_id = p.get("app_id") or p.get("id")
            if p_id and p_id in evaluated_app_ids:
                continue

            p_status = str(p.get("status") or "").upper()
            if p_status == "PAYMENT_PENDING":
                pending_payments += 1
                evaluated_app_ids.add(p_id)
            elif p_status == "PAYMENT_CONFIRMED" and p.get("transaction_hash"):
                confirmed_payments += 1
                evaluated_app_ids.add(p_id)
                try:
                    confirmed_earnings_usd += float(p.get("actual_amount_received") or p.get("amount") or 0.0)
                except (ValueError, TypeError):
                    pass

        # Check approvals table for rejected candidates
        for ap in apprs:
            if self._matches_date(ap, target_date) and ap.get("approval_status") == "REJECTED":
                if ap.get("id") not in evaluated_app_ids and ap.get("opportunity_id") not in evaluated_app_ids:
                    apps_rejected += 1

        from payments.revenue_split import calculate_splits
        splits = calculate_splits(confirmed_earnings_usd)

        return {
            "date": target_date,
            "opportunities_discovered": opps_discovered,
            "verified_paid_opportunities": verified_opps,
            "applications_submitted": apps_submitted,
            "applications_accepted": apps_accepted,
            "applications_rejected": apps_rejected,
            "active_work": active_work,
            "completed_work": completed_work,
            "pending_payments": pending_payments,
            "confirmed_payments": confirmed_payments,
            "confirmed_earnings": round(confirmed_earnings_usd, 2),
            "owner_confirmed_earnings": splits["owner_share"],
            "agent_confirmed_earnings": splits["agent_share"]
        }

    def format_report_text(self, summary: Dict[str, Any]) -> str:
        """Formats the daily summary into a clean readable message without violating integrity rules."""
        date_str = summary.get("date", "Today")
        lines = [
            f"📊 **MEGA FREELANCER — Daily Operational Summary ({date_str})**",
            f"---",
            f"🎯 **Opportunities Discovered:** `{summary.get('opportunities_discovered', 0)}` (Verified Paid: `{summary.get('verified_paid_opportunities', 0)}`)",
            f"📤 **Applications Submitted:** `{summary.get('applications_submitted', 0)}`",
            f"🤝 **Applications Accepted (Active Work):** `{summary.get('applications_accepted', 0)}` (Active: `{summary.get('active_work', 0)}`)",
            f"🚫 **Applications Rejected:** `{summary.get('applications_rejected', 0)}`",
            f"🏁 **Work Completed:** `{summary.get('completed_work', 0)}`",
            f"---",
            f"⏳ **Pending Payments:** `{summary.get('pending_payments', 0)}` *(Unverified/Awaiting Receipt)*",
            f"💵 **Confirmed Payments:** `{summary.get('confirmed_payments', 0)}`",
            f"💰 **Confirmed Earnings:** `${summary.get('confirmed_earnings', 0.0):,.2f}`",
            f"   ↳ 👑 **Owner (70%):** `${summary.get('owner_confirmed_earnings', 0.0):,.2f}` | 🤖 **Agent (30%):** `${summary.get('agent_confirmed_earnings', 0.0):,.2f}`",
            f"---",
            f"ℹ️ *Confirmed earnings reflect strictly verified receipts with transaction hash evidence.*"
        ]
        return "\n".join(lines)

    def send_daily_summary(self, notifier=None, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Sends daily summary via existing notification system (TelegramProvider).
        Gracefully handles failing or offline notification providers without throwing exceptions.
        """
        try:
            summary = self.generate_summary(target_date=target_date)
            report_text = self.format_report_text(summary)

            if notifier is None:
                try:
                    from notifications import TelegramNotifier
                    notifier = TelegramNotifier()
                except Exception:
                    logger.warning("[DailySummary] Could not load TelegramNotifier. Continuing without sending alert.")
                    return {"success": False, "sent": False, "summary": summary, "reason": "Notifier unavailable."}

            res = notifier.notify(
                event_type="DAILY_SUMMARY",
                item_data={"title": f"Daily Summary ({summary['date']})", "id": f"daily_{summary['date']}"},
                message_override=report_text
            )
            return {"success": res.get("sent", False), "sent": res.get("sent", False), "summary": summary, "notification_result": res}
        except Exception as e:
            logger.error(f"[DailySummary] Gracefully handled error while attempting to send summary: {str(e)}")
            return {"success": False, "sent": False, "summary": self.generate_summary(target_date), "error": str(e)}
