# infra/run_setup_sql.py
#
# One-off runner that executes infra/snowflake_setup.sql statement-by-statement
# against whichever account the plain SNOWFLAKE_* env vars currently point at.
#
# Usage:
#     python infra/run_setup_sql.py

import logging
import os
import re
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_setup_sql")

SQL_PATH = Path(__file__).parent / "snowflake_setup.sql"

REQUIRED_ENV_VARS = [
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
]
# SNOWFLAKE_DATABASE is intentionally not required/used here — this script
# creates the databases from scratch, so connecting with one pre-selected
# would fail if it doesn't exist yet.


def parse_statements(sql_text: str) -> list[str]:
    """Strip `--` comment lines and split the remaining SQL into statements."""
    lines = [
        line for line in sql_text.splitlines() if not line.strip().startswith("--")
    ]
    body = "\n".join(lines)
    statements = [s.strip() for s in body.split(";")]
    return [s for s in statements if s]


def get_connection() -> snowflake.connector.SnowflakeConnection:
    missing = [k for k in REQUIRED_ENV_VARS if not os.getenv(k)]
    if missing:
        raise EnvironmentError(f"Missing Snowflake env vars: {missing}")

    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
    )


def main() -> None:
    statements = parse_statements(SQL_PATH.read_text(encoding="utf-8"))
    log.info(f"Parsed {len(statements)} statements from {SQL_PATH}")

    conn = get_connection()
    account = os.getenv("SNOWFLAKE_ACCOUNT")
    log.info(f"Connected to account={account}")

    cur = conn.cursor()
    try:
        for i, statement in enumerate(statements, start=1):
            preview = re.sub(r"\s+", " ", statement)[:100]
            log.info(f"[{i}/{len(statements)}] {preview}")
            try:
                cur.execute(statement)
            except Exception as e:
                log.error(f"Statement {i} failed: {e}\n--- statement ---\n{statement}")
                raise
        log.info("All statements executed successfully.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
