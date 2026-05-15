# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY homelab_ai ./homelab_ai
RUN pip install --no-cache-dir --upgrade pip build && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" aiohttp pyyaml pydantic httpx python-multipart && \
    rm -rf /wheels

COPY homelab_ai ./homelab_ai
COPY config.example.yaml ./config.example.yaml

# Run as non-root.
RUN useradd -m -u 1000 homelab && \
    mkdir -p /data && chown -R homelab:homelab /data /app
USER homelab

EXPOSE 9105
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:9105/api/health', timeout=3)"

ENTRYPOINT ["python", "-m", "homelab_ai"]
CMD ["run", "--config", "/data/config.yaml"]
