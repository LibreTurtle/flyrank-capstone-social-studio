import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

import repositories
from api_responses import ResponseEnvelopeMiddleware, error_envelope, error_message
from database import initialize_database
from environment import load_environment_file
from profiles import PROFILES, validate_variant
from publishers import PublishFailure
from services import (
    approve_variant,
    edit_variant,
    generate_post_variants,
    ingest_markdown,
    ingest_url,
    publish_slot,
    reject_variant,
    resolve_unknown_publication,
    schedule_variant,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_environment_file()
    initialize_database()
    yield


app = FastAPI(title="Social Media Studio", lifespan=lifespan)
app.add_middleware(ResponseEnvelopeMiddleware)
logger = logging.getLogger(__name__)


def _exception_headers(
    request: Request, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    headers = dict(extra or {})
    headers["X-Request-ID"] = getattr(request.state, "request_id", "unavailable")
    return headers


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    request: Request, error: StarletteHTTPException
) -> JSONResponse:
    error_type = "validation_error" if error.status_code == 422 else "request_error"
    return JSONResponse(
        error_envelope(
            error_message(error.detail),
            {"type": error_type, "details": error.detail},
        ),
        status_code=error.status_code,
        headers=_exception_headers(request, error.headers),
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    details = jsonable_encoder(error.errors())
    return JSONResponse(
        error_envelope(
            error_message(details), {"type": "validation_error", "details": details}
        ),
        status_code=422,
        headers=_exception_headers(request),
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(
    request: Request, error: Exception
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unavailable")
    logger.error(
        "Unhandled API error request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    return JSONResponse(
        error_envelope(
            "Internal server error",
            {
                "type": "internal_server_error",
                "details": "An unexpected error occurred",
            },
        ),
        status_code=500,
        headers=_exception_headers(request),
    )


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    success_schema = {
        "type": "object",
        "required": ["success", "message", "timestamp", "data"],
        "properties": {
            "success": {"type": "boolean", "enum": [True]},
            "message": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "data": {},
        },
    }
    error_schema = {
        "type": "object",
        "required": ["success", "message", "timestamp", "error"],
        "properties": {
            "success": {"type": "boolean", "enum": [False]},
            "message": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"},
            "error": {
                "type": "object",
                "required": ["type", "details"],
                "properties": {
                    "type": {"type": "string"},
                    "details": {},
                },
            },
        },
    }
    for path in schema["paths"].values():
        for operation in path.values():
            for status, response in operation.get("responses", {}).items():
                code = int(status) if status.isdigit() else 0
                response_data_schema = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                if code == 0 or code < 400:
                    target = deepcopy(success_schema)
                    if response_data_schema is not None:
                        target["properties"]["data"] = response_data_schema
                else:
                    target = error_schema
                if code == 204:
                    continue
                response["content"] = {"application/json": {"schema": target}}
                response.setdefault("headers", {})["X-Request-ID"] = {
                    "description": "Unique identifier for this request",
                    "schema": {"type": "string", "format": "uuid"},
                }
            operation.setdefault("responses", {}).setdefault(
                "500",
                {
                    "description": "Internal server error",
                    "content": {"application/json": {"schema": error_schema}},
                    "headers": {
                        "X-Request-ID": {"schema": {"type": "string", "format": "uuid"}}
                    },
                },
            )
            operation["responses"].setdefault(
                "default",
                {
                    "description": "Other API error",
                    "content": {"application/json": {"schema": error_schema}},
                    "headers": {
                        "X-Request-ID": {
                            "description": "Unique identifier for this request",
                            "schema": {"type": "string", "format": "uuid"},
                        }
                    },
                },
            )
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


class PostIn(BaseModel):
    markdown: str | None = Field(default=None, min_length=1)
    url: str | None = None

    @model_validator(mode="after")
    def require_one_source(self):
        if bool(self.markdown) == bool(self.url):
            raise ValueError("Provide exactly one of markdown or url")
        return self


class VariantCheck(BaseModel):
    platform: str
    text: str = Field(min_length=1)


class VariantEdit(BaseModel):
    text: str = Field(min_length=1)


class ScheduleIn(BaseModel):
    scheduled_at: datetime


class ResolvePublishIn(BaseModel):
    delivered: bool
    remote_reference: str | None = None


def _public_http_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        return parsed.hostname.casefold() not in {"localhost", "localhost.localdomain"}
    return address.is_global


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/profiles")
def profiles() -> list[dict]:
    return [
        {
            "platform": name,
            "max_length": profile.max_length,
            "max_hashtags": profile.max_hashtags,
            "blocked_phrases": list(profile.blocked_phrases),
            "required_tone_words": list(profile.required_tone_words),
        }
        for name, profile in PROFILES.items()
    ]


@app.post("/posts", status_code=201)
def create_post(payload: PostIn) -> dict:
    if payload.markdown is not None:
        if not payload.markdown.strip():
            raise HTTPException(status_code=422, detail="Markdown body cannot be blank")
        return ingest_markdown(payload.markdown)
    if payload.url is None or not _public_http_url(payload.url):
        raise HTTPException(
            status_code=422, detail="URL must be a public HTTP or HTTPS address"
        )
    try:
        return ingest_url(payload.url)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/posts/{post_id}")
def read_post(post_id: int) -> dict:
    post = repositories.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.post("/posts/{post_id}/variants", status_code=201)
def create_variants(post_id: int) -> list[dict]:
    try:
        return generate_post_variants(post_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/posts/{post_id}/variants")
def read_variants(post_id: int) -> list[dict]:
    if repositories.get_post(post_id) is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return repositories.list_variants(post_id)


@app.get("/variants/{variant_id}")
def read_variant(variant_id: int) -> dict:
    variant = repositories.get_variant(variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return variant


@app.patch("/variants/{variant_id}")
def update_variant(variant_id: int, payload: VariantEdit) -> dict:
    try:
        return edit_variant(variant_id, payload.text)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/variants/{variant_id}/approve")
def approve(variant_id: int) -> dict:
    try:
        return approve_variant(variant_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/variants/{variant_id}/reject")
def reject(variant_id: int) -> dict:
    try:
        return reject_variant(variant_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/variants/{variant_id}/schedule", status_code=201)
def schedule(variant_id: int, payload: ScheduleIn) -> dict:
    try:
        return schedule_variant(variant_id, payload.scheduled_at)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/slots/{slot_id}/publish")
def publish(slot_id: int) -> dict:
    try:
        return publish_slot(slot_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PublishFailure as error:
        status_code = 409 if error.uncertain else 502
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/history")
def publish_history(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return repositories.list_publish_history(limit)


@app.post("/slots/{slot_id}/resolve")
def resolve_publish(slot_id: int, payload: ResolvePublishIn) -> dict:
    try:
        return resolve_unknown_publication(
            slot_id, payload.delivered, payload.remote_reference
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/variants/validate")
def check_variant(payload: VariantCheck) -> dict:
    result = validate_variant(payload.platform, payload.text)
    result["platform"] = payload.platform
    if not result["valid"]:
        raise HTTPException(status_code=422, detail=result)
    return result
