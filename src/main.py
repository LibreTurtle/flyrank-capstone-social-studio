from contextlib import asynccontextmanager
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

import repositories
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
def profiles() -> dict:
    return {
        name: {
            "max_length": profile.max_length,
            "max_hashtags": profile.max_hashtags,
            "blocked_phrases": list(profile.blocked_phrases),
            "required_tone_words": list(profile.required_tone_words),
        }
        for name, profile in PROFILES.items()
    }


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
    problems = validate_variant(payload.platform, payload.text)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    return {"valid": True, "platform": payload.platform}
