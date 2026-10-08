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
