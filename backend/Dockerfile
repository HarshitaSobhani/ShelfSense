FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models
WORKDIR /app

# CPU-only torch keeps the image small. Build with --build-arg EMBEDDINGS=0 for a keyword-only image.
ARG EMBEDDINGS=1
COPY pyproject.toml ./
COPY app ./app
RUN if [ "$EMBEDDINGS" = "1" ]; then \
      pip install --extra-index-url https://download.pytorch.org/whl/cpu ".[embeddings]"; \
    else pip install .; fi

COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && useradd -m app && mkdir -p /models && chown -R app /models /app
USER app

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
