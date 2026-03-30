# whatsapp_automation

FastAPI webhook receiver for WhatsApp Cloud API that:

- verifies the Meta webhook subscription on `GET /`
- persists every webhook payload and normalized message rows in Postgres
- downloads inbound image media to local disk and stores file metadata in Postgres
- exposes `/messages` for a browser view and `/api/messages` for JSON access

## Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Start PostgreSQL locally:

   ```bash
   docker compose up -d db
   ```

   If port `5432` is already in use, run:

   ```bash
   POSTGRES_PORT=55432 docker compose up -d db
   ```

   Then update `DATABASE_URL` to use the same port.

3. Install dependencies:

   ```bash
   uv sync --group dev
   ```

4. Run database migrations:

   ```bash
   uv run alembic upgrade head
   ```

5. Start the webhook server:

   ```bash
   uv run uvicorn whatsapp_automation.main:app --app-dir src --host 0.0.0.0 --port 3000
   ```

## Development

- Run tests:

  ```bash
  uv run pytest
  ```

- Local Postgres connection string:

  ```text
  postgresql+psycopg://postgres:postgres@localhost:5432/whatsapp_automation
  ```

## Stored data

- `webhook_events`: every raw webhook POST body
- `messages`: normalized `messages` and `message_echoes` rows
- `media_assets`: image download metadata and local storage path

## Viewer endpoints

- `GET /messages`: HTML page listing stored messages and inline images
- `GET /api/messages`: JSON list of stored messages and media URLs
- `GET /media/<path>`: serves downloaded image files from local storage
- `POST /api/media/retry`: retries pending or failed media downloads after token/network issues are fixed
