import os
import unittest
from evaluator.llm_evaluator import LLMEvaluator
from models.opportunity import Opportunity

class DummyClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                class Choice:
                    class message:
                        content = '{"estimated_hours": 10, "difficulty": 5, "success_probability_pct": 50, "task_category": "technical", "decision": "SELECT", "proposal": "This is a valid proposal."}'
                class Response:
                    choices = [Choice()]
                return Response()

class DummyEmptyProposalClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                class Choice:
                    class message:
                        content = '{"estimated_hours": 10, "difficulty": 5, "success_probability_pct": 50, "task_category": "technical", "decision": "SELECT", "proposal": ""}'
                class Response:
                    choices = [Choice()]
                return Response()

class DummyFailingClient:
    class chat:
        class completions:
            @staticmethod
            def create(*args, **kwargs):
                raise Exception("Simulated API Error")

class TestProposalGenerationFailureHandling(unittest.TestCase):
    def test_successful_proposal(self):
        evaluator = LLMEvaluator(DummyClient())
        opp_dict = {"id": "1", "platform": "GitHub", "title": "Test", "url": "http"}
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertEqual(evaluated["proposal_status"], "SUCCESS")
        self.assertEqual(evaluated["failure_reason"], "")
        self.assertEqual(evaluated["proposal"], "This is a valid proposal.")
        self.assertTrue(evaluated["proposal_exists"])
        
        opp_obj = Opportunity.from_dict(evaluated)
        self.assertTrue(opp_obj.proposal_exists)
        self.assertEqual(opp_obj.proposal, "This is a valid proposal.")
        self.assertEqual(opp_obj.proposal_status, "SUCCESS")

    def test_empty_proposal_response(self):
        evaluator = LLMEvaluator(DummyEmptyProposalClient())
        opp_dict = {"id": "2", "platform": "GitHub", "title": "Test", "url": "http"}
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertEqual(evaluated["proposal_status"], "FAILED")
        self.assertEqual(evaluated["failure_reason"], "LLM returned empty proposal")
        self.assertEqual(evaluated["proposal"], "")
        self.assertFalse(evaluated["proposal_exists"])
        
        opp_obj = Opportunity.from_dict(evaluated)
        self.assertFalse(opp_obj.proposal_exists)
        self.assertEqual(opp_obj.proposal, "")
        self.assertEqual(opp_obj.proposal_status, "FAILED")

    def test_parsing_failure(self):
        evaluator = LLMEvaluator(DummyFailingClient())
        opp_dict = {"id": "3", "platform": "GitHub", "title": "Test", "url": "http"}
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        self.assertEqual(evaluated["proposal_status"], "FAILED")
        self.assertTrue(evaluated["failure_reason"].startswith("LLM parsing failed: Simulated API Error"))
        self.assertEqual(evaluated["proposal"], "")
        self.assertFalse(evaluated["proposal_exists"])
        
        opp_obj = Opportunity.from_dict(evaluated)
        self.assertFalse(opp_obj.proposal_exists)
        self.assertEqual(opp_obj.proposal, "")
        self.assertEqual(opp_obj.proposal_status, "FAILED")

    def test_failed_proposal_blocked_from_submission(self):
        # We simulate the worker.py logic
        evaluator = LLMEvaluator(DummyFailingClient())
        opp_dict = {"id": "4", "platform": "GitHub", "title": "Test", "url": "http"}
        evaluated = evaluator.evaluate_opportunity(opp_dict)
        
        # worker.py does this:
        proposal = evaluated.get("proposal", "")
        draft_created = False
        if proposal:
            draft_created = True
        
        self.assertFalse(draft_created, "Failed proposal should not trigger draft creation")

    def test_retry_after_failure(self):
        # If it failed, the next run with a successful client should update it
        evaluator_fail = LLMEvaluator(DummyFailingClient())
        opp_dict = {"id": "5", "platform": "GitHub", "title": "Test", "url": "http"}
        evaluated = evaluator_fail.evaluate_opportunity(opp_dict)
        
        # Now simulate a retry
        evaluator_success = LLMEvaluator(DummyClient())
        retry_evaluated = evaluator_success.evaluate_opportunity(evaluated)
        
        self.assertEqual(retry_evaluated["proposal_status"], "SUCCESS")
        self.assertEqual(retry_evaluated["failure_reason"], "")
        self.assertEqual(retry_evaluated["proposal"], "This is a valid proposal.")
        self.assertTrue(retry_evaluated["proposal_exists"])

if __name__ == '__main__':
    unittest.main()
