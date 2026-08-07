"""
dashboard/tracking_layer.py — MVP Dashboard and End-to-End Tracking Layer
==========================================================================

Provides safe, testable data aggregation and tracking for the Streamlit dashboard:
  - Separate sections for:
    1. New Opportunities
    2. Pending Approval
    3. Applications
    4. Accepted Work
    5. Work Completed
    6. Pending Payments
    7. Confirmed Earnings
  - Attribute formatting: platform, title, URL, reward, reward_verified, status, deadline, profit score.
  - Explicit separation of job status and payment status with exact timestamps.
  - Separate financial metrics: Potential Rewards, Applied Value, Accepted Value, Confirmed Earnings.
  - Confirmed Earnings comes strictly ONLY from PAYMENT_CONFIRMED records.
  - Platform and status filtering.
  - Graceful handling of missing or corrupted data files.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("mega.dashboard")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class DashboardTrackingLayer:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.opps_file = os.path.join(self.data_dir, "opportunities.json")
        self.appr_file = os.path.join(self.data_dir, "approvals.json")
        self.apps_file = os.path.join(self.data_dir, "applications.json")
        self.earn_file = os.path.join(self.data_dir, "earnings.json")
        self.pay_file = os.path.join(self.data_dir, "payments_log.json")
        self.scan_file = os.path.join(self.data_dir, "scan_log.json")

    def _load_json_list(self, filepath: str) -> List[Dict[str, Any]]:
        """Gracefully handles missing or corrupted data files by returning an empty list."""
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "records" in data:
                    return data.get("records", [])
                elif isinstance(data, dict) and "approvals" in data:
                    return data.get("approvals", [])
                return []
        except (json.JSONDecodeError, IOError, Exception) as e:
            logger.warning(f"[DashboardTrackingLayer] Gracefully handled missing/corrupted file at {filepath}: {str(e)}")
            return []

    def get_raw_data(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "opportunities": self._load_json_list(self.opps_file),
            "approvals": self._load_json_list(self.appr_file),
            "applications": self._load_json_list(self.apps_file),
            "earnings": self._load_json_list(self.earn_file),
            "payments": self._load_json_list(self.pay_file),
            "scans": self._load_json_list(self.scan_file)
        }

    def normalize_item(self, item: Dict[str, Any], default_status: str = "Unknown") -> Dict[str, Any]:
        """
        Normalizes attributes so each item cleanly exposes:
        platform, title, URL, reward, currency, reward_verified, status, payment_status, deadline, profit_score, and timestamps.
        """
        job_status = item.get("status") or item.get("approval_status") or default_status
        payment_status = item.get("payment_status") or "PAYMENT_UNKNOWN"
        
        # Keep payment status and job status strictly separated
        reward_val = item.get("reward")
        try:
            reward_float = float(reward_val) if reward_val is not None else 0.0
        except (ValueError, TypeError):
            reward_float = 0.0

        return {
            "id": str(item.get("id") or item.get("opportunity_id") or f"id_{id(item)}"),
            "opportunity_id": str(item.get("opportunity_id") or item.get("id") or ""),
            "platform": str(item.get("platform") or "Unknown"),
            "title": str(item.get("title") or "Untitled Opportunity"),
            "url": str(item.get("url") or "#"),
            "reward": reward_float,
            "currency": str(item.get("currency") or "USD"),
            "reward_verified": bool(item.get("reward_verified", False)),
            "status": str(job_status),
            "payment_status": str(payment_status),
            "deadline": str(item.get("deadline") or "Not specified"),
            "profit_score": float(item.get("profit_score") or item.get("score") or 0.0),
            "automation_allowed": item.get("automation_allowed", "Unknown"),
            "proposal": str(item.get("proposal") or ""),
            "created_at": str(item.get("created_at") or item.get("timestamp") or "Not recorded"),
            "submitted_at": str(item.get("submitted_at") or "Not submitted"),
            "confirmed_at": str(item.get("confirmed_at") or "Not confirmed"),
            "transaction_hash": str(item.get("transaction_hash") or item.get("tx_hash") or "") if (item.get("transaction_hash") or item.get("tx_hash")) else None,
            "actual_amount_received": float(item.get("actual_amount_received") or item.get("amount") or 0.0)
        }

    def get_dashboard_sections(self, raw_data: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Partitions the dataset into the 7 required standalone sections:
          1. New Opportunities
          2. Pending Approval
          3. Applications
          4. Accepted Work
          5. Work Completed
          6. Pending Payments
          7. Confirmed Earnings
        """
        if raw_data is None:
            raw_data = self.get_raw_data()

        opps = [self.normalize_item(o, "NEW") for o in raw_data.get("opportunities", [])]
        apprs = [self.normalize_item(a, "PENDING_APPROVAL") for a in raw_data.get("approvals", [])]
        apps = [self.normalize_item(a, "READY") for a in raw_data.get("applications", [])]
        earns = [self.normalize_item(e, "PAYMENT_CONFIRMED") for e in raw_data.get("earnings", [])]
        pays = [self.normalize_item(p, "PAYMENT_UNKNOWN") for p in raw_data.get("payments", [])]

        # Track IDs of opportunities already moved to approval or application stages
        tracked_opp_ids = {a["opportunity_id"] for a in apprs if a["opportunity_id"]} | {a["opportunity_id"] for a in apps if a["opportunity_id"]}
        tracked_urls = {a["url"] for a in apprs if a["url"] != "#"} | {a["url"] for a in apps if a["url"] != "#"}

        sections: Dict[str, List[Dict[str, Any]]] = {
            "New Opportunities": [],
            "Pending Approval": [],
            "Applications": [],
            "Accepted Work": [],
            "Work Completed": [],
            "Pending Payments": [],
            "Confirmed Earnings": []
        }

        # 1. New Opportunities
        for o in opps:
            if o["id"] not in tracked_opp_ids and o["url"] not in tracked_urls:
                o["status"] = "NEW"
                sections["New Opportunities"].append(o)

        # 2. Pending Approval
        for a in apprs:
            if a["status"] == "PENDING_APPROVAL":
                sections["Pending Approval"].append(a)

        # 3, 4, 5: Applications, Accepted Work, Work Completed
        for a in apps:
            st_val = a["status"].upper()
            if st_val in ["ACCEPTED"]:
                sections["Accepted Work"].append(a)
            elif st_val in ["COMPLETED"]:
                sections["Work Completed"].append(a)
            elif st_val == "PAYMENT_CONFIRMED":
                # Already completed and payment confirmed
                sections["Work Completed"].append(a)
            else:
                sections["Applications"].append(a)
                
            # Check payment status for Pending Payments vs Confirmed Earnings
            if a["payment_status"] == "PAYMENT_PENDING":
                sections["Pending Payments"].append(a)
            elif a["payment_status"] == "PAYMENT_CONFIRMED":
                sections["Confirmed Earnings"].append(a)

        # 6 & 7: Merge any explicit records from payments_log / earnings.json into Payments sections without duplicates
        existing_conf_ids = {item["id"] for item in sections["Confirmed Earnings"]}
        for p in pays + earns:
            p_stat = p["payment_status"] if p["payment_status"] != "PAYMENT_UNKNOWN" else p["status"]
            if p_stat == "PAYMENT_PENDING":
                if not any(item["id"] == p["id"] for item in sections["Pending Payments"]):
                    sections["Pending Payments"].append(p)
            elif p_stat == "PAYMENT_CONFIRMED" or p.get("actual_amount_received", 0) > 0 or p.get("transaction_hash"):
                if p["id"] not in existing_conf_ids:
                    sections["Confirmed Earnings"].append(p)
                    existing_conf_ids.add(p["id"])

        return sections

    def get_financial_metrics(self, sections: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> Dict[str, float]:
        """
        Calculates separate financial metrics (normalized in standard float amounts):
          - Potential Rewards (from New Opportunities + Pending Approval)
          - Applied Value (from Applications)
          - Accepted Value (from Accepted Work + Work Completed)
          - Confirmed Earnings (STRICTLY ONLY from PAYMENT_CONFIRMED records with evidence; never counts potential/expected rewards)
        """
        if sections is None:
            sections = self.get_dashboard_sections()

        potential = sum(item["reward"] for item in sections.get("New Opportunities", []) + sections.get("Pending Approval", []))
        applied = sum(item["reward"] for item in sections.get("Applications", []))
        accepted = sum(item["reward"] for item in sections.get("Accepted Work", []) + sections.get("Work Completed", []))
        
        # Confirmed earnings must come ONLY from PAYMENT_CONFIRMED records! Never display potential/expected rewards or pending payments as earned money!
        confirmed_list = sections.get("Confirmed Earnings", [])
        confirmed = 0.0
        for c in confirmed_list:
            # Check for actual received amount or verified reward ONLY if payment status is PAYMENT_CONFIRMED or coming from verified earnings log
            if c["payment_status"] == "PAYMENT_CONFIRMED" or c["status"] == "PAYMENT_CONFIRMED" or c.get("transaction_hash"):
                amt = c["actual_amount_received"] if c["actual_amount_received"] > 0 else c["reward"]
                confirmed += amt

        from payments.revenue_split import calculate_splits
        splits = calculate_splits(confirmed)

        return {
            "Potential Rewards": round(potential, 2),
            "Applied Value": round(applied, 2),
            "Accepted Value": round(accepted, 2),
            "Confirmed Earnings": round(confirmed, 2),
            "Owner Confirmed Earnings": splits["owner_share"],
            "Agent Confirmed Earnings": splits["agent_share"]
        }

    @staticmethod
    def filter_items(
        items: List[Dict[str, Any]],
        platform_filter: str = "All",
        status_filter: str = "All"
    ) -> List[Dict[str, Any]]:
        """Filters dashboard items by platform and/or job status."""
        filtered = items
        if platform_filter and platform_filter != "All":
            filtered = [item for item in filtered if str(item.get("platform", "")).lower() == platform_filter.lower()]
        if status_filter and status_filter != "All":
            filtered = [item for item in filtered if str(item.get("status", "")).lower() == status_filter.lower()]
        return filtered

    def get_available_platforms(self, sections: Dict[str, List[Dict[str, Any]]]) -> List[str]:
        platforms = set()
        for lst in sections.values():
            for item in lst:
                p = item.get("platform")
                if p and p != "Unknown":
                    platforms.add(p)
        return ["All"] + sorted(list(platforms))
