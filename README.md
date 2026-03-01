# Forecheck v2

Self-hosted fantasy hockey analytics platform focused on one local owner user.

Forecheck v2 is the clean break from v1 (Fly + iOS): Docker-first, analytics-only, no social layer, and no required third-party auth to use core features.

## Table of contents

- [What v2 is](#what-v2-is)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [First-run setup](#first-run-setup)
- [Core features](#core-features)
- [Streamer score model](#streamer-score-model)
- [Worker and sync pipeline](#worker-and-sync-pipeline)
- [Migration checklist (v1 -> v2)](#migration-checklist-v1---v2)
- [Configuration](#configuration)
- [Operations guide](#operations-guide)
- [Troubleshooting](#troubleshooting)
- [Security and licensing](#security-and-licensing)

## What v2 is

### Included

- FastAPI backend + React/Vite PWA frontend.
- All-in-one Docker Compose stack:
  - `web` (nginx + PWA)
  - `api` (FastAPI)
  - `worker` (periodic NHL sync process)
  - `db` (PostgreSQL)
- Single-owner bootstrap flow via `/setup/bootstrap`.
- Analytics workflows:
  - Discover streamers and scan sections
  - Explore with advanced rolling-stat filters
  - Player detail analytics
  - Rule-based scans (preset + custom)
  - League scoring profiles (categories/points)
  - Editable streamer-score model with full recalculation progress
  - Scan alerts feed (“What’s New”)

### Explicitly removed from v1

- Social/feed/notifications stack:
  - no posts/comments/polls
  - no feed generation
  - no in-app social notifications
- Fly/iOS deployment assumptions.

## Architecture

```text
Browser / PWA (http://localhost:6767)
  -> nginx (web container)
     -> /api/* proxied to FastAPI (api container)
        -> PostgreSQL (db container)

Background sync:
  worker container -> same FastAPI service layer -> PostgreSQL
```

### Service map

| Service | Purpose | Default |
|---|---|---|
| `web` | PWA UI + reverse proxy to API | `localhost:6767` |
| `api` | REST API, auth, scans, analytics/admin endpoints | internal `:8000` |
| `worker` | Periodic ingestion/sync loop (`python -m app.worker`) | internal |
| `db` | Postgres data store | persisted via `postgres_data` volume |

## Quick start

### Prerequisites

- Docker Desktop with Compose v2.
- Port `6767` available.

### Start the full stack

```bash
git clone https://github.com/mresnick67/Forecheck-V2.git
cd Forecheck-V2
docker compose up -d --build
```

Open:

- App: `http://localhost:6767`
- API docs (Swagger): `http://localhost:6767/api/docs`

## First-run setup

1. Open `http://localhost:6767`.
2. Complete owner bootstrap form.
3. Log in.
4. Optional but recommended: in **Settings**, run a sync pipeline/backfill to fully hydrate season data.

Setup endpoints:

- `GET /setup/status`
- `POST /setup/bootstrap`

Bootstrap is intentionally one-time. After the first user exists, bootstrap returns `409`.

## Core features

## Discover

- Shows top streamers by current score.
- Renders featured and favorited scans as horizontal player carousels.
- Includes “What’s New” scan alert feed (recently-entered matches for alert-enabled scans).
- Includes weekly schedule summary (light/heavy nights).

Key data sources:

- `/players/top-streamers`
- `/players/trending`
- `/schedule/week`
- `/scans` + `/scans/{id}/evaluate`
- `/scans/alerts/feed`

## Explore

Window-aware player search/ranking with filters:

- window: `L5`, `L10`, `L20`, `Season`
- position/team/search
- min score, min games played
- min weekly games and min light-night games
- sort by score/stats/schedule dimensions

Key endpoint:

- `GET /players/explore`

## Player detail

Player page includes:

- Team-themed hero with headshot/logo and score ring.
- **Streamer Score Explainer** card with exact backend contribution breakdown.
  - compact top contributors
  - expandable full component table (caps, weights, normalized values, and final contribution)
- Stat comparison table across windows.
- Recent games and upcoming schedule (opponent color chips).
- Preset signal tags (e.g., trending + matching scans).

Key endpoints:

- `GET /players/{id}`
- `GET /players/{id}/score-breakdown`
- `GET /players/{id}/signals`
- `GET /players/{id}/schedule`

## Scans

Supports both preset and custom scans:

- Presets are auto-seeded and cannot be deleted.
- Custom scans support multi-rule logic across rolling windows.
- Actions:
  - preview unsaved scan
  - evaluate and persist matches
  - refresh stale/forced match counts
  - hide preset scans
  - favorite scans (surfaces in Discover)
  - alert toggle per scan (powers What’s New feed)

Key endpoints:

- `GET /scans`
- `POST /scans`
- `PUT /scans/{id}`
- `DELETE /scans/{id}`
- `POST /scans/{id}/evaluate`
- `POST /scans/preview`
- `POST /scans/refresh-counts`
- `GET /scans/alerts/feed`
- `GET /scans/alerts/summary`

## Leagues

Save Yahoo-style scoring profiles locally (no Yahoo OAuth required):

- mode: `categories` or `points`
- editable stat weights
- custom stat keys allowed
- one active league at a time

Active league can be blended into streamer score when enabled in Settings.

Key endpoints:

- `GET /leagues`
- `POST /leagues`
- `PUT /leagues/{id}`
- `DELETE /leagues/{id}`

## Settings / Admin

- Account/session actions.
- PWA install prompt.
- Admin sync controls:
  - run full pipeline
  - run full-season game-log backfill
  - refresh scan counts
  - inspect recent sync runs/status
- Streamer score model editor:
  - league influence toggles/weights
  - skater/goalie weights/scales/toggles
  - live skater/goalie weight budget indicators (`All Weights`, `Active Hot Max`, `Active Stable Max`)
  - save + start full recalculation
  - live progress bar and run state

Key endpoints:

- `GET /admin/status`
- `POST /admin/sync/pipeline`
- `POST /admin/sync/game-logs/full`
- `POST /scans/refresh-counts`
- `GET/PUT /admin/streamer-score/config`
- `GET/POST /admin/streamer-score/recalculate`

## Streamer score model

Streamer score is a normalized 0-100 form score calculated per rolling window.

High-level inputs:

- Skaters: points, shots, PPP, TOI, plus-minus, hits/blocks, trend state, optional availability bonus.
- Goalies: SV%, GAA, wins, starts, trend state, optional availability/sample handling.

It supports optional **league influence blending**:

- Pulls the active league profile’s scoring weights.
- Computes a league-fit score.
- Blends base score and league-fit score using `league_influence.weight`.
- Uses `minimum_games` to down-weight league influence for tiny samples.

Model config persists in `app_settings` (`streamer_score_config`) and is editable in UI.

### Weight totals and calibration

- Weights do **not** need to sum to exactly `100`.
- In practice, keeping active max budgets near ~`100` avoids over-clipping many players at score cap.
- Settings shows three budget hints per skater/goalie model:
  - `All Weights`: raw sum of all configured weights
  - `Active Hot Max`: effective max base budget when hot trend path is active
  - `Active Stable Max`: effective max base budget for stable trend path

## Worker and sync pipeline

This is the most important operational section for data freshness.

### API vs Worker responsibilities

- `api` container:
  - serves requests
  - `RUN_SYNC_LOOP=false` by default in Compose
- `worker` container:
  - runs `python -m app.worker`
  - `RUN_SYNC_LOOP=true`
  - executes the periodic sync loop

Both processes share the same DB and service code.

### Periodic worker loop behavior

Worker loop runs every `NHL_SYNC_INTERVAL_MINUTES` (min 5m enforced in code):

1. `sync_players` (rosters/basic player records)
2. schedule sync for yesterday + next 14 days
3. weekly schedule materialization
4. conditional nightly heavy sync (`_maybe_run_nightly_sync`)

Nightly heavy sync (runs at most once after `NHL_NIGHTLY_SYNC_HOUR_UTC`):

1. incremental GameCenter game-log sync
2. rolling stats recomputation
3. scan count refresh
4. Yahoo ownership sync (only if enabled and connected)

### Manual on-demand pipeline (Settings -> Run Sync Pipeline)

`POST /admin/sync/pipeline` executes immediately and returns counts:

1. sync players
2. sync schedule window + weekly table
3. sync game logs (incremental)
4. recompute rolling stats
5. refresh scan counts
6. optional Yahoo ownership sync

Use this whenever you want immediate consistency without waiting for worker timing.

### Full-season game-log backfill

`POST /admin/sync/game-logs/full`:

- Replays full-season GameCenter boxscore ingestion.
- Useful when migrating fresh DBs or when coverage is incomplete.
- Can optionally reset existing rows (`reset_existing=true` query param).
- Followed by rolling-stat + scan-count refresh in endpoint flow.

### State tracking and visibility

Sync observability is built in:

- `sync_runs`: run history (`running/success/failed/skipped`, row counts, errors)
- `sync_state`: last successful timestamps by stage
- `sync_checkpoints`: game-log cursor/checkpoint
- Settings page surfaces these via `/admin/status`

Useful status endpoint:

- `GET /admin/status`

Includes:

- season id
- loop enabled/disabled
- last run times per sync stage
- game-log row count and date range
- running jobs
- recent run history

## Migration checklist (v1 -> v2)

Use this as an operational checklist for migration closure.

### Completed in v2 codebase

- [x] Standalone repo and all-in-one Docker Compose stack.
- [x] Self-hosted PWA on `http://localhost:6767`.
- [x] Single-owner bootstrap (`/setup/status`, `/setup/bootstrap`) and registration-off default.
- [x] Social/feed/notification surfaces removed from product scope.
- [x] Core analytics feature parity: Discover, Explore, Player Detail, Scans, Leagues, Settings/Admin.
- [x] Worker + sync pipeline + full-season backfill controls.
- [x] Streamer score settings editor + full recalculation progress.
- [x] Scan favorites + alert feed (“What’s New”).
- [x] True per-player streamer-score contribution breakdown API/UI.

### Verify/finish (may still be pending outside this repo)

- [ ] Update legacy v1 README with pointer to this v2 repo.
- [ ] Create final v1 tag/release notes (legacy archive marker).
- [ ] Set legacy v1 GitHub repo to archived/read-only.
- [ ] Confirm legacy Fly resources are scaled down/removed if no longer needed.
- [ ] Keep Yahoo local OAuth disabled for local-first flow unless explicitly reintroduced.

### Future roadmap item (planned)

- [ ] Chrome extension approach for Yahoo site overlay, using local Forecheck v2 data as source-of-truth.

## Configuration

Default Compose values are in [`docker-compose.yml`](./docker-compose.yml).

Backend reference envs are in [`backend/.env.example`](./backend/.env.example).

### Key env vars

| Variable | Default | Meaning |
|---|---|---|
| `APP_MODE` | `single_owner` | Deployment mode flag |
| `ENABLE_REGISTRATION` | `false` | Public `/auth/register` gate |
| `PUBLIC_BASE_URL` | `http://localhost:6767` | External app URL |
| `API_CORS_ORIGINS` | `http://localhost:6767` | CORS allow-list |
| `NHL_SYNC_ENABLED` | `true` | Master NHL sync toggle |
| `RUN_SYNC_LOOP` | `false` on API, `true` on worker | Enables periodic loop in process |
| `NHL_SYNC_INTERVAL_MINUTES` | `60` | Worker interval cadence |
| `NHL_GAME_CENTER_DELAY_SECONDS` | `0.25` | Per-game ingestion throttle |
| `YAHOO_ENABLED` | `false` | Optional Yahoo integration gate |

### Overriding config safely

Recommended: create `docker-compose.override.yml` and override only needed environment keys.

Example:

```yaml
services:
  api:
    environment:
      SECRET_KEY: "replace-with-strong-secret"
  worker:
    environment:
      NHL_SYNC_INTERVAL_MINUTES: "30"
```

Then run:

```bash
docker compose up -d --build
```

## Operations guide

### Common commands

Start/update:

```bash
docker compose up -d --build
```

Stop:

```bash
docker compose down
```

Tail logs:

```bash
docker compose logs -f api worker web
```

Check service state:

```bash
docker compose ps
```

### Data persistence

Postgres data is stored in Docker volume `postgres_data`.

Full reset (destructive):

```bash
docker compose down -v
```

Then recreate:

```bash
docker compose up -d --build
```

## Troubleshooting

### Worker is down / no background sync

- Check `docker compose ps worker`.
- Restart worker:

```bash
docker compose up -d worker
```

- Inspect worker logs:

```bash
docker compose logs -f worker
```

### Not enough game logs / incomplete season coverage

- In Settings, run **Full-Season Game Log Backfill**.
- Then verify in Settings Admin summary:
  - game-log row count
  - min/max game-log dates

### Scans look stale or empty

- Use **Refresh Scan Counts** in Settings.
- Re-evaluate a scan in Scans page.

### Setup blocked after initial user

- Bootstrap is intentionally one-time.
- If you need to re-bootstrap, reset DB volume (`docker compose down -v`).

## Security and licensing

- v2 is intentionally local-first, single-owner oriented.
- In current v2 behavior, any authenticated user is treated as admin.
- Keep `ENABLE_REGISTRATION=false` unless you explicitly want open registration.
- Set a strong `SECRET_KEY` before exposing outside local environment.

License: AGPLv3 ([`LICENSE`](./LICENSE)).

Additional repo docs:

- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md)
- [`SECURITY.md`](./SECURITY.md)
- [`THIRD_PARTY_DATA_POLICY.md`](./THIRD_PARTY_DATA_POLICY.md)

---

Legacy v1 (Fly + iOS) is intentionally separate and treated as archived/legacy workflow.
