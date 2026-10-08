import repositories
from publishers import PublishResult


class MockPublisher:
    def __init__(self, name: str, display_name: str):
        self.name = name
        self.display_name = display_name

    def publish(self, *, text: str, idempotency_key: str) -> PublishResult:
        preview = f"Would publish to {self.display_name}:\n\n{text}"
        record = repositories.record_mock_post(
            adapter=self.name,
            idempotency_key=idempotency_key,
            preview=preview,
        )
        return PublishResult(
            remote_reference=f"mock:{record['id']}", preview=record["preview"]
        )
