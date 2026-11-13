import json
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from support import PASSWORD

from app import ops
from app.core.clock import utc_now
from app.core.config import Settings
from app.db.session import create_db_engine
from app.models import (
    ActivityEvent,
    AuthAttempt,
    Notification,
    NotificationKind,
    Organization,
    PasswordResetToken,
    Role,
    User,
    UserSession,
)
from app.models.notifications import LinkKind
from app.services import housekeeping
from app.services.organizations import add_membership, create_organization
from app.services.sessions import create_session
from app.services.users import create_user

pytestmark = pytest.mark.skipif(
    __import__("os").environ.get("WORKLEDGER_TEST_DATABASE_URL") is not None,
    reason="These tests use SQLite files; the PostgreSQL path is covered by command tests",
)


def settings_for(db_file: Path, uploads: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{db_file}", upload_dir=uploads)


@pytest.fixture
def installation(tmp_path: Path, alembic_config: Config, migrated_engine: Engine) -> dict[str, Any]:
    """A migrated database with an organization, a user, and one uploaded file."""
    database = Path(migrated_engine.url.database or "")
    uploads = tmp_path / "uploads"
    (uploads / "requests").mkdir(parents=True)
    (uploads / "requests" / "photo.bin").write_bytes(b"photo bytes")
    with Session(migrated_engine) as session:
        user = create_user(session, email="alex@example.com", full_name="Alex", password=PASSWORD)
        organization = create_organization(session, name="Harbor", actor=None)
        add_membership(
            session, organization=organization, user=user, roles=[Role.ADMINISTRATOR], actor=None
        )
        session.commit()
    return {
        "settings": settings_for(database, uploads),
        "database": database,
        "uploads": uploads,
        "backups": tmp_path / "backups",
        "config": alembic_config,
    }


def user_count(settings: Settings) -> int:
    engine = create_db_engine(settings.database_url)
    try:
        with Session(engine) as session:
            return session.scalar(select(func.count()).select_from(User)) or 0
    finally:
        engine.dispose()


# --- Backup and restore ------------------------------------------------------------------


def test_a_backup_holds_the_database_the_files_and_a_manifest(installation: dict[str, Any]):
    folder = ops.backup(installation["settings"], installation["backups"])

    manifest = json.loads((folder / "manifest.json").read_text())
    assert folder.name.startswith("workledger-")
    assert {path.name for path in folder.iterdir()} == {
        "manifest.json",
        "database.sqlite",
        "uploads.tar.gz",
    }
    assert manifest["database_kind"] == "sqlite"
    assert manifest["schema_revision"] in ops.known_revisions()
    assert set(manifest["files"]) == {"database.sqlite", "uploads.tar.gz"}
    assert all(len(checksum) == 64 for checksum in manifest["files"].values())


def test_a_backup_is_private_to_the_operator(installation: dict[str, Any]):
    folder = ops.backup(installation["settings"], installation["backups"])

    assert folder.stat().st_mode & 0o077 == 0


def test_a_backup_can_be_restored_into_an_empty_installation(
    installation: dict[str, Any], tmp_path: Path
):
    folder = ops.backup(installation["settings"], installation["backups"])
    fresh = settings_for(tmp_path / "new" / "restored.db", tmp_path / "new" / "uploads")

    ops.restore(fresh, folder)

    assert user_count(fresh) == 1
    assert (tmp_path / "new" / "uploads" / "requests" / "photo.bin").read_bytes() == b"photo bytes"
    # The restored database is a working one: it is at the current schema and signs in.
    assert ops.schema_revision(fresh) == ops.schema_revision(installation["settings"])


def test_the_backup_is_a_snapshot_that_later_changes_do_not_touch(
    installation: dict[str, Any], tmp_path: Path, migrated_engine: Engine
):
    folder = ops.backup(installation["settings"], installation["backups"])
    with Session(migrated_engine) as session:
        create_user(session, email="later@example.com", full_name="Later", password=PASSWORD)
        session.commit()
    fresh = settings_for(tmp_path / "new.db", tmp_path / "new-uploads")

    ops.restore(fresh, folder)

    assert user_count(installation["settings"]) == 2
    assert user_count(fresh) == 1


def test_restoring_over_a_database_with_data_needs_replace(
    installation: dict[str, Any], migrated_engine: Engine
):
    folder = ops.backup(installation["settings"], installation["backups"])
    with Session(migrated_engine) as session:
        create_user(session, email="later@example.com", full_name="Later", password=PASSWORD)
        session.commit()

    with pytest.raises(ops.OpsError, match="already has data"):
        ops.restore(installation["settings"], folder)
    assert user_count(installation["settings"]) == 2

    ops.restore(installation["settings"], folder, replace=True)
    assert user_count(installation["settings"]) == 1


def test_a_replaced_upload_folder_matches_the_backup(installation: dict[str, Any]):
    folder = ops.backup(installation["settings"], installation["backups"])
    (installation["uploads"] / "requests" / "photo.bin").write_bytes(b"changed")
    (installation["uploads"] / "stray.bin").write_bytes(b"not in the backup")
    # In a container the folder is a mounted volume, so it must be emptied, never replaced.
    inode = installation["uploads"].stat().st_ino

    ops.restore(installation["settings"], folder, replace=True)

    assert installation["uploads"].stat().st_ino == inode
    assert (installation["uploads"] / "requests" / "photo.bin").read_bytes() == b"photo bytes"
    assert not (installation["uploads"] / "stray.bin").exists()


def test_a_damaged_backup_is_refused_before_anything_changes(
    installation: dict[str, Any], migrated_engine: Engine
):
    folder = ops.backup(installation["settings"], installation["backups"])
    with Session(migrated_engine) as session:
        create_user(session, email="later@example.com", full_name="Later", password=PASSWORD)
        session.commit()
    damaged = folder / "database.sqlite"
    damaged.write_bytes(damaged.read_bytes() + b"x")

    with pytest.raises(ops.OpsError, match="checksum"):
        ops.restore(installation["settings"], folder, replace=True)

    assert user_count(installation["settings"]) == 2


def test_a_backup_missing_a_file_is_refused(installation: dict[str, Any]):
    folder = ops.backup(installation["settings"], installation["backups"])
    (folder / "uploads.tar.gz").unlink()

    with pytest.raises(ops.OpsError, match="missing uploads.tar.gz"):
        ops.verify(folder)


def test_a_folder_that_is_not_a_backup_is_refused(tmp_path: Path):
    with pytest.raises(ops.OpsError, match="not a WorkLedger backup"):
        ops.verify(tmp_path)


def test_a_backup_from_a_newer_version_is_refused(installation: dict[str, Any], tmp_path: Path):
    folder = ops.backup(installation["settings"], installation["backups"])
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["schema_revision"] = "ffffffffffff"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    fresh = settings_for(tmp_path / "new.db", tmp_path / "new-uploads")

    with pytest.raises(ops.OpsError, match="newer version"):
        ops.restore(fresh, folder)


def test_a_backup_cannot_be_restored_into_another_kind_of_database(
    installation: dict[str, Any], tmp_path: Path
):
    folder = ops.backup(installation["settings"], installation["backups"])
    postgres = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost/db",
        upload_dir=tmp_path / "x",
    )

    with pytest.raises(ops.OpsError, match="sqlite but the configured database is postgresql"):
        ops.restore(postgres, folder)


