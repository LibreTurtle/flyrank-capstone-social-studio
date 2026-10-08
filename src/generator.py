import re


def _first_sentences(body: str, limit: int) -> str:
    plain_text = re.sub(r"[`*_>#]", "", body)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    if len(plain_text) <= limit:
        return plain_text
    excerpt = plain_text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{excerpt}…"


def generate_variants(body: str) -> dict[str, str]:
    telegram_text = _first_sentences(body, 850)
    x_text = _first_sentences(body, 205)
    return {
        "telegram": telegram_text,
        "mock_x": f"{x_text} #Ideas",
    }
