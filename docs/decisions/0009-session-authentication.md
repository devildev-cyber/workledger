# 0009. Server-side sessions with a cookie and a CSRF header

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The README calls for secure, server-managed sessions with HTTP-only cookies. Sign-out must really end a session, and deactivating a user must cut off access immediately, which signed stateless tokens cannot do without extra machinery.

## Decision

- A sign-in creates a row in `user_sessions`. The browser receives a random token in an `HttpOnly`, `SameSite=Lax` cookie, marked `Secure` in production. The database stores only a SHA-256 hash of the token.
- Each session also has a CSRF token. Every request that is not `GET`, `HEAD`, or `OPTIONS` must send it in the `X-CSRF-Token` header. The sign-in and session-lookup responses return it.
- A session ends after 7 days, or after 12 hours without activity, whichever comes first. Both limits are configurable.
- Sign-in answers an unknown email and a wrong password identically, and spends the same time on both.
- Signing out deletes the session row. A deactivated user's sessions stop working on their next request.

## Consequences

- Every request that needs a signed-in user reads one session row from the database.
- Sessions can be ended individually, for example after a password reset.
- The browser app keeps the CSRF token in memory and sends it with each change.
- Expired rows are deleted when their token is next presented; a periodic cleanup of abandoned sessions is still needed before production.
- Limiting repeated failed sign-in attempts is not included here and is part of production readiness (Phase 10).
