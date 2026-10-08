import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx

import repositories
from database import connect, initialize_database
from publishers import PublishFailure
from services import (
    approve_variant,
    generate_post_variants,
    ingest_markdown,
    publish_slot,
)
from telegram_publisher import TelegramPublisher


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {
                "SOCIAL_STUDIO_DATABASE": str(
                    Path(self.temp_dir.name) / "publish.sqlite3"
                ),
                "SOCIAL_PUBLISHER": "",
            },
        )
        self.environment.start()
        initialize_database()
        post = ingest_markdown(
            "# Team notes\n\nClear notes help teams share decisions."
        )
        variants = generate_post_variants(post["id"])
        self.variant = next(item for item in variants if item["platform"] == "mock_x")

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def due_slot(self, approved=True):
        if approved:
            approve_variant(self.variant["id"])
        timestamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat(
            timespec="microseconds"
        )
        return repositories.create_slot(
            self.variant["id"], timestamp, f"variant-{self.variant['id']}-slot-1"
        )

    def test_mock_publish_repeats_return_one_saved_post(self):
        slot = self.due_slot()

        first = publish_slot(slot["id"])
        repeated = publish_slot(slot["id"])

        self.assertEqual(first["state"], "succeeded")
        self.assertFalse(first["idempotent"])
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(first["remote_reference"], repeated["remote_reference"])
        with connect() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM mock_posts").fetchone()[0], 1
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM publish_attempts").fetchone()[
                    0
                ],
                1,
            )
        self.assertEqual(
            repositories.get_variant(self.variant["id"])["status"], "published"
        )

    def test_unapproved_and_future_slots_are_not_published(self):
        timestamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat(
            timespec="microseconds"
        )
        with connect() as connection:
            cursor = connection.execute(
                "INSERT INTO slots (variant_id, scheduled_at, idempotency_key) VALUES (?, ?, ?)",
                (self.variant["id"], timestamp, "unapproved-slot"),
            )
            unapproved_slot_id = cursor.lastrowid
        with self.assertRaisesRegex(ValueError, "Only approved"):
            publish_slot(unapproved_slot_id)

        approve_variant(self.variant["id"])
        future = repositories.create_slot(
            self.variant["id"],
            (datetime.now(UTC) + timedelta(minutes=5)).isoformat(
                timespec="microseconds"
            ),
            "future-slot",
        )
        with self.assertRaisesRegex(ValueError, "not due"):
            publish_slot(future["id"])

    def test_configuration_can_swap_to_another_mock_adapter(self):
        slot = self.due_slot()
        with patch.dict(os.environ, {"SOCIAL_PUBLISHER": "mock_linkedin"}):
            result = publish_slot(slot["id"])
        self.assertEqual(result["adapter"], "mock_linkedin")

    def test_telegram_adapter_parses_successful_send(self):
        def respond(request):
            self.assertEqual(request.url.path, "/botbottoken/sendMessage")
            self.assertEqual(request.read(), b'{"chat_id":"@channel","text":"hello"}')
            return httpx.Response(
                200,
                json={"ok": True, "result": {"chat": {"id": -1001}, "message_id": 24}},
            )

        publisher = TelegramPublisher(
            "bottoken", "@channel", httpx.MockTransport(respond)
        )
        result = publisher.publish(text="hello", idempotency_key="key")
        self.assertEqual(result.remote_reference, "-1001:24")
        self.assertEqual(result.preview, "hello")

    def test_telegram_rejection_is_a_known_failure(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ok": False, "description": "chat not found"}
            )
        )
        publisher = TelegramPublisher("bottoken", "@channel", transport)
        with self.assertRaisesRegex(PublishFailure, "chat not found") as raised:
            publisher.publish(text="hello", idempotency_key="key")
        self.assertFalse(raised.exception.uncertain)

    def test_telegram_network_error_is_uncertain(self):
        transport = httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timed out"))
        )
        publisher = TelegramPublisher("bottoken", "@channel", transport)
        with self.assertRaises(PublishFailure) as raised:
            publisher.publish(text="hello", idempotency_key="key")
        self.assertTrue(raised.exception.uncertain)


if __name__ == "__main__":
    unittest.main()
