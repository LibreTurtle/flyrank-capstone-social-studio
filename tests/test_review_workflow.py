import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import repositories
from database import initialize_database
from services import (
    approve_variant,
    edit_variant,
    generate_post_variants,
    ingest_markdown,
    reject_variant,
    schedule_variant,
)


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.setting = patch.dict(
            os.environ,
            {
                "SOCIAL_STUDIO_DATABASE": str(
                    Path(self.temp_dir.name) / "review.sqlite3"
                )
            },
        )
        self.setting.start()
        initialize_database()
        post = ingest_markdown(
            "# Team notes\n\nClear notes help teams share decisions and follow up."
        )
        variants = generate_post_variants(post["id"])
        self.variant_id = next(
            item["id"] for item in variants if item["platform"] == "mock_x"
        )

    def tearDown(self):
        self.setting.stop()
        self.temp_dir.cleanup()

    def test_variant_can_be_read_and_edited_back_to_draft(self):
        edited_text = "Edited for a clearer update. #Ideas"

        variant = edit_variant(self.variant_id, edited_text)

        self.assertEqual(variant["text"], edited_text)
        self.assertEqual(variant["status"], "draft")
        self.assertEqual(repositories.get_variant(self.variant_id)["text"], edited_text)

    def test_invalid_edit_is_blocked_without_changing_the_variant(self):
        before = repositories.get_variant(self.variant_id)

        with self.assertRaisesRegex(ValueError, "maximum length"):
            edit_variant(
                self.variant_id,
                "Buy now " + "x" * 300 + " #one #two #three",
            )

        after = repositories.get_variant(self.variant_id)
        self.assertEqual(after["text"], before["text"])
        self.assertEqual(after["status"], "draft")

    def test_variant_can_be_approved_and_rejected(self):
        approved = approve_variant(self.variant_id)
        self.assertEqual(approved["status"], "approved")

        rejected = reject_variant(self.variant_id)
        self.assertEqual(rejected["status"], "rejected")

    def test_draft_variant_cannot_be_scheduled(self):
        with self.assertRaisesRegex(ValueError, "Only approved"):
            schedule_variant(self.variant_id, datetime.now(UTC) + timedelta(minutes=5))

    def test_approved_variant_can_be_scheduled_once(self):
        approve_variant(self.variant_id)
        scheduled_at = datetime.now(UTC) + timedelta(minutes=5)

        slot = schedule_variant(self.variant_id, scheduled_at)

        self.assertEqual(slot["state"], "pending")
        self.assertEqual(slot["variant_id"], self.variant_id)
        with self.assertRaisesRegex(ValueError, "already has a slot"):
            schedule_variant(self.variant_id, scheduled_at)

    def test_schedule_requires_timezone_and_future_time(self):
        approve_variant(self.variant_id)
        with self.assertRaisesRegex(ValueError, "timezone"):
            naive_time = datetime(2035, 1, 1, 10, tzinfo=UTC).replace(tzinfo=None)
            schedule_variant(self.variant_id, naive_time)
        with self.assertRaisesRegex(ValueError, "future"):
            schedule_variant(self.variant_id, datetime.now(UTC) - timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main()
