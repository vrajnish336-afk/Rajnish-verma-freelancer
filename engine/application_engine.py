import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from models.opportunity import (
    Opportunity, 
    APP_STATE_DRAFT, APP_STATE_READY, APP_STATE_APPROVED, 
    APP_STATE_SUBMITTED, APP_STATE_ACCEPTED, APP_STATE_REJECTED, 
    APP_STATE_COMPLETED,
    PAYMENT_UNKNOWN, PAYMENT_PENDING, PAYMENT_CONFIRMED
)
from notifications import ApprovalManager
from proposals import ProposalGenerator

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Application Engine State Tracking Constants
STATE_READY = "READY"
STATE_MANUAL_ACTION_REQUIRED = "MANUAL_ACTION_REQUIRED"
STATE_SUBMITTED = "SUBMITTED"
STATE_REJECTED = "REJECTED"
STATE_ACCEPTED = "ACCEPTED"
STATE_COMPLETED = "COMPLETED"
STATE_PAYMENT_PENDING = "PAYMENT_PENDING"
STATE_PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"


class ApplicationEngine:
    def __init__(self, dry_run: bool = True):
        os.makedirs(DATA_DIR, exist_ok=True)
        env_live = os.getenv("LIVE_SUBMISSION", "false").lower() == "true"
        if not dry_run and not env_live:
            logger.warning("LIVE_SUBMISSION=true is required to disable DRY_RUN. Forcing DRY_RUN=True.")
            self.dry_run = True
        else:
            self.dry_run = dry_run
        self.opps_file = os.path.join(DATA_DIR, "opportunities.json")
        self.apps_file = os.path.join(DATA_DIR, "applications.json")
        self.earn_file = os.path.join(DATA_DIR, "earnings.json")
        self.scan_file = os.path.join(DATA_DIR, "scan_log.json")
        self._ensure_files()
        self.approval_manager = ApprovalManager()
        self.proposal_generator = ProposalGenerator()

    def _ensure_files(self):
        for f in [self.opps_file, self.apps_file, self.earn_file, self.scan_file]:
            if not os.path.exists(f):
                with open(f, 'w', encoding="utf-8") as fh:
                    json.dump([], fh)

    def _load(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            with open(file_path, 'r', encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, file_path: str, data: List[Dict[str, Any]]):
        with open(file_path, 'w', encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    def has_applied(self, platform: str, url: str) -> bool:
        """Duplicate protection."""
        apps = self._load(self.apps_file)
        for app in apps:
            if app.get("platform") == platform and app.get("url") == url:
                return True
        return False

    def get_applications(self) -> List[Dict[str, Any]]:
        return self._load(self.apps_file)
        
    def get_earnings(self) -> List[Dict[str, Any]]:
        return self._load(self.earn_file)

    def get_scan_logs(self) -> List[Dict[str, Any]]:
        return self._load(self.scan_file)

    def get_latest_scan(self) -> Optional[Dict[str, Any]]:
        logs = self.get_scan_logs()
        if not logs:
            return None
        return logs[-1]

    def record_scan(
        self,
        scan_time: str,
        sources_scanned: List[str],
        opportunities_found: int,
        verified_paid_opportunities: int,
        errors: List[str],
        duration_seconds: float,
        scanner_health: Optional[Dict[str, str]] = None,
        raw_count: int = 0
    ) -> Dict[str, Any]:
        """Records a scan-cycle with scan time, sources scanned, opportunities found, verified paid opportunities, errors, and duration."""
        entry = {
            "scan_time": scan_time,
            "timestamp": scan_time,
            "sources_scanned": sources_scanned,
            "scanner_health": scanner_health or {s: "OK" for s in sources_scanned},
            "opportunities_found": opportunities_found,
            "verified_paid_opportunities": verified_paid_opportunities,
            "errors": errors,
            "duration": duration_seconds,
            "duration_seconds": duration_seconds,
            "counts": {
                "raw_scanned": raw_count or opportunities_found,
                "unique": opportunities_found,
                "verified": verified_paid_opportunities
            }
        }
        logs = self.get_scan_logs()
        logs.append(entry)
        logs = logs[-50:]  # keep last 50 runs only
        self._save(self.scan_file, logs)
        return entry

    def save_opportunity(self, opp: Opportunity):
        opps = self._load(self.opps_file)
        # Update if exists, else append
        for i, existing in enumerate(opps):
            if existing.get("id") == opp.id and existing.get("platform") == opp.platform:
                opps[i] = opp.to_dict()
                self._save(self.opps_file, opps)
                return
        opps.append(opp.to_dict())
        self._save(self.opps_file, opps)

    def create_application_draft(self, opp: Dict[str, Any], proposal: str) -> Dict[str, Any]:
        """Diverts newly discovered high-quality opportunities to PENDING_APPROVAL in ApprovalManager."""
        platform = opp.get("platform")
        url = opp.get("url")
        
        # Duplicate protection check against existing applications AND existing approvals
        if self.has_applied(platform, url) or self.approval_manager.is_tracked(platform, url):
            logger.info(f"Already applied, drafted, or tracked in approvals for {platform} - {url}")
            return {}

        # Generate verified, persistent proposal linked to opportunity_id
        prop_rec = self.proposal_generator.generate_and_save_proposal(opp, raw_proposal=proposal)
        clean_proposal = prop_rec.get("content", proposal)

        # Divert to PENDING_APPROVAL (do not add directly to applications.json)
        return self.approval_manager.register_opportunity_for_approval(opp, clean_proposal)

    def promote_approved_opportunity(self, approval_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Accepts applications ONLY from APPROVED opportunities.
        Verifies automation_allowed before assigning READY vs MANUAL_ACTION_REQUIRED.
        Prevents duplicate applications.
        """
        # 1. Block unapproved opportunities
        if approval_record.get("approval_status") != "APPROVED":
            logger.warning(f"Blocked unapproved opportunity from reaching Application Engine: status={approval_record.get('approval_status')}")
            return {}

        platform = approval_record.get("platform")
        url = approval_record.get("url")
        
        # 2. Prevent duplicate applications (using untouched has_applied logic)
        if self.has_applied(platform, url):
            logger.info(f"Duplicate application blocked for {platform} - {url}")
            return {}

        opp_id = approval_record.get("opportunity_id")
        # Ensure we fetch the most recent persistently saved/edited proposal text
        stored_prop = self.proposal_generator.get_proposal_by_opp_id(opp_id)
        final_proposal = stored_prop.get("content", approval_record.get("proposal"))

        # 3. Verify automation_allowed
        automation_allowed = approval_record.get("automation_allowed")
        if automation_allowed is None:
            for opp in self._load(self.opps_file):
                if str(opp.get("id")) == str(opp_id) or (opp.get("platform") == platform and opp.get("url") == url):
                    automation_allowed = opp.get("automation_allowed", False)
                    break

        # If automation_allowed is false (or unknown/default False), mark MANUAL_ACTION_REQUIRED
        if automation_allowed is True:
            initial_status = STATE_READY
        else:
            initial_status = STATE_MANUAL_ACTION_REQUIRED

        app_record = {
            "id": f"app_{datetime.utcnow().timestamp()}_{len(self.get_applications())+1}",
            "opportunity_id": opp_id,
            "platform": platform,
            "title": approval_record.get("title"),
            "url": url,
            "proposal": final_proposal,
            "status": initial_status,
            "automation_allowed": bool(automation_allowed),
            "created_at": datetime.utcnow().isoformat(),
            "submitted_at": None,
            "payment_status": PAYMENT_UNKNOWN,
            "reward": approval_record.get("reward"),
            "currency": approval_record.get("currency")
        }
        
        apps = self._load(self.apps_file)
        apps.append(app_record)
        self._save(self.apps_file, apps)
        logger.info(f"Accepted approved opportunity into Application Engine as [{initial_status}]: {url}")
        return app_record

    def submit_application(self, app_id: str, dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """
        Attempts application submission with strict safety guarantees:
          - Verify automation_allowed before any submission attempt.
          - If automation_allowed is false, block automation and ensure status is MANUAL_ACTION_REQUIRED.
          - DRY_RUN mode simulates the submission step only without external calls and clearly labels it as DRY_RUN.
          - Never claim an application was actually submitted unless real platform submission succeeds.
          - Never claim payment.
        """
        if dry_run is None:
            dry_run = self.dry_run

        if not dry_run:
            env_live = os.getenv("LIVE_SUBMISSION", "false").lower() == "true"
            if not env_live:
                logger.warning("LIVE_SUBMISSION=true is required for REAL submission. Forcing dry_run=True.")
                dry_run = True

        apps = self._load(self.apps_file)
        target_app = None
        for app in apps:
            if str(app.get("id")) == str(app_id) or str(app.get("opportunity_id")) == str(app_id):
                target_app = app
                break

        if not target_app:
            return {"error": "Application record not found", "success": False}

        # 1. Verify automation_allowed before any submission attempt
        if not target_app.get("automation_allowed", False) or target_app.get("status") == STATE_MANUAL_ACTION_REQUIRED:
            target_app["status"] = STATE_MANUAL_ACTION_REQUIRED
            self._save(self.apps_file, apps)
            logger.warning(f"Automation blocked for application {app_id}: automation_allowed is False -> MANUAL_ACTION_REQUIRED")
            return {
                "success": False,
                "error": "MANUAL_ACTION_REQUIRED: This platform/opportunity does not allow automated submissions.",
                "status": STATE_MANUAL_ACTION_REQUIRED,
                "actual_submission": False
            }

        # 2. Prevent duplicate submission
        if target_app.get("status") in [STATE_SUBMITTED, STATE_ACCEPTED, STATE_COMPLETED]:
            return {
                "success": False,
                "error": f"Application already processed (current state: {target_app.get('status')}). Duplicate submission blocked.",
                "status": target_app.get("status"),
                "actual_submission": False
            }

        # 3. Delegate to adapters based on platform
        platform = target_app.get("platform")
        if platform == "GitHub":
            from engine.adapters.github_adapter import GitHubAdapter
            adapter = GitHubAdapter(dry_run=dry_run)
            logger.info(f"[{'DRY_RUN' if dry_run else 'REAL'}] Routing submission to GitHubAdapter")
            res = adapter.submit_proposal(target_app.get("url"), target_app.get("proposal"))
            
            if dry_run:
                target_app["last_attempt"] = f"DRY_RUN: Simulated POST to {res.get('endpoint')}."
                target_app["dry_run_simulated_at"] = datetime.utcnow().isoformat()
                self._save(self.apps_file, apps)
                return {
                    "success": True,
                    "mode": "DRY_RUN",
                    "label": "DRY_RUN: Simulated submission step only.",
                    "actual_submission": False,
                    "status": target_app["status"],
                    "submitted_at": None,
                    "endpoint": res.get("endpoint"),
                    "method": res.get("method"),
                    "payload": res.get("payload"),
                    "message": "DRY_RUN simulation completed successfully without external submission."
                }
            else:
                if res.get("success"):
                    target_app["status"] = STATE_SUBMITTED
                    target_app["submitted_at"] = datetime.utcnow().isoformat()
                    target_app["last_attempt"] = "Real API submission successful"
                    self._save(self.apps_file, apps)
                    return {
                        "success": True,
                        "mode": "REAL",
                        "status": STATE_SUBMITTED,
                        "actual_submission": True,
                        "submitted_at": target_app["submitted_at"],
                        "message": "Submission succeeded"
                    }
                else:
                    target_app["last_attempt"] = res.get("error", "Unknown submission error")
                    self._save(self.apps_file, apps)
                    return {
                        "success": False,
                        "mode": "REAL",
                        "error": res.get("error"),
                        "actual_submission": False,
                        "status": target_app["status"],
                        "submitted_at": None
                    }
        else:
            # 4. Fallback for no adapter
            if dry_run:
                logger.info(f"[DRY_RUN] Simulating application submission step for: {target_app.get('title')}")
                target_app["last_attempt"] = "DRY_RUN: Simulated submission step only. No external request sent."
                target_app["dry_run_simulated_at"] = datetime.utcnow().isoformat()
                self._save(self.apps_file, apps)
                return {
                    "success": True,
                    "mode": "DRY_RUN",
                    "label": "DRY_RUN: Simulated submission step only.",
                    "actual_submission": False,
                    "status": target_app["status"],
                    "submitted_at": None,
                    "message": "DRY_RUN simulation completed successfully without external submission."
                }
            else:
                logger.warning(f"[REAL SUBMISSION] No external automated submission adapter confirmed for {target_app.get('platform')}. Not submitted.")
                target_app["last_attempt"] = "Real submission attempted: No platform submission adapter/credentials confirmed. Not submitted."
                self._save(self.apps_file, apps)
                return {
                    "success": False,
                    "mode": "REAL",
                    "error": "Real platform submission adapter unavailable or failed. Status remains unchanged.",
                    "actual_submission": False,
                    "status": target_app["status"],
                    "submitted_at": None
                }
        
    def update_application_status(self, app_id: str, new_status: str) -> bool:
        apps = self._load(self.apps_file)
        for app in apps:
            if app.get("id") == app_id:
                app["status"] = new_status
                if new_status == STATE_SUBMITTED:
                    app["submitted_at"] = datetime.utcnow().isoformat()
                self._save(self.apps_file, apps)
                return True
        return False

    def mark_payment_confirmed(self, app_id: str, actual_amount_received: float, tx_hash: str = None) -> bool:
        apps = self._load(self.apps_file)
        app_record = None
        for app in apps:
            if app.get("id") == app_id:
                app["payment_status"] = PAYMENT_CONFIRMED
                app["status"] = STATE_PAYMENT_CONFIRMED
                app["actual_amount_received"] = actual_amount_received
                app["payment_evidence"] = tx_hash
                app_record = app
                break
                
        if not app_record:
            return False
            
        self._save(self.apps_file, apps)
        
        # Add to earnings
        earnings = self._load(self.earn_file)
        earnings.append({
            "app_id": app_id,
            "platform": app_record.get("platform"),
            "amount": actual_amount_received,
            "currency": app_record.get("currency"),
            "tx_hash": tx_hash,
            "confirmed_at": datetime.utcnow().isoformat()
        })
        self._save(self.earn_file, earnings)
        return True
