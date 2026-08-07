"""
submission/unsupported_adapter.py — Unsupported Platform Fallback Adapter
=========================================================================

Handles platforms without an officially documented/allowed open automated submission method (e.g., Superteam, Web3 bounties, scraping targets).
Safety Guarantees:
  - Never bypass CAPTCHA, login, anti-bot systems, or platform restrictions.
  - If no supported API/submission method exists, immediately returns MANUAL_ACTION_REQUIRED.
  - Never invents a successful submission.
"""

from typing import Dict, Any
from datetime import datetime
import logging

from .base import BaseApplicationAdapter

logger = logging.getLogger("mega.submission.unsupported")


class UnsupportedPlatformAdapter(BaseApplicationAdapter):
    def __init__(self, platform_name: str = "Unknown"):
        super().__init__(platform_name=platform_name)

    def submit(self, app_record: Dict[str, Any], dry_run: bool = True, http_client=None) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()
        
        # Even on unsupported platforms, enforce preflight check first
        preflight_error = self.preflight_check(app_record)
        if preflight_error:
            return preflight_error

        msg = (
            f"No documented/supported open automated submission API exists for platform '{self.platform_name}' "
            f"without violating anti-bot, CAPTCHA, wallet-signing, or login rules. MANUAL_ACTION_REQUIRED."
        )
        logger.warning(f"[{self.platform_name} Adapter] {msg}")

        return {
            "success": False,
            "status": "MANUAL_ACTION_REQUIRED",
            "message": msg,
            "error": msg,
            "external_reference": None,
            "timestamp": timestamp,
            "mode": "MANUAL_ACTION_REQUIRED" if not dry_run else "DRY_RUN_MANUAL_REQUIRED"
        }
