import json
import os
from datetime import UTC, datetime, timedelta

from database import initialize_database
from environment import load_environment_file
from services import (
    approve_variant,
    generate_post_variants,
    ingest_markdown,
    schedule_variant,
)


def create_demo_campaign() -> dict:
    publisher = os.getenv("SOCIAL_PUBLISHER", "").strip()
    if publisher not in {"", "mock_x", "mock_linkedin"}:
        raise ValueError(
            "Demo seed requires a mock publisher; it will not send to Telegram."
        )

    post = ingest_markdown(
        "# A small team update\n\n"
        "Our team shared weekly notes and learned how clear updates help everyone "
        "follow decisions and plan the next steps."
    )
    variants = generate_post_variants(post["id"])
    variant = next(item for item in variants if item["platform"] == "mock_x")
    approved = approve_variant(variant["id"])
    slot = schedule_variant(approved["id"], datetime.now(UTC) + timedelta(minutes=2))
    return {
        "post_id": post["id"],
        "variant_id": approved["id"],
        "slot_id": slot["id"],
        "scheduled_at": slot["scheduled_at"],
    }


def main() -> None:
    load_environment_file()
    initialize_database()
    print(json.dumps(create_demo_campaign(), indent=2))


if __name__ == "__main__":
    main()
