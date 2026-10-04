"""Read-only QA evidence, including absence of lazy authority tables."""

import sqlite3


def snapshot(database, tables):
    with sqlite3.connect(database) as db:
        existing = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        # Absence differs from an empty table: unexpected startup initialization
        # must fail the same equality assertion as an unexpected authority write.
        return {
            table: db.execute(f'SELECT * FROM "{table}"').fetchall() if table in existing else None
            for table in tables
        }
