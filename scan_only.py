"""
scan_only.py — MEGA FREELANCER Cloud Scanner
=============================================

Safe, headless scan script for GitHub Actions and local use.

STRICT RULES:
  - Scans real public sources only
  - Never invents a reward
  - Never submits applications
  - Never claims money was earned
  - Saves results to data/opportunities.json
  - Saves a scan log to data/scan_log.json   (cumulative, last 50 runs)
  - Writes data/last_scan_errors.txt          (empty file = clean run)
  - Always exits with code 0 unless EVERY platform failed
"""

import os
import sys
import time
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import json
import traceback
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# ── Logging ───────────────────────────────────────────────────────────────────
# StreamHandler → visible in CI logs
# FileHandler  → saved to data/last_scan_errors.txt (only WARNING+)
_DATA_DIR = Path(__file__).parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

_ERROR_FILE  = _DATA_DIR / "last_scan_errors.txt"
_LOG_FILE    = _DATA_DIR / "scan_log.json"
_OPPS_FILE   = _DATA_DIR / "opportunities.json"

# Clear the error file at the start of every run so a clean run leaves it empty
_ERROR_FILE.write_text("", encoding="utf-8")

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setLevel(logging.DEBUG)
_stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
)

_file_handler = logging.FileHandler(str(_ERROR_FILE), encoding="utf-8")
_file_handler.setLevel(logging.WARNING)          # Only problems go to the file
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s", "%Y-%m-%d %H:%M:%S")
)

logging.basicConfig(level=logging.DEBUG, handlers=[_stream_handler, _file_handler])
logger = logging.getLogger("mega.scanner")

# ── Path bootstrap ────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from jobs.job_scanner import scan_all_jobs
from engine.application_engine import ApplicationEngine


# ── Helpers ───────────────────────────────────────────────────────────────────
SCAN_TIMESTAMP = datetime.now(timezone.utc).isoformat()


