# ── Stage 1: Build Frontend ──────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python Runtime ──────────────────────────────────────────
FROM python:3.12-slim

# system deps for psycopg2 + build
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY nexus/ ./nexus/

# Frontend build from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8080"]
