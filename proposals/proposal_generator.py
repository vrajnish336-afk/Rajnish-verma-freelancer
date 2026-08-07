"""
proposals/proposal_generator.py — Proposal Generation Layer
===========================================================

Generates concise, professional, personalized proposals strictly from verified opportunity data.

Rules & Safety Guarantees:
  - NEVER invent experience, clients, portfolio, certifications, reward, deadline, or requirements.
  - If required opportunity information is missing, clearly mark it as unknown instead of guessing.
  - Links each proposal persistently to opportunity_id in data/proposals.json.
  - Allows proposal preview and editing before human approval.
"""

import os
import re
import json
import logging

logger = logging.getLogger("mega.proposals")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Regex patterns catching fabricated claims or unverified credentials
_INVENTED_CLAIM_PATTERNS = [
    re.compile(r"\b(years of experience|previous clients?|past client|my client|worked at|worked for|my portfolio)\b", re.IGNORECASE),
    re.compile(r"\b(ex-(?:google|meta|amazon|apple|microsoft|netflix|uber))\b", re.IGNORECASE),
    re.compile(r"\b(bachelor|master|ph\.?d|certified|certification)\b", re.IGNORECASE),
    re.compile(r"\b(in my previous project|similar project for|my team previously)\b", re.IGNORECASE),
]


class ProposalGenerator:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.proposals_file = os.path.join(DATA_DIR, "proposals.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.proposals_file):
            with open(self.proposals_file, "w", encoding="utf-8") as fh:
                json.dump([], fh)

    def _load(self) -> list:
        try:
            with open(self.proposals_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, data: list):
        with open(self.proposals_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4, ensure_ascii=False)

    def get_proposal_by_opp_id(self, opportunity_id: str) -> dict:
        """Fetch a persistently stored proposal by its opportunity_id."""
        if not opportunity_id:
            return {}
        for prop in reversed(self._load()):
            if str(prop.get("opportunity_id")) == str(opportunity_id):
                return prop
        return {}

    def get_all_proposals(self) -> list:
        return self._load()

    def save_proposal_edits(self, opportunity_id: str, edited_content: str) -> dict:
        """Allow proposal preview/editing before approval."""
        records = self._load()
        for i, rec in enumerate(records):
            if str(rec.get("opportunity_id")) == str(opportunity_id):
                rec["content"] = edited_content.strip()
                rec["is_edited"] = True
                self._save(records)
                logger.info(f"Updated persistent proposal for opportunity_id: {opportunity_id}")
                return rec

        # If not found, create a new record linked to opportunity_id
        new_record = {
            "id": f"prop_{opportunity_id}_{len(records)+1}",
            "opportunity_id": str(opportunity_id),
            "content": edited_content.strip(),
            "is_edited": True
        }
        records.append(new_record)
        self._save(records)
        return new_record

    def has_invented_claims(self, text: str) -> bool:
        """Check if a text contains forbidden fabricated claims (experience, clients, portfolio, certifications)."""
        if not text:
            return False
        for pattern in _INVENTED_CLAIM_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def generate_verified_template(self, opp: dict) -> str:
        """
        Generate a strictly verified, factual proposal template.
        Missing information is explicitly marked as [Unknown/Not specified in listing].
        """
        title = (opp.get("title") or "Untitled").strip()
        platform = (opp.get("platform") or "Unknown Platform").strip()
        url = (opp.get("url") or "#").strip()
        desc = (opp.get("description") or "").strip()

        # 1. Reward Verification Guarantee
        if opp.get("reward_verified") and opp.get("reward") is not None and float(opp.get("reward")) > 0:
            reward_str = f"{opp.get('reward')} {opp.get('currency', 'USD')}"
        else:
            reward_str = "[Unknown/Not specified in listing]"

        # 2. Deadline Verification Guarantee
        deadline_match = re.search(r"(?:deadline|due date|closes on|due by)[:\s]+([A-Za-z0-9,\s/-]{4,25})", desc, re.IGNORECASE)
        if deadline_match and len(deadline_match.group(1).strip()) >= 4:
            deadline_str = deadline_match.group(1).strip()
        else:
            deadline_str = "[Unknown/Not specified]"

        # 3. Requirements Verification Guarantee
        req_match = re.search(r"(?:requirements?|deliverables?|expected output|scope)[:\s]+([^\n\.]{10,200})", desc, re.IGNORECASE)
        if req_match:
            requirements_str = req_match.group(1).strip()
        elif len(desc) > 30:
            # Take the objective description summary as requirement scope if detailed enough
            requirements_str = desc[:180].replace("\r", " ").replace("\n", " ") + "..."
        else:
            requirements_str = "[Unknown/Not explicitly specified in listing]"

        proposal = f"""### Professional Execution Plan: {title}
- **Target Platform**: {platform}
- **Verified Reward**: {reward_str}
- **Project Deadline**: {deadline_str}
- **Key Requirements**: {requirements_str}

#### Proposed Approach:
1. **Requirement Verification**: Review scope in [{title}]({url}) to ensure precise alignment with documented deliverables.
2. **Systematic Implementation**: Build and implement the requested functionality cleanly using standard engineering practices.
3. **Quality & Acceptance Testing**: Verify code correctness and run test validations against specified acceptance criteria prior to handover.

*Note: This proposal relies solely on verified listing data without making unstated assumptions about prior background or unverified specifications.*"""
        return proposal.strip()

    def validate_and_clean_proposal(self, raw_proposal: str, opp: dict) -> str:
        """
        Audits raw proposal text against safety rules.
        If it contains invented experience, clients, certifications, or guesses missing facts,
        replaces it with the strict verified factual template.
        """
        if not raw_proposal or len(raw_proposal.strip()) < 25:
            return self.generate_verified_template(opp)

        if self.has_invented_claims(raw_proposal):
            logger.warning(f"Invented claims detected in raw proposal for opp {opp.get('id', '?')}. Overriding with strict verified template.")
            return self.generate_verified_template(opp)

        # Even if raw proposal is kept, ensure unknown reward/requirements aren't mischaracterized
        if not opp.get("reward_verified") and re.search(r"\$[0-9]+|USDC|USDT|USD|SOL", raw_proposal):
            logger.warning(f"Unverified reward numerical guessing detected in proposal for opp {opp.get('id', '?')}. Overriding with strict verified template.")
            return self.generate_verified_template(opp)

        return raw_proposal.strip()

    def generate_and_save_proposal(self, opp: dict, raw_proposal: str = "") -> dict:
        """
        Main entry point: validates/generates proposal and stores it persistently linked to opportunity_id.
        """
        opportunity_id = str(opp.get("id", ""))
        if not opportunity_id:
            opportunity_id = f"{opp.get('platform', '?')}_{opp.get('title', '?')}"
            opp["id"] = opportunity_id

        clean_text = self.validate_and_clean_proposal(raw_proposal, opp)

        records = self._load()
        # Check if already exists; if so update unless it was manually edited by the user
        for r in records:
            if str(r.get("opportunity_id")) == opportunity_id:
                if not r.get("is_edited"):
                    r["content"] = clean_text
                    r["platform"] = opp.get("platform")
                    r["title"] = opp.get("title")
                    self._save(records)
                return r

        new_record = {
            "id": f"prop_{opportunity_id}_{len(records)+1}",
            "opportunity_id": opportunity_id,
            "platform": opp.get("platform"),
            "title": opp.get("title"),
            "content": clean_text,
            "is_edited": False
        }
        records.append(new_record)
        self._save(records)
        logger.info(f"Saved verified proposal for opportunity_id: {opportunity_id}")
        return new_record
