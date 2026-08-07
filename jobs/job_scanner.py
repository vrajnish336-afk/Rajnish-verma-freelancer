import time
import logging
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from platforms.github import GitHubPlatform
from platforms.superteam import SuperteamPlatform
from payment_states import PAYMENT_UNKNOWN

logger = logging.getLogger(__name__)

def fetch_github_opportunities() -> Tuple[List[Dict[str, Any]], str]:
    try:
        platform = GitHubPlatform()
        jobs = platform.scan_opportunities()
        return [job.to_dict() for job in jobs], "OK"
    except Exception as e:
        logger.error(f"GitHub Scanner Error: {e}\n{traceback.format_exc()}")
        return [], "FAILED"


def fetch_superteam_opportunities() -> Tuple[List[Dict[str, Any]], str]:
    try:
        platform = SuperteamPlatform()
        jobs = platform.scan_opportunities()
        return [job.to_dict() for job in jobs], "OK"
    except Exception as e:
        logger.error(f"Superteam Scanner Error: {e}\n{traceback.format_exc()}")
        return [], "FAILED"


def scan_all_jobs() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    raw_jobs: List[Dict[str, Any]] = []
    health_status: Dict[str, str] = {
        "GitHub": "FAILED",
        "Superteam": "FAILED"
    }

    gh_jobs, gh_status = fetch_github_opportunities()
    health_status["GitHub"] = gh_status
    raw_jobs.extend(gh_jobs)

    st_jobs, st_status = fetch_superteam_opportunities()
    health_status["Superteam"] = st_status
    raw_jobs.extend(st_jobs)

    return raw_jobs, health_status


class JobScanner:
    """Compatibility wrapper used by app.py."""

    def scan_for_opportunities(self) -> List[Dict[str, Any]]:
        start_time = time.time()
        scan_time = datetime.now(timezone.utc).isoformat()
        jobs, health = scan_all_jobs()
        duration_seconds = round(time.time() - start_time, 2)

        try:
            from engine.application_engine import ApplicationEngine
            engine = ApplicationEngine()
            sources_scanned = list(health.keys()) if health else ["GitHub", "Superteam"]
            errors = [f"{platform} scanner returned status: {status}" for platform, status in health.items() if status != "OK"]
            
            unique_jobs = {}
            for j in jobs:
                key = j.get("url") or f"{j.get('platform')}:{j.get('title')}"
                if key not in unique_jobs:
                    unique_jobs[key] = j
            opps_list = list(unique_jobs.values())
            verified_count = sum(1 for j in opps_list if j.get("reward_verified"))

            engine.record_scan(
                scan_time=scan_time,
                sources_scanned=sources_scanned,
                opportunities_found=len(opps_list),
                verified_paid_opportunities=verified_count,
                errors=errors,
                duration_seconds=duration_seconds,
                scanner_health=health,
                raw_count=len(jobs)
            )
        except Exception as e:
            logger.error(f"Error recording scan in JobScanner: {e}\n{traceback.format_exc()}")

        return jobs

    def scan_for_bounties(self) -> List[Dict[str, Any]]:
        return self.scan_for_opportunities()

scan_jobs = scan_all_jobs
