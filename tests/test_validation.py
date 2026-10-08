import unittest

from profiles import validate_variant


class ValidationTests(unittest.TestCase):
    def test_valid_generated_text_passes_profile(self):
        result = validate_variant("mock_x", "Share clear ideas with your team. #Ideas")
        self.assertEqual(result, {"valid": True, "errors": []})

    def test_text_over_limit_reports_length_rule(self):
        result = validate_variant("mock_x", "x" * 281)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("maximum length" in problem for problem in result["errors"])
        )

    def test_too_many_hashtags_reports_count_rule(self):
        result = validate_variant("mock_x", "One #one #two #three")
        self.assertTrue(any("hashtag count" in problem for problem in result["errors"]))

    def test_sales_phrase_reports_tone_rule(self):
        result = validate_variant("telegram", "Buy now and get started.")
        self.assertTrue(any("tone rule" in problem for problem in result["errors"]))

    def test_unknown_platform_is_rejected(self):
        result = validate_variant("elsewhere", "A post")
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("unsupported platform" in problem for problem in result["errors"])
        )
