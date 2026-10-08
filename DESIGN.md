# Social Media Studio — Design

## Problem and scope

Turn one stored blog post into reviewed, platform-specific drafts, then publish approved drafts at scheduled times. Generation reads only the stored source post. The application uses FastAPI, SQLite, SQL migration files, and a separate polling worker. The real publishing target is Telegram; X and LinkedIn are mock targets that save previews locally.

## Platform profiles

Length includes spaces and hashtags. Tone checks use a small phrase/word list as a practical guardrail.

| Platform | Maximum length | Tone rule | Maximum hashtags |
| --- | ---: | --- | ---: |
| Telegram | 4,096 | Reject sales-push phrases such as “buy now”, “guaranteed”, and “act now” | 5 |
| Mock X | 280 | Reject the same sales-push phrases | 2 |
| Mock LinkedIn | 3,000 | Reject sales-push phrases; require “learn”, “insight”, or “experience” | 5 |

Each stored post produces one draft for every configured profile. Validation runs before a draft is created or approved and returns named violations such as `maximum length`, `hashtag count`, or `tone rule`.

## Data model

- **`posts`** stores the source type, optional URL, title, body, and creation time. It is the generation source of truth.
- **`variants`** belongs to a post and stores platform, text, validation result, status, and timestamps. A post can have one variant per platform. Statuses are `draft`, `approved`, `rejected`, and `published`.
- **`slots`** belongs to a variant and stores its timezone-normalized schedule time, idempotency key, state, and timestamps. `(variant_id, scheduled_at)` is unique. Slot states are `pending`, `processing`, `published`, and `failed`.
- **`publish_attempts`** records each adapter call and its attempt number, result, remote reference, preview, error, and timestamps. A partial unique index allows at most one successful attempt per slot.
- **`mock_posts`** stores mock adapter previews. Unique slot and idempotency-key constraints prevent a mock slot from recording twice.

Schema changes live in ordered SQL files under `src/migrations/`. SQLite foreign keys are enabled, and repository updates and slot claims use transactions.

## Publishing and recovery

Services use one interface: `SocialPublisher.publish(*, text, idempotency_key) -> PublishResult`. A result contains `remote_reference` and `preview`. Configuration selects Telegram, Mock X, or Mock LinkedIn; with no override, the adapter follows the variant platform. Adding an adapter should not require changing review or scheduling logic.

The worker polls due `pending` slots every five seconds and records an attempt before calling the adapter. A successful slot is returned from its saved result on a repeated call. On restart, interrupted mock attempts are reconciled from the mock-post record or safely retried if no record exists. Telegram does not accept idempotency keys: an interrupted send with an unknown delivery outcome is held for a person to check and resolve through the API. Failed slots are not automatically retried; a confirmed undelivered slot can be retried manually.

The application runs through Docker Compose: separate API and worker services use the same multi-stage image and share a persistent SQLite volume. The image runs tests in a cached build stage when source, tests, or dependencies change, then runs the application as a non-root user. A container health check polls `/health` every 30 seconds. Documentation files are excluded from the build context.

## API surface

| Method and path | Purpose |
| --- | --- |
| `GET /health`, `GET /profiles` | Health check and platform rule profiles. |
| `POST /posts`, `GET /posts/{post_id}` | Ingest Markdown or a public article URL; read the stored source. |
| `POST /posts/{post_id}/variants`, `GET /posts/{post_id}/variants` | Generate all configured variants from the stored source; list them. |
| `GET /variants/{variant_id}`, `PATCH /variants/{variant_id}` | Read or validate/edit a variant. Editing returns it to draft. |
| `POST /variants/{variant_id}/approve`, `POST /variants/{variant_id}/reject` | Review a variant. Only an approved variant can be scheduled. |
| `POST /variants/{variant_id}/schedule` | Create a future, timezone-aware slot. |
| `POST /slots/{slot_id}/publish` | Publish a due slot immediately through its selected adapter. |
| `POST /slots/{slot_id}/resolve` | Resolve an unknown Telegram attempt after checking whether it arrived. |
| `GET /history` | Read publish attempts and outcomes, newest first. |
| `POST /variants/validate` | Validate text against a profile without storing a variant. |

## Non-goal

This project does not generate media or provide analytics, and it never publishes to real X, LinkedIn, or Instagram accounts.
