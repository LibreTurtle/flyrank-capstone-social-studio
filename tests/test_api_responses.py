import json
import unittest
import uuid

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from api_responses import ResponseEnvelopeMiddleware, error_envelope
from main import VariantCheck, app, check_variant, profiles


class ApiResponseTests(unittest.IsolatedAsyncioTestCase):
    def test_profiles_route_returns_a_list_of_named_profiles(self):
        result = profiles()
        self.assertIsInstance(result, list)
        self.assertEqual(
            {item["platform"] for item in result},
            {"telegram", "mock_x", "mock_linkedin"},
        )

    def test_invalid_variant_route_raises_with_structured_validation_detail(self):
        with self.assertRaises(HTTPException) as raised:
            check_variant(VariantCheck(platform="mock_x", text="Buy now " + "x" * 300))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIsInstance(raised.exception.detail, dict)
        self.assertFalse(raised.exception.detail["valid"])
        self.assertTrue(raised.exception.detail["errors"])

    async def request(self, path: str, status: int, payload: object):
        async def app(scope, receive, send):
            response = JSONResponse(payload, status_code=status)
            await response(scope, receive, send)

        middleware = ResponseEnvelopeMiddleware(app)
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await middleware(
            {"type": "http", "path": path, "method": "GET", "headers": []},
            receive,
            send,
        )
        start = next(
            message for message in sent if message["type"] == "http.response.start"
        )
        body = next(
            message["body"]
            for message in sent
            if message["type"] == "http.response.body"
        )
        return start, json.loads(body)

    async def test_success_response_has_envelope_and_request_id(self):
        start, body = await self.request(
            "/profiles", 200, [{"platform": "telegram", "max_length": 4096}]
        )
        headers = dict(start["headers"])
        self.assertTrue(body["success"])
        self.assertEqual(body["data"][0]["platform"], "telegram")
        self.assertEqual(body["data"][0]["max_length"], 4096)
        self.assertTrue(body["message"])
        self.assertTrue(body["timestamp"].endswith("+00:00"))
        self.assertEqual(
            str(uuid.UUID(headers[b"x-request-id"].decode())),
            headers[b"x-request-id"].decode(),
        )

    async def test_list_response_stays_a_list_inside_data(self):
        _, body = await self.request(
            "/history", 200, [{"attempt_id": 1}, {"attempt_id": 2}]
        )
        self.assertTrue(body["success"])
        self.assertEqual(body["data"], [{"attempt_id": 1}, {"attempt_id": 2}])

    async def test_existing_error_envelope_is_not_wrapped_again(self):
        expected = error_envelope(
            "Request validation failed",
            {"type": "validation_error", "details": ["invalid text"]},
        )
        _, body = await self.request("/variants/validate", 422, expected)
        self.assertEqual(body, expected)

    async def test_error_preserves_status_and_detail(self):
        start, body = await self.request("/posts", 422, {"detail": "Invalid source"})
        self.assertEqual(start["status"], 422)
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "Invalid source")
        self.assertEqual(body["error"]["type"], "validation_error")
        self.assertEqual(body["error"]["details"], "Invalid source")

    async def test_validation_error_keeps_multiple_details_in_error_object(self):
        _, body = await self.request(
            "/variants/validate", 422, {"detail": ["maximum length", "tone rule"]}
        )
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["type"], "validation_error")
        self.assertEqual(body["error"]["details"], ["maximum length", "tone rule"])

    async def test_request_error_wraps_string_detail_in_error_object(self):
        _, body = await self.request("/variants/1", 409, {"detail": "Conflict"})
        self.assertFalse(body["success"])
        self.assertEqual(
            body["error"], {"type": "request_error", "details": "Conflict"}
        )

    async def test_openapi_keeps_document_shape_and_request_id_header(self):
        start, body = await self.request("/openapi.json", 200, {"openapi": "3.1.0"})
        self.assertEqual(body, {"openapi": "3.1.0"})
        self.assertIn(b"x-request-id", dict(start["headers"]))
        schema = app.openapi()
        profiles_data = schema["paths"]["/profiles"]["get"]["responses"]["200"]
        data_schema = profiles_data["content"]["application/json"]["schema"][
            "properties"
        ]["data"]
        self.assertEqual(data_schema["type"], "array")
        error_schema = schema["paths"]["/variants/{variant_id}"]["get"]["responses"][
            "default"
        ]
        error_properties = error_schema["content"]["application/json"]["schema"][
            "properties"
        ]["error"]["properties"]
        self.assertIn("type", error_properties)
        self.assertIn("details", error_properties)
