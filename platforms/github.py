"""
platforms/github.py — GitHub Bounty Scanner
============================================

Scans GitHub for open issues that have a 'bounty' label
AND contain a verifiable reward amount in the title or body.

RULES:
  - 'help wanted' label alone does NOT mean a paid job.
  - A reward is only set if a dollar amount or token amount
    is explicitly stated in the issue text.
  - reward_verified = True only when a number is found.
  - If GITHUB_TOKEN is missing, requests are unauthenticated
    (60 req/hr limit). The scanner logs a warning and continues.
  - Respects X-RateLimit-Remaining; stops if < 5 remaining.
"""

import os
import re
import logging
from typing import List, Optional, Tuple

import requests

from models.opportunity import Opportunity
from platforms.base import BasePlatform

logger = logging.getLogger(__name__)

# Patterns that match explicit monetary amounts
_DOLLAR_RE = re.compile(r'\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)', re.IGNORECASE)
_TOKEN_RE  = re.compile(
    r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(USDC|USDT|SOL|ETH|DAI|BTC|MATIC)',
    re.IGNORECASE,
)

# Max results per scan (keeps CI runtime short; GitHub caps search at 1000)
_PER_PAGE = 15


def _extract_reward(text: str) -> Tuple[Optional[float], str, bool, bool]:
    """
    Try to extract a reward amount from text.

    Returns (reward_float, currency, reward_verified, is_conflict).
    If nothing is found returns (None, 'USD', False, False).
    If conflicting amounts are found, returns (None, 'USD', False, True).
    """
    if not text:
        return None, "USD", False, False

    amounts_found = set()
    first_currency = "USD"

    # Dollar match is strongest signal
    for m in _DOLLAR_RE.finditer(text):
        try:
            amount = float(m.group(1).replace(",", ""))
            if amount > 0:
                amounts_found.add(amount)
        except ValueError:
            pass

    # Token match (USDC / SOL / ETH etc.)
    for m in _TOKEN_RE.finditer(text):
        try:
            amount = float(m.group(1).replace(",", ""))
            currency = m.group(2).upper()
            if amount > 0:
                amounts_found.add(amount)
                # Keep the first currency we find if it's USD so far
                if first_currency == "USD":
                    first_currency = currency
        except ValueError:
            pass

    if not amounts_found:
        return None, "USD", False, False
        
    if len(amounts_found) > 1:
        # Conflict detected! Do not guess.
        return None, "USD", False, True

    return list(amounts_found)[0], first_currency, True, False


class GitHubPlatform(BasePlatform):

    @property
    def name(self) -> str:
        return "GitHub"

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MEGA-Freelancer-Bot",
        }
        if self.token and not self.token.startswith("ghp_aapka"):
            self.headers["Authorization"] = f"token {self.token}"
        else:
            logger.warning(
                "GITHUB_TOKEN not configured or invalid. "
                "Running unauthenticated (60 requests/hour limit)."
            )

    def _check_rate_limit(self, response: requests.Response) -> bool:
        """
        Return False if we're too close to the rate limit.
        Logs remaining count so it's visible in CI logs.
        """
        remaining = response.headers.get("X-RateLimit-Remaining")
        limit     = response.headers.get("X-RateLimit-Limit")
        if remaining is not None:
            remaining = int(remaining)
            logger.info(f"GitHub rate limit: {remaining}/{limit} remaining")
            if remaining < 5:
                logger.warning("GitHub rate limit nearly exhausted. Stopping scan.")
                return False
        return True

    def scan_opportunities(self) -> List[Opportunity]:
        opportunities: List[Opportunity] = []

        # Search for issues explicitly labelled "bounty"
        # We do NOT search for "help wanted" — that label alone is not a bounty.
        query = "label:bounty state:open"
        url = (
            f"https://api.github.com/search/issues"
            f"?q={query}&sort=created&order=desc&per_page={_PER_PAGE}"
        )

        try:
            response = requests.get(url, headers=self.headers, timeout=12)
        except requests.RequestException as exc:
            logger.error(f"Network error reaching GitHub API: {exc}")
            return []

        if response.status_code == 401:
            logger.error("GitHub API: 401 Unauthorised. Check GITHUB_TOKEN.")
            return []
        if response.status_code == 403:
            logger.error("GitHub API: 403 Forbidden. Rate limit exceeded or token lacks permission.")
            return []
        if response.status_code != 200:
            logger.error(f"GitHub API returned {response.status_code}: {response.text[:200]}")
            return []

        if not self._check_rate_limit(response):
            return []

        data  = response.json()
        items = data.get("items", [])
        logger.info(f"GitHub returned {data.get('total_count', '?')} total matches; processing {len(items)}.")

        for item in items:
            labels = [lbl.get("name", "").lower() for lbl in item.get("labels", [])]

            # Sanity check — issue must have "bounty" label (it was in our query,
            # but double-check in case GitHub Search returns fuzzy results)
            if "bounty" not in labels:
                continue

            title = (item.get("title") or "").strip()
            body  = (item.get("body")  or "")[:2000]  # cap body to 2000 chars

            # Try title first, then body
            reward, currency, reward_verified, is_conflict = _extract_reward(title)
            
            if is_conflict:
                reward = None
                reward_verified = False
                evidence = "Conflicting amounts found in title"
            elif not reward_verified:
                reward, currency, reward_verified, is_conflict_body = _extract_reward(body)
                if is_conflict_body:
                    reward = None
                    reward_verified = False
                    evidence = "Conflicting amounts found in body"
                else:
                    evidence = f"Amount found in body: {reward} {currency}" if reward_verified else ""
            else:
                evidence = f"Amount found in title: {reward} {currency}"

            opp = Opportunity(
                id=str(item.get("id")),
                platform=self.name,
                title=title,
                description=body,
                url=item.get("html_url", ""),
                reward=reward,
                currency=currency,
                reward_verified=reward_verified,
                reward_source="github_issue_text" if reward_verified else "unknown",
                reward_evidence=evidence,
                # GitHub issues with bounty label CAN be applied to via comments
                automation_allowed=True,
                eligibility="potentially_eligible",
            )
            opportunities.append(opp)

        logger.info(
            f"GitHub scan: {len(opportunities)} issues kept "
            f"({sum(1 for o in opportunities if o.reward_verified)} with verified reward)."
        )
        return opportunities
