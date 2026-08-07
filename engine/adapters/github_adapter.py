import os
import re
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class GitHubAdapter:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MEGA-Freelancer-Bot",
        }
        if self.token and not self.token.startswith("ghp_aapka"):
            self.headers["Authorization"] = f"token {self.token}"

    def parse_github_url(self, url: str) -> Optional[Dict[str, str]]:
        """Parses a github issue URL to extract owner, repo, and issue_number."""
        if not url or "github.com" not in url:
            return None
        
        # Expected format: https://github.com/{owner}/{repo}/issues/{issue_number}
        match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url)
        if match:
            return {
                "owner": match.group(1),
                "repo": match.group(2),
                "issue_number": match.group(3)
            }
        return None

    def submit_proposal(self, url: str, proposal_text: str) -> Dict[str, Any]:
        """
        Attempts to submit a proposal to a GitHub issue as a comment.
        Returns a dict with:
        - success (bool)
        - error (str, optional)
        - mode (str)
        - payload (str, optional)
        - endpoint (str, optional)
        - method (str, optional)
        """
        parsed = self.parse_github_url(url)
        if not parsed:
            return {
                "success": False,
                "error": "Invalid GitHub URL",
                "mode": "DRY_RUN" if self.dry_run else "REAL"
            }
            
        endpoint = f"https://api.github.com/repos/{parsed['owner']}/{parsed['repo']}/issues/{parsed['issue_number']}/comments"
        payload = {"body": proposal_text}
        
        if self.dry_run:
            logger.info(f"[DRY_RUN] GitHubAdapter would POST to {endpoint}")
            return {
                "success": True,
                "mode": "DRY_RUN",
                "endpoint": endpoint,
                "method": "POST",
                "payload": payload,
                "message": "DRY_RUN: Simulated GitHub comment submission successfully."
            }

        # Real submission mode
        if "Authorization" not in self.headers:
            return {
                "success": False,
                "error": "GITHUB_TOKEN is required for real submission",
                "mode": "REAL"
            }
            
        try:
            response = requests.post(endpoint, json=payload, headers=self.headers, timeout=15)
        except requests.RequestException as e:
            logger.error(f"GitHubAdapter network error: {e}")
            return {
                "success": False,
                "error": f"Network error: {str(e)}",
                "mode": "REAL"
            }
            
        if response.status_code == 201:
            logger.info(f"[REAL SUBMISSION] Successfully posted comment to {url}")
            return {
                "success": True,
                "mode": "REAL",
                "endpoint": endpoint,
                "method": "POST",
                "message": "Real API submission successful"
            }
        else:
            logger.error(f"GitHub API Error {response.status_code}: {response.text}")
            return {
                "success": False,
                "error": f"API Error {response.status_code}: {response.text}",
                "mode": "REAL"
            }