def test_an_upload_archive_that_tries_to_escape_is_refused(tmp_path: Path):
    import io
    import tarfile

    archive_path = tmp_path / "evil.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("uploads/../../escaped.txt")
        info.size = 3
        archive.addfile(info, io.BytesIO(b"bad"))
        link = tarfile.TarInfo("uploads/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)

    with pytest.raises(ops.OpsError, match="unexpected entry"):
        ops._restore_uploads(archive_path, tmp_path / "uploads")

    assert not (tmp_path / "escaped.txt").exists()


def test_a_failed_backup_leaves_no_half_finished_folder(
    installation: dict[str, Any], monkeypatch: pytest.MonkeyPatch
):
    def fail(*_: object) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(ops, "_sha256", fail)

    with pytest.raises(RuntimeError):
        ops.backup(installation["settings"], installation["backups"])

    assert list(installation["backups"].iterdir()) == []


def test_old_backups_are_pruned_but_the_newest_are_kept(tmp_path: Path):
    for stamp in ("20261101T020000Z", "20261102T020000Z", "20261103T020000Z"):
        folder = tmp_path / f"workledger-{stamp}"
        folder.mkdir()
        (folder / "manifest.json").write_text("{}")
    (tmp_path / "notes").mkdir()

    removed = ops.prune(tmp_path, keep=2)

    assert [path.name for path in removed] == ["workledger-20261101T020000Z"]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "notes",
        "workledger-20261102T020000Z",
        "workledger-20261103T020000Z",
    ]
    with pytest.raises(ops.OpsError):
        ops.prune(tmp_path, keep=0)


