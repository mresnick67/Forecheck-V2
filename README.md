# Forecheck v2

Self-hosted fantasy hockey analytics platform for one local owner user.

## What v2 includes

- Analytics-first product: discover streamers, explore players, evaluate scans, manage leagues.
- FastAPI backend + React PWA frontend.
- All-in-one Docker Compose setup.
- Single-owner bootstrap flow (`/setup/bootstrap`) with public registration disabled by default.
- Local-first defaults with no required third-party auth provider.
- NHL headshots and team logos rendered from official public asset URLs.

## What v2 removes

- No social feed.
- No posts, comments, polls, likes, or notification endpoints.
- No iOS/Fly deployment assumptions.

## Quick start

```bash
docker compose up -d --build
```

Open:

- App: http://localhost:6767
- API docs: http://localhost:6767/api/docs

Install as PWA (optional):

- Chrome/Edge desktop: open `http://localhost:6767`, then use browser install action.
- iOS Safari: Share -> Add to Home Screen.

## First run

1. Open `http://localhost:6767`.
2. Complete owner bootstrap form.
3. Sign in with the owner credentials.
4. Keep the stack running for initial data bootstrap; first full-season GameCenter sync can take several minutes.

## Services

- `web`: React PWA behind nginx (`6767:80`)
- `api`: FastAPI
- `worker`: periodic sync worker
- `db`: PostgreSQL

## Core API surface

- `POST /setup/bootstrap`
- `GET /setup/status`
- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`
- `GET /players`, `GET /players/{id}`
- `GET /players/{id}/signals`
- `GET /players/explore` (window-aware advanced filters)
- `GET/POST/PUT/DELETE /scans`
- `POST /scans/refresh-counts`
- `GET/POST/PUT/DELETE /leagues`
- `GET /schedule/week`
- `POST /admin/sync/pipeline`
- `GET /admin/status`
- `POST /admin/sync/game-logs/full`

## Environment defaults

See [backend/.env.example](/Users/mylesresnick/xCode Projects/Forecheck Fantasy/forecheck-v2/backend/.env.example).

## Local-first integration posture

- Core analytics stack is designed to run fully local on `http://localhost:6767`.
- Yahoo OAuth is disabled by default (`YAHOO_ENABLED=false`) and is not required for normal use.
- Planned Yahoo integration direction is browser-extension based rather than required local OAuth setup.

## Security notes

- Set `SECRET_KEY` before exposing beyond localhost.
- In v2 single-owner mode, any authenticated user is treated as admin.
- Keep `ENABLE_REGISTRATION=false` for single-owner mode.

## License

AGPLv3 (see [LICENSE](/Users/mylesresnick/xCode Projects/Forecheck Fantasy/forecheck-v2/LICENSE)).

## Legacy

v1 (Fly + iOS) is maintained as a separate legacy archive repository/workflow.
