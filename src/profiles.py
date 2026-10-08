import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ConstraintProfile:
    name: str
    max_length: int
    max_hashtags: int
    blocked_phrases: tuple[str, ...]
    required_tone_words: tuple[str, ...] = ()


PROFILES = {
    "telegram": ConstraintProfile(
        "telegram", 4096, 5, ("buy now", "guaranteed", "act now")
    ),
    "mock_x": ConstraintProfile("mock_x", 280, 2, ("buy now", "guaranteed", "act now")),
    "mock_linkedin": ConstraintProfile(
        "mock_linkedin",
        3000,
        5,
        ("buy now", "guaranteed", "act now"),
        ("learn", "insight", "experience"),
    ),
}


def validate_variant(platform: str, text: str) -> list[str]:
    profile = PROFILES.get(platform)
    if profile is None:
        return [f"platform profile: unsupported platform '{platform}'"]

    problems = []
    if len(text) > profile.max_length:
        problems.append(
            f"maximum length: {len(text)} exceeds {profile.max_length} characters"
        )

    hashtags = re.findall(r"(?<!\w)#[\w]+", text)
    if len(hashtags) > profile.max_hashtags:
        problems.append(
            f"hashtag count: {len(hashtags)} exceeds {profile.max_hashtags}"
        )

    lowered = text.casefold()
    if any(phrase in lowered for phrase in profile.blocked_phrases):
        problems.append("tone rule: sales-push language is not allowed")

    if profile.required_tone_words and not any(
        re.search(rf"\b{re.escape(word)}\b", lowered)
        for word in profile.required_tone_words
    ):
        problems.append("tone rule: include 'learn', 'insight', or 'experience'")
    return problems