# --- PostgreSQL uses the standard tools --------------------------------------------------


class FakeRun:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs["env"]))
        if command[0] == "pg_dump":
            Path(command[-1].removeprefix("--file=")).write_bytes(b"dump")
        return subprocess.CompletedProcess(command, self.returncode, "", self.stderr)


def postgres_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://workledger:s3cret@db.internal:5433/ledger",
        upload_dir=tmp_path / "uploads",
    )


def test_a_postgresql_backup_runs_pg_dump_with_the_password_in_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fake = FakeRun()
    monkeypatch.setattr(ops.subprocess, "run", fake)
    monkeypatch.setattr(ops.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ops, "schema_revision", lambda _: "e3b67b0bbd48")

    folder = ops.backup(postgres_settings(tmp_path), tmp_path / "backups")

    [(command, environment)] = fake.calls
    assert command[:3] == ["pg_dump", "--format=custom", "--no-owner"]
    assert "s3cret" not in " ".join(command)
    assert environment["PGPASSWORD"] == "s3cret"
    assert (environment["PGHOST"], environment["PGPORT"]) == ("db.internal", "5433")
    assert (environment["PGUSER"], environment["PGDATABASE"]) == ("workledger", "ledger")
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["database_kind"] == "postgresql"
    assert manifest["database_file"] == "database.dump"


def test_a_postgresql_restore_runs_pg_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = FakeRun()
    monkeypatch.setattr(ops.subprocess, "run", fake)
    monkeypatch.setattr(ops.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ops, "schema_revision", lambda _: "e3b67b0bbd48")
    settings = postgres_settings(tmp_path)
    folder = ops.backup(settings, tmp_path / "backups")
    fake.calls.clear()
    monkeypatch.setattr(ops, "database_has_data", lambda _: False)

    ops.restore(settings, folder)

    [(command, environment)] = fake.calls
    assert command[0] == "pg_restore"
    assert {"--clean", "--if-exists", "--exit-on-error", "--single-transaction"} <= set(command)
    # pg_restore ignores PGDATABASE, so the database must be named on the command line.
    assert "--dbname=ledger" in command
    assert command[-1].endswith("database.dump")
    assert environment["PGPASSWORD"] == "s3cret"


def test_a_missing_postgresql_tool_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ops.shutil, "which", lambda name: None)
    monkeypatch.setattr(ops, "schema_revision", lambda _: None)

    with pytest.raises(ops.OpsError, match="pg_dump is not installed"):
        ops.backup(postgres_settings(tmp_path), tmp_path / "backups")

    assert list((tmp_path / "backups").iterdir()) == []


def test_a_failing_postgresql_tool_reports_its_message_without_the_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(ops.subprocess, "run", FakeRun(1, "connection refused"))
    monkeypatch.setattr(ops.shutil, "which", lambda name: name)
    monkeypatch.setattr(ops, "schema_revision", lambda _: None)

    with pytest.raises(ops.OpsError) as caught:
        ops.backup(postgres_settings(tmp_path), tmp_path / "backups")

    assert "connection refused" in str(caught.value)
    assert "s3cret" not in str(caught.value)


# --- The command line --------------------------------------------------------------------


