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
