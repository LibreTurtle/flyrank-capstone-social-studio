import json
import sqlite3

from database import connect


def create_post(
    source_type: str, title: str, body: str, source_url: str | None = None
) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO posts (source_type, source_url, title, body) VALUES (?, ?, ?, ?)",
            (source_type, source_url, title, body),
        )
        row = connection.execute(
            "SELECT * FROM posts WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_post(post_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        return dict(row) if row else None


def create_variant(post_id: int, platform: str, text: str) -> dict:
    try:
        with connect() as connection:
            cursor = connection.execute(
                "INSERT INTO variants (post_id, platform, text, validation_result) VALUES (?, ?, ?, ?)",
                (post_id, platform, text, json.dumps([])),
            )
            row = connection.execute(
                "SELECT * FROM variants WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed: variants.post_id, variants.platform" in str(
            error
        ):
            raise ValueError(
                f"A {platform} variant already exists for this post"
            ) from error
        raise


def list_variants(post_id: int) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM variants WHERE post_id = ? ORDER BY id", (post_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_variant(variant_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM variants WHERE id = ?", (variant_id,)
        ).fetchone()
        return dict(row) if row else None


def update_variant_text(variant_id: int, text: str) -> dict | None:
    with connect() as connection:
        variant = connection.execute(
            "SELECT status FROM variants WHERE id = ?", (variant_id,)
        ).fetchone()
        if variant is None:
            return None
        if variant["status"] == "published":
            raise ValueError("Published variants cannot be edited")

        connection.execute(
            "UPDATE variants SET text = ?, status = 'draft', updated_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (text, variant_id),
        )
        connection.execute(
            "DELETE FROM slots WHERE variant_id = ? AND state = 'pending'",
            (variant_id,),
        )
        row = connection.execute(
            "SELECT * FROM variants WHERE id = ?", (variant_id,)
        ).fetchone()
        return dict(row)


def set_variant_status(variant_id: int, status: str) -> dict | None:
    with connect() as connection:
        variant = connection.execute(
            "SELECT status FROM variants WHERE id = ?", (variant_id,)
        ).fetchone()
        if variant is None:
            return None
        if variant["status"] == "published":
            raise ValueError("Published variants cannot be reviewed")

        connection.execute(
            "UPDATE variants SET status = ?, updated_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (status, variant_id),
        )
        if status == "rejected":
            connection.execute(
                "DELETE FROM slots WHERE variant_id = ? AND state = 'pending'",
                (variant_id,),
            )
        row = connection.execute(
            "SELECT * FROM variants WHERE id = ?", (variant_id,)
        ).fetchone()
        return dict(row)


def create_slot(variant_id: int, scheduled_at: str, idempotency_key: str) -> dict:
    try:
        with connect() as connection:
            variant = connection.execute(
                "SELECT status FROM variants WHERE id = ?", (variant_id,)
            ).fetchone()
            if variant is None:
                raise LookupError("Variant not found")
            if variant["status"] != "approved":
                raise ValueError("Only approved variants can be scheduled")

            cursor = connection.execute(
                "INSERT INTO slots (variant_id, scheduled_at, idempotency_key) "
                "VALUES (?, ?, ?)",
                (variant_id, scheduled_at, idempotency_key),
            )
            row = connection.execute(
                "SELECT * FROM slots WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(row)
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed: slots.variant_id, slots.scheduled_at" in str(
            error
        ):
            raise ValueError("This variant already has a slot at that time") from error
        raise


def get_slot(slot_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT slots.*, variants.platform, variants.text, variants.status AS variant_status "
            "FROM slots JOIN variants ON variants.id = slots.variant_id "
            "WHERE slots.id = ?",
            (slot_id,),
        ).fetchone()
        return dict(row) if row else None


def get_successful_attempt(slot_id: int) -> dict | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM publish_attempts WHERE slot_id = ? AND result = 'succeeded'",
            (slot_id,),
        ).fetchone()
        return dict(row) if row else None


def claim_slot_for_publication(slot_id: int, adapter: str, now: str) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT slots.*, variants.platform, variants.text, variants.status AS variant_status "
            "FROM slots JOIN variants ON variants.id = slots.variant_id "
            "WHERE slots.id = ?",
            (slot_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Schedule slot not found")
        slot = dict(row)

        if slot["state"] == "published":
            successful = connection.execute(
                "SELECT * FROM publish_attempts "
                "WHERE slot_id = ? AND result = 'succeeded'",
                (slot_id,),
            ).fetchone()
            if successful is None:
                raise RuntimeError("Published slot has no successful attempt")
            return {"already_published": True, **slot, **dict(successful)}

        if slot["state"] == "processing":
            raise ValueError(
                "This slot is already being published or its delivery result is unknown."
            )
        if slot["scheduled_at"] > now:
            raise ValueError("This slot is not due yet")
        if slot["variant_status"] != "approved":
            raise ValueError("Only approved variants can be published")

        previous = connection.execute(
            "SELECT MAX(attempt_number) FROM publish_attempts WHERE slot_id = ?",
            (slot_id,),
        ).fetchone()[0]
        attempt_number = (previous or 0) + 1
        cursor = connection.execute(
            "INSERT INTO publish_attempts (slot_id, attempt_number, adapter, result) "
            "VALUES (?, ?, ?, 'in_progress')",
            (slot_id, attempt_number, adapter),
        )
        connection.execute(
            "UPDATE slots SET state = 'processing', updated_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (slot_id,),
        )
        return {
            **slot,
            "attempt_id": cursor.lastrowid,
            "attempt_number": attempt_number,
            "adapter": adapter,
            "already_published": False,
        }


def finish_slot_publication(
    slot_id: int, attempt_id: int, remote_reference: str, preview: str
) -> dict:
    with connect() as connection:
        connection.execute(
            "UPDATE publish_attempts SET result = 'succeeded', remote_reference = ?, "
            "preview = ?, finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND slot_id = ? AND result = 'in_progress'",
            (remote_reference, preview, attempt_id, slot_id),
        )
        connection.execute(
            "UPDATE slots SET state = 'published', updated_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ? AND state = 'processing'",
            (slot_id,),
        )
        connection.execute(
            "UPDATE variants SET status = 'published', updated_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = (SELECT variant_id FROM slots WHERE id = ?)",
            (slot_id,),
        )
        row = connection.execute(
            "SELECT * FROM publish_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return dict(row)


def fail_slot_publication(
    slot_id: int, attempt_id: int, message: str, uncertain: bool
) -> None:
    result = "unknown" if uncertain else "failed"
    with connect() as connection:
        connection.execute(
            "UPDATE publish_attempts SET result = ?, error = ?, "
            "finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
            "WHERE id = ? AND slot_id = ? AND result = 'in_progress'",
            (result, message, attempt_id, slot_id),
        )
        if not uncertain:
            connection.execute(
                "UPDATE slots SET state = 'failed', updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ', 'now') "
                "WHERE id = ? AND state = 'processing'",
                (slot_id,),
            )


def record_mock_post(adapter: str, idempotency_key: str, preview: str) -> dict:
    with connect() as connection:
        slot = connection.execute(
            "SELECT id FROM slots WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if slot is None:
            raise ValueError("No schedule slot matches this idempotency key")
        connection.execute(
            "INSERT OR IGNORE INTO mock_posts (slot_id, adapter, idempotency_key, preview) "
            "VALUES (?, ?, ?, ?)",
            (slot["id"], adapter, idempotency_key, preview),
        )
        row = connection.execute(
            "SELECT * FROM mock_posts WHERE slot_id = ?", (slot["id"],)
        ).fetchone()
        return dict(row)
