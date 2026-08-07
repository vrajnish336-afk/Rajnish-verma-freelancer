"""
main.py — MEGA Freelancer Local Worker Entrypoint
=================================================

Launches the controlled background Windows worker to continuously scan
and evaluate opportunities with configurable scan intervals and graceful shutdown.
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv

from pipeline import LocalWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mega.main")


def parse_args():
    load_dotenv()
    default_interval = int(os.getenv("WORKER_SCAN_INTERVAL", "300"))
    
    parser = argparse.ArgumentParser(description="MEGA Freelancer Controlled Local Worker")
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=default_interval,
        help=f"Scan interval in seconds between cycles (default: {default_interval}s)"
    )
    parser.add_argument(
        "-c", "--cycles",
        type=int,
        default=0,
        help="Number of scan cycles to execute before stopping (default: 0 = infinite until shutdown)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one scan cycle and exit (shortcut for --cycles 1)"
    )
    return parser.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = parse_args()
    max_cycles = 1 if args.once else args.cycles

    print("============================================================")
    print("      MEGA FREELANCER - CONTROLLED LOCAL WORKER             ")
    print(f"      Interval: {args.interval}s | Max Cycles: {'1 (once)' if args.once else (max_cycles or 'Unlimited')}")
    print("============================================================")

    worker = LocalWorker(interval_seconds=args.interval, max_cycles=max_cycles)
    exit_code = worker.start()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
