"""Real SQLite cleanup races retain the launcher's strict private-file boundary."""

import os
import sqlite3
from contextlib import closing

import pytest
from test_lifecycle import state as state

from agentgate.lifecycle import state as files
from agentgate.lifecycle.install import configuration


@pytest.mark.parametrize(
    "database", ["agentgate.sqlite3", "collector.sqlite3", "semantic-quota.sqlite3"]
)
@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_live_sqlite_cleanup_during_configuration_is_safe(state, monkeypatch, database, suffix):
    data = state / "data"
    files.private_dir(data, create=True)
    source = data / database
    files.write_new(source, b"")
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE evidence(value TEXT)")
    connection.execute("INSERT INTO evidence VALUES ('retained')")
    connection.commit()
    sidecar = data / (database + suffix)
    assert sidecar.exists()
    original = files.check_file
    closed = False

    def close_live_connection(path):
        nonlocal closed
        if path == sidecar and not closed:
            assert path.exists()  # Listed by the actual directory iterator.
            connection.close()  # SQLite itself removes the listed sidecars.
            closed = True
            assert not path.exists()
        original(path)

    monkeypatch.setattr(files, "check_file", close_live_connection)
    try:
        assert configuration(state)["local_console"] is False
        assert closed
        with closing(sqlite3.connect(source)) as probe:
            assert probe.execute("SELECT value FROM evidence").fetchall() == [("retained",)]
    finally:
        connection.close()


@pytest.mark.parametrize(
    "name",
    [
        "agentgate.sqlite3",
        "client.token",
        "foreign.sqlite3-shm",
        "agentgate.sqlite3-journal",
        "agentgate.sqlite3-wal.bak",
    ],
)
def test_vanished_required_or_unrecognized_files_still_fail(state, monkeypatch, name):
    data = state / "data"
    files.private_dir(data, create=True)
    files.write_new(data / "foreign.sqlite3", b"")
    target = data / name
    files.write_new(target, b"retained")
    original = files.check_file

    def disappear(path):
        if path == target:
            target.unlink()
        original(path)

    monkeypatch.setattr(files, "check_file", disappear)
    with pytest.raises(FileNotFoundError):
        configuration(state)


@pytest.mark.parametrize("unsafe", ["symlink", "permissions", "hardlink"])
def test_existing_sqlite_sidecars_still_require_safe_files(state, monkeypatch, tmp_path, unsafe):
    data = state / "data"
    files.private_dir(data, create=True)
    files.write_new(data / "agentgate.sqlite3", b"")
    sidecar = data / "agentgate.sqlite3-shm"
    files.write_new(sidecar, b"retained")
    if unsafe == "symlink":
        sidecar.unlink()
        sidecar.symlink_to(tmp_path / "missing-target")
    elif unsafe == "permissions":
        sidecar.chmod(0o644)
    else:
        os.link(sidecar, tmp_path / "foreign-link")
    with pytest.raises(files.LifecycleError):
        configuration(state)


@pytest.mark.parametrize("unsafe", ["missing", "permissions", "symlink"])
def test_vanished_sidecar_does_not_hide_unsafe_or_missing_database(
    state, monkeypatch, tmp_path, unsafe
):
    data = state / "data"
    files.private_dir(data, create=True)
    source = data / "agentgate.sqlite3"
    files.write_new(source, b"")
    sidecar = data / "agentgate.sqlite3-shm"
    files.write_new(sidecar, b"")
    original = files.check_file

    def replace_database(path):
        if path == sidecar:
            sidecar.unlink()
            if unsafe == "missing":
                source.unlink()
            elif unsafe == "permissions":
                source.chmod(0o644)
            else:
                source.unlink()
                source.symlink_to(tmp_path / "missing-target")
        original(path)

    monkeypatch.setattr(files, "check_file", replace_database)
    with pytest.raises(FileNotFoundError if unsafe == "missing" else files.LifecycleError):
        configuration(state)


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("I/O failure")])
def test_sqlite_sidecar_errors_other_than_disappearance_propagate(state, monkeypatch, error):
    data = state / "data"
    files.private_dir(data, create=True)
    files.write_new(data / "agentgate.sqlite3", b"")
    sidecar = data / "agentgate.sqlite3-shm"
    files.write_new(sidecar, b"")
    original = files.check_file

    def fail(path):
        if path == sidecar:
            raise error
        original(path)

    monkeypatch.setattr(files, "check_file", fail)
    with pytest.raises(type(error)):
        configuration(state)
