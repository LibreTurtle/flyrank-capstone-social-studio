# Evidence

## Automated tests

I ran:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Output: `Ran 41 tests in 0.157s` and `OK`.

### API response contract

- `test_success_response_has_envelope_and_request_id` — `ok`; success data is nested under `data`, includes a UTC timestamp, and has a UUID `X-Request-ID` header.
- `test_list_response_stays_a_list_inside_data` — `ok`; list results remain JSON arrays under `data`.
- `test_error_preserves_status_and_detail` — `ok`; a 422 remains 422 and its detail is returned in the dictionary at `error.details` with `success: false`.
- `test_validation_error_keeps_multiple_details_in_error_object` — `ok`; multiple validation messages remain available under `error.details`.
- `test_request_error_wraps_string_detail_in_error_object` — `ok`; operation failures use the same dictionary shape.
- `test_profiles_route_returns_a_list_of_named_profiles` — `ok`; `/profiles` returns an array containing each platform name.
- `test_openapi_keeps_document_shape_and_request_id_header` — `ok`; the OpenAPI document remains directly accessible and includes the request ID header.
- `test_invalid_variant_route_raises_with_structured_validation_detail` — `ok`; the route receives the validator's dictionary result and includes it in its validation error.
- `test_existing_error_envelope_is_not_wrapped_again` — `ok`; global exception responses keep a single envelope when they pass through the middleware.
- `test_http_exception_returns_error_envelope_and_status` — `ok`; HTTP errors preserve status and request ID.
- `test_request_validation_exception_keeps_structured_details` — `ok`; FastAPI request validation errors use the shared envelope and retain structured details.
- `test_unexpected_exception_returns_safe_500_envelope` — `ok`; unexpected errors return a safe 500 response with a request ID.
- `test_global_handler_gets_request_id_from_middleware` — `ok`; an unhandled route exception is converted by FastAPI's global handler and keeps the middleware-generated request ID.

I also inspected the generated `/openapi.json`: documented success and error responses use the matching envelope schema, and each operation documents `X-Request-ID`.

### Ingestion and generation

- `test_markdown_post_is_stored_with_its_heading` — `ok`; stores the Markdown heading as the post title.
- `test_markdown_without_heading_uses_default_title` — `ok`; stores Markdown without a heading using the fallback title.
- `test_article_page_title_and_readable_body_are_extracted` — `ok`; extracts an article title and readable body.
- `test_one_stored_post_creates_each_configured_draft_variant` — `ok`; creates distinct Telegram, mock X, and mock LinkedIn drafts from one stored post.
- `test_missing_post_cannot_generate_variants` — `ok`; returns a not-found error for a missing source post.

### Constraint profiles

- `test_valid_generated_text_passes_profile` — `ok`; accepts valid text.
- `test_text_over_limit_reports_length_rule` — `ok`; reports the maximum-length violation.
- `test_too_many_hashtags_reports_count_rule` — `ok`; reports the hashtag-count violation.
- `test_sales_phrase_reports_tone_rule` — `ok`; reports blocked sales language.
- `test_unknown_platform_is_rejected` — `ok`; reports an unsupported platform.

### Review and scheduling rules

- `test_variant_can_be_read_and_edited_back_to_draft` — `ok`; saves an edit and returns the variant to draft.
- `test_invalid_edit_is_blocked_without_changing_the_variant` — `ok`; rejects invalid text and leaves the stored variant unchanged.
- `test_variant_can_be_approved_and_rejected` — `ok`; accepts both review decisions.
- `test_draft_variant_cannot_be_scheduled` — `ok`; refuses a schedule request for a draft.
- `test_approved_variant_can_be_scheduled_once` — `ok`; creates one pending slot for an approved variant and rejects a duplicate time.
- `test_schedule_requires_timezone_and_future_time` — `ok`; rejects a timezone-free or past schedule time.

### Adapters and idempotent publishing

- `test_configuration_can_swap_to_another_mock_adapter` — `ok`; selects Mock LinkedIn by configuration without changing publishing logic.
- `test_mock_publish_repeats_return_one_saved_post` — `ok`; the repeated call returns the saved result, with one mock post and one successful attempt.
- `test_unapproved_and_future_slots_are_not_published` — `ok`; prevents publication before approval or before the scheduled time.
- `test_telegram_adapter_parses_successful_send` — `ok`; reads the remote message reference from a successful Telegram response.
- `test_telegram_rejection_is_a_known_failure` — `ok`; reports Telegram's rejection as a known failure.
- `test_telegram_network_error_is_uncertain` — `ok`; marks an unconfirmed network outcome as uncertain.

### Durable worker and recovery

- `test_worker_processes_due_slots_and_next_run_does_not_duplicate` — `ok`; the next worker run finds no duplicate work after publication.
- `test_worker_restart_continues_with_the_rest_of_a_due_batch` — `ok`; after one slot is processed and the worker stops, the next run publishes the remaining due slot. The database contains two successful attempts and two mock posts.
- `test_worker_recovers_mock_publish_written_before_worker_stopped` — `ok`; reconciles the mock post as successful after an interrupted attempt.
- `test_worker_retries_mock_publish_interrupted_before_recording` — `ok`; safely retries a mock attempt that stopped before its post was recorded.
- `test_interrupted_telegram_attempt_can_be_resolved_after_target_check` — `ok`; after confirming no message arrived, resolves the unknown attempt and permits a manual retry.

### Publish history

- `test_history_shows_publish_attempt_and_result` — `ok`; history includes the slot, platform, adapter, success state, preview, and remote reference.

## API and Swagger checks

I can inspect and exercise each HTTP route through an API client or the interactive Swagger UI at `http://localhost:8000/docs`.

I also ran an in-process API route smoke check for Markdown ingestion, variant generation, approval, scheduling, worker publication, history, and a repeated publish. Output:

```text
{'generated': 3, 'worker': {'checked': 1, 'published': 1, 'failed': 0, 'skipped': 0}, 'history': 'succeeded', 'repeat_idempotent': True}
```

## Telegram live check

I manually tested the Telegram Bot API with my test channel and confirmed that sending a message works. The automated adapter tests above cover the application's response handling. To verify a complete scheduled send from this application, I approve and schedule the Telegram variant, keep the worker running, then confirm the delivered message and its reference in `GET /history`.

Telegram does not accept an idempotency key. If a send is interrupted and delivery is unclear, the attempt remains `unknown` until I check the channel and resolve it. This avoids an automatic retry that could duplicate a delivered message.
