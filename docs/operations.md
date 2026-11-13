# Operations guide

How to deploy, run, back up, and recover WorkLedger on one machine. The reasoning behind these choices is in [decision 0025](decisions/0025-production-readiness.md).

## What you need

- A Linux machine with Docker and the Compose plugin, 2 GB of memory or more.
- For a real deployment: a domain name whose DNS points at the machine, and ports 80 and 443 open to the internet. Caddy gets and renews the HTTPS certificate on its own. Port 80 must stay open for that.
- An SMTP account for sending email (invitations, password resets, notifications). Production refuses to start without one.

## Deploy

```bash
cd deploy
cp .env.example .env
# Edit .env: the domain, a database password, a secret key, the public https address, SMTP.
docker compose up -d --build
```

What happens: the database starts, a one-shot `migrate` service applies the migrations (**a failed migration stops the deploy** and the old API keeps running), then the API and the web server start.

Check it:

```bash
curl -fsS https://YOUR-DOMAIN/api/health/ready      # {"status":"ready"}
docker compose ps                                    # api should say "healthy"
```

Create the first administrator and organization with the existing bootstrap command (see the README, "Local development"), run inside the API container:

```bash
docker compose exec api python -m app.bootstrap --help
```

To try the product with sample people and properties, `docker compose exec api python -m app.seed` creates the demo organization and prints one shared password, once. **Do not seed a real installation.**

### Trying it on your own computer

Leave `WORKLEDGER_DOMAIN=localhost`. Caddy issues a certificate from its own authority, so the browser warns once. If ports 80 and 443 are busy, set `HTTP_PORT=8080`, `HTTPS_PORT=8443` and use `WORKLEDGER_FRONTEND_URL=https://localhost:8443`. Email goes to your SMTP host, so use a throwaway one (nothing is sent until someone is invited or resets a password).

## Settings

All settings are environment variables with the prefix `WORKLEDGER_`. The complete annotated list is `deploy/.env.example`. The ones that matter:

| Setting | Meaning |
| --- | --- |
| `WORKLEDGER_SECRET_KEY` | At least 32 characters. Signs and hashes security data. **Changing it signs everyone out and resets the sign-in counts.** Keep it out of backups of the code. |
| `WORKLEDGER_FRONTEND_URL` | The address people type, with `https://`. Links in emails use it. |
| `WORKLEDGER_EMAIL_BACKEND`, `WORKLEDGER_SMTP_*` | How email is sent. `starttls` for port 587, `ssl` for 465. |
| `WORKLEDGER_TRUST_FORWARDED_FOR` | `true` only behind a proxy you control (the compose file does). |
| `WORKLEDGER_SIGN_IN_*`, `WORKLEDGER_RESET_*` | Brute-force limits. Defaults: 5 failures per account and 30 per address in 15 minutes; 5 reset requests per account and 20 per address per hour. |
| `WORKLEDGER_SESSION_MAX_AGE_HOURS`, `..._IDLE_TIMEOUT_HOURS` | A sign-in lasts at most 168 hours and ends after 12 hours idle. |
| `WORKLEDGER_MAX_UPLOAD_MEGABYTES` | Per file, default 10. Caddy accepts requests up to 12 MB; raise both together. |

If production is misconfigured the API **exits at start** and says which setting is wrong (`docker compose logs api`).

## Update

```bash
git pull
docker compose up -d --build        # migrate runs first; if it fails nothing else changes
```

Take a backup before updating. Migrations only go forward in production; to undo an update, restore the backup made before it and deploy the previous version.

## Back up

```bash
docker compose run --rm backup
```

This writes `workledger-<UTC time>/` into the `backups` volume with `database.dump`, `uploads.tar.gz` and `manifest.json` (checksums and schema revision). It does not stop the service.

**Schedule it** and keep the newest few. With cron on the host, daily at 02:30:

```cron
30 2 * * * cd /srv/workledger/deploy && docker compose --profile tools run --rm backup >> /var/log/workledger-backup.log 2>&1
45 2 * * * cd /srv/workledger/deploy && docker compose --profile tools run --rm backup python -m app.ops prune --in /backups --keep 14 >> /var/log/workledger-backup.log 2>&1
```

**Copy the backups off the machine** (object storage, another host). The `backups` volume lives on the same disk as the database, so on its own it does not protect against losing the machine. Treat the copies like the data itself: they contain personal information.

