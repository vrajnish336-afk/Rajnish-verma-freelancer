"""
monitoring/system_health.py — System Health Monitoring and Alerting MVP
========================================================================

Monitors system vitality across 5 critical subsystems:
  1. GitHub / cloud scanner ("cloud_scanner")
  2. local worker ("local_worker")
  3. platform adapters ("platform_adapters")
  4. AI evaluator ("ai_evaluator")
  5. notification service ("notification_service")

Core Guarantees:
  - Tracks last successful run, last failure, current status (HEALTHY, UNHEALTHY, DEGRADED, UNKNOWN), and error message.
  - Send an alert when an important component fails repeatedly.
  - Never sends repeated alerts for the exact same failure (deduplication/suppression).
  - Never reports a component as healthy unless its last check actually succeeded.
  - Handles missing data and unavailable services gracefully without uncaught exceptions.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("mega.monitoring.health")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

STATUS_HEALTHY = "HEALTHY"
STATUS_UNHEALTHY = "UNHEALTHY"
STATUS_DEGRADED = "DEGRADED"
STATUS_UNKNOWN = "UNKNOWN"

VALID_COMPONENTS = ["cloud_scanner", "local_worker", "platform_adapters", "ai_evaluator", "notification_service"]


class SystemHealthTracker:
    def __init__(self, cache_file: Optional[str] = None):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.cache_file = cache_file or os.path.join(DATA_DIR, "health_status.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.cache_file):
            initial_data = {}
            for comp in VALID_COMPONENTS:
                initial_data[comp] = {
                    "component": comp,
                    "current_status": STATUS_UNKNOWN,
                    "last_successful_run": None,
                    "last_failure": None,
                    "error_message": None,
                    "consecutive_failures": 0,
                    "last_alerted_error_hash": None
                }
            try:
                with open(self.cache_file, "w", encoding="utf-8") as fh:
                    json.dump(initial_data, fh, indent=2, ensure_ascii=False)
            except IOError:
                pass

    def _load_data(self) -> Dict[str, Any]:
        try:
            with open(self.cache_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if not isinstance(data, dict):
                    return {}
                return data
        except (json.JSONDecodeError, IOError, Exception):
            return {}

    def _save_data(self, data: Dict[str, Any]):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.warning(f"[SystemHealthTracker] Could not write health data to disk: {e}")

    def get_health_status(self, component_name: Optional[str] = None) -> Dict[str, Any]:
        """Returns health status of a specific component or all components."""
        data = self._load_data()
        if component_name:
            rec = data.get(component_name)
            if not rec:
                return {
                    "component": component_name,
                    "current_status": STATUS_UNKNOWN,
                    "last_successful_run": None,
                    "last_failure": None,
                    "error_message": None,
                    "consecutive_failures": 0
                }
            return rec
        return data

    def record_success(self, component_name: str) -> Dict[str, Any]:
        """
        Records a successful health check or operation.
        Promotes status to HEALTHY only when check explicitly succeeds.
        """
        data = self._load_data()
        if component_name not in data:
            data[component_name] = {"component": component_name}

        rec = data[component_name]
        rec["current_status"] = STATUS_HEALTHY
        rec["last_successful_run"] = datetime.utcnow().isoformat()
        rec["error_message"] = None
        rec["consecutive_failures"] = 0
        rec["last_alerted_error_hash"] = None

        self._save_data(data)
        logger.info(f"[SystemHealthTracker] Recorded SUCCESS for component '{component_name}'. Status -> HEALTHY.")
        return rec

    def record_failure(
        self,
        component_name: str,
        error_message: str,
        notifier=None,
        threshold: int = 2
    ) -> Dict[str, Any]:
        """
        Records a failure for a subsystem:
          - Sets status to UNHEALTHY immediately upon failure (never reports healthy unless last check succeeded).
          - Increments consecutive failures.
          - If consecutive failures >= threshold, triggers an alert notification.
          - Suppresses duplicate alerts for the exact same failure error message.
          - Gracefully handles offline or failing notification service.
        """
        data = self._load_data()
        if component_name not in data:
            data[component_name] = {"component": component_name, "consecutive_failures": 0}

        rec = data[component_name]
        rec["current_status"] = STATUS_UNHEALTHY
        rec["last_failure"] = datetime.utcnow().isoformat()
        rec["error_message"] = str(error_message)
        rec["consecutive_failures"] = int(rec.get("consecutive_failures", 0)) + 1

        alert_triggered = False
        alert_sent = False
        alert_reason = "No threshold breach."

        # Check repeated failure threshold
        if rec["consecutive_failures"] >= threshold:
            err_hash = f"{component_name}::{str(error_message).strip().lower()}"
            last_alerted = rec.get("last_alerted_error_hash")

            # Check duplicate alert suppression
            if last_alerted == err_hash:
                alert_triggered = False
                alert_reason = f"Repeated alert suppressed: failure '{error_message}' was already alerted."
                logger.info(f"[SystemHealthTracker] Suppressed repeat alert for '{component_name}': same error already notified.")
            else:
                alert_triggered = True
                alert_reason = f"Threshold breached ({rec['consecutive_failures']} consecutive failures). Alert triggered."
                
                # Try sending notification alert via provider
                if notifier is None:
                    try:
                        from notifications import TelegramNotifier, EVENT_SYSTEM_FAILURE
                        notifier = TelegramNotifier()
                    except Exception:
                        notifier = None

                if notifier:
                    try:
                        from notifications import EVENT_SYSTEM_FAILURE
                        res = notifier.notify(
                            event_type=EVENT_SYSTEM_FAILURE,
                            item_data={
                                "platform": f"{component_name.upper()} (Subsystem)",
                                "error": f"Repeated Failure ({rec['consecutive_failures']}x): {error_message}",
                                "title": f"Critical Subsystem Alert: {component_name}"
                            },
                            deduplication_key=f"health_alert::{err_hash}"
                        )
                        alert_sent = res.get("sent", False) if isinstance(res, dict) else False
                        # Record error hash so we don't spam repeated alerts for this exact failure!
                        rec["last_alerted_error_hash"] = err_hash
                    except Exception as e:
                        logger.error(f"[SystemHealthTracker] Graceful notification failure during health alerting: {str(e)}")
                        alert_reason += f" Notification dispatch error handled gracefully: {str(e)}"
                        # Even if notification failed, we mark as attempted/alerted to avoid tight exception retry loops
                        rec["last_alerted_error_hash"] = err_hash
                else:
                    alert_reason += " Notifier provider unavailable or offline."
                    rec["last_alerted_error_hash"] = err_hash

        rec["alert_info"] = {
            "triggered": alert_triggered,
            "sent": alert_sent,
            "reason": alert_reason
        }

        self._save_data(data)
        logger.warning(f"[SystemHealthTracker] Recorded FAILURE for '{component_name}': {error_message} (Failures: {rec['consecutive_failures']})")
        return rec
