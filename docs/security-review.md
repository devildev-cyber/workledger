# Security review (Phase 10)

- **Date:** 2026-11-13
- **Method:** a manual review of the code and the deployed stack by the author of the change, against the threats below. No external penetration test and no automated scanner subagent was run. **This is a self-review, and a pilot with real data should have an independent one.**
- **Scope:** the API, the web app, the container deployment, backups, and logs. Not covered: the host operating system, the SMTP provider, the DNS provider, and the people operating the machine.

Status: **Resolved** (fixed and tested), **Accepted** (known, with the reason), **Deferred** (to be done, with the trigger).

## Findings

| # | Area | Finding | Status |
| --- | --- | --- | --- |
| 1 | Sign-in | Passwords could be guessed without limit | **Resolved.** Per-account and per-address limits with lock-out, tested including that a locked account refuses the right password and that attempts while locked do not extend the lock |
| 2 | Sign-in | Lock-out can be abused to annoy a known user | **Accepted.** 15 minutes, expires by itself, reset by email still works. See decision 0025 |
| 3 | Password reset | Endpoint could be used to send many emails, or to find which addresses have accounts | **Resolved.** Requests are limited per account and address; past the limit the answer is the same `202` and nothing is sent |
| 4 | Privacy | Throttle records would reveal who tried to sign in from where | **Resolved.** Only keyed hashes are stored, and they are deleted after a day |
| 5 | Address spoofing | A client could choose its own address through `X-Forwarded-For` and escape the per-address limit | **Resolved.** The header is ignored unless `trust_forwarded_for` is on, and then only the last entry (the one the trusted proxy added) is used. The compose file sets it because Caddy is in front |
| 6 | Configuration | A production server could be started over plain HTTP, on SQLite, or without real email | **Resolved.** Startup is refused with the setting named |
| 7 | Transport | HTTPS | **Resolved** in the deployment: Caddy terminates HTTPS with automatic certificates, redirects HTTP, and sends HSTS. Session cookies are `Secure`, `HttpOnly`, `SameSite=Lax` in production. **Not yet verified on a public domain** |
| 8 | Session | Cookie theft and cross-site requests | **Already in place and re-checked:** `HttpOnly`; a per-session CSRF token required on every state-changing request; sessions have a maximum age (168 h) and an idle timeout (12 h) and are deleted by housekeeping |
| 9 | Browser | Clickjacking, content sniffing, referrer leakage | **Resolved.** `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy`, `Permissions-Policy`; the app has a strict content security policy with no inline scripts |
| 10 | API responses | Cached private data | **Resolved.** `Cache-Control: no-store` on `/api`; uploaded files are `private, no-store` |
| 11 | Errors | Stack traces or messages in responses | **Resolved.** A plain `500` with a request id. Health checks answer `503 Not ready` without details |
| 12 | Logs | Personal data or secrets in logs | **Resolved.** No query strings, real paths, bodies, headers, cookies or emails. Exceptions are logged as type and location only. Tests raise an exception whose message holds an email address and check that it never reaches the log |
| 13 | Information | API documentation exposed in production | **Resolved.** `/docs`, `/redoc` and `/openapi.json` return 404 in production |
| 14 | Input | Request validation | **Re-checked.** Request bodies and parameters go through Pydantic models with length and range limits and identifiers are UUIDs. The only raw SQL is a few fixed strings in the migrations, the readiness check and the backup tool, none with user input |
| 15 | Authorization | Cross-organization and direct-ID access | **Re-checked.** Every route is covered by tests for the allowed role, the wrong role (`403`) and out-of-scope records (`404`), including the new reports and exports |
| 16 | Uploads | Hostile files | **Already in place and re-checked:** type decided from the bytes, allowlist (JPEG, PNG, WebP, PDF; no SVG or HTML), generated storage names, size limited while streaming, `nosniff`, non-images forced to download |
| 17 | Uploads | Malware in an accepted PDF; location data in photos | **Deferred.** Add scanning and metadata removal before files are shared with people outside the firm, or when a firm asks |
| 18 | Exports | Spreadsheet formula injection; leaking personal data | **Resolved.** Dangerous leading characters are neutralised; residents' contact details, descriptions and notes are excluded; every export is recorded in the activity history |
| 19 | Backups | Backup contents readable by others; a tampered or wrong backup being restored | **Resolved.** Folders are private to the owner; restore checks checksums, schema revision and database kind before changing anything. **Operator duty:** protect off-site copies as strictly as the database |
| 20 | Restore tar archive | Path traversal or links in an uploads archive | **Resolved.** Only plain files and folders under `uploads/` are accepted, extraction uses the `data` filter, tested with `..` and link entries |
| 21 | Container | Running as root | **Resolved.** The API runs as an unprivileged user; the database and API publish no ports |
| 22 | Secrets | Secrets in the repository or images | **Resolved.** `.env` is ignored by git and both Docker contexts; the image contains no secrets; the example file has empty values |
| 23 | Dependencies | Known vulnerable packages | **Deferred.** Enable automated dependency updates and a periodic audit (`pip-audit`, `npm audit`) on the repository host |
| 24 | Authentication | No second factor; passwords are 12 or more characters with no breach check | **Accepted for the pilot, Deferred.** Revisit with two-factor sign-in before a large rollout |
| 25 | Accountability | Deleting a person's data on request | **Deferred.** A manual operator task today; a supported anonymise action is future work |
| 26 | Disk | Uploads and the database are not encrypted at rest by the application | **Accepted.** Use an encrypted disk or volume at the host; this is the host's responsibility |

## Faults found by exercising the system rather than reading it

These came out of running the real stack, not from the review, and are recorded because they would have been invisible in unit tests:

- The API image lacked the PostgreSQL driver, so a deployment would not have migrated. Fixed; the driver is now a declared dependency.
- A restore into PostgreSQL did nothing useful (`pg_restore` ignores the database environment variable). Fixed and made atomic.
- The container's PostgreSQL client was newer than the server and its dump could not be read back. Fixed by pinning the client's major version to the server's.
- A mounted uploads folder could not be replaced during restore. Fixed.

## What this review does not claim

- That the deployment is safe on the public internet: it was run locally with a locally issued certificate.
- That there are no vulnerabilities: a self-review finds what its author thinks of.

## Before real personal data is loaded

1. Deploy on the real domain and confirm HTTPS, HSTS and the headers with an external checker.
2. Schedule backups, copy them off the machine, and perform one restore on a spare machine.
3. Set up uptime monitoring on `/api/health/ready`.
4. Turn on dependency alerts and run the audits (finding 23).
5. Ask someone independent to review this document and the deployment.
