"""SQLite migration and short transactions. Network I/O stays outside writes."""

from contextlib import contextmanager, closing
from pathlib import Path
import sqlite3

from .errors import Problem


def connect(path):
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA secure_delete = ON")
    return connection


def migrate(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            raise RuntimeError(
                "Database is newer than this server; do not downgrade it."
            )
        if version == 0:
            script = Path(__file__).with_name("schema.sql").read_text()
            connection.executescript("BEGIN IMMEDIATE;\n" + script + "\nCOMMIT;")
        if version < 2:
            script = Path(__file__).with_name("migrations").joinpath("002-archive.sql").read_text()
            connection.executescript("BEGIN IMMEDIATE;\n" + script + "\nCOMMIT;")


@contextmanager
def transaction(path, *, write=False):
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection
        connection.commit()
    except BaseException as error:
        if isinstance(error, Problem) and error.commit:
            connection.commit()
        else:
            connection.rollback()
        raise
    finally:
        connection.close()


def one(connection, query, args=()):
    row = connection.execute(query, args).fetchone()
    return dict(row) if row else None


def many(connection, query, args=()):
    return [dict(row) for row in connection.execute(query, args)]
