# 0025. Production readiness: hosting, hardening, backups, retention, and logging

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Until now WorkLedger ran on a laptop with SQLite. Running it for a real firm means deciding where it lives, what it refuses to do when it is misconfigured, how it survives a mistake or a lost disk, how long it keeps what, and what its logs may say. These decisions are written down together because they depend on each other: a backup is only as good as the retention rules around it, and a log is only safe if the hardening is also in place.

## Decision

**Hosting**

- **One provider-neutral machine** running Docker Compose: PostgreSQL 16, the API, and a Caddy web server that serves the built app, proxies `/api`, and obtains and renews HTTPS certificates by itself (`deploy/`). Nothing in it depends on one cloud, so the choice of provider is the firm's, and the same files run on a laptop for a trial.
- Only the web server publishes ports. The database and API are reachable only on the internal network.
- **File storage stays on a volume** (`uploads`). It is part of every backup. An S3-compatible `FileStore` is deferred until one machine is no longer enough; the upload code already addresses files only by their id, so the change is contained.
- **PostgreSQL is the production database; SQLite is for development and tests.** The whole backend suite passes on PostgreSQL 16 (589 passed; 22 tests skipped because they are about SQLite files), and so do the migrations, backup and restore, and the volume measurements. CI runs a subset of the suite on PostgreSQL for every pull request and the whole suite every week.
- The PostgreSQL client tools in the API image are pinned to the **same major version as the database image**. A dump made by a newer client cannot be read by an older one, and a mismatch was found and fixed while rehearsing the restore (see below).

**A production server refuses to start unsafely**

With `WORKLEDGER_ENVIRONMENT=production` the settings are rejected unless: the frontend URL is `https://`, the database is not SQLite, email goes through SMTP, and an SMTP host is set. A misconfiguration is a failed deploy, not a silent weakness. API documentation pages (`/docs`, `/redoc`, `/openapi.json`) are switched off.

**Brute-force protection**

- Failed sign-ins are counted per account (5 in 15 minutes) and per network address (30 in 15 minutes). A locked account refuses even the right password with `429` and `Retry-After`; attempts made while locked do not extend the lock. A correct password clears the account's count.
- Password-reset requests are counted per account (5 per hour) and per address (20 per hour). Past the limit the answer is the same `202` but no email is sent, so the endpoint still reveals nothing about which addresses have accounts.
- Counts are stored as **HMAC-SHA256 of the email and of the address, keyed by the secret key**, never as the raw values. A leaked table does not list who tried to sign in from where, and rotating the key resets the counts.
- The network address comes from the proxy's `X-Forwarded-For` (the last entry only) when `trust_forwarded_for` is on, which the compose file sets because Caddy is in front. It is off by default: otherwise anyone could choose their own address.
- **Accepted trade-off:** a lock can be used to annoy a known user by failing on purpose. We accept it because it is short (15 minutes), it is not a flag on the account (it expires by itself), the person can still reset the password by email, and the alternative (no limit) lets passwords be guessed. A per-address limit is far above one household or office, so it does not lock people out together.

**HTTP safety and errors**

- Every response carries `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin` and a restrictive `Permissions-Policy`. `/api` responses also get a locked-down content security policy and `Cache-Control: no-store` unless a route sets its own. Production adds HSTS. Caddy adds the same set, plus a policy for the app itself.
- An unexpected error becomes a plain `500` with a request id, never a stack trace.
- Uploads were reviewed and already fit this model: type decided from the file's own bytes, an allowlist of JPEG, PNG, WebP and PDF (no SVG), files stored under generated ids, size enforced while streaming, served with `nosniff`, `no-store` and, for non-images, as downloads. **Deferred:** virus scanning and removal of photo metadata (location) before a file is shown to others.

**Logging**

- Production logs are one JSON object per line on standard output, for the platform to collect.
- A request line is `METHOD route-template status duration id`. It never contains the query string, the real path (which holds identifiers), a body, a header, a cookie, or an email address. The server's own access log is switched off because it prints full URLs.
- An exception is logged as its **type and the file, line and function** of each frame. Not the message (which can contain a value) and not the source line.
- Business actions are in the activity history, not in the log. The log answers "is it running and what failed", the history answers "who did what".

**Monitoring**

- `/api/health` says the process is up. `/api/health/ready` also runs a database query and answers `503 Not ready` without details. The container health check and the uptime monitor use the second.
- What to watch is in [the operations guide](../operations.md).

**Backups and recovery**

- `python -m app.ops backup` writes one folder per backup holding the database, the uploads, and a manifest with checksums and the schema revision. SQLite uses its online backup; PostgreSQL uses `pg_dump`. The folder is private to its owner.
- **Restore verifies before it changes anything:** checksums match, the schema revision is one this code knows, the database kind is the same, and a database that already holds data is only overwritten with `--replace`. A PostgreSQL restore runs in one transaction, so a failed restore leaves the database as it was. Uploads are restored through a staging folder, with every archive entry checked.
- **The restore was rehearsed on the real stack, not only in tests.** Seeded data was backed up, deliberately destroyed, restored, and the application started again with the rows and a test file back and a stray file gone. The rehearsal found three faults that the unit tests had missed: `pg_restore` does not read `PGDATABASE`; the container's client was newer than the server; and a mounted uploads folder cannot be replaced, only emptied. All three are fixed and covered by tests.
- Recommended schedule and retention of backups: daily, keep 14 (`prune`). Copy the folder off the machine; a backup on the same disk is not a backup.

**Retention**

| What | Rule | Status |
| --- | --- | --- |
| Expired or idle sessions | Deleted | Enforced by `purge` |
| Password reset links | Deleted a day after they expire or are used | Enforced |
| Invitations | Deleted 90 days after they finish (accepted, expired, revoked) | Enforced |
| Sign-in and reset counts | Deleted after a day | Enforced |
| Notifications | Deleted after 365 days | Enforced |
| Activity history | **Never deleted** | The accountability record |
| Requests, work orders, estimates, attachments | **Kept** until a firm sets its own rule | Not enforced; see below |
| Departed residents and members | Access ends at once; the record of their past requests stays, because the repair history belongs to the property | Behaviour as built |

- `purge` never touches business records or the activity history. Schedule it daily.
- **Business-record retention is a proposal, not a feature.** A reasonable default for a firm to adopt is to keep repair records for the life of the property plus the legal period of its country (commonly 6 to 10 years), and to keep photos as long as their work order. Because the law differs and the firm is the data controller, the product keeps everything and does not delete automatically. Deleting a person's personal data on request is a manual operator task for now; a supported erase-or-anonymise action is future work and is listed under deferred items.

**Deferred**

Provider-specific infrastructure as code; an S3 `FileStore`; virus scanning and photo-metadata removal; pagination of the unpaginated lists (measured fine at the target size, see the production review); per-property time zones; two-factor sign-in; supported anonymisation of a person; external monitoring and alerting setup (the health endpoints are ready for it); a real staging environment on a public domain.

## Consequences

- A firm can deploy with one command and a filled-in `.env`, and recover with two commands.
- The deployment has been exercised end to end on one machine over HTTPS with a locally issued certificate. It has **not** been run on a public host with a real domain and a real certificate authority; that is the first pilot task.
- Locking an account is a deliberate nuisance risk traded for protection from guessing.
- Keeping business records indefinitely is safe for accountability but means storage grows. The measured size at the target scale is small.
