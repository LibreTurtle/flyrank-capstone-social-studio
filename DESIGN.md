# Social Media Studio — Design

## Problem and scope

Turn one stored blog post into reviewed, platform-specific social posts, then publish approved versions on a durable schedule. The stored post is the only input to generation. Initial profiles cover Telegram, X-style (mock), and LinkedIn (mock); generation starts with Telegram and X-style in Phase 2. Telegram is the planned real publisher, using a channel the owner controls.

## Constraint profiles

Length counts all characters, including spaces and hashtags. A tone rule is checked in code against a small, explicit vocabulary; it is a guardrail, not a claim of understanding prose.

| Platform | Maximum length | Tone rule | Hashtags |
| --- | ---: | --- | ---: |
| Telegram | 4,096 | Clear and conversational; reject sales-push phrases such as “buy now” and “guaranteed” | 0–5 |
| X-style (mock) | 280 | Concise and conversational; reject sales-push phrases | 0–2 |
| LinkedIn (mock) | 3,000 | Professional; require one of “learn”, “insight”, or “experience”; reject sales-push phrases | 0–5 |

Validation runs before a variant can enter review and returns named rule violations (for example, `maximum length` or `hashtag count`).

## Data model

- `posts`: id, source type (`markdown` or `url`), original URL when present, title, stored body, created time.
- `variants`: id, post id, platform, text, status (`draft`, `approved`, `rejected`, `published`), validation result, created/updated times.
- `slots`: id, variant id, scheduled time, unique idempotency key derived from variant and slot, state (`pending`, `processing`, `published`, `failed`), lease/update times. Unique `(variant_id, scheduled_at)` prevents duplicate slots.
- `publish_attempts`: id, slot id, attempt number, result, remote reference, error, started/finished times. Every attempt is retained; a successful result is unique per slot.
- `mock_posts`: id, slot id, platform, preview text, created time. Unique slot id ensures a mock retry records one post.

SQLite foreign keys are enabled. Status changes and claiming due slots happen in transactions. A stale `processing` lease can be reclaimed after restart. External delivery uses the slot idempotency key where supported; Telegram does not guarantee key-based deduplication, so a timeout after remote acceptance remains an explicit limitation that will be documented and handled conservatively.

## Publisher interface

`SocialPublisher.publish(*, text: str, idempotency_key: str) -> PublishResult`, where `PublishResult` contains `remote_id` and `preview`. Adapters are selected from configuration (`telegram`, `mock_x`, `mock_linkedin`). Services depend on this protocol, not concrete platform classes.

## API surface

- `POST /posts` — ingest pasted Markdown or fetch a URL and store it.
- `POST /posts/{post_id}/variants` — generate configured variants from stored content.
- `GET /posts/{post_id}` and `GET /posts/{post_id}/variants` — inspect source and variants.
- `PATCH /variants/{variant_id}` — edit text after validation; editing returns it to `draft`.
- `POST /variants/{variant_id}/approve` and `/reject` — review decision.
- `POST /variants/{variant_id}/schedule` — create a future slot; reject non-approved variants with 4xx.
- `GET /history` — inspect attempts and publish outcomes.

## Architecture and non-goal

FastAPI routes call small application services; services use SQLite repositories and the `SocialPublisher` protocol. A separate worker claims due slots, records attempts, and updates history. Mock adapters write previews to SQLite. Telegram configuration comes from environment variables; secrets are never stored in the database.

**Non-goal:** media generation, analytics, and publishing to real X, LinkedIn, or Instagram accounts.
