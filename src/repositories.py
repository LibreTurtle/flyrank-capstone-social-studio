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
