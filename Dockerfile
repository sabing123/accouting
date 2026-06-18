# syntax=docker/dockerfile:1

# Build stage
FROM python:3.13-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/ .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r production.txt \
    && pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r base.txt


# Production stage
FROM python:3.13-slim-bookworm AS production

# Create non-root user
RUN groupadd -r accounting && useradd -r -g accounting accounting

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libffi8 \
    libssl3 \
    libxml2 \
    libxslt1.1 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    mime-support \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*.whl && rm -rf /wheels

# Copy application code
COPY --chown=accounting:accounting . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Switch to non-root user
USER accounting

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120", "config.wsgi:application"]


# Development stage
FROM production AS development

USER root

# Install development dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/development.txt .
RUN pip install --no-cache-dir -r development.txt

USER accounting

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
