"""
test_proposal_layer.py — Focused Tests for Proposal Generation Layer
=====================================================================

Tests:
1. valid opportunity (verified reward, requirements, deadline included cleanly)
2. missing reward (marked as unknown without guessing)
3. missing requirements (marked as unknown without guessing)
4. invented-claim prevention (blocks fabricated experience, clients, certifications)
5. persistence (links to opportunity_id, saves edits across reloading, approval required)
"""

import sys
import os
from proposals import ProposalGenerator
from engine.application_engine import ApplicationEngine

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_tests():
    print("======================================================================")
    print("   TESTING PROPOSAL GENERATION LAYER (MVP)                            ")
    print("======================================================================")
    
    generator = ProposalGenerator()

    # 1. VALID OPPORTUNITY
    print("\n[1/5] Testing Valid Opportunity Proposal Generation...")
    valid_opp = {
        "id": "opp_valid_001",
        "platform": "Superteam",
        "title": "Solana Smart Contract Fuzzing",
        "url": "https://earn.superteam.fun/bounties/fuzz-001",
        "reward": 4500.0,
        "currency": "USDC",
        "reward_verified": True,
        "description": "Scope: Perform security fuzzing on core DeFi staking vaults. Due by Nov 30, 2026."
    }
    prop_valid = generator.generate_verified_template(valid_opp)
    assert "4500.0 USDC" in prop_valid, "Verified reward missing!"
    assert "Nov 30, 2026" in prop_valid, "Verified deadline missing!"
    assert "Perform security fuzzing" in prop_valid, "Verified scope missing!"
    assert "years of experience" not in prop_valid, "Invented phrase appeared!"
    print("  ✅ Passed: Valid opportunity generated clean, concise, factual proposal.")

    # 2. MISSING REWARD
    print("\n[2/5] Testing Missing or Unverified Reward...")
    unverified_opp = {
        "id": "opp_no_reward_002",
        "platform": "GitHub",
        "title": "Refactor CLI Authentication Engine",
        "url": "https://github.com/org/repo/issues/10",
        "reward_verified": False, # Reward unverified / unstated
        "reward": None,
        "description": "Please help clean up auth tokens in CLI."
    }
    prop_unverified = generator.generate_verified_template(unverified_opp)
    assert "[Unknown/Not specified in listing]" in prop_unverified, f"Failed to mark missing reward as unknown:\n{prop_unverified}"
    assert "USD" not in prop_unverified and "USDC" not in prop_unverified, "Guessed a numerical reward!"
    print("  ✅ Passed: Missing reward explicitly marked as [Unknown/Not specified in listing] without guessing.")

    # 3. MISSING REQUIREMENTS & DEADLINE
    print("\n[3/5] Testing Missing Requirements & Deadline...")
    minimal_opp = {
        "id": "opp_min_003",
        "platform": "GitHub",
        "title": "Bug in user login modal",
        "url": "https://github.com/org/ui/issues/404",
        "description": "Small bug fix."
    }
    prop_min = generator.generate_verified_template(minimal_opp)
    assert "Project Deadline**: [Unknown/Not specified]" in prop_min, "Failed to handle missing deadline!"
    assert "Key Requirements**: [Unknown/Not explicitly specified in listing]" in prop_min, "Failed to handle missing requirements!"
    print("  ✅ Passed: Missing requirements and deadlines explicitly marked as unknown without guessing.")

    # 4. INVENTED-CLAIM PREVENTION
    print("\n[4/5] Testing Invented-Claim Prevention & Audit Filter...")
    fabricated_proposal = (
        "I have over 12 years of experience as an ex-Google tech lead and certified Solidity security auditor. "
        "In my previous clients engagement with Meta and Amazon, my portfolio generated over $50M in value."
    )
    assert generator.has_invented_claims(fabricated_proposal) is True, "Failed to detect invented claims!"
    
    cleaned_prop = generator.validate_and_clean_proposal(fabricated_proposal, valid_opp)
    assert generator.has_invented_claims(cleaned_prop) is False, "Invented claims were not cleaned out!"
    assert "ex-Google" not in cleaned_prop and "previous clients" not in cleaned_prop, "Fabricated keywords remained!"
    assert "Professional Execution Plan" in cleaned_prop, "Failed to fall back to strict verified factual plan!"
    print("  ✅ Passed: Invented claims (experience, clients, certifications, portfolio) detected and replaced with verified facts.")

    # 5. PERSISTENCE & PREVIEW/EDITING BEFORE APPROVAL
    print("\n[5/5] Testing Persistence & Proposal Preview/Editing Before Approval...")
    engine = ApplicationEngine()
    test_opp_persist = {
        "id": "opp_persist_777",
        "platform": "GitHub",
        "title": "[TEST] Persisted Proposal Opportunity",
        "url": "https://github.com/test/persist-777",
        "reward": 1000.0,
        "currency": "USD",
        "reward_verified": True,
        "description": "Deliverables: Fix concurrency deadlock in database connections."
    }
    
    # Save proposal linked to opportunity_id
    save_rec = engine.proposal_generator.generate_and_save_proposal(test_opp_persist)
    opp_id = test_opp_persist["id"]
    assert save_rec["opportunity_id"] == opp_id, "Proposal not linked to opportunity_id!"
    
    # Simulate user editing the proposal during preview in dashboard
    edited_text = "### Custom Edited Execution Plan\n- I will apply thread mutex locks to resolve the deadlock cleanly."
    engine.proposal_generator.save_proposal_edits(opp_id, edited_text)
    
    # Simulate app restart by instantiating brand new generators/engines
    reloaded_engine = ApplicationEngine()
    fetched_prop = reloaded_engine.proposal_generator.get_proposal_by_opp_id(opp_id)
    assert fetched_prop["content"] == edited_text, f"Persisted edits mismatch: {fetched_prop}"
    assert fetched_prop["is_edited"] is True, "is_edited flag not set!"
    
    # Ensure approval remains required before application can proceed
    apps_before = len(reloaded_engine.get_applications())
    reloaded_engine.create_application_draft(test_opp_persist, edited_text)
    apps_after = len(reloaded_engine.get_applications())
    assert apps_before == apps_after, "Safety violation: Opportunity bypassed human approval!"
    print("  ✅ Passed: Proposals persistently linked to opportunity_id, editable before approval, and human approval remains strictly required.")

    print("\n======================================================================")
    print("   🎉 ALL 5 FOCUSED PROPOSAL TESTS PASSED CLEANLY!                    ")
    print("======================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
