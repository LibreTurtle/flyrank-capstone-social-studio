import unittest

from profiles import validate_variant


class ValidationTests(unittest.TestCase):
    def test_valid_generated_text_passes_profile(self):
        self.assertEqual(
            validate_variant("mock_x", "Share clear ideas with your team. #Ideas"), []
        )

    def test_text_over_limit_reports_length_rule(self):
        problems = validate_variant("mock_x", "x" * 281)
        self.assertTrue(any("maximum length" in problem for problem in problems))

    def test_too_many_hashtags_reports_count_rule(self):
        problems = validate_variant("mock_x", "One #one #two #three")
        self.assertTrue(any("hashtag count" in problem for problem in problems))

    def test_sales_phrase_reports_tone_rule(self):
        problems = validate_variant("telegram", "Buy now and get started.")
        self.assertTrue(any("tone rule" in problem for problem in problems))

    def test_unknown_platform_is_rejected(self):
        problems = validate_variant("elsewhere", "A post")
        self.assertTrue(any("unsupported platform" in problem for problem in problems))
