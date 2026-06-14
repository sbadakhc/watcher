# --- Stage 1: Build React frontend ---
FROM node:20-alpine AS ui-builder

WORKDIR /ui
COPY ui/package.json ui/package-lock.json ui/.npmrc ./
RUN npm ci --ignore-scripts --prefer-offline

COPY ui/ .
RUN npm run build

# --- Stage 2: Build Python dependencies ---
FROM python:3.12-slim AS py-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY watcher/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 3: Runtime ---
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python dependencies
COPY --from=py-builder /install /usr/local

# Copy backend code
COPY watcher/*.py .

# Copy built frontend
COPY --from=ui-builder /ui/dist static

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:9104/api/health | grep -q ok || exit 1

EXPOSE 9104

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9104", "--log-level", "info"]
