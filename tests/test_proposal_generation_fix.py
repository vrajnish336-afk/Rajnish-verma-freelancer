import os
import json
import unittest
from evaluator.llm_evaluator import LLMEvaluator
from proposals.proposal_generator import ProposalGenerator
from engine.application_engine import ApplicationEngine
from models.opportunity import Opportunity

class DummyClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                class Choice:
                    class message:
                        content = '{"estimated_hours": 10, "difficulty": 5, "success_probability_pct": 50, "task_category": "technical", "decision": "SELECT", "proposal": "This is a valid proposal for the test case."}'
                class Response:
                    choices = [Choice()]
                return Response()

class DummyFailingClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                raise Exception("Simulated API Error")

class TestProposalGenerationFix(unittest.TestCase):
    def setUp(self):
        # Create fresh data directory for tests
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.prop_file = os.path.join(self.data_dir, "proposals.json")
        if os.path.exists(self.prop_file):
            os.remove(self.prop_file)

    def test_verified_github_opportunity_proposal_generated(self):
        evaluator = LLMEvaluator(DummyClient())
        opp_dict = {
            "id": "github_1",
            "platform": "GitHub",
            "title": "Fix bug",
            "url": "http://example.com/1",
            "reward": 1000,
            "currency": "USD",
            "reward_verified": True,
            "automation_allowed": True
        }
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertIn("This is a valid proposal", evaluated["proposal"])

        # Check Opportunity dataclass supports the field
        opp_obj = Opportunity.from_dict(evaluated)
        self.assertEqual(opp_obj.proposal, evaluated["proposal"])

    def test_missing_opportunity_data_safe_failure(self):
        evaluator = LLMEvaluator(DummyClient())
        opp_dict = {
            "id": "missing_1",
            "platform": "Unknown",
            "title": "Untitled",
            "url": "http://example.com/missing"
        }  # Minimal required fields
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertEqual(evaluated.get("title"), "Untitled")
        self.assertIn("proposal", evaluated)

    def test_proposal_persistence(self):
        gen = ProposalGenerator()
        opp_dict = {"id": "github_2", "platform": "GitHub", "title": "Test 2"}
        rec = gen.generate_and_save_proposal(opp_dict, "This is a raw proposal that is long enough to pass validation!")
        
        # Check if it was persisted
        records = gen._load()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["opportunity_id"], "github_2")

    def test_proposal_generation_failure_visible(self):
        evaluator = LLMEvaluator(DummyFailingClient())
        opp_dict = {
            "id": "github_failing",
            "platform": "GitHub",
            "title": "Failing test",
            "url": "http://example.com/fail"
        }
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertEqual(evaluated.get("proposal", ""), "")
        
        opp_obj = Opportunity.from_dict(evaluated)
        self.assertEqual(opp_obj.proposal, "")

    def test_duplicate_opportunity_does_not_create_duplicate_proposals(self):
        gen = ProposalGenerator()
        opp_dict = {"id": "github_duplicate", "platform": "GitHub"}
        
        # First save
        gen.generate_and_save_proposal(opp_dict, "First long proposal that is definitely long enough.")
        
        # Second save with same id
        gen.generate_and_save_proposal(opp_dict, "Second long proposal that is also long enough.")
        
        records = gen._load()
        # Should still be 1 because it updates instead of duplicating
        self.assertEqual(len([r for r in records if r["opportunity_id"] == "github_duplicate"]), 1)

if __name__ == '__main__':
    unittest.main()
