import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


def error_message(error: Any) -> str:
    if isinstance(error, str):
        return error
    if isinstance(error, dict) and isinstance(error.get("errors"), list):
        return "; ".join(str(item) for item in error["errors"])
    if isinstance(error, list) and all(isinstance(item, str) for item in error):
        return "; ".join(error)
    return "Request validation failed" if isinstance(error, list) else "Request failed"


def response_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def success_envelope(
    data: Any, message: str = "Request completed successfully"
) -> dict:
    return {
        "success": True,
        "message": message,
        "timestamp": response_timestamp(),
        "data": data,
    }


def error_envelope(message: str, error: dict) -> dict:
    return {
        "success": False,
        "message": message,
        "timestamp": response_timestamp(),
        "error": error,
    }


class ResponseEnvelopeMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.documentation_paths = {
            "/docs",
            "/openapi.json",
            "/redoc",
            "/docs/oauth2-redirect",
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        messages: list[Message] = []

        async def collect(message: Message) -> None:
            messages.append(message)

        await self.app(scope, receive, collect)

        start = next(
            (
                message
                for message in messages
                if message["type"] == "http.response.start"
            ),
            None,
        )
        if start is None:
            return

        status_code = start["status"]
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        headers = [
            (name, value)
            for name, value in start.get("headers", [])
            if name.lower() not in {b"content-length", b"x-request-id"}
        ]
        headers.append((b"x-request-id", request_id.encode("ascii")))
        content_type = next(
            (
                value.decode("latin-1").split(";", 1)[0].lower()
                for name, value in headers
                if name.lower() == b"content-type"
            ),
            "",
        )

        if (
            scope.get("path") not in self.documentation_paths
            and content_type == "application/json"
        ):
            try:
                payload = json.loads(body or b"null")
            except (ValueError, UnicodeDecodeError):
                payload = {"detail": body.decode("utf-8", errors="replace")}

            is_envelope = (
                isinstance(payload, dict)
                and isinstance(payload.get("success"), bool)
                and {"message", "timestamp"}.issubset(payload)
                and ("data" in payload or "error" in payload)
            )
            if not is_envelope:
                if 200 <= status_code < 400:
                    message = (
                        "Resource created successfully"
                        if status_code == 201
                        else "Request completed successfully"
                    )
                    envelope = success_envelope(payload, message)
                else:
                    error = (
                        payload.get("detail", payload)
                        if isinstance(payload, dict)
                        else payload
                    )
                    message = error_message(error)
                    error_type = (
                        "validation_error" if status_code == 422 else "request_error"
                    )
                    envelope = error_envelope(
                        message, {"type": error_type, "details": error}
                    )
                body = json.dumps(
                    envelope, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != b"content-type"
                ]
                headers.append((b"content-type", b"application/json"))

        headers.append((b"content-length", str(len(body)).encode("ascii")))
        start["headers"] = headers
        await send(start)
        await send({"type": "http.response.body", "body": body, "more_body": False})
        logger.info(
            "API request request_id=%s method=%s path=%s status=%s",
            request_id,
            scope.get("method", ""),
            scope.get("path", ""),
            status_code,
        )
