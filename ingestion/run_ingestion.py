# run_ingestion.py — Ingestion Orchestrator
# Triggered every 3 days by GitHub Actions cron.
# Runs all ingestion sources independently — a failure in one
# logs the error and allows the others to continue, but the overall
# run exits with code 1 so GitHub Actions fires a failure notification.

import logging
import sys
from datetime import datetime, timezone, timedelta

from ingestion.jsearch_client import JSearchClient
from ingestion.theirstack_client import TheirStackClient
from ingestion.builtin_client import BuiltInNYCScraper
from infra.snowflake_client import SnowflakeLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("orchestrator")

JSEARCH_QUERIES = [
    "Data Analyst in New York",
    "Analytics Engineer in New York",
    "Data Engineer in New York",
    "Data Scientist in New York",
]

THEIRSTACK_CONFIGS = [
    {
        "label": "Data Analyst",
        "job_title_pattern_or": ["(?i)data analyst"],
    },
    {
        "label": "Analytics Engineer",
        "job_title_pattern_or": ["(?i)analytics engineer"],
    },
    {
        "label": "Data Engineer",
        "job_title_pattern_or": ["(?i)data engineer"],
    },
    {
        "label": "Data Scientist",
        "job_title_pattern_or": ["(?i)data scientist"],
    },
]

BUILTIN_CONFIGS = [
    {"label": "Data Analyst", "search_term": "Data+Analyst"},
    {"label": "Analytics Engineer", "search_term": "Analytics+Engineer"},
    {"label": "Data Engineer", "search_term": "Data+Engineer"},
    {"label": "Data Scientist", "search_term": "Data+Scientist"},
]

def calc_credits_this_run(
    cumulative: int | None,
    remaining: int | None,
    prev: dict | None,
    ) -> int | None:
    """
    Calculate credits spent on this run.
    - If no previous row exists: this is the first tracked run,
    cumulative IS the per-run cost (billing period just started)
    - If remaining > prev remaining: billing period reset,
    treat cumulative as per-run cost for this first run of new window
    - Otherwise: diff cumulative from previous
    """
    if cumulative is None:
        return 0
    if prev is None:
        return cumulative
    if remaining is not None and prev["credits_remaining"] is not None:
        if remaining > prev["credits_remaining"]:
            # window reset — cumulative starts fresh
            return cumulative
    prev_cumulative = prev.get("credits_used_cumulative")
    if prev_cumulative is not None:
        return cumulative - prev_cumulative
    return cumulative