## Restore

Practise this before you need it. It has been rehearsed on the real stack: back up, destroy data, restore, start again.

```bash
docker compose stop api web                       # nobody should be writing
docker compose --profile tools run --rm --entrypoint sh restore -c 'ls /backups'   # pick a folder
docker compose --profile tools run --rm restore \
  python -m app.ops restore --from /backups/workledger-20261113T020000Z --replace
docker compose --profile tools run --rm migrate   # only if the backup is older than the code
docker compose start api web
curl -fsS https://YOUR-DOMAIN/api/health/ready
```

- The restore **checks the checksums first** and refuses a backup made by a newer version of WorkLedger. Without `--replace` it refuses to overwrite a database that has data.
- The database part runs in a single transaction: if it fails, the database is unchanged. Uploads are then replaced by the backup's files (files added since are removed).
- Everything after the backup time is lost. People signed in are signed out (their sessions come back from the backup, so a long-lived one may still work).
- To restore onto a new machine: deploy as above with an empty database, copy the backup folder into the `backups` volume, then run the restore.
- A backup restored into a different database kind (SQLite into PostgreSQL) is refused.

## Housekeeping

Delete expired sessions, used or expired reset links, finished invitations, old sign-in counts and old notifications. It never touches requests, work orders, estimates, files or the activity history.

```cron
15 3 * * * cd /srv/workledger/deploy && docker compose --profile tools run --rm backup python -m app.ops purge >> /var/log/workledger-purge.log 2>&1
```

## Monitoring

| What | How | Act when |
| --- | --- | --- |
| Is it up? | An external monitor requesting `https://YOUR-DOMAIN/api/health/ready` every minute | Two failures in a row |
| Is it slow? | The log line for each request ends with its duration | Typical requests above 1 second |
| Errors | `docker compose logs api` shows each unexpected error with its type and location and a request id; the user sees the same id | Any `ERROR` line |
| Backups | The log of the scheduled backup; the newest folder in the volume | No new backup in 26 hours |
| Disk | The `db-data`, `uploads` and `backups` volumes | Above 80 percent |
| Certificate | Caddy renews by itself; the monitor above fails if it does not | Monitor fails with a certificate error |

The log holds **no personal data**: no query strings, identifiers in paths, request bodies, cookies, or email addresses, and exceptions are logged without their messages. It is safe to send to a log service. To find what happened to one request, search for the id shown on the error screen.

## Incidents

**The site is down.** `docker compose ps`, then `docker compose logs --tail 100 api web db`. `Not ready` means the database is unreachable: check the `db` container and the disk. An API that exits at start names the misconfigured setting.

**A person cannot sign in.** After 5 wrong passwords an account is locked for 15 minutes. They can wait, or reset the password by email. Locks expire by themselves; there is nothing to unlock. If a whole office is blocked, the network address limit (30 in 15 minutes) was hit: check `WORKLEDGER_TRUST_FORWARDED_FOR` is `true`, otherwise everyone looks like one address (the proxy's).

**Suspected account compromise.** Reset the person's password (they get an email link), and ask an administrator to remove and re-invite them if needed. The activity history shows what the account did and when.

**Data was changed or deleted by mistake.** Stop writes if needed, find the newest backup before the mistake, and restore as above. A single record cannot be restored on its own; the activity history records what changed, which allows correcting it by hand.

**A leaked secret key.** Generate a new one, put it in `.env`, restart. Everyone is signed out. Rotate the database and SMTP passwords too if they could have leaked.

**A leaked backup.** It contains personal data (names, emails, addresses of residents). Treat it as a data breach under your local law and your agreement with the property owners.

## Tests on PostgreSQL

The test suite runs on SQLite by default. To run it on PostgreSQL:

```bash
docker run -d --name wl-pg -e POSTGRES_PASSWORD=pgtest -e POSTGRES_DB=workledger -p 55432:5432 postgres:16-alpine
cd backend
WORKLEDGER_TEST_DATABASE_URL='postgresql+psycopg://postgres:pgtest@127.0.0.1:55432/workledger' pytest -q
```

The tests empty that database before each test. **Use a throwaway one.** It is slower (about 2 seconds a test), and CI runs a subset on every pull request and everything weekly. The backup and restore tests of the command-line tool are SQLite-only and are skipped here.
