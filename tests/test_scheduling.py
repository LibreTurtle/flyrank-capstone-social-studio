import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import repositories
from database import connect, initialize_database
from services import (
    approve_variant,
    generate_post_variants,
    ingest_markdown,
    publish_slot,
    resolve_unknown_publication,
)
from worker import process_due_slots


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "SOCIAL_STUDIO_DATABASE": str(
                    Path(self.temp_dir.name) / "schedule.sqlite3"
                ),
                "SOCIAL_PUBLISHER": "mock_x",
            },
        )
        self.environment.start()
        initialize_database()
        post = ingest_markdown("# Update\n\nA clear update from our team.")
        variants = generate_post_variants(post["id"])
        self.variant_id = next(
            item["id"] for item in variants if item["platform"] == "mock_x"
        )
        self.linkedin_variant_id = next(
            item["id"] for item in variants if item["platform"] == "mock_linkedin"
        )
        approve_variant(self.variant_id)

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def make_due_slot(self, key):
        scheduled_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat(
            timespec="microseconds"
        )
        return repositories.create_slot(self.variant_id, scheduled_at, key)

    def test_worker_processes_due_slots_and_next_run_does_not_duplicate(self):
        slot = self.make_due_slot("worker-slot")

        first_run = process_due_slots()
        second_run = process_due_slots()

        self.assertEqual(first_run["published"], 1)
        self.assertEqual(second_run["checked"], 0)
        with connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mock_posts").fetchone()[0], 1
            )
            self.assertEqual(
                connection.execute(
                    "SELECT state FROM slots WHERE id = ?", (slot["id"],)
                ).fetchone()[0],
                "published",
            )

    def test_worker_restart_continues_with_the_rest_of_a_due_batch(self):
        self.make_due_slot("first-batch-slot")
        approve_variant(self.linkedin_variant_id)
        linkedin_slot = repositories.create_slot(
            self.linkedin_variant_id,
            (datetime.now(UTC) - timedelta(seconds=50)).isoformat(
                timespec="microseconds"
            ),
            "second-batch-slot",
        )

        stopped_run = process_due_slots(limit=1)
        restarted_run = process_due_slots()

        self.assertEqual(stopped_run["published"], 1)
        self.assertEqual(restarted_run["published"], 1)
        self.assertEqual(
            repositories.get_slot(linkedin_slot["id"])["state"], "published"
        )
        with connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mock_posts").fetchone()[0], 2
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM publish_attempts WHERE result = 'succeeded'"
                ).fetchone()[0],
                2,
            )

    def test_worker_recovers_mock_publish_written_before_worker_stopped(self):
        slot = self.make_due_slot("interrupted-slot")
        with connect() as connection:
            attempt_id = connection.execute(
                "INSERT INTO publish_attempts (slot_id, attempt_number, adapter, result) "
                "VALUES (?, 1, 'mock_x', 'in_progress')",
                (slot["id"],),
            ).lastrowid
            connection.execute(
                "UPDATE slots SET state = 'processing' WHERE id = ?", (slot["id"],)
            )
            connection.execute(
                "INSERT INTO mock_posts (slot_id, adapter, idempotency_key, preview) "
                "VALUES (?, 'mock_x', 'interrupted-slot', 'already recorded')",
                (slot["id"],),
            )

        recovered = repositories.recover_interrupted_publications()
        run = process_due_slots()

        self.assertEqual(recovered["published"], 1)
        self.assertEqual(run["checked"], 0)
        with connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT result FROM publish_attempts WHERE id = ?", (attempt_id,)
                ).fetchone()[0],
                "succeeded",
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mock_posts").fetchone()[0], 1
            )

    def test_worker_retries_mock_publish_interrupted_before_recording(self):
        slot = self.make_due_slot("not-recorded-slot")
        with connect() as connection:
            attempt_id = connection.execute(
                "INSERT INTO publish_attempts (slot_id, attempt_number, adapter, result) "
                "VALUES (?, 1, 'mock_x', 'in_progress')",
                (slot["id"],),
            ).lastrowid
            connection.execute(
                "UPDATE slots SET state = 'processing' WHERE id = ?", (slot["id"],)
            )

        recovered = repositories.recover_interrupted_publications()
        run = process_due_slots()

        self.assertEqual(recovered["retryable"], 1)
        self.assertEqual(run["published"], 1)
        with connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT result FROM publish_attempts WHERE id = ?", (attempt_id,)
                ).fetchone()[0],
                "failed",
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mock_posts").fetchone()[0], 1
            )

    def test_interrupted_telegram_attempt_can_be_resolved_after_target_check(self):
        slot = self.make_due_slot("telegram-unknown-slot")
        with connect() as connection:
            connection.execute(
                "UPDATE slots SET state = 'processing' WHERE id = ?", (slot["id"],)
            )
            connection.execute(
                "INSERT INTO publish_attempts (slot_id, attempt_number, adapter, result) "
                "VALUES (?, 1, 'telegram', 'in_progress')",
                (slot["id"],),
            )

        repositories.recover_interrupted_publications()
        resolved = resolve_unknown_publication(slot["id"], delivered=False)
        retried = publish_slot(slot["id"])

        self.assertEqual(resolved["state"], "failed")
        self.assertEqual(retried["state"], "succeeded")
        self.assertEqual(repositories.get_slot(slot["id"])["state"], "published")


if __name__ == "__main__":
    unittest.main()
