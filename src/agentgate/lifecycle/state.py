"""Private filesystem and exclusive ownership primitives for the native launcher."""

import fcntl
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class LifecycleError(Exception):
    """Safe, operator-facing diagnostic; never include child output or credentials."""


def check_path(path: Path) -> None:
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise LifecycleError("Unsafe symlink in state path; choose a real private directory")


def private_dir(path: Path, *, create: bool = False) -> None:
    check_path(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise LifecycleError("State directory must be owned by this user with mode 0700")


def check_file(path: Path) -> None:
    check_path(path)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise LifecycleError("State files must be private, regular, owned files without hard links")


def write_new(path: Path, content: bytes) -> None:
    check_path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    check_file(path)
    try:
        if path.stat().st_size > 65536:
            raise ValueError
        result = json.loads(path.read_bytes())
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError) as error:
        raise LifecycleError("Corrupt installation state; preserve it for recovery") from error


def save_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        check_file(path)
    temporary = path.with_suffix(path.suffix + ".new")
    write_new(temporary, (json.dumps(value, sort_keys=True) + "\n").encode())
    os.replace(temporary, path)


@contextmanager
def ownership(directory: Path) -> Iterator[None]:
    private_dir(directory)
    path = directory / "owner.lock"
    if not path.exists():
        try:
            write_new(path, b"")
        except FileExistsError:
            pass
    check_file(path)
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise LifecycleError(
                "Installation is busy or running; stop it before changing state"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def validate_data(directory: Path) -> None:
    private_dir(directory)
    for item in directory.iterdir():
        if item.is_dir():
            validate_data(item)
        else:
            check_file(item)
