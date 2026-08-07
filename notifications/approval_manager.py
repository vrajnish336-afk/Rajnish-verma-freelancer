"""
notifications/approval_manager.py — Notifications & User Approval MVP Module
=============================================================================

Manages user approvals and system notifications for discovered opportunities.
  - Newly discovered high-quality opportunities start as PENDING_APPROVAL.
  - Approval state is persistently stored in data/approvals.json.
  - Only approved opportunities may reach the Application Engine.
  - Rejected opportunities are blocked forever and never submitted.
  - Provides system/log notifications (no phone integration in MVP).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("mega.notifications")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

STATUS_PENDING = "PENDING_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"


class ApprovalManager:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.approvals_file = os.path.join(DATA_DIR, "approvals.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.approvals_file):
            with open(self.approvals_file, "w") as fh:
                json.dump([], fh)

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.approvals_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, data: List[Dict[str, Any]]):
        with open(self.approvals_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    def is_tracked(self, platform: str, url: str) -> bool:
        """Check if an opportunity is already tracked in approvals (pending, approved, or rejected)."""
        for item in self._load():
            if item.get("platform") == platform and item.get("url") == url:
                return True
        return False

    def get_all_approvals(self) -> List[Dict[str, Any]]:
        return self._load()

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        return [item for item in self._load() if item.get("approval_status") == STATUS_PENDING]

    def register_opportunity_for_approval(self, opp: Dict[str, Any], proposal: str) -> Dict[str, Any]:
        """
        Register a high-quality opportunity as PENDING_APPROVAL.
        Does NOT put it into the application engine yet.
        """
        platform = opp.get("platform")
        url = opp.get("url")

        if self.is_tracked(platform, url):
            logger.info(f"Opportunity already tracked in approvals: {platform} - {url}")
            return {}

        record_id = f"appr_{datetime.utcnow().timestamp()}"
        approval_record = {
            "id": record_id,
            "opportunity_id": opp.get("id"),
            "platform": platform,
            "title": opp.get("title"),
            "url": url,
            "reward": opp.get("reward"),
            "currency": opp.get("currency", "USD"),
            "reward_verified": opp.get("reward_verified", False),
            "reward_evidence": opp.get("reward_evidence", ""),
            "proposal": proposal,
            "approval_status": STATUS_PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "profit_score": opp.get("profit_score"),
            "estimated_hours": opp.get("estimated_hours")
        }

        records = self._load()
        records.append(approval_record)
        self._save(records)

        # Emit system notification (no phone integration yet)
        short_title = (opp.get("title") or "Untitled")[:45]
        reward_str = f"{opp.get('reward', 'Unknown')} {opp.get('currency', 'USD')}"
        logger.info(f"🔔 [NOTIFICATION] High-quality opportunity requires approval -> PENDING_APPROVAL:")
        logger.info(f"    -> [{platform}] {short_title} | Reward: {reward_str}")

        return approval_record

    def approve(self, approval_id: str, engine_instance) -> bool:
        """
        Approve an opportunity. Only upon approval is it sent to the Application Engine.
        """
        records = self._load()
        target_record = None
        for r in records:
            if r.get("id") == approval_id:
                if r.get("approval_status") == STATUS_REJECTED:
                    logger.warning(f"Cannot approve {approval_id}: already REJECTED.")
                    return False
                r["approval_status"] = STATUS_APPROVED
                r["updated_at"] = datetime.utcnow().isoformat()
                target_record = r
                break

        if not target_record:
            return False

        self._save(records)

        # Handoff to application engine ONLY when approved
        # Promoted as an APPROVED application record (awaiting manual submission; no auto-submission)
        engine_instance.promote_approved_opportunity(target_record)
        logger.info(f"✅ [APPROVED] Opportunity '{str(target_record.get('title', ''))[:35]}' promoted to Application Engine.")
        return True

    def reject(self, approval_id: str) -> bool:
        """
        Reject an opportunity. Rejected items will never reach the application engine or be submitted.
        """
        records = self._load()
        found = False
        for r in records:
            if r.get("id") == approval_id:
                r["approval_status"] = STATUS_REJECTED
                r["updated_at"] = datetime.utcnow().isoformat()
                found = True
                logger.info(f"🚫 [REJECTED] Opportunity '{str(r.get('title', ''))[:35]}' rejected. Blocked from application engine.")
                break

        if found:
            self._save(records)
        return found
