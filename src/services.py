import hashlib
from datetime import UTC, datetime

import repositories
from content import extract_article, title_from_markdown
from generator import generate_variants
from profiles import validate_variant


def ingest_markdown(markdown: str) -> dict:
    return repositories.create_post("markdown", title_from_markdown(markdown), markdown)


def ingest_url(url: str) -> dict:
    import httpx

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "SocialMediaStudio/1.0"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise ValueError(f"Could not fetch article URL: {error}") from error
    try:
        title, body = extract_article(response.text)
    except ValueError as error:
        raise ValueError(str(error)) from error
    return repositories.create_post("url", title, body, url)


def generate_post_variants(post_id: int) -> list[dict]:
    post = repositories.get_post(post_id)
    if post is None:
        raise LookupError("Post not found")

    generated = generate_variants(post["body"])
    variants = []
    for platform, text in generated.items():
        problems = validate_variant(platform, text)
        if problems:
            raise ValueError("; ".join(problems))
        variants.append(repositories.create_variant(post_id, platform, text))
    return variants


def edit_variant(variant_id: int, text: str) -> dict:
    variant = repositories.get_variant(variant_id)
    if variant is None:
        raise LookupError("Variant not found")
    if not text.strip():
        raise ValueError("text cannot be blank")
    problems = validate_variant(variant["platform"], text)
    if problems:
        raise ValueError("; ".join(problems))
    updated = repositories.update_variant_text(variant_id, text)
    if updated is None:
        raise LookupError("Variant not found")
    return updated


def approve_variant(variant_id: int) -> dict:
    variant = repositories.get_variant(variant_id)
    if variant is None:
        raise LookupError("Variant not found")
    problems = validate_variant(variant["platform"], variant["text"])
    if problems:
        raise ValueError("; ".join(problems))
    updated = repositories.set_variant_status(variant_id, "approved")
    if updated is None:
        raise LookupError("Variant not found")
    return updated


def reject_variant(variant_id: int) -> dict:
    rejected = repositories.set_variant_status(variant_id, "rejected")
    if rejected is None:
        raise LookupError("Variant not found")
    return rejected


def schedule_variant(variant_id: int, scheduled_at: datetime) -> dict:
    if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
        raise ValueError("scheduled_at must include a timezone")
    normalized_time = scheduled_at.astimezone(UTC)
    if normalized_time <= datetime.now(UTC):
        raise ValueError("scheduled_at must be in the future")

    timestamp = normalized_time.isoformat(timespec="microseconds")
    idempotency_key = hashlib.sha256(f"{variant_id}:{timestamp}".encode()).hexdigest()
    return repositories.create_slot(variant_id, timestamp, idempotency_key)
