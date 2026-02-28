# Contributing

Thanks for contributing to Forecheck v2.

## Development setup

1. Start services:
   - `docker compose up -d --build`
2. App URL:
   - `http://localhost:6767`

## Scope guardrails

- Keep v2 analytics-only.
- Do not introduce social feed/comments/polls/notifications.
- Preserve single-owner self-host defaults.

## Pull request expectations

- Describe user impact and API changes.
- Include test notes and manual verification steps.
- Keep documentation updated when behavior changes.

## Security and secrets

- Never commit `.env` values or OAuth credential files.
- Use `backend/.env.example` for required config shape.
