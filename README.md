# Social Media Studio

Social Media Studio stores a blog post, generates platform-specific drafts, lets a person review them, and publishes approved variants through adapters. SQLite holds posts, variants, scheduled slots, mock posts, and every publish attempt.

## Requirements

- Docker Engine with the Docker Compose plugin
- A Telegram bot and a channel or chat where the bot is allowed to post

## Setup and run

```bash
cp -n .env.example .env
```

Edit `.env` as needed. Leave `SOCIAL_PUBLISHER` blank to use the variant's platform, or set it to `telegram`, `mock_x`, or `mock_linkedin`. For Telegram, set the bot token and chat ID. Keep `.env` private.

Start the application from the project root:

```bash
docker compose up --build
```

Compose builds the image and starts both the API and worker. The containers share a persistent SQLite volume. The API is available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`. Stop the services with `Ctrl+C`; use `docker compose down` to remove the containers while keeping the database volume.

Seed one sample campaign (run once; it schedules a mock X post two minutes ahead):

```bash
docker compose run --rm api python -m seed
```

The worker checks SQLite for due slots every five seconds and starts automatically with Compose.

## Create and publish a campaign

1. Create a post with `POST /posts`, providing either `markdown` or a public `url`.
2. Generate its Telegram, mock X, and mock LinkedIn variants with `POST /posts/{post_id}/variants`.
3. Review each result. Approve it with `POST /variants/{variant_id}/approve` or edit/reject it.
4. Schedule an approved variant with `POST /variants/{variant_id}/schedule`. The schedule time must include a timezone and be in the future.
5. The worker publishes it when due. `GET /history` shows attempt result, adapter, preview, and remote reference. `POST /slots/{slot_id}/publish` is also available for a due slot.

With `SOCIAL_PUBLISHER` blank (recommended) or set to `telegram`, approve and schedule the Telegram variant to check the live flow. The worker should publish it around its scheduled time, and `/history` should show the Telegram message reference.

## API reference

All request and response bodies use JSON. Path values such as `{post_id}` are integer IDs returned by earlier requests.

| Method and path                        | What it does                                                                                                                                                                                  |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health`                          | Returns the API health status.                                                                                                                                                                |
| `GET /profiles`                        | Lists platform rules for length, hashtags, blocked phrases, and required tone words.                                                                                                          |
| `POST /posts`                          | Stores pasted Markdown or fetches and stores a public HTTP(S) article URL. Provide exactly one of `markdown` or `url`.                                                                        |
| `GET /posts/{post_id}`                 | Returns a stored source post.                                                                                                                                                                 |
| `POST /posts/{post_id}/variants`       | Generates and stores Telegram, mock X, and mock LinkedIn drafts from the stored post.                                                                                                         |
| `GET /posts/{post_id}/variants`        | Lists variants generated for a post.                                                                                                                                                          |
| `GET /variants/{variant_id}`           | Returns one variant and its review status.                                                                                                                                                    |
| `PATCH /variants/{variant_id}`         | Updates variant text after constraint validation. An edited variant returns to `draft`.                                                                                                       |
| `POST /variants/{variant_id}/approve`  | Approves a valid draft for scheduling.                                                                                                                                                        |
| `POST /variants/{variant_id}/reject`   | Rejects a variant.                                                                                                                                                                            |
| `POST /variants/{variant_id}/schedule` | Schedules an approved variant for a future, timezone-aware time. Returns the new slot.                                                                                                        |
| `POST /slots/{slot_id}/publish`        | Publishes a due slot now. Repeated calls return the saved result without publishing again.                                                                                                    |
| `GET /history?limit=100`               | Lists publish attempts, newest first. `limit` can be from 1 to 500.                                                                                                                           |
| `POST /slots/{slot_id}/resolve`        | Resolves an uncertain delivery after a person checks the target. Send `{"delivered": true, "remote_reference": "chat-id:message-id"}` if it arrived, or `{"delivered": false}` if it did not. |
| `POST /variants/validate`              | Checks text against a platform profile without storing it. Provide `platform` and `text`.                                                                                                     |

Scheduling requires an approved variant. Validation or review conflicts return a 4xx response with a detail explaining the rejection; publishing errors return 409 or 502 depending on whether delivery is uncertain or rejected.

## Interactive API docs

With the API running, open [http://localhost:8000/docs](http://localhost:8000/docs) to use FastAPI's Swagger UI. Expand an endpoint, choose **Try it out**, fill in any path values and JSON request body, then select **Execute** to send the request and inspect its status code and response. For example, create a post first, then use its returned ID in the path for generating variants. Approve a variant before scheduling it; schedule times must be in the future and include a timezone.

## Tests

The Docker build includes a test stage that runs the feature suite before producing the runtime image. It runs when application code, tests, or `requirements.txt` change. Documentation is excluded from the build context, so documentation-only changes do not rerun the tests. A failing test prevents the runtime image from building and Compose from starting the application.

## Architecture

```mermaid
flowchart TD
    Author[Markdown or article URL] --> API[FastAPI]
    API --> Ingest[Ingestion and variant generation]
    Ingest --> Review[Review and scheduling]
    Compose[Docker Compose] --> API
    Compose --> Worker[Polling worker]
    Review --> DB[(Shared SQLite volume: posts, variants, slots, attempts)]
    Worker --> DB
    Worker --> Publisher[SocialPublisher interface]
    API --> Publisher
    Publisher --> Telegram[Telegram adapter]
    Publisher --> MockX[Mock X adapter]
    Publisher --> MockLinkedIn[Mock LinkedIn adapter]
    MockX --> DB
    MockLinkedIn --> DB
    Telegram --> History[Publish attempts and remote reference]
    MockX --> History
    MockLinkedIn --> History
    History --> Endpoint[GET /history]
    DB --> Endpoint
```

The worker uses durable SQLite slots and records every attempt. Mock publishes are reconciled after a crash using their unique local post record.

> [!NOTE]
> Telegram does not support idempotency keys. If a worker stops during a send and cannot confirm whether Telegram accepted it, the attempt becomes `unknown` and is held for review instead of being sent again automatically. Check the Telegram target, then resolve the attempt with `POST /slots/{slot_id}/resolve`: send `{"delivered": true, "remote_reference": "chat-id:message-id"}` if it arrived, or `{"delivered": false}` if it did not. A confirmed undelivered slot becomes failed and can be retried manually.
