# The API and its command-line tools (migrations, backups). Build context: backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# The PostgreSQL client tools are what `python -m app.ops backup` and `restore` run. A dump can
# only be restored by a client at least as new as the server that made it, and `pg_dump` refuses
# a newer server, so the client's major version must match the `db` image in deploy/.
ARG PG_MAJOR=16
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d /usr/share/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-${PG_MAJOR} \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY alembic ./alembic
# Editable, so the code stays in /app where the migration scripts are.
RUN pip install -e .

# Never run as root. Uploaded files and backups live on volumes this user owns.
RUN useradd --system --uid 10001 --home-dir /app workledger \
    && mkdir -p /data/uploads /backups \
    && chown -R workledger /data /backups
USER workledger

ENV WORKLEDGER_ENVIRONMENT=production \
    WORKLEDGER_UPLOAD_DIR=/data/uploads

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=4)"

# --no-access-log: the server's own log prints full URLs. The application logs routes instead.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
