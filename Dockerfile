FROM python:3.14-slim AS builder

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /build
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM builder AS test

WORKDIR /app
COPY src/ ./src/
COPY tests/ ./tests/
RUN PYTHONPATH=/app/src python -B -m unittest discover -s tests -v

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SOCIAL_STUDIO_DATABASE=/data/social_studio.sqlite3 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN addgroup --system appuser \
    && adduser --system --ingroup appuser --home /app appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=test --chown=appuser:appuser /app/src/ ./src/

VOLUME ["/data"]
EXPOSE 8000
USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
