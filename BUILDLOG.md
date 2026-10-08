# Build log

## How I used ChatGPT and Codex

I made the architecture decisions with help from ChatGPT so I could learn how to make them myself. That included the entity design, choosing FastAPI and SQLite, planning the migration approach, and deciding where the publisher interface belongs.

Code is written by me with the guided help of ChatGPT. I manually tested the work in case the AI was wrong. Codex wrote and updated the feature tests and project documentation as the work progressed. I ran the tests and reviewed the API behavior, then fixed errors found during implementation and verification.

## Phase 1 — Design (2026-10-08)

I defined the project scope, platform constraint profiles, publisher interface, SQLite entities, API surface, and non-goals in `DESIGN.md`. The design uses SQL migration files for schema changes and keeps the application modules directly in `src/`. This phase defined the API but did not yet have endpoints to exercise.

## Phase 2 — Ingestion and generation (2026-10-08)

I built Markdown and URL ingestion, SQLite storage, generation from the stored post, three platform constraint profiles, and validation that reports named rule violations. Feature tests cover ingestion, generation, and validation. I manually tested the APIs implemented in this phase through a third-party API client application to check their requests and responses.

## Phase 3 — Review workflow (2026-10-08)

I added draft, approved, rejected, and published variant states; validated editing; approval and rejection actions; and timezone-aware future scheduling. SQLite schema changes are in a versioned migration. Tests cover review decisions, edit validation, and schedule guards. I manually tested the APIs implemented so far, including the new review and scheduling endpoints, through a third-party API client application.

## Phase 4 — Publisher adapters and idempotent publishing (2026-10-09)

I added the `SocialPublisher` interface, Telegram as the real adapter, and Mock X and Mock LinkedIn adapters. A slot is claimed and a publish attempt is stored before a publisher is called. Repeated calls reuse the successful result. Telegram does not accept an idempotency key, so an ambiguous send is recorded as unknown and held for inspection rather than automatically retried. I manually tested the APIs implemented so far through a third-party API client application. I also checked that a Telegram Bot API send reached my test channel; the application's complete scheduled Telegram flow still needs its own end-to-end check.

## Phase 5 — Worker, history, and final review (2026-10-09)

I added a polling worker backed by SQLite slots, recovery for interrupted mock sends, a publish history endpoint, a safe demo seed command, and README setup/API documentation. The final audit found that the configured LinkedIn profile was not included in generation; I added LinkedIn generation and updated the tests. I also added an operator action for resolving an uncertain Telegram attempt after checking the target. I manually tested the APIs implemented so far through a third-party API client application and the interactive API docs.

The full feature suite currently reports `Ran 28 tests ... OK`. I also checked Python compilation, the API route smoke flow, and that all API request YAML files parse.

## Bugs, warnings, and test failures

### 2026-10-09 — Phase 3: Database context manager warnings

The editor warned that annotating the `@contextmanager` function with `Iterator[sqlite3.Connection]` was deprecated. I changed the return annotation to `Generator[sqlite3.Connection, None, None]`.

The editor then warned that `Generator` should come from `collections.abc` instead of `typing`. I imported `Generator` from `collections.abc`.

### 2026-10-09 — Phase 3: Naive datetime test warning

The editor flagged a `datetime` constructor without `tzinfo` in `test_schedule_requires_timezone_and_future_time`. I made the value timezone-aware at construction, then removed the timezone explicitly with `.replace(tzinfo=None)` because that test needs to verify rejection of a naive timestamp.

### 2026-10-09 — Phase 4: Invalid test fixture for an unapproved slot

The first publishing test setup tried to create an unapproved slot through the normal scheduling repository. The repository correctly refused it, so the test failed before reaching the publish-time guard. I changed the test fixture to insert that invalid state directly into the temporary test database, allowing the test to verify that publishing still refuses it.

### 2026-10-09 — Phase 5: Missing LinkedIn generation

The audit found that `mock_linkedin` had a profile and adapter but `generate_variants` returned only Telegram and mock X. I added a LinkedIn draft to generation, updated the generation test to expect all three platforms, and updated the API request checks.

### 2026-10-09 — Phase 5: Telegram retry test expectation

An initial recovery test expected the worker to automatically retry a Telegram attempt after it had been resolved as undelivered. Failed slots are intentionally excluded from automatic worker polling so a permanent publisher rejection cannot cause repeated sends every five seconds. I changed the test to perform the retry through the explicit publish action after resolving the attempt.

### 2026-10-09 — Phase 5: Broad worker exception warning

The editor flagged `except Exception` in `process_due_slots` as a blind exception catch. I replaced it with explicit `LookupError`, `RuntimeError`, `PublishFailure`, and `sqlite3.Error` handling, while continuing to count `ValueError` conditions as skipped slots. The worker logs expected slot failures and continues with the batch.

### 2026-10-09 — API smoke-test environment limitation

An HTTPX ASGI smoke attempt timed out while invoking synchronous FastAPI handlers through the environment's AnyIO worker thread. I used a direct route-level smoke run plus the service/repository feature tests instead. The smoke run created three variants, published one mock slot, read a successful history entry, and confirmed the repeated publish returned `idempotent: true`.

## Dockerization — 2026-10-09

I dockerized the whole application at the end of the project. I learned multi-stage image builds, build-time test gates, non-root containers, and health checks from a YouTube tutorial, then adapted them to this project. The builder installs the listed dependencies; the test stage runs the feature suite when source, tests, or requirements change; and the runtime stage runs as the dedicated `appuser` account. The image checks `/health` every 30 seconds. Docker Compose starts the API and worker as separate services sharing the persistent SQLite volume. Documentation is excluded from the build context, so documentation-only changes do not trigger the test stage. I tested Docker Compose successfully.
