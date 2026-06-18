# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React SPA ----------
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build            # -> /web/dist

# ---------- Stage 2: Python API + static SPA ----------
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# application code
COPY config.py translit.py server.py ./
COPY api/ ./api/
COPY extract/ ./extract/
COPY tools/ ./tools/
# prebuilt database (receipts.db with PDF blobs) + editable CSVs
COPY data/ ./data/
# built frontend from stage 1
COPY --from=web /web/dist ./web/dist

EXPOSE 8000
CMD ["uvicorn", "server:server", "--host", "0.0.0.0", "--port", "8000"]
