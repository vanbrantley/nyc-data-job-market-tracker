# infra/snowflake_client.py
#
# Loads Snowflake-ready row dicts into the appropriate RAW landing tables.
#
# Each row must have this shape (produced by all three ingestion clients):
#     SOURCE       str  — identifies the source and query context
#     RAW_PAYLOAD  dict — complete raw job record, untouched
#     INGESTED_AT  str  — ISO 8601 UTC timestamp
#
# Routing logic: the SOURCE field prefix determines the target table.
#     jsearch:*    → RAW.JSEARCH.SRC_POSTINGS
#     theirstack:* → RAW.THEIRSTACK.SRC_POSTINGS
#     builtin_nyc  → RAW.BUILTIN.SRC_POSTINGS
#
# The loader batches all rows for each table into a single executemany()
# call rather than one INSERT per row, which is significantly faster
# for larger result sets.

import json
import logging
import os
from collections import defaultdict

import snowflake.connector
from snowflake.connector import SnowflakeConnection

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

SOURCE_TABLE_MAP = {
    "jsearch": "RAW.JSEARCH.SRC_POSTINGS",
    "theirstack": "RAW.THEIRSTACK.SRC_POSTINGS",
    "builtin_nyc": "RAW.BUILTIN.SRC_POSTINGS",
}


class SnowflakeLoader:
    """
    Loads job rows into Snowflake RAW landing tables.

    Usage:
        loader = SnowflakeLoader()
        loader.load(all_rows)
        loader.close()

    Or as a context manager:
        with SnowflakeLoader() as loader:
            loader.load(all_rows)
    """

    def __init__(self) -> None:
        self._conn = self._connect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self) -> None:
        if self._conn and not self._conn.is_closed():
            self._conn.close()
            log.info("Snowflake connection closed.")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def load(self, rows: list[dict]) -> dict[str, int]:
        """
        Insert rows into the appropriate Snowflake landing tables.
        Rows are batched by target table for efficiency.

        Returns a dict of {table_name: rows_inserted} for logging.
        Raises on any insert failure — the caller (main.py) handles
        the exception and marks the snowflake source as failed.
        """
        if not rows:
            log.warning("load() called with empty rows list — nothing to do.")
            return {}

        # Group rows by target table
        batches: dict[str, list[tuple]] = defaultdict(list)

        for row in rows:
            source = row["SOURCE"]
            table = self._get_target_table(source)
            payload = json.dumps(row["RAW_PAYLOAD"], default=str)

            batches[table].append(
                (
                    source,
                    payload,
                    row["INGESTED_AT"],
                )
            )

        # Insert each batch
        results: dict[str, int] = {}
        cur = self._conn.cursor()

        try:
            for table, batch in batches.items():
                log.info(f"Inserting {len(batch)} rows into {table}...")

                cur.executemany(
                    f"""
                    INSERT INTO {table} (SOURCE, RAW_PAYLOAD, INGESTED_AT)
                    SELECT %s, PARSE_JSON(%s), %s::TIMESTAMP_TZ
                    """,
                    batch,
                )

                results[table] = len(batch)
                log.info(f"  ✓ {len(batch)} rows inserted into {table}.")

            self._conn.commit()
            log.info(
                f"Snowflake load committed — "
                f"{sum(results.values())} total rows across "
                f"{len(results)} tables."
            )

        except Exception as e:
            self._conn.rollback()
            log.error(f"Snowflake insert failed — transaction rolled back: {e}")
            raise

        finally:
            cur.close()

        return results

    def get_theirstack_high_water_mark(self) -> str | None:
        """
        Returns the MAX(discovered_at) from the TheirStack landing table
        as an ISO 8601 string, for use as discovered_at_gte on the next run.
        Returns None if the table is empty (first run).
        """
        cur = self._conn.cursor()
        try:
            cur.execute("""
                SELECT MAX(RAW_PAYLOAD:discovered_at::TIMESTAMP_TZ)
                FROM RAW.THEIRSTACK.SRC_POSTINGS
            """)
            result = cur.fetchone()[0]
            if result:
                hwm = result.isoformat()
                log.info(f"TheirStack high-water mark: {hwm}")
                return hwm
            else:
                log.info("TheirStack table is empty — no high-water mark.")
                return None
        finally:
            cur.close()

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _connect(self) -> SnowflakeConnection:
        required = [
            "SNOWFLAKE_ACCOUNT",
            "SNOWFLAKE_USER",
            "SNOWFLAKE_PASSWORD",
            "SNOWFLAKE_ROLE",
            "SNOWFLAKE_WAREHOUSE",
            "SNOWFLAKE_DATABASE",
        ]
        missing = [k for k in required if not os.getenv(k)]
        if missing:
            raise EnvironmentError(
                f"Missing Snowflake env vars: {missing}. "
                f"Add them to your .env file or GitHub Actions secrets."
            )

        conn = snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            role=os.getenv("SNOWFLAKE_ROLE"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
            database=os.getenv("SNOWFLAKE_DATABASE"),
        )
        log.info("Snowflake connection established.")
        return conn

    def _get_target_table(self, source: str) -> str:
        for prefix, table in SOURCE_TABLE_MAP.items():
            if source.startswith(prefix):
                return table
        raise ValueError(
            f"No table mapping found for SOURCE={source!r}. "
            f"Known prefixes: {list(SOURCE_TABLE_MAP.keys())}"
        )
