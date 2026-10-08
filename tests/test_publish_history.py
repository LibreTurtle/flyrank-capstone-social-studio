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
    generate_post_variants,
    ingest_markdown,
    publish_slot,
)


class PublishHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "SOCIAL_STUDIO_DATABASE": str(
                    Path(self.temp_dir.name) / "history.sqlite3"
                ),
                "SOCIAL_PUBLISHER": "mock_x",
            },
        )
        self.environment.start()
        initialize_database()
        post = ingest_markdown("# Release\n\nWe learned a lot from this experience.")
        variant = next(
            item
            for item in generate_post_variants(post["id"])
            if item["platform"] == "mock_x"
        )
        self.variant_id = variant["id"]
        approve_variant(self.variant_id)

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_history_shows_publish_attempt_and_result(self):
        slot = repositories.create_slot(
            self.variant_id,
            (datetime.now(UTC) - timedelta(minutes=1)).isoformat(
                timespec="microseconds"
            ),
            "history-slot",
        )
        publish_slot(slot["id"])

        history = repositories.list_publish_history()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["slot_id"], slot["id"])
        self.assertEqual(history[0]["platform"], "mock_x")
        self.assertEqual(history[0]["adapter"], "mock_x")
        self.assertEqual(history[0]["result"], "succeeded")
        self.assertTrue(history[0]["remote_reference"].startswith("mock:"))
        self.assertIn("Would publish", history[0]["preview"])


if __name__ == "__main__":
    unittest.main()
