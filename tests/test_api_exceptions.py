import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request

from api_responses import ResponseEnvelopeMiddleware
from main import (
    handle_http_exception,
    handle_request_validation_error,
    handle_unexpected_exception,
)


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
            "state": {"request_id": "request-123"},
        }
    )


class ApiExceptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_exception_returns_error_envelope_and_status(self):
        response = await handle_http_exception(
            make_request(), HTTPException(status_code=404, detail="Post not found")
        )
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["X-Request-ID"], "request-123")
        self.assertEqual(
            body["error"],
            {
                "type": "request_error",
                "details": "Post not found",
            },
        )

    async def test_request_validation_exception_keeps_structured_details(self):
        error = RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": ("body", "text"),
                    "msg": "Field required",
                    "input": None,
                }
            ]
        )
        response = await handle_request_validation_error(make_request(), error)
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["error"]["type"], "validation_error")
        self.assertIsInstance(body["error"]["details"], list)

    async def test_unexpected_exception_returns_safe_500_envelope(self):
        error = RuntimeError("internal detail")
        with patch("main.logger.error"):
            response = await handle_unexpected_exception(make_request(), error)
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers["X-Request-ID"], "request-123")
        self.assertEqual(body["error"]["type"], "internal_server_error")
        self.assertEqual(body["error"]["details"], "An unexpected error occurred")

    async def test_global_handler_gets_request_id_from_middleware(self):
        test_app = FastAPI()
        test_app.add_exception_handler(Exception, handle_unexpected_exception)
        test_app.add_middleware(ResponseEnvelopeMiddleware)

        @test_app.get("/explode")
        async def explode():
            raise RuntimeError("internal detail")

        scope = make_request().scope
        scope["path"] = "/explode"
        scope["raw_path"] = b"/explode"
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        with patch("main.logger.error"):
            try:
                await test_app(scope, receive, send)
            except RuntimeError:
                pass

        start = next(item for item in messages if item["type"] == "http.response.start")
        body_message = next(
            item for item in messages if item["type"] == "http.response.body"
        )
        body = json.loads(body_message["body"])
        self.assertEqual(start["status"], 500)
        self.assertIn(b"x-request-id", dict(start["headers"]))
        self.assertEqual(body["error"]["type"], "internal_server_error")
