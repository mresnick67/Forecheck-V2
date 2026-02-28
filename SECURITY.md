# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities privately to the maintainer.
Do not open public issues for unpatched security bugs.

## Recommended local hardening

- Set strong values for `SECRET_KEY` and `ADMIN_API_KEY`.
- Keep `ENABLE_REGISTRATION=false` in single-owner mode.
- Keep the deployment private unless intentionally exposed.
- Disable Yahoo integration unless needed (`YAHOO_ENABLED=false`).

## Supported versions

Security fixes are provided for the latest v2 mainline only.
