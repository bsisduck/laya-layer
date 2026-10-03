"""Durable installation-wide call admission; no content or credentials stored."""

import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class QuotaExhausted(Exception):
    pass


class QuotaUnavailable(Exception):
    pass


class SemanticQuota:
    def __init__(
        self, path: Path, daily_calls: int = 1000, *, clock: Callable[[], float] = time.time
    ) -> None:
        if type(daily_calls) is not int or not 1 <= daily_calls <= 1_000_000:
            raise ValueError("Daily semantic calls must be between 1 and 1000000")
        self.path, self.daily_calls, self.clock = path, daily_calls, clock
        if path.is_symlink() or not path.parent.is_dir():
            raise QuotaUnavailable
        # Production state is private; never follow a final-component symlink.
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS semantic_days ("
                "day TEXT PRIMARY KEY, calls INTEGER NOT NULL CHECK(calls>=0), "
                "ceiling INTEGER NOT NULL CHECK(ceiling>0))"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=1, isolation_level=None)
            db.execute("PRAGMA synchronous=FULL")
            yield db
        except sqlite3.Error as error:
            raise QuotaUnavailable from error
        finally:
            if db is not None:
                db.close()

    def day(self) -> str:
        return datetime.fromtimestamp(self.clock(), UTC).date().isoformat()

    def admit(self) -> None:
        """Commit one debit before dispatch. Unknown outcomes are never refunded."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            day = self.day()
            db.execute(
                "INSERT OR IGNORE INTO semantic_days VALUES (?,0,?)", (day, self.daily_calls)
            )
            # Starting a differently configured backend cannot raise today's cap.
            db.execute(
                "UPDATE semantic_days SET ceiling=MIN(ceiling,?) WHERE day=?",
                (self.daily_calls, day),
            )
            changed = db.execute(
                "UPDATE semantic_days SET calls=calls+1 WHERE day=? AND calls<ceiling", (day,)
            ).rowcount
            db.execute("COMMIT")
            if changed != 1:
                raise QuotaExhausted

    def status(self) -> dict[str, str | int]:
        with self.connection() as db:
            day = self.day()
            row = db.execute(
                "SELECT calls,ceiling FROM semantic_days WHERE day=?", (day,)
            ).fetchone()
        spent, ceiling = (row[0], min(row[1], self.daily_calls)) if row else (0, self.daily_calls)
        return {
            "scope": "installation_utc_day",
            "day": day,
            "calls": spent,
            "limit": ceiling,
            "remaining": max(0, ceiling - spent),
        }
