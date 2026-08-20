# infra/migrate_data.py
#
# Copies all pipeline data from the old Snowflake trial account (read via the
# SNOWFLAKE_*_OLD env vars) into the new account (read via the plain
# SNOWFLAKE_* env vars, which infra/run_setup_sql.py must have already
# provisioned). analytics_dev/analytics_prod marts are NOT copied here —
# they're dbt-built and get rebuilt with `dbt run` after this script.
#
# Usage:
#     python infra/migrate_data.py

import logging
import os

import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_data")

# Table -> (ordered columns, set of columns that are VARIANT and need PARSE_JSON)
TABLES: list[tuple[str, list[str], set[str]]] = [
    (
        "RAW.JSEARCH.SRC_POSTINGS",
        ["SOURCE", "RAW_PAYLOAD", "INGESTED_AT"],
        {"RAW_PAYLOAD"},
    ),
    (
        "RAW.THEIRSTACK.SRC_POSTINGS",
        ["SOURCE", "RAW_PAYLOAD", "INGESTED_AT"],
        {"RAW_PAYLOAD"},
    ),
    (
        "RAW.BUILTIN.SRC_POSTINGS",
        ["SOURCE", "RAW_PAYLOAD", "INGESTED_AT"],
        {"RAW_PAYLOAD"},
    ),
    (
        "ENRICHED.PUBLIC.JOB_ENRICHMENT",
        [
            "JOB_ID", "SOURCE", "INFERRED_SENIORITY", "ROLE_ARCHETYPE", "WORK_FOCUS",
            "TECH_STACK_REQUIRED", "TECH_STACK_PREFERRED",
            "PARADIGMS_REQUIRED", "PARADIGMS_PREFERRED",
            "DEGREE_REQUIREMENT", "YEARS_REQUIRED_MIN", "YEARS_REQUIRED_MAX",
            "SALARY_MIN", "SALARY_MAX",
            "ACKNOWLEDGES_AI", "DOMAIN", "EXPLICITLY_ENCOURAGES_APPLICANTS",
            "CONFIDENCE_SCORE", "ENRICHED_AT", "MODEL_VERSION",
        ],
        {"TECH_STACK_REQUIRED", "TECH_STACK_PREFERRED", "PARADIGMS_REQUIRED", "PARADIGMS_PREFERRED"},
    ),
    (
        "RAW.PIPELINE.RUNS",
        [
            "RUN_ID", "RUN_AT", "DURATION_SECONDS", "STATUS",
            "JSEARCH_ROWS", "THEIRSTACK_ROWS", "BUILTIN_ROWS", "TOTAL_ROWS",
        ],
        set(),
    ),
    (
        "RAW.PIPELINE.API_USAGE",
        [
            "RUN_ID", "RUN_AT", "SOURCE", "CREDITS_REMAINING", "CREDITS_LIMIT",
            "CREDITS_USED_CUMULATIVE", "CREDITS_USED_THIS_RUN", "RESET_DATE",
        ],
        set(),
    ),
]


def get_connection(suffix: str) -> snowflake.connector.SnowflakeConnection:
    def env(key: str) -> str:
        val = os.getenv(f"{key}{suffix}")
        if not val:
            raise EnvironmentError(f"Missing env var {key}{suffix}")
        return val

    return snowflake.connector.connect(
        account=env("SNOWFLAKE_ACCOUNT"),
        user=env("SNOWFLAKE_USER"),
        password=env("SNOWFLAKE_PASSWORD"),
        role=env("SNOWFLAKE_ROLE"),
        warehouse=env("SNOWFLAKE_WAREHOUSE"),
    )


def build_insert_sql(table: str, columns: list[str], variant_columns: set[str]) -> str:
    select_exprs = [
        f"PARSE_JSON(${i})" if col in variant_columns else f"${i}"
        for i, col in enumerate(columns, start=1)
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    return f"""
        INSERT INTO {table} ({", ".join(columns)})
        SELECT {", ".join(select_exprs)}
        FROM VALUES ({placeholders})
    """


def migrate_table(
    old_cur, new_cur, table: str, columns: list[str], variant_columns: set[str]
) -> tuple[int, int]:
    old_cur.execute(f"SELECT {', '.join(columns)} FROM {table}")
    rows = old_cur.fetchall()
    old_count = len(rows)

    if rows:
        insert_sql = build_insert_sql(table, columns, variant_columns)
        new_cur.executemany(insert_sql, rows)

    new_cur.execute(f"SELECT COUNT(*) FROM {table}")
    new_count = new_cur.fetchone()[0]

    return old_count, new_count


def main() -> None:
    old_conn = get_connection("_OLD")
    new_conn = get_connection("")
    log.info("Connected to both old and new accounts.")

    old_cur = old_conn.cursor()
    new_cur = new_conn.cursor()

    mismatches = []
    try:
        for table, columns, variant_columns in TABLES:
            log.info(f"Migrating {table}...")
            old_count, new_count = migrate_table(old_cur, new_cur, table, columns, variant_columns)
            new_conn.commit()
            status = "OK" if new_count == old_count else "MISMATCH"
            if status == "MISMATCH":
                mismatches.append(table)
            log.info(f"  {table}: old={old_count} new={new_count} [{status}]")
    finally:
        old_cur.close()
        new_cur.close()
        old_conn.close()
        new_conn.close()

    if mismatches:
        log.error(f"Row count mismatches in: {mismatches}")
        raise SystemExit(1)
    log.info("All tables migrated with matching row counts.")


if __name__ == "__main__":
    main()
