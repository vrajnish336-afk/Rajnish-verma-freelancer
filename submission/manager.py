"""
submission/manager.py — Application Submission Adapter Dispatcher
=================================================================

Dispatches applications to appropriate platform adapters.
Enforces safety constraints, DRY_RUN capabilities, and MANUAL_ACTION_REQUIRED rules.
"""

from typing import Dict, Any, Optional
import logging

from .base import BaseApplicationAdapter
from .github_adapter import GitHubSubmissionAdapter
from .unsupported_adapter import UnsupportedPlatformAdapter

logger = logging.getLogger("mega.submission.manager")


class SubmissionManager:
    def __init__(self):
        self.adapters: Dict[str, BaseApplicationAdapter] = {
            "github": GitHubSubmissionAdapter(),
            # Platforms without documented open automated submission APIs (e.g. Superteam) default to unsupported adapter
        }

    def get_adapter_for_platform(self, platform_name: str) -> BaseApplicationAdapter:
        if not platform_name:
            return UnsupportedPlatformAdapter("Unknown")
        key = platform_name.strip().lower()
        if key in self.adapters:
            return self.adapters[key]
        return UnsupportedPlatformAdapter(platform_name)

    def submit_application(self, app_record: Dict[str, Any], dry_run: bool = True, http_client=None) -> Dict[str, Any]:
        """
        Dispatches submission to the appropriate adapter while recording exact results and timestamp.
        """
        platform = app_record.get("platform", "Unknown")
        adapter = self.get_adapter_for_platform(platform)
        logger.info(f"[SubmissionManager] Dispatching '{str(app_record.get('title', 'Job'))[:35]}' ({platform}) with dry_run={dry_run}")
        return adapter.submit(app_record, dry_run=dry_run, http_client=http_client)