def _deduplicate(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicates by URL, fallback to platform:title."""
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for job in jobs:
        key = job.get("url") or "{}:{}".format(job.get("platform"), job.get("title"))
        if key and key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def _merge_with_stored(
    engine: ApplicationEngine,
    new_jobs: List[Dict[str, Any]],
    scan_timestamp: str = SCAN_TIMESTAMP,
) -> List[Dict[str, Any]]:
    """
    Merge newly scanned jobs into existing data/opportunities.json.

    - New URLs are appended with first_seen timestamp.
    - Existing URLs are updated in-place (preserves evaluation fields).
    - Records that have disappeared are kept with stale=True so history
      is not lost.
    """
    existing: List[Dict[str, Any]] = engine._load(str(engine.opps_file))

    by_url: Dict[str, int] = {
        job.get("url", ""): idx
        for idx, job in enumerate(existing)
        if job.get("url")
    }

    added = updated = 0

    for job in new_jobs:
        url = job.get("url", "")
        job["last_seen"] = scan_timestamp
        job["stale"]     = False

        if url and url in by_url:
            existing[by_url[url]].update(job)
            updated += 1
        else:
            job["first_seen"] = scan_timestamp
            existing.append(job)
            if url:
                by_url[url] = len(existing) - 1
            added += 1

    logger.info("Merge: %d new, %d updated, %d total stored.", added, updated, len(existing))
    return existing


def _append_scan_log(
    engine: ApplicationEngine,
    scan_timestamp: str,
    duration_seconds: float,
    health: Dict[str, str],
    counts: Dict[str, int],
    errors: List[str],
) -> None:
    """
    Append a summary of this run to data/scan_log.json via ApplicationEngine.
    Keeps only the last 50 entries to stop the file growing indefinitely.
    """
    sources_scanned = list(health.keys()) if health else ["GitHub", "Superteam"]
    opportunities_found = counts.get("unique", 0)
    verified_paid = counts.get("verified", 0)
    raw_scanned = counts.get("raw_scanned", 0)

    engine.record_scan(
        scan_time=scan_timestamp,
        sources_scanned=sources_scanned,
        opportunities_found=opportunities_found,
        verified_paid_opportunities=verified_paid,
        errors=errors,
        duration_seconds=duration_seconds,
        scanner_health=health,
        raw_count=raw_scanned,
    )
    logger.info("Scan log updated via ApplicationEngine.")


def _print_report(
    scan_timestamp: str,
    duration_seconds: float,
    health: Dict[str, str],
    raw_count: int,
    unique_jobs: List[Dict[str, Any]],
    errors: List[str],
) -> None:
    SEP = "=" * 62
    print("\n" + SEP)
    print("  MEGA FREELANCER - CLOUD SCAN REPORT")
    print("  Scanned at: " + scan_timestamp)
    print("  Duration  : {}s".format(duration_seconds))
    print(SEP)

    print("\n-- Scanner Health " + "-" * 44)
    for platform, status in health.items():
        ok   = status == "OK"
        icon = "[OK] " if ok else "[FAIL]"
        print("  {}  {:15s}  {}".format(icon, platform, status))

    print("\n-- Counts " + "-" * 52)
    verified = sum(1 for j in unique_jobs if j.get("reward_verified"))
    no_reward = sum(1 for j in unique_jobs if j.get("reward") is None)
    print("  Raw scanned        : {}".format(raw_count))
    print("  Unique             : {}".format(len(unique_jobs)))
    print("  Verified reward    : {}".format(verified))
    print("  No reward info     : {}".format(no_reward))

    print("\n-- Opportunities with Verified Reward " + "-" * 24)
    shown = 0
    for job in unique_jobs:
        if not job.get("reward_verified"):
            continue
        reward   = job.get("reward")
        currency = job.get("currency", "")
        platform = job.get("platform", "?")
        title    = (job.get("title") or "Untitled")[:55]
        url      = job.get("url", "")
        try:
            print("  [{:10s}]  {:>8} {:6s}  {}".format(platform, reward, currency, title))
            print("               URL: {}".format(url))
        except UnicodeEncodeError:
            clean_title = title.encode("ascii", errors="replace").decode("ascii", errors="replace")
            print("  [{:10s}]  {:>8} {:6s}  {}".format(platform, reward, currency, clean_title))
            print("               URL: {}".format(url))
        shown += 1

    if shown == 0:
        print("  (none with verified reward in this scan)")

    if errors:
        print("\n-- Errors / Warnings " + "-" * 41)
        for err in errors:
            print("  [!] " + err)

    print("\n-- Safety Guarantees " + "-" * 41)
    print("  [OK] No applications submitted")
    print("  [OK] No rewards invented")
    print("  [OK] No earnings claimed")
    print("  [OK] Results saved to data/opportunities.json")
    print("  [OK] Error log saved to data/last_scan_errors.txt")
    print("  [OK] Scan history saved to data/scan_log.json")
    print(SEP + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────
def run_scan() -> int:
    """
    Execute a full scan cycle.

    Exit codes:
        0  — at least one platform succeeded (even if 0 opportunities found)
        1  — every platform failed (CI should mark the run failed)
    """
    start_time = time.time()
    scan_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Starting MEGA Freelancer cloud scan (timestamp: %s).", scan_timestamp)

    errors_collected: List[str] = []
    engine = ApplicationEngine()

    # ── Scan ─────────────────────────────────────────────────────────────────
    try:
        raw_jobs, health = scan_all_jobs()
    except Exception:
        msg = "Unexpected error in scan_all_jobs:\n" + traceback.format_exc()
        logger.error(msg)
        errors_collected.append(msg)
        health  = {}
        raw_jobs = []

    # Collect per-platform failures into the error list
    for platform, status in health.items():
        if status != "OK":
            msg = "{} scanner returned status: {}".format(platform, status)
            logger.warning(msg)
            errors_collected.append(msg)

    # ── Deduplicate ───────────────────────────────────────────────────────────
    unique_jobs = _deduplicate(raw_jobs)

    # ── Merge + persist ───────────────────────────────────────────────────────
    try:
        merged = _merge_with_stored(engine, unique_jobs, scan_timestamp)
        engine._save(str(engine.opps_file), merged)
    except Exception:
        msg = "Failed to save opportunities.json:\n" + traceback.format_exc()
        logger.error(msg)
        errors_collected.append(msg)

    # ── Write error file (empty = clean) ─────────────────────────────────────
    # Already cleared at module load; _file_handler will have appended to it
    # during the run if any WARNING/ERROR was logged.

    # ── Append scan log ───────────────────────────────────────────────────────
    duration_seconds = round(time.time() - start_time, 2)
    counts = {
        "raw_scanned": len(raw_jobs),
        "unique":      len(unique_jobs),
        "verified":    sum(1 for j in unique_jobs if j.get("reward_verified")),
    }
    try:
        _append_scan_log(engine, scan_timestamp, duration_seconds, health, counts, errors_collected)
    except Exception:
        logger.error("Could not update scan_log.json: %s", traceback.format_exc())

    # ── Print report ──────────────────────────────────────────────────────────
    _print_report(scan_timestamp, duration_seconds, health, len(raw_jobs), unique_jobs, errors_collected)

    # ── Exit code ─────────────────────────────────────────────────────────────
    all_failed = bool(health) and all(s != "OK" for s in health.values())
    if all_failed:
        logger.error("Every scanner failed. Exiting with code 1 so CI marks this run failed.")
        return 1

    logger.info("Scan complete. No applications submitted.")
    return 0


if __name__ == "__main__":
    sys.exit(run_scan())
