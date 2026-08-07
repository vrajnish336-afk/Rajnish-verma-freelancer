import unittest
from platforms.github import _extract_reward
from platforms.superteam import _safe_reward

class TestRewardVerification(unittest.TestCase):
    def test_api_verified_reward(self):
        reward, is_verified = _safe_reward(5000)
        self.assertEqual(reward, 5000.0)
        self.assertTrue(is_verified)

    def test_title_based_explicit_github_reward(self):
        reward, currency, is_verified, is_conflict = _extract_reward("[Bounty $3000] Fix Blackhole destination")
        self.assertEqual(reward, 3000.0)
        self.assertEqual(currency, "USD")
        self.assertTrue(is_verified)
        self.assertFalse(is_conflict)

    def test_api_failure_no_evidence(self):
        reward, is_verified = _safe_reward(None)
        self.assertIsNone(reward)
        self.assertFalse(is_verified)

    def test_conflicting_reward_amounts_github(self):
        reward, currency, is_verified, is_conflict = _extract_reward("Bounty is $50000 but wait it's actually 5000 USDT")
        self.assertIsNone(reward)
        self.assertFalse(is_verified)
        self.assertTrue(is_conflict)

    def test_ai_only_reward_inference(self):
        pass

if __name__ == '__main__':
    unittest.main()