def test_the_commands_back_up_prune_restore_and_purge(
    installation: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    settings = installation["settings"]
    backups = installation["backups"]

    assert ops.main(["backup", "--to", str(backups)], settings_factory=lambda: settings) == 0
    assert "Backup written to" in capsys.readouterr().out
    [folder] = backups.iterdir()

    assert ops.main(["purge"], settings_factory=lambda: settings) == 0
    assert "Removed 0 expired" in capsys.readouterr().out

    assert (
        ops.main(["prune", "--in", str(backups), "--keep", "5"], settings_factory=lambda: settings)
        == 0
    )
    assert "Removed 0 old" in capsys.readouterr().out

    code = ops.main(["restore", "--from", str(folder)], settings_factory=lambda: settings)
    captured = capsys.readouterr()
    assert code == 1
    assert "already has data" in captured.err

    code = ops.main(
        ["restore", "--from", str(folder), "--replace"], settings_factory=lambda: settings
    )
    assert code == 0
    assert "alembic upgrade head" in capsys.readouterr().out


# --- Housekeeping ------------------------------------------------------------------------


def test_housekeeping_removes_only_what_has_outlived_its_purpose(
    db_session: Session, installation: dict[str, Any]
):
    now = utc_now()
    user = db_session.scalars(select(User)).one()
    live, _ = create_session(db_session, user, max_age=timedelta(days=1))
    dead, _ = create_session(db_session, user, max_age=timedelta(days=1))
    dead.expires_at = now - timedelta(minutes=1)
    idle, _ = create_session(db_session, user, max_age=timedelta(days=7))
    idle.last_seen_at = now - timedelta(hours=13)
    db_session.add_all(
        [
            PasswordResetToken(
                user_id=user.id, token_hash="a" * 64, expires_at=now - timedelta(days=2)
            ),
            PasswordResetToken(
                user_id=user.id, token_hash="b" * 64, expires_at=now + timedelta(minutes=30)
            ),
            AuthAttempt(kind="sign_in", account_key="k" * 64, created_at=now - timedelta(days=2)),
            AuthAttempt(kind="sign_in", account_key="k" * 64),
        ]
    )
    organization = db_session.scalars(select(Organization.id)).one()
    db_session.add_all(
        [
            Notification(
                organization_id=organization,
                recipient_user_id=user.id,
                kind=NotificationKind.REQUEST_SUBMITTED,
                link_kind=LinkKind.STAFF_REQUEST,
                subject_id=user.id,
                title="Old",
                created_at=now - timedelta(days=400),
            ),
            Notification(
                organization_id=organization,
                recipient_user_id=user.id,
                kind=NotificationKind.REQUEST_SUBMITTED,
                link_kind=LinkKind.STAFF_REQUEST,
                subject_id=user.id,
                title="Recent",
            ),
        ]
    )
    db_session.commit()

    result = housekeeping.purge_expired(db_session, idle_timeout=timedelta(hours=12))
    db_session.commit()

    assert (result.sessions, result.reset_tokens, result.auth_attempts) == (2, 1, 1)
    assert result.notifications == 1
    assert result.total == 5
    assert db_session.scalar(select(func.count()).select_from(UserSession)) == 1
    assert db_session.scalar(select(Notification.title)) == "Recent"
    assert db_session.scalar(select(func.count()).select_from(PasswordResetToken)) == 1
    assert db_session.scalar(select(func.count()).select_from(AuthAttempt)) == 1


def test_housekeeping_keeps_the_activity_history_and_business_records(
    db_session: Session, installation: dict[str, Any]
):
    before = (
        db_session.scalar(select(func.count()).select_from(ActivityEvent)),
        db_session.scalar(select(func.count()).select_from(Organization)),
    )

    housekeeping.purge_expired(
        db_session, idle_timeout=timedelta(hours=12), now=utc_now() + timedelta(days=10_000)
    )
    db_session.commit()

    after = (
        db_session.scalar(select(func.count()).select_from(ActivityEvent)),
        db_session.scalar(select(func.count()).select_from(Organization)),
    )
    assert after == before
    assert before[0] and before[1]
