import repositories
from publishers import PublishResult


class MockPublisher:
    name = ""
    display_name = ""

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


class MockXPublisher(MockPublisher):
    name = "mock_x"
    display_name = "Mock X"


class MockLinkedInPublisher(MockPublisher):
    name = "mock_linkedin"
    display_name = "Mock LinkedIn"
