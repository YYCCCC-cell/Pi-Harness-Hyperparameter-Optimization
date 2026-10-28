from decimal import Decimal
import unittest

from scripts.review_timeout_budget import scenarios


class TimeoutBudgetReviewTests(unittest.TestCase):
    def test_v4_entitlement_and_arithmetic_do_not_drop_default_or_heldout(self):
        result = scenarios("1.03555110")
        self.assertEqual((result["validation_attempts"], result["heldout_attempts"], result["total_attempts"]), (424, 80, 504))
        self.assertEqual(result["dispatch_caps_usd"], {"default": 5, "each_search": 30, "heldout": 30, "total": 155})
        self.assertEqual(Decimal(result["same_as_default_arithmetic_usd"]), Decimal("65.23971930"))

    def test_missing_bicycle_fee_has_material_budget_sensitivity(self):
        result = scenarios("2.03555110")
        self.assertEqual(result["dispatch_caps_usd"]["total"], 285)
        self.assertEqual(Decimal(result["same_as_default_arithmetic_usd"]), Decimal("128.23971930"))
