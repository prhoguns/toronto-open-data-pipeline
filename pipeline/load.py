"""Load step: raw CSV -> PostgreSQL ``raw`` schema using COPY.

Design choices, on purpose:
  * Every column lands as TEXT. Type casting is dbt's job (staging models), so a
    bad value in the source never breaks the load - it breaks a dbt test instead,
    where it is visible and explainable.
  * Full refresh (truncate + COPY) per run. The City republishes complete
    snapshots, not deltas, so incremental loading would only add complexity.
  * A ``_loaded_at`` column records when the batch landed. Useful for freshness
    checks and for debugging "which run produced this row".
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from pipeline.config import RAW_SCHEMA, DbConfig

log = logging.getLogger(__name__)


def _clean_ident(name: str) -> str:
    """Turn a CSV header into a safe snake_case column name."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if not name:
        name = "col"
    if name[0].isdigit():
        name = f"c_{name}"
    return name


def _existing_columns(cur: psycopg.Cursor, table: str) -> list[str] | None:
    """Column names of raw.<table> in definition order, minus _loaded_at; None if the table is absent."""
    cur.execute(
        """
        select column_name from information_schema.columns
        where table_schema = %s and table_name = %s and column_name <> '_loaded_at'
        order by ordinal_position
        """,
        (RAW_SCHEMA, table),
    )
    rows = [r[0] for r in cur.fetchall()]
    return rows or None


def _header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh))


def load_csv(path: Path, table: str, db: DbConfig | None = None) -> int:
    db = db or DbConfig()
    raw_cols = _header(path)
    cols = [_clean_ident(c) for c in raw_cols]
    if len(set(cols)) != len(cols):
        raise ValueError(f"duplicate column names after cleaning: {cols}")

    loaded_at = datetime.now(timezone.utc)
    with psycopg.connect(db.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(RAW_SCHEMA))
        )
        if _existing_columns(cur, table) == cols:
            # Same shape as last run: keep the table (dbt views depend on it) and just empty it.
            cur.execute(
                sql.SQL("TRUNCATE {}.{}").format(
                    sql.Identifier(RAW_SCHEMA), sql.Identifier(table)
                )
            )
            cur.execute(
                sql.SQL(
                    "ALTER TABLE {}.{} ALTER COLUMN _loaded_at SET DEFAULT {}"
                ).format(
                    sql.Identifier(RAW_SCHEMA),
                    sql.Identifier(table),
                    sql.Literal(loaded_at),
                )
            )
        else:
            # Source changed shape (or first run): rebuild. CASCADE drops dependent dbt views,
            # which `dbt run` recreates a step later.
            cur.execute(
                sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                    sql.Identifier(RAW_SCHEMA), sql.Identifier(table)
                )
            )
            col_defs = sql.SQL(", ").join(
                sql.SQL("{} TEXT").format(sql.Identifier(c)) for c in cols
            )
            cur.execute(
                sql.SQL(
                    "CREATE TABLE {}.{} ({}, _loaded_at TIMESTAMPTZ NOT NULL DEFAULT {})"
                ).format(
                    sql.Identifier(RAW_SCHEMA),
                    sql.Identifier(table),
                    col_defs,
                    sql.Literal(loaded_at),
                )
            )
        copy_stmt = sql.SQL(
            "COPY {}.{} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)"
        ).format(
            sql.Identifier(RAW_SCHEMA),
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, cols)),
        )
        with path.open("rb") as fh, cur.copy(copy_stmt) as copy:
            while chunk := fh.read(1 << 20):
                copy.write(chunk)
        cur.execute(
            sql.SQL("UPDATE {}.{} SET _loaded_at = %s").format(
                sql.Identifier(RAW_SCHEMA), sql.Identifier(table)
            ),
            (loaded_at,),
        )
        cur.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(RAW_SCHEMA), sql.Identifier(table)
            )
        )
        n = cur.fetchone()[0]
    log.info(
        "loaded %s rows into %s.%s from %s", f"{n:,}", RAW_SCHEMA, table, path.name
    )
    return n
