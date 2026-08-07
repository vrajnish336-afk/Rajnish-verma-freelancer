"""
notifications/telegram_notifier.py — Notification System MVP (Telegram Provider)
==============================================================================

Provides secure, throttled, and integrity-verified notification services for MEGA FREELANCER:
  - Supports Telegram as the first provider when configured in environment variables.
  - Reads credentials strictly from os.environ (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
  - Never hardcodes or prints tokens in logs or console output.
  - If unconfigured or missing credentials, execution continues normally without failing.
  - Enforces payment notification correctness: never describes potential or pending rewards as earnings; only PAYMENT_CONFIRMED uses confirmed earnings terminology.
  - Basic throttling prevents repeated scan cycles from spamming identical alerts.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger("mega.notifications.telegram")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Event Type Constants
EVENT_NEW_OPPORTUNITY = "NEW_VERIFIED_OPPORTUNITY"
EVENT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
EVENT_APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
EVENT_APPLICATION_ACCEPTED = "APPLICATION_ACCEPTED"
EVENT_APPLICATION_REJECTED = "APPLICATION_REJECTED"
EVENT_WORK_COMPLETED = "WORK_COMPLETED"
EVENT_PAYMENT_PENDING = "PAYMENT_PENDING"
EVENT_PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
EVENT_SYSTEM_FAILURE = "SYSTEM_FAILURE"


class TelegramNotifier:
    def __init__(self, enabled: Optional[bool] = None, cache_file: Optional[str] = None):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.cache_file = cache_file or os.path.join(DATA_DIR, "sent_notifications.json")
        self._ensure_cache_file()

        # Secure credential reading exclusively from environment variables
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

        # If enabled not passed explicitly, determine based on credentials and environment flag
        if enabled is not None:
            self.enabled = enabled
        else:
            env_flag = os.environ.get("TELEGRAM_NOTIFICATIONS_ENABLED", "true").lower() == "true"
            self.enabled = bool(self.token and self.chat_id and env_flag)

        if not self.enabled:
            logger.info("[TelegramNotifier] Notifications provider unconfigured or disabled. Normal application execution continues silently.")

    def _ensure_cache_file(self):
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, "w", encoding="utf-8") as fh:
                json.dump({"sent_history": {}}, fh)

    def _load_history(self) -> Dict[str, str]:
        try:
            with open(self.cache_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data.get("sent_history", {})
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_history(self, history: Dict[str, str]):
        with open(self.cache_file, "w", encoding="utf-8") as fh:
            json.dump({"sent_history": history}, fh, indent=2, ensure_ascii=False)

    def _is_throttled(self, deduplication_key: str, cooldown_hours: float = 24.0) -> bool:
        if not deduplication_key:
            return False
        history = self._load_history()
        last_sent_str = history.get(deduplication_key)
        if not last_sent_str:
            return False
        try:
            last_sent = datetime.fromisoformat(last_sent_str)
            if datetime.utcnow() - last_sent < timedelta(hours=cooldown_hours):
                return True
        except ValueError:
            return False
        return False

    def _record_sent(self, deduplication_key: str):
        if not deduplication_key:
            return
        history = self._load_history()
        history[deduplication_key] = datetime.utcnow().isoformat()
        self._save_history(history)

    def _format_message(self, event_type: str, item_data: Dict[str, Any], message_override: Optional[str] = None) -> str:
        """
        Formats alert text relying strictly on verified information and enforcing payment integrity rules:
          - Never call a potential reward an earning.
          - Only PAYMENT_CONFIRMED may be described as confirmed earnings.
        """
        if message_override and event_type != EVENT_PAYMENT_CONFIRMED:
            # Safety cleanse override if attempting to use forbidden words for unconfirmed events
            cleaned_msg = message_override.replace("Confirmed Earnings", "Potential Reward").replace("confirmed earnings", "potential reward").replace("Earned Money", "Expected Reward").replace("earned money", "expected reward")
        else:
            cleaned_msg = message_override

        title = item_data.get("title", "System Alert")
        platform = item_data.get("platform", "MEGA Engine")
        url = item_data.get("url", "No URL")
        reward = item_data.get("reward", item_data.get("expected_amount", "N/A"))
        currency = item_data.get("currency", "USD")
        reward_verified = item_data.get("reward_verified", False)
        tx_hash = item_data.get("transaction_hash") or item_data.get("tx_hash", "None")

        reward_label = f"**Potential Reward:** `{reward} {currency}`" if reward != "N/A" else ""
        if not reward_verified and event_type not in [EVENT_PAYMENT_CONFIRMED, EVENT_SYSTEM_FAILURE]:
            reward_label += " *(Unverified/Unstated in Listing)*"

        lines = []
        if event_type == EVENT_NEW_OPPORTUNITY:
            lines = [
                f"🚨 **New Verified High-Quality Opportunity Discovered!**",
                f"📌 **Title:** {title}",
                f"🌐 **Platform:** {platform}",
                f"🔗 **URL:** {url}",
                reward_label
            ]
        elif event_type == EVENT_APPROVAL_REQUIRED:
            lines = [
                f"🔔 **User Approval Required before Application Pipeline!**",
                f"📌 **Opportunity:** {title} ({platform})",
                f"🔗 **URL:** {url}",
                reward_label,
                f"👉 *Please check dashboard tab '🔔 Approvals' to review or edit proposal.*"
            ]
        elif event_type == EVENT_APPLICATION_SUBMITTED:
            lines = [
                f"📤 **Application Submitted Successfully**",
                f"📌 **Opportunity:** {title} ({platform})",
                f"🔗 **URL:** {url}",
                f"**Expected Reward upon Completion:** `{reward} {currency}`"
            ]
        elif event_type == EVENT_APPLICATION_ACCEPTED:
            lines = [
                f"🤝 **Application Accepted by Client! Work Starting.**",
                f"📌 **Project:** {title} ({platform})",
                f"**Expected Reward upon Completion:** `{reward} {currency}`"
            ]
        elif event_type == EVENT_APPLICATION_REJECTED:
            lines = [
                f"🚫 **Application / Opportunity Rejected**",
                f"📌 **Target:** {title} ({platform})",
                f"ℹ️ *Candidate blocked from automated submission.*"
            ]
        elif event_type == EVENT_WORK_COMPLETED:
            lines = [
                f"🏁 **Work Completed & Delivered!**",
                f"📌 **Project:** {title} ({platform})",
                f"**Expected Reward Awaiting Payment Verification:** `{reward} {currency}`"
            ]
        elif event_type == EVENT_PAYMENT_PENDING:
            lines = [
                f"⏳ **Payment Status: PENDING VERIFICATION**",
                f"📌 **Project:** {title} ({platform})",
                f"**Pending Payment Amount:** `{reward} {currency}`",
                f"ℹ️ *Note: Potential or pending rewards cannot be treated as finalized receipts until verified.*"
            ]
        elif event_type == EVENT_PAYMENT_CONFIRMED:
            actual_received = item_data.get("actual_amount_received", reward)
            lines = [
                f"💵 **PAYMENT CONFIRMED! Verified Earnings Updated**",
                f"📌 **Project:** {title} ({platform})",
                f"**Confirmed Payment Received:** `${actual_received} {currency}`",
                f"**Verified Evidence (TX Hash):** `{tx_hash}`",
                f"✅ *Successfully added to Confirmed Earnings dashboard total!*"
            ]
        elif event_type == EVENT_SYSTEM_FAILURE:
            err_details = item_data.get("error", "Unknown system fault.")
            lines = [
                f"⚠️ **IMPORTANT SYSTEM / SCANNER FAILURE DETECTED**",
                f"🌐 **Component / Source:** {platform}",
                f"🛑 **Error Details:** {err_details}"
            ]
        else:
            lines = [
                f"🔔 **Notification ({event_type}):** {title}",
                cleaned_msg or "No extra details."
            ]

        if cleaned_msg and not lines[-1] == cleaned_msg:
            lines.append(f"\n💬 *Note:* {cleaned_msg}")

        return "\n".join([l for l in lines if l])

    def notify(
        self,
        event_type: str,
        item_data: Dict[str, Any],
        message_override: Optional[str] = None,
        deduplication_key: Optional[str] = None,
        http_client = None
    ) -> Dict[str, Any]:
        """
        Dispatches notification via Telegram API if configured.
        Silently degrades without raising exceptions when disabled or credentials missing.
        """
        # 1. Check if disabled or missing credentials
        if not self.enabled or not self.token or not self.chat_id:
            logger.info(f"[TelegramNotifier] Skipped notification for event '{event_type}': Provider disabled or credentials missing.")
            return {
                "success": False,
                "sent": False,
                "reason": "Notification provider unconfigured or disabled. Application continues normally.",
                "throttled": False
            }

        # 2. Derive deduplication key for throttling against spam
        if not deduplication_key:
            item_id = item_data.get("id") or item_data.get("opportunity_id") or item_data.get("url") or item_data.get("title", "general")
            deduplication_key = f"{event_type}::{item_id}"

        # 3. Check throttling cooldown
        if self._is_throttled(deduplication_key):
            logger.info(f"[TelegramNotifier] Throttled duplicate alert for key: {deduplication_key}")
            return {
                "success": True,
                "sent": False,
                "throttled": True,
                "reason": f"Duplicate notification suppressed by throttle (key: {deduplication_key})."
            }

        text = self._format_message(event_type, item_data, message_override)
        api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        # Use injected mock HTTP client or default urllib poster
        try:
            if http_client is not None:
                status, resp = http_client(api_url, payload)
            else:
                req = urllib.request.Request(
                    api_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    status = response.getcode()
                    resp = json.loads(response.read().decode("utf-8"))

            if status in [200, 201] and resp.get("ok"):
                self._record_sent(deduplication_key)
                logger.info(f"[TelegramNotifier] Successfully dispatched {event_type} alert.")
                return {
                    "success": True,
                    "sent": True,
                    "throttled": False,
                    "event_type": event_type,
                    "formatted_text": text
                }
            else:
                err_text = resp.get("description", "Unknown Telegram API error.")
                # Never print or log sensitive tokens!
                logger.error(f"[TelegramNotifier] Telegram API error: {err_text}")
                return {
                    "success": False,
                    "sent": False,
                    "throttled": False,
                    "error": err_text
                }
        except Exception as e:
            err_msg = str(e)
            # Guarantee token suppression if exception text includes API URL
            if self.token and self.token in err_msg:
                err_msg = err_msg.replace(self.token, "[REDACTED_BOT_TOKEN]")
            logger.error(f"[TelegramNotifier] Safe network failure during notification dispatch: {err_msg}")
            return {
                "success": False,
                "sent": False,
                "throttled": False,
                "error": err_msg,
                "reason": "Safe network execution failure."
            }
