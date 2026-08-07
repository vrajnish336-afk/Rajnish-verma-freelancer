"""
submission/base.py — BaseApplicationAdapter Interface
======================================================

Defines the core interface for official Application Submission Adapters.

Safety Guarantees & Rules:
  - Add adapters only for platforms with a documented/allowed submission method.
  - Use official APIs or explicitly permitted endpoints only.
  - Never bypass CAPTCHA, login, anti-bot systems, or platform restrictions.
  - Never invent a successful submission.
  - Require APPROVED status before attempting submission.
  - Require automation_allowed == true.
  - Store external application ID/reference only when actually returned by the platform.
  - Keep DRY_RUN mode available.
  - Fail safely when credentials are missing.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger("mega.submission")


class BaseApplicationAdapter(ABC):
    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    def preflight_check(self, app_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Enforces strict safety rules before any submission attempt (DRY_RUN or REAL).
        Returns None if preflight passes, or an error dictionary if blocked.
        """
        timestamp = datetime.utcnow().isoformat()

        # 1. Require APPROVED status
        is_approved = app_record.get("approval_status") == "APPROVED" or app_record.get("status") in ["APPROVED", "READY"]
        if not is_approved or app_record.get("approval_status") in ["PENDING_APPROVAL", "REJECTED"]:
            msg = f"Safety block: Application must have APPROVED status before attempting submission (current status: {app_record.get('status') or app_record.get('approval_status')})."
            logger.warning(f"[{self.platform_name}] {msg}")
            return {
                "success": False,
                "status": "BLOCKED",
                "error": msg,
                "external_reference": None,
                "timestamp": timestamp,
                "mode": "FAILED_PREFLIGHT"
            }

        # 2. Require automation_allowed == true
        if app_record.get("automation_allowed") is not True:
            msg = "Automation blocked: automation_allowed is not explicitly set to True -> MANUAL_ACTION_REQUIRED."
            logger.warning(f"[{self.platform_name}] {msg}")
            return {
                "success": False,
                "status": "MANUAL_ACTION_REQUIRED",
                "error": msg,
                "external_reference": None,
                "timestamp": timestamp,
                "mode": "MANUAL_ACTION_REQUIRED"
            }

        return None

    @abstractmethod
    def submit(self, app_record: Dict[str, Any], dry_run: bool = True, http_client=None) -> Dict[str, Any]:
        """
        Executes submission against official platform APIs or simulated DRY_RUN.
        Must return a standardized response dict:
        {
            "success": bool,
            "status": str,
            "error" or "message": str,
            "external_reference": Optional[str],
            "timestamp": str (ISO-8601),
            "mode": "DRY_RUN" or "REAL"
        }
        """
        pass
