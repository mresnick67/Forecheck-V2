# Forecheck v2 Backend

FastAPI backend for self-hosted Forecheck v2.

## Scope

- NHL player/game ingestion and rolling analytics
- Streamer scoring
- Rule-based scans
- League scoring profiles
- Weekly schedule summaries
- Optional Yahoo ownership sync (opt-in)

## Explicitly removed

- Feed/posts/comments/polls
- Notification APIs
- Social interactions

## Run locally (backend only)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Setup endpoints

- `GET /setup/status`
- `POST /setup/bootstrap`

## Auth defaults

- `APP_MODE=single_owner`
- `ENABLE_REGISTRATION=false`

## Yahoo defaults

- `YAHOO_ENABLED=false`

If disabled, Yahoo routes return `503` with an enablement hint.

## Worker

The sync worker entrypoint is:

```bash
python -m app.worker
```

## Preferred local run

Use the root Compose stack from repo root:

```bash
docker compose up -d --build
```

## Useful admin ops

- `POST /admin/sync/pipeline`
- `POST /admin/sync/game-logs/full`
- `POST /scans/refresh-counts`
