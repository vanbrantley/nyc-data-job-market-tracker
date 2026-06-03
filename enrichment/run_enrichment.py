import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import snowflake.connector
from openai import OpenAI
from pydantic import ValidationError

from enrichment.schemas.enrichment_schema import JobEnrichmentSchema

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_VERSION = "gpt-4o-mini"
MAX_TOKENS = 512
TEMPERATURE = 0
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries
PROMPT_PATH = Path(__file__).parent / "prompts" / "job_extraction.txt"

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
UNENRICHED_QUERY = """
WITH jsearch AS (
    SELECT
        RAW_PAYLOAD:job_id::STRING          AS job_id,
        SOURCE,
        RAW_PAYLOAD:job_title::STRING       AS job_title,
        RAW_PAYLOAD:job_description::STRING AS description
    FROM raw.jsearch.src_postings
    WHERE RAW_PAYLOAD:job_id::STRING IS NOT NULL
      AND RAW_PAYLOAD:job_id::STRING NOT IN (
          SELECT job_id FROM enriched.public.job_enrichment
      )
),
theirstack AS (
    SELECT
        RAW_PAYLOAD:id::STRING              AS job_id,
        SOURCE,
        RAW_PAYLOAD:job_title::STRING       AS job_title,
        RAW_PAYLOAD:description::STRING     AS description
    FROM raw.theirstack.src_postings
    WHERE RAW_PAYLOAD:id::STRING IS NOT NULL
      AND RAW_PAYLOAD:id::STRING NOT IN (
          SELECT job_id FROM enriched.public.job_enrichment
      )
),
builtin AS (
    SELECT
        RAW_PAYLOAD:identifier:value::STRING AS job_id,
        SOURCE,
        RAW_PAYLOAD:title::STRING            AS job_title,
        RAW_PAYLOAD:description::STRING      AS description
    FROM raw.builtin.src_postings
    WHERE RAW_PAYLOAD:identifier:value::STRING IS NOT NULL
      AND RAW_PAYLOAD:identifier:value::STRING NOT IN (
          SELECT job_id FROM enriched.public.job_enrichment
      )
)
SELECT * FROM jsearch
UNION ALL
SELECT * FROM theirstack
UNION ALL
SELECT * FROM builtin
ORDER BY source, job_id
"""

INSERT_QUERY = """
INSERT INTO enriched.public.job_enrichment (
    job_id, source, inferred_seniority, is_title_inflated, inflation_reasoning,
    role_archetype, work_focus, tech_stack_required, tech_stack_preferred,
    paradigms_required, paradigms_preferred, degree_requirement,
    years_required_min, years_required_max, salary_min, salary_max,
    confidence_score, enriched_at, model_version
)
SELECT
    $1, $2, $3, $4, $5, $6, $7,
    PARSE_JSON($8), PARSE_JSON($9), PARSE_JSON($10), PARSE_JSON($11),
    $12, $13, $14, $15, $16, $17, $18::TIMESTAMP_TZ, $19
FROM VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
    )


def fetch_unenriched_jobs(conn: snowflake.connector.SnowflakeConnection) -> list[dict]:
    cur = conn.cursor()
    cur.execute(UNENRICHED_QUERY)
    col_names = [desc[0].lower() for desc in cur.description]
    rows = [dict(zip(col_names, row)) for row in cur.fetchall()]
    cur.close()
    log.info(f"Fetched {len(rows)} unenriched jobs")
    return rows


def enrich_job(
    client: OpenAI,
    system_prompt: str,
    job: dict,
) -> Optional[JobEnrichmentSchema]:
    """Call the LLM and validate the response. Retries up to MAX_RETRIES times."""

    user_msg = (
        f"Job Title: {job['job_title']}\n\nJob Description:\n{job['description']}"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL_VERSION,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            validated = JobEnrichmentSchema(**parsed)
            return validated

        except ValidationError as e:
            log.warning(
                f"Attempt {attempt}/{MAX_RETRIES} — Pydantic validation failed for {job['job_id']}: {e}"
            )
        except json.JSONDecodeError as e:
            log.warning(
                f"Attempt {attempt}/{MAX_RETRIES} — JSON decode failed for {job['job_id']}: {e}"
            )
        except Exception as e:
            log.warning(
                f"Attempt {attempt}/{MAX_RETRIES} — Unexpected error for {job['job_id']}: {e}"
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    log.error(f"All {MAX_RETRIES} attempts failed for {job['job_id']} — skipping")
    return None


def write_row(
    cur: snowflake.connector.cursor.SnowflakeCursor,
    job: dict,
    validated: JobEnrichmentSchema,
) -> None:
    cur.execute(
        INSERT_QUERY,
        (
            job["job_id"],
            job["source"],
            validated.inferred_seniority,
            validated.is_title_inflated,
            validated.inflation_reasoning,
            validated.role_archetype,
            validated.work_focus,
            json.dumps(validated.tech_stack_required),
            json.dumps(validated.tech_stack_preferred),
            json.dumps(validated.paradigms_required),
            json.dumps(validated.paradigms_preferred),
            validated.degree_requirement,
            validated.years_required_min,
            validated.years_required_max,
            validated.salary_min,
            validated.salary_max,
            validated.confidence_score,
            datetime.now(timezone.utc).isoformat(),
            MODEL_VERSION,
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> bool:
    log.info("=== LLM Enricher starting ===")

    system_prompt = load_prompt()
    log.info(f"Loaded prompt from {PROMPT_PATH} ({len(system_prompt)} chars)")

    client = OpenAI(api_key=os.environ["OPENAI_KEY"])
    conn = get_snowflake_connection()

    jobs = fetch_unenriched_jobs(conn)

    if not jobs:
        log.info("No unenriched jobs found — nothing to do")
        conn.close()
        return True

    cur = conn.cursor()
    succeeded = 0
    failed = 0
    skipped = 0

    for i, job in enumerate(jobs, start=1):
        job_id = job["job_id"]
        source = job["source"]

        if not job.get("description"):
            log.warning(
                f"[{i}/{len(jobs)}] SKIP — empty description | {source} | {job_id}"
            )
            skipped += 1
            continue

        validated = enrich_job(client, system_prompt, job)

        if validated is None:
            failed += 1
            continue

        try:
            write_row(cur, job, validated)
            succeeded += 1
            log.info(
                f"[{i}/{len(jobs)}] OK — {source} | {job_id} | "
                f"archetype={validated.role_archetype} | "
                f"seniority={validated.inferred_seniority} | "
                f"confidence={validated.confidence_score:.2f}"
            )
        except Exception as e:
            log.error(f"[{i}/{len(jobs)}] WRITE FAILED — {source} | {job_id} | {e}")
            failed += 1

    cur.close()
    conn.close()

    log.info("=== LLM Enricher complete ===")
    log.info(f"    Succeeded : {succeeded}")
    log.info(f"    Failed    : {failed}")
    log.info(f"    Skipped   : {skipped}")
    log.info(f"    Total     : {len(jobs)}")

    if failed > 0:
        log.error(f"{failed} jobs failed enrichment — check logs above")
        return False

    return True