def run_pipeline() -> bool:
    """
    Runs all ingestion sources and loads results to Snowflake.
    Returns True if every source succeeded, False if any source failed.
    """
    run_start = datetime.now(timezone.utc)
    log.info(f"Pipeline run starting at {run_start.isoformat()}")

    # Instantiate all clients up front so they remain in scope for the
    # run summary (usage stats) at the end of the function.
    jsearch_client = JSearchClient()
    theirstack_client = TheirStackClient()
    builtin_scraper = BuiltInNYCScraper()

    results: dict[str, list[dict] | None] = {
        "jsearch": None,
        "theirstack": None,
        "builtin": None,
    }
    failures: list[str] = []

    with SnowflakeLoader() as loader:
        # ------------------------------------------------------------------ #
        # 1. JSearch — collect then immediately load
        # ------------------------------------------------------------------ #
        try:
            results["jsearch"] = jsearch_client.fetch_all(
                queries=JSEARCH_QUERIES,
                date_posted="3days",
            )
            log.info(f"JSearch — {len(results['jsearch'])} rows collected.")
        except Exception as e:
            log.error(f"JSearch source FAILED: {e}", exc_info=True)
            failures.append("jsearch")

        try:
            if results["jsearch"]:
                load_results = loader.load(results["jsearch"])
                for table, count in load_results.items():
                    log.info(f"  {table}: {count} rows inserted.")
            else:
                log.warning("JSearch — no rows to load, skipping Snowflake write.")
        except Exception as e:
            log.error(f"JSearch Snowflake load FAILED: {e}", exc_info=True)
            failures.append("jsearch_snowflake")

        # ------------------------------------------------------------------ #
        # 2. TheirStack — collect then immediately load
        # ------------------------------------------------------------------ #
        try:
            discovered_at_gte = None
            try:
                discovered_at_gte = loader.get_theirstack_high_water_mark()
            except Exception as e:
                log.warning(
                    f"Could not fetch TheirStack high-water mark: {e}. "
                    f"Falling back to full 7-day window."
                )

            results["theirstack"] = theirstack_client.fetch_all(
                configs=THEIRSTACK_CONFIGS,
                discovered_at_gte=discovered_at_gte,
            )
            log.info(f"TheirStack — {len(results['theirstack'])} rows collected.")
        except Exception as e:
            log.error(f"TheirStack source FAILED: {e}", exc_info=True)
            failures.append("theirstack")

        try:
            if results["theirstack"]:
                load_results = loader.load(results["theirstack"])
                for table, count in load_results.items():
                    log.info(f"  {table}: {count} rows inserted.")
            else:
                log.warning("TheirStack — no rows to load, skipping Snowflake write.")
        except Exception as e:
            log.error(f"TheirStack Snowflake load FAILED: {e}", exc_info=True)
            failures.append("theirstack_snowflake")

        # ------------------------------------------------------------------ #
        # 3. Built In NYC — collect then immediately load
        # ------------------------------------------------------------------ #
        try:
            results["builtin"] = builtin_scraper.fetch_all(configs=BUILTIN_CONFIGS)
            log.info(f"Built In NYC — {len(results['builtin'])} rows collected.")
        except Exception as e:
            log.error(f"Built In NYC source FAILED: {e}", exc_info=True)
            failures.append("builtin")

        try:
            if results["builtin"]:
                load_results = loader.load(results["builtin"])
                for table, count in load_results.items():
                    log.info(f"  {table}: {count} rows inserted.")
            else:
                log.warning("Built In NYC — no rows to load, skipping Snowflake write.")
        except Exception as e:
            log.error(f"Built In NYC Snowflake load FAILED: {e}", exc_info=True)
            failures.append("builtin_snowflake")

    # ------------------------------------------------------------------ #
    # 4. Run summary
    # ------------------------------------------------------------------ #
    duration = (datetime.now(timezone.utc) - run_start).total_seconds()

    jsearch_count = len(results["jsearch"]) if results["jsearch"] else 0
    theirstack_count = len(results["theirstack"]) if results["theirstack"] else 0
    builtin_count = len(results["builtin"]) if results["builtin"] else 0
    total_count = jsearch_count + theirstack_count + builtin_count

    if failures and total_count == 0:
        status = "failure"
    elif failures:
        status = "partial"
    else:
        status = "success"

    run_id = run_start.isoformat()
    api_usage_rows = []

    try:
        with SnowflakeLoader() as tracking_loader:

            # Fetch prev usage for both sources before building api_usage_rows
            prev_jsearch = tracking_loader.get_prev_api_usage("jsearch")
            prev_theirstack = tracking_loader.get_prev_api_usage("theirstack")

            # JSearch usage stats
            try:
                js = jsearch_client.get_usage_stats()
                if js:
                    remaining = int(js.get("requests_remaining")) if js.get("requests_remaining") else None
                    limit = int(js.get("requests_limit")) if js.get("requests_limit") else None
                    reset_seconds = js.get("requests_reset")
                    reset_date = (
                        (run_start + timedelta(seconds=int(reset_seconds))).isoformat()
                        if reset_seconds else None
                    )
                    cumulative = (limit - remaining) if (limit and remaining) else None
                    credits_this_run = calc_credits_this_run(cumulative, remaining, prev_jsearch)
                    log.info(
                        f"JSearch    — {remaining} of {limit} requests remaining "
                        f"(resets in {reset_seconds}s)"
                    )
                    api_usage_rows.append({
                        "run_id": run_id,
                        "run_at": run_start,
                        "source": "jsearch",
                        "credits_remaining": remaining,
                        "credits_limit": limit,
                        "credits_used_cumulative": cumulative,
                        "credits_used_this_run": credits_this_run,
                        "reset_date": reset_date,
                    })
                else:
                    log.info("JSearch    — no usage stats available (no requests made).")
            except Exception as e:
                log.warning(f"Could not retrieve JSearch usage stats: {e}")

            # TheirStack usage stats
            try:
                ts = theirstack_client.get_usage_stats()
                total = ts.get("api_credits")
                used = ts.get("used_api_credits")
                remaining = (
                    int(total) - int(used)
                    if isinstance(total, int) and isinstance(used, int)
                    else None
                )
                expiry = (ts.get("earliest_expiration") or "")[:10]
                cumulative = int(used) if used else None
                credits_this_run = calc_credits_this_run(cumulative, remaining, prev_theirstack)
                log.info(
                    f"TheirStack — {remaining} of {total} API credits remaining "
                    f"({used} used, expires {expiry})"
                )
                api_usage_rows.append({
                    "run_id": run_id,
                    "run_at": run_start,
                    "source": "theirstack",
                    "credits_remaining": remaining,
                    "credits_limit": int(total) if total else None,
                    "credits_used_cumulative": cumulative,
                    "credits_used_this_run": credits_this_run,
                    "reset_date": expiry or None,
                })
            except Exception as e:
                log.warning(f"Could not retrieve TheirStack usage stats: {e}")

            log.info(
                f"Row counts — jsearch: {jsearch_count} | theirstack: {theirstack_count} "
                f"| builtin: {builtin_count} | total: {total_count}"
            )

            # Write pipeline tracking
            tracking_loader.write_pipeline_run(
                run_id=run_id,
                run_at=run_start,
                duration_seconds=duration,
                status=status,
                jsearch_rows=jsearch_count,
                theirstack_rows=theirstack_count,
                builtin_rows=builtin_count,
                total_rows=total_count,
            )
            if api_usage_rows:
                tracking_loader.write_api_usage(api_usage_rows)
            log.info("Pipeline tracking written to Snowflake.")

    except Exception as e:
        log.warning(f"Could not write pipeline tracking to Snowflake: {e}")

    if failures:
        log.error(
            f"Pipeline finished with failures in: {failures}. "
            f"Duration: {duration:.1f}s"
        )
        return False
    else:
        log.info(f"Pipeline finished successfully. Duration: {duration:.1f}s")
        return True


if __name__ == "__main__":
    success = run_pipeline()
    sys.exit(0 if success else 1)
