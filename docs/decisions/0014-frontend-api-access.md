# 0014. How the frontend talks to the API

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The backend uses a server-side session cookie and a CSRF header ([0009](0009-session-authentication.md)). The frontend needs one consistent way to call the API, keep track of who is signed in, and move between organizations ([0010](0010-organization-scoped-access.md)).

## Decision

- **One origin:** in development the Vite server forwards `/api` to the backend. In production the same arrangement is expected, with one host serving both. This keeps the session cookie same-site and needs no CORS settings.
- **One client:** every request goes through `api()` in `src/api/client.ts`. It sends JSON, adds the `X-CSRF-Token` header on changes, and turns error replies into an `ApiError` with a readable message.
- **No stored credentials:** the session cookie is HTTP-only and never touched by scripts. The CSRF token is kept in memory only. After a reload the app asks `/api/auth/me`, which returns the token again.
- **Ended sessions:** a `401` while signed in returns the person to the sign-in form. A `401` from the sign-in form itself is shown as a wrong password.
- **Organization in the address:** pages for an organization live under `/organizations/:organizationId`, mirroring the API. The switcher changes that address. The last organization used is remembered in the browser only to choose where `/` opens.
- **Unknown or foreign organizations:** both show the same "page not found", as the API does.
- **Routing:** `react-router` is the one added runtime dependency. Later tasks need real addresses for invitation and password reset links.
- **Tests:** frontend tests replace `fetch` with a small fake server (`src/test/fetch-mock.ts`). No mocking library is added.

## Consequences

- The sign-in page returns people to the page they first asked for, but only to paths inside the app.
- What the interface hides is for convenience only. The API still decides what each role may do.
- The remembered organization is not cleared on sign-out. It is only an address hint, and it is ignored when the person is not a member.
- Roles shown in the header area come from the session reply, so a role change by an administrator shows up after the next reload.
