# One image runs three jobs: the API (default), the Chroma vector server, and
# the one-off data setup. Same code, same pinned dependencies (uv.lock).
# Base images are pinned by digest so a rebuild gets exactly the same bytes.

FROM ghcr.io/astral-sh/uv:0.12.7@sha256:95f2aa1fe59274951cfe9b0cbc7972e879ff1004bc8945d130a32eb0dbd85945 AS uv

# Stage 1: build the virtualenv. Build tools stay here and never reach the final image.
FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first: this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
# --no-editable copies the package into the venv, so /app/src is not needed later.
RUN uv sync --frozen --no-dev --no-editable

# Stage 2: the runtime image.
FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64
# A fixed non-root user. The two folders are created here so named volumes
# mounted on them start out owned by this user and are writable.
RUN useradd --system --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && install -d -o app -g app /app/data /home/app/.cache
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
USER 10001
EXPOSE 8000
# Ready means the API answers. `serve` has already checked the graph server at startup.
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# 0.0.0.0 is correct inside a container: Compose decides who can reach it from outside.
CMD ["attack-graph", "serve", "--host", "0.0.0.0", "--port", "8000"]
