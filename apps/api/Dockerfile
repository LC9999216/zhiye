# syntax=docker/dockerfile:1
# 知辨 Zhibian API — multi-stage Python build.
#
# Stage 1 (builder): build the project and all dependencies into wheels.
# Stage 2 (runtime): minimal slim image that installs the local wheels
#                    (no network needed at runtime) and runs uvicorn.

# ---------------- Stage 1: builder ----------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build context is apps/api; copy the package sources first.
COPY pyproject.toml ./
COPY app ./app

# Build wheels for the project and every pinned dependency.
RUN pip wheel --wheel-dir /wheels .

# ---------------- Stage 2: runtime ----------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the wheels built in Stage 1 (offline).
COPY --from=builder /wheels /wheels
RUN pip install /wheels/* && rm -rf /wheels

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
