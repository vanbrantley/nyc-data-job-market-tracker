# run_ingestion.py — Ingestion Orchestrator
# Triggered every 3 days by GitHub Actions cron.
# Runs all ingestion sources independently — a failure in one
# logs the error and allows the others to continue, but the overall
# run exits with code 1 so GitHub Actions fires a failure notification.

import logging
import sys
from datetime import datetime, timezone

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
                queries=[
                    "Data Analyst in New York",
                    "Analytics Engineer in New York",
                ],
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
                discovered_at_gte=discovered_at_gte
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
            results["builtin"] = builtin_scraper.fetch_all()
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
    # 5. Run summary
    # ------------------------------------------------------------------ #
    duration = (datetime.now(timezone.utc) - run_start).total_seconds()

    # API usage / credit stats — failures here must never affect the exit code.
    try:
        js = jsearch_client.get_usage_stats()
        if js:
            remaining = js.get("requests_remaining", "?")
            limit = js.get("requests_limit", "?")
            reset = js.get("requests_reset", "?")
            log.info(
                f"JSearch    — {remaining} of {limit} requests remaining "
                f"(resets in {reset}s)"
            )
        else:
            log.info("JSearch    — no usage stats available (no requests made).")
    except Exception as e:
        log.warning(f"Could not retrieve JSearch usage stats: {e}")

    try:
        ts = theirstack_client.get_usage_stats()
        total = ts.get("api_credits", "?")
        used = ts.get("used_api_credits", "?")
        remaining = (
            int(total) - int(used)
            if isinstance(total, int) and isinstance(used, int)
            else "?"
        )
        expiry = (ts.get("earliest_expiration") or "")[:10]  # trim to YYYY-MM-DD
        log.info(
            f"TheirStack — {remaining} of {total} API credits remaining "
            f"({used} used, expires {expiry})"
        )
    except Exception as e:
        log.warning(f"Could not retrieve TheirStack usage stats: {e}")

    jsearch_count = len(results["jsearch"]) if results["jsearch"] else 0
    theirstack_count = len(results["theirstack"]) if results["theirstack"] else 0
    builtin_count = len(results["builtin"]) if results["builtin"] else 0
    total_count = jsearch_count + theirstack_count + builtin_count
    log.info(
        f"Row counts — jsearch: {jsearch_count} | theirstack: {theirstack_count} "
        f"| builtin: {builtin_count} | total: {total_count}"
    )

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
