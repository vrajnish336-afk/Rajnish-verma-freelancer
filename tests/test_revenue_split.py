import unittest
from unittest.mock import patch
import sys
import importlib
import payments.revenue_split as revenue_split

class TestRevenueSplit(unittest.TestCase):
    def test_70_30_calculation(self):
        # Normal value
        splits = revenue_split.calculate_splits(100.0)
        self.assertEqual(splits["owner_share"], 70.0)
        self.assertEqual(splits["agent_share"], 30.0)
        self.assertEqual(splits["total"], 100.0)

    def test_zero_amount(self):
        # 0 amount
        splits = revenue_split.calculate_splits(0.0)
        self.assertEqual(splits["owner_share"], 0.0)
        self.assertEqual(splits["agent_share"], 0.0)
        self.assertEqual(splits["total"], 0.0)

    def test_decimal_monetary_amounts(self):
        # Odd amounts that test rounding
        splits = revenue_split.calculate_splits(3.33)
        # owner gets 70% of 3.33 = 2.331 -> rounded to 2.33
        # agent gets 3.33 - 2.33 = 1.00
        self.assertEqual(splits["owner_share"], 2.33)
        self.assertEqual(splits["agent_share"], 1.00)
        self.assertEqual(splits["total"], 3.33)

        splits2 = revenue_split.calculate_splits(10.05)
        # 70% of 10.05 = 7.035 -> rounded to 7.04
        # agent gets 10.05 - 7.04 = 3.01
        self.assertEqual(splits2["owner_share"], 7.04)
        self.assertEqual(splits2["agent_share"], 3.01)
        self.assertEqual(splits2["total"], 10.05)

    def test_total_split_always_equals_original(self):
        # Test many odd amounts to guarantee perfect sum
        amounts = [1.01, 0.99, 1000.33, 9999.99, 15.55]
        for amt in amounts:
            splits = revenue_split.calculate_splits(amt)
            self.assertAlmostEqual(splits["owner_share"] + splits["agent_share"], amt, places=2)

    def test_invalid_percentages(self):
        # Monkey patch values and test failure
        original_owner = revenue_split.OWNER_SHARE
        original_agent = revenue_split.AGENT_SHARE
        
        try:
            revenue_split.OWNER_SHARE = 110
            revenue_split.AGENT_SHARE = -10
            with self.assertRaises(ValueError):
                revenue_split.validate_shares()
                
            revenue_split.OWNER_SHARE = 60
            revenue_split.AGENT_SHARE = 30
            with self.assertRaises(ValueError):
                revenue_split.validate_shares()
                
        finally:
            revenue_split.OWNER_SHARE = original_owner
            revenue_split.AGENT_SHARE = original_agent

if __name__ == "__main__":
    unittest.main()
