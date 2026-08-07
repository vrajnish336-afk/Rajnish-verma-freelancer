"""
submission/github_adapter.py — GitHub API Application Submission Adapter
========================================================================

Official API submission adapter for GitHub bounties/issues via REST endpoints.
Uses personal access tokens (GITHUB_TOKEN) to submit formal proposals without hacking or bypassing restrictions.
"""

import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from .base import BaseApplicationAdapter

logger = logging.getLogger("mega.submission.github")


class GitHubSubmissionAdapter(BaseApplicationAdapter):
    def __init__(self):
        super().__init__(platform_name="GitHub")

    def _default_http_client(self, url: str, headers: Dict[str, str], data: Dict[str, Any]):
        """Default HTTP poster to GitHub REST API using built-in urllib."""
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status_code = resp.getcode()
                resp_json = json.loads(resp.read().decode('utf-8'))
                return status_code, resp_json
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
            except Exception:
                err_body = {"message": str(e)}
            return e.code, err_body
        except Exception as e:
            return 500, {"message": str(e)}

    def submit(self, app_record: Dict[str, Any], dry_run: bool = True, http_client=None) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()
        
        # Enforce preflight safety rules (APPROVED status and automation_allowed == True)
        preflight_error = self.preflight_check(app_record)
        if preflight_error:
            return preflight_error

        title = app_record.get("title", "Untitled Job")
        url = app_record.get("url", "")
        proposal = app_record.get("proposal", "")

        if dry_run:
            logger.info(f"[GitHub Adapter | DRY_RUN] Simulating issue comment submission for: {title}")
            # Do NOT send external network requests; do NOT invent a successful submission ID.
            return {
                "success": True,
                "status": "READY",
                "mode": "DRY_RUN",
                "message": "DRY_RUN: Successfully simulated GitHub REST API proposal submission step without sending network request.",
                "external_reference": None, # Never invent external reference ID during dry run
                "timestamp": timestamp
            }

        # Real submission mode: check credentials first (Fail safely when credentials missing)
        token = os.environ.get("GITHUB_TOKEN") or app_record.get("github_token")
        if not token or len(token.strip()) < 5:
            msg = "Missing API credentials (GITHUB_TOKEN not configured in environment or record). Failing safely without attempting network request."
            logger.warning(f"[GitHub Adapter] {msg}")
            return {
                "success": False,
                "status": "FAILED",
                "error": msg,
                "external_reference": None,
                "timestamp": timestamp,
                "mode": "REAL"
            }

        # Extract owner/repo and issue number from standard GitHub URL
        # e.g., https://github.com/owner/repo/issues/123 -> api endpoint https://api.github.com/repos/owner/repo/issues/123/comments
        match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url, re.IGNORECASE)
        if not match:
            msg = f"Cannot extract repository/issue parameters from target URL for official API: {url}"
            logger.error(f"[GitHub Adapter] {msg}")
            return {
                "success": False,
                "status": "FAILED",
                "error": msg,
                "external_reference": None,
                "timestamp": timestamp,
                "mode": "REAL"
            }

        owner, repo, issue_num = match.groups()
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}/comments"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "MEGA-Freelancer-Antigravity-MVP"
        }
        payload = {"body": proposal}

        client = http_client if http_client is not None else self._default_http_client
        logger.info(f"[GitHub Adapter | REAL] Executing official API submission to {api_url}...")
        status_code, response_data = client(api_url, headers, payload)

        # Store external reference ONLY when actually returned by the platform upon successful creation
        if status_code in [200, 201]:
            ext_ref = str(response_data.get("id") or response_data.get("html_url") or "")
            if not ext_ref:
                ext_ref = None
            logger.info(f"[GitHub Adapter] Submission successful! External reference: {ext_ref}")
            return {
                "success": True,
                "status": "SUBMITTED",
                "message": f"Successfully posted application via official GitHub API (HTTP {status_code}).",
                "external_reference": ext_ref,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "REAL"
            }
        else:
            err_msg = f"Platform API submission rejected (HTTP {status_code}): {response_data.get('message', 'Unknown API failure')}"
            logger.error(f"[GitHub Adapter] {err_msg}")
            # Never invent successful submission upon failure
            return {
                "success": False,
                "status": "FAILED",
                "error": err_msg,
                "external_reference": None,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "REAL"
            }
