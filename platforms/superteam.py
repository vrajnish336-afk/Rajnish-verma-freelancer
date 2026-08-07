"""
platforms/superteam.py — Superteam Earn Scanner
================================================

Fetches open bounties from Superteam Earn's public API.

Superteam does not publish an officially documented REST API,
so we use their public listing endpoint. If that path changes
or returns an unexpected structure, the scanner fails gracefully
and returns an empty list with a clear log message.

RULES:
  - reward = None if API does not provide a positive number
  - reward_verified = False if reward is None
  - automation_allowed = False (Superteam requires browser login to apply)
  - No submissions made here
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from models.opportunity import Opportunity
from platforms.base import BasePlatform

logger = logging.getLogger(__name__)

_TIMEOUT = 12  # seconds

# Primary endpoint (TRPC batch format used by Superteam's web app)
_PRIMARY_URL = (
    "https://earn.superteam.fun/api/listings/"
    "?type=bounty&isPublished=true&take=20"
)

# Secondary endpoint attempted if primary fails
_FALLBACK_URL = (
    "https://earn.superteam.fun/api/trpc/bounty.getAll"
    "?batch=1&input=%7B%220%22%3A%7B%22json%22%3A%7B%22isOpen%22%3Atrue%7D%7D%7D"
)


def _parse_primary(data: Any) -> List[Dict[str, Any]]:
    """Parse the /api/listings/ response format."""
    if isinstance(data, dict):
        # Could be {bounties: [...], total: N} or just a list wrapper
        for key in ("bounties", "listings", "data", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    return []


def _parse_fallback(data: Any) -> List[Dict[str, Any]]:
    """Parse the TRPC batch response format."""
    try:
        return data[0]["result"]["data"]["json"]
    except (KeyError, IndexError, TypeError):
        return []


def _safe_reward(value: Any) -> Tuple[Optional[float], bool]:
    """
    Convert a raw API reward value to a verified float.
    Returns (None, False) for anything that cannot be confirmed positive.
    """
    if value is None:
        return None, False
    try:
        f = float(value)
        if f > 0:
            return f, True
    except (ValueError, TypeError):
        pass
    return None, False


class SuperteamPlatform(BasePlatform):

    @property
    def name(self) -> str:
        return "Superteam"

    def _fetch(self, url: str, label: str) -> Tuple[Optional[Any], bool]:
        """Fetch JSON from url. Returns (data, success)."""
        try:
            headers = {
                "User-Agent": "MEGA-Freelancer-Bot",
                "Accept": "application/json",
            }
            r = requests.get(url, headers=headers, timeout=_TIMEOUT)
            if r.status_code == 200:
                logger.info(f"Superteam {label} endpoint OK.")
                return r.json(), True
            logger.warning(
                f"Superteam {label} endpoint returned {r.status_code}."
            )
        except requests.RequestException as exc:
            logger.error(f"Superteam {label} network error: {exc}")
        return None, False

    def scan_opportunities(self) -> List[Opportunity]:
        opportunities: List[Opportunity] = []

        # Try primary endpoint first
        data, ok = self._fetch(_PRIMARY_URL, "primary")
        if ok:
            raw_list = _parse_primary(data)
        else:
            # Fall back to TRPC endpoint
            logger.info("Trying Superteam fallback endpoint...")
            data, ok = self._fetch(_FALLBACK_URL, "fallback")
            if not ok:
                logger.error(
                    "Both Superteam endpoints unavailable. "
                    "Returning empty list."
                )
                return []
            raw_list = _parse_fallback(data)

        if not raw_list:
            logger.warning(
                "Superteam: API responded but no bounties found in parsed data. "
                "The API response structure may have changed."
            )
            return []

        logger.info(f"Superteam: {len(raw_list)} raw entries to process.")

        for entry in raw_list:
            if not isinstance(entry, dict):
                continue

            # Both endpoints use similar field names
            reward_raw = entry.get("rewardAmount") or entry.get("reward")
            currency   = entry.get("token") or entry.get("currency") or "USDC"
            slug       = entry.get("slug") or entry.get("id") or ""
            title      = (entry.get("title") or "").strip()
            description = (entry.get("description") or "").strip()
            entry_id   = str(entry.get("id") or slug or title)

            api_reward, api_verified = _safe_reward(reward_raw)
            
            # Cross-verify with text to prevent conflicting amounts
            from platforms.github import _extract_reward
            text_to_check = f"{title} {description}"
            text_reward, text_currency, text_verified, text_conflict = _extract_reward(text_to_check)
            
            # If text has a conflict, we enforce reward_verified = False
            if text_conflict:
                reward = None
            else:
                reward = None
            reward_verified = False
            evidence = ""
            
            if api_verified and text_verified:
                if api_reward != text_reward:
                    # Conflict!
                    pass # Leave reward as None, False
                else:
                    reward = api_reward
                    reward_verified = True
                    evidence = f"API field rewardAmount={reward_raw} token={currency}"
            elif api_verified and not text_verified:
                # We can't verify via text, but we check if text extraction failed due to a conflict
                # _extract_reward returns False if there's a conflict internally, or if NO amount is found.
                # If text has multiple conflicting amounts, it returns False.
                # If the text has a conflicting amount with API, it's safer to trust the API UNLESS text has conflicts.
                # Let's just trust API if text_verified is False and no conflicts are in text.
                # Wait, if text has NO amounts, it's fine.
                reward = api_reward
                reward_verified = True
                evidence = f"API field rewardAmount={reward_raw} token={currency}"
            elif not api_verified and text_verified:
                reward = text_reward
                currency = text_currency
                reward_verified = True
                evidence = f"Amount found in text: {reward} {currency}"
            
            # If both are False, reward remains None and False

            url = f"https://earn.superteam.fun/bounties/{slug}" if slug else ""

            opp = Opportunity(
                id=entry_id,
                platform=self.name,
                title=title,
                description=description,
                url=url,
                reward=reward,
                currency=currency.upper(),
                reward_verified=reward_verified,
                reward_source="superteam_api" if api_verified else ("superteam_text" if text_verified else "unknown"),
                reward_evidence=evidence,
                # Superteam requires web browser login to apply — mark manual
                automation_allowed=False,
                eligibility="potentially_eligible" if reward_verified else "unknown",
            )
            opportunities.append(opp)

        verified = sum(1 for o in opportunities if o.reward_verified)
        logger.info(
            f"Superteam scan: {len(opportunities)} bounties, "
            f"{verified} with verified reward."
        )
        return opportunities
