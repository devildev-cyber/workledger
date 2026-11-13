"""Operating a WorkLedger installation: backups, restores, and housekeeping (decision 0025).

Usage, from backend/ with the same environment as the server:

    python -m app.ops backup  --to /var/backups/workledger
    python -m app.ops prune   --in /var/backups/workledger --keep 14
    python -m app.ops restore --from /var/backups/workledger/workledger-20261113T020000Z
    python -m app.ops purge

A backup is one folder holding the database, the uploaded files, and a manifest with their
checksums and the schema version. A restore checks the checksums before it touches anything,
and refuses to overwrite a database that already has data unless told to replace it.

SQLite is copied with SQLite's own online backup. PostgreSQL uses pg_dump and pg_restore, which
must be installed; the password is passed in the environment, never on the command line.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import Settings, get_settings
from app.db.session import create_db_engine
from app.services.housekeeping import purge_expired

MANIFEST = "manifest.json"
UPLOADS_ARCHIVE = "uploads.tar.gz"
PREFIX = "workledger-"
BACKEND_DIR = Path(__file__).resolve().parents[1]


class OpsError(Exception):
    """Something the operator can fix. The message says what."""


# --- Helpers -----------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_file(url: URL) -> Path:
    if not url.database or url.database == ":memory:":
        raise OpsError("The SQLite database is in memory, so there is nothing to back up")
    return Path(url.database)


def _pg_environment(url: URL) -> dict[str, str]:
    environment = dict(os.environ)
    for variable, value in (
        ("PGHOST", url.host),
        ("PGPORT", str(url.port) if url.port else None),
        ("PGUSER", url.username),
        ("PGPASSWORD", url.password),
        ("PGDATABASE", url.database),
    ):
        if value:
            environment[variable] = value
    return environment


def _run_pg(command: list[str], url: URL) -> None:
    tool = command[0]
    if shutil.which(tool) is None:
        raise OpsError(f"{tool} is not installed. Install the PostgreSQL client tools.")
    result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        command, env=_pg_environment(url), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        # The tool's own message names the problem; it does not contain the password.
        raise OpsError(f"{tool} failed: {result.stderr.strip() or 'no details'}")


def schema_revision(settings: Settings) -> str | None:
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names():
                return None
            return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def known_revisions() -> set[str]:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}


def database_has_data(settings: Settings) -> bool:
    engine = create_db_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
            if not tables:
                return False
            if "users" in tables:
                return connection.execute(text("SELECT 1 FROM users LIMIT 1")).first() is not None
            return True
    finally:
        engine.dispose()


# --- Backup ------------------------------------------------------------------------------


def backup(settings: Settings, destination: Path) -> Path:
    """Write a new backup folder under destination and return it."""
    url = make_url(settings.database_url)
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    folder = destination / f"{PREFIX}{stamp}"
    if folder.exists():
        raise OpsError(f"{folder} already exists. Wait a second and try again.")
    folder.mkdir(parents=True, mode=0o700)

    try:
        if url.get_backend_name() == "sqlite":
            database = folder / "database.sqlite"
            source = sqlite3.connect(_database_file(url))
            try:
                target = sqlite3.connect(database)
                with target:
                    source.backup(target)
                target.close()
            finally:
                source.close()
            kind = "sqlite"
        else:
            database = folder / "database.dump"
            _run_pg(
                ["pg_dump", "--format=custom", "--no-owner", f"--file={database}"],
                url,
            )
            kind = "postgresql"

        with tarfile.open(folder / UPLOADS_ARCHIVE, "w:gz") as archive:
            if settings.upload_dir.exists():
                archive.add(settings.upload_dir, arcname="uploads")

        manifest: dict[str, Any] = {
            "created_at": utc_now().isoformat(),
            "database_kind": kind,
            "database_file": database.name,
            "schema_revision": schema_revision(settings),
            "files": {path.name: _sha256(path) for path in (database, folder / UPLOADS_ARCHIVE)},
        }
        (folder / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder


def prune(directory: Path, *, keep: int) -> list[Path]:
    """Delete all but the newest `keep` backups in directory. Returns what was deleted."""
    if keep < 1:
        raise OpsError("Keep at least one backup")
    backups = sorted(
        (
            path
            for path in directory.glob(f"{PREFIX}*")
            if path.is_dir() and (path / MANIFEST).exists()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    removed = backups[keep:]
    for path in removed:
        shutil.rmtree(path)
    return removed


# --- Restore -----------------------------------------------------------------------------


def verify(folder: Path) -> dict[str, Any]:
    """Check that a backup is complete and unchanged. Returns its manifest."""
    manifest_path = folder / MANIFEST
    if not manifest_path.exists():
        raise OpsError(f"{folder} is not a WorkLedger backup (no {MANIFEST})")
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["files"].items():
        path = folder / name
        if not path.exists():
            raise OpsError(f"The backup is missing {name}")
        if _sha256(path) != expected:
            raise OpsError(f"{name} does not match its checksum. The backup is damaged.")
    return manifest


def _restore_uploads(archive_path: Path, upload_dir: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            upload_dir.mkdir(parents=True, exist_ok=True)
            return
        # Only plain files and folders under uploads/, none of which can point elsewhere.
        for member in members:
            if not (member.isfile() or member.isdir()) or not (
                member.name == "uploads" or member.name.startswith("uploads/")
            ):
                raise OpsError(f"The backup holds an unexpected entry: {member.name}")
        staging = upload_dir.parent / f".{upload_dir.name}.restoring"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        archive.extractall(staging, filter="data")
    # The folder itself stays: in a container it is a mounted volume and cannot be replaced.
    # Contents are moved (copied across devices when needed), not renamed.
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old in upload_dir.iterdir():
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)
        else:
            old.unlink()
    for new in (staging / "uploads").iterdir():
        shutil.move(str(new), upload_dir / new.name)
    shutil.rmtree(staging, ignore_errors=True)


def restore(settings: Settings, folder: Path, *, replace: bool = False) -> dict[str, Any]:
    """Put a backup back. Returns the manifest.

    Nothing is changed unless the backup passes its checksums and its schema version is one this
    code knows. A database that already has data is only overwritten with replace=True.
    """
    manifest = verify(folder)
    revision = manifest.get("schema_revision")
    if revision is not None and revision not in known_revisions():
        raise OpsError(
            f"The backup was made by a newer version (schema {revision}). Update WorkLedger first."
        )
    url = make_url(settings.database_url)
    if manifest["database_kind"] != url.get_backend_name():
        raise OpsError(
            f"The backup is {manifest['database_kind']} but the configured database is "
            f"{url.get_backend_name()}"
        )
    if url.get_backend_name() == "sqlite":
        _database_file(url).parent.mkdir(parents=True, exist_ok=True)
    if database_has_data(settings) and not replace:
        raise OpsError("The database already has data. Use --replace to overwrite it.")

    database = folder / manifest["database_file"]
    if manifest["database_kind"] == "sqlite":
        target = _database_file(url)
        staging = target.with_name(f".{target.name}.restoring")
        shutil.copyfile(database, staging)
        staging.replace(target)
    else:
        # pg_restore ignores PGDATABASE: without --dbname it prints a script instead of
        # restoring. One transaction makes a failed restore leave the database as it was.
        _run_pg(
            ["pg_restore", f"--dbname={url.database}", "--clean", "--if-exists", "--no-owner",
             "--single-transaction", "--exit-on-error", str(database)],
            url,
        )  # fmt: skip
    _restore_uploads(folder / UPLOADS_ARCHIVE, settings.upload_dir)
    return manifest


# --- Command line ------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.ops", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    make = commands.add_parser("backup", help="Back up the database and uploaded files")
    make.add_argument("--to", required=True, type=Path, help="Folder that holds all backups")

    old = commands.add_parser("prune", help="Delete all but the newest backups")
    old.add_argument("--in", dest="source", required=True, type=Path)
    old.add_argument("--keep", required=True, type=int, help="How many backups to keep")

    back = commands.add_parser("restore", help="Restore one backup")
    back.add_argument("--from", dest="source", required=True, type=Path)
    back.add_argument("--replace", action="store_true", help="Overwrite a database with data")

    commands.add_parser("purge", help="Delete expired sessions, links, counts, notifications")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_factory: Callable[[], Settings] = get_settings,
) -> int:
    args = _build_parser().parse_args(argv)
    settings = settings_factory()
    try:
        if args.command == "backup":
            folder = backup(settings, args.to)
            print(f"Backup written to {folder}")
        elif args.command == "prune":
            removed = prune(args.source, keep=args.keep)
            print(f"Removed {len(removed)} old backup(s)")
        elif args.command == "restore":
            manifest = restore(settings, args.source, replace=args.replace)
            print(
                f"Restored the backup made {manifest['created_at']}. Now run: alembic upgrade head"
            )
        else:
            engine = create_db_engine(settings.database_url)
            with Session(engine) as session:
                result = purge_expired(session, idle_timeout=settings.session_idle_timeout)
                session.commit()
            engine.dispose()
            print(f"Removed {result.total} expired record(s)")
            for name, count in vars(result).items():
                print(f"  {name.replace('_', ' ')}: {count}")
    except OpsError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
