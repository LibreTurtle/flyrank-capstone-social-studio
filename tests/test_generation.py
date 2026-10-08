import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import initialize_database
from services import generate_post_variants, ingest_markdown


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.setting = patch.dict(
            os.environ,
            {
                "SOCIAL_STUDIO_DATABASE": str(
                    Path(self.temp_dir.name) / "campaign.sqlite3"
                )
            },
        )
        self.setting.start()
        initialize_database()

    def tearDown(self):
        self.setting.stop()
        self.temp_dir.cleanup()

    def test_one_stored_post_creates_two_distinct_draft_variants(self):
        post = ingest_markdown(
            "# Team notes\n\nClear notes help teams share decisions and follow up on work."
        )
        variants = generate_post_variants(post["id"])

        self.assertEqual(
            {item["platform"] for item in variants}, {"telegram", "mock_x"}
        )
        self.assertNotEqual(variants[0]["text"], variants[1]["text"])
        self.assertTrue(all(item["status"] == "draft" for item in variants))

    def test_missing_post_cannot_generate_variants(self):
        with self.assertRaisesRegex(LookupError, "Post not found"):
            generate_post_variants(999)
