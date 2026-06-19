# ingestion/jsearch_client.py
#
# Fetches job listings from the JSearch API (via RapidAPI).
#
# Design decisions:
#   - One public method: fetch_all(). Accepts a list of queries and
#     loops over them, paginating each with cursor logic.
#   - Hard page cap per query (MAX_PAGES_PER_QUERY) prevents a runaway
#     cursor loop from consuming the monthly credit budget.
#   - Each page is fetched with retry logic (up to MAX_RETRIES attempts
#     with exponential backoff) to handle transient 5xx errors gracefully.
#   - Returns a flat list of Snowflake-ready row dicts:
#       { "SOURCE": str, "RAW_PAYLOAD": dict, "INGESTED_AT": str }
#     The orchestrator does not need to know anything about JSearch
#     internals — it just receives rows and passes them to the loader.

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

BASE_URL = "https://jsearch.p.rapidapi.com/search-v2"
RAPIDAPI_HOST = "jsearch.p.rapidapi.com"

# 200 credits/month, runs every 3 days (~10 runs/month),
# 3 queries per run → 6 pages per query = 180 credits max.
# Leaves 20 for debugging/reruns.
# MAX_PAGES_PER_QUERY = 6
# MAX_PAGES_PER_QUERY = 1  # for testing
MAX_PAGES_PER_QUERY = 20  # for data scientist backfill

RESULTS_PER_PAGE = 10  # JSearch default; not configurable on free tier
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds; doubles on each retry (2, 4, 8)
REQUEST_TIMEOUT = 30  # seconds

RELEVANT_TITLE_PATTERN = re.compile(
            r'data analyst|data engineer|analytics engineer|data scientist',
            re.IGNORECASE
        )


class JSearchClient:
    """
    Client for the JSearch API.

    Usage:
        client = JSearchClient()
        rows = client.fetch_all(
            queries=["Data Analyst in New York", "Analytics Engineer in New York", "Data Engineer in New York",],
            date_posted="3days",
        )
    """

    def __init__(self) -> None:
        api_key = os.getenv("RAPIDAPI_KEY")
        if not api_key:
            raise EnvironmentError(
                "RAPIDAPI_KEY is not set. Add it to your .env file or "
                "GitHub Actions secrets."
            )
        self._headers = {
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": RAPIDAPI_HOST,
            "Content-Type": "application/json",
        }
        self._ingested_at = datetime.now(timezone.utc).isoformat()
        self._last_response: requests.Response | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_usage_stats(self) -> dict:
        """
        Return rate-limit headers from the most recent API response.

        Returns an empty dict if no request has been made yet.
        Header values are strings as returned by the API.
        """
        if self._last_response is None:
            return {}
        h = self._last_response.headers
        return {
            "requests_remaining": h.get("x-ratelimit-requests-remaining"),
            "requests_limit": h.get("x-ratelimit-requests-limit"),
            "requests_reset": h.get("x-ratelimit-requests-reset"),
        }

    def fetch_all(
        self,
        queries: list[str],
        date_posted: str = "month",
    ) -> list[dict]:
        """
        Fetch jobs for every query in the list, paginating each with
        cursor logic until results are exhausted or MAX_PAGES_PER_QUERY
        is reached.

        Returns a flat list of Snowflake-ready row dicts.
        """
        all_rows: list[dict] = []

        for query in queries:
            log.info(f"Starting fetch for query: {query!r}")
            try:
                rows = self._fetch_query(query=query, date_posted=date_posted)
                all_rows.extend(rows)
                log.info(
                    f"Query {query!r} complete — "
                    f"{len(rows)} jobs collected across "
                    f"up to {MAX_PAGES_PER_QUERY} pages."
                )
            except Exception as e:
                # Log and continue — one bad query shouldn't abort the others.
                log.error(f"Query {query!r} failed: {e}", exc_info=True)

        # filter to relevant data roles by title before dedup
        pre_filter = len(all_rows)
        all_rows = [
            row for row in all_rows
            if RELEVANT_TITLE_PATTERN.search(row["RAW_PAYLOAD"].get("job_title", ""))
        ]
        log.info(f"Title filter: {pre_filter} → {len(all_rows)} rows ({pre_filter - len(all_rows)} dropped)")

        log.info(f"fetch_all complete — {len(all_rows)} total rows before dedup.")

        # deduplicate by job_id across queries — same job can appear in multiple query results
        seen_ids: set[str] = set()
        deduped_rows: list[dict] = []
        for row in all_rows:
            job_id = row["RAW_PAYLOAD"].get("job_id")
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                deduped_rows.append(row)

        log.info(f"fetch_all complete — {len(deduped_rows)} rows after dedup ({len(all_rows) - len(deduped_rows)} duplicates removed).")
        return deduped_rows

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _fetch_query(
        self,
        query: str,
        date_posted: str,
    ) -> list[dict]:
        """
        Paginate a single query using cursor logic.
        Stops when:
          - the API returns an empty jobs list, or
          - the API returns no cursor (last page), or
          - MAX_PAGES_PER_QUERY is reached.
        """
        rows: list[dict] = []
        cursor: str | None = None
        page = 0

        while page < MAX_PAGES_PER_QUERY:
            page += 1
            log.info(
                f"  Fetching page {page}/{MAX_PAGES_PER_QUERY} "
                f"for query {query!r} ..."
            )

            data = self._fetch_page(
                query=query,
                date_posted=date_posted,
                cursor=cursor,
            )

            jobs = data.get("jobs", [])
            if not jobs:
                log.info(f"  Empty page returned at page {page} — stopping.")
                break

            rows.extend(self._to_snowflake_rows(jobs, query))
            log.info(
                f"  Page {page}: {len(jobs)} jobs added "
                f"(running total: {len(rows)})."
            )

            cursor = data.get("cursor")
            if not cursor:
                log.info(f"  No cursor returned — reached last page.")
                break

        if page == MAX_PAGES_PER_QUERY:
            log.warning(
                f"  Hit MAX_PAGES_PER_QUERY ({MAX_PAGES_PER_QUERY}) for "
                f"query {query!r}. There may be more results. Consider "
                f"increasing the limit or tightening the date window."
            )

        return rows

    def _fetch_page(
        self,
        query: str,
        date_posted: str,
        cursor: str | None,
    ) -> dict[str, Any]:
        """
        Make one API request with retry/backoff.
        Returns the contents of response["data"].
        Raises on non-recoverable errors.
        """
        params: dict[str, str] = {
            "query": query,
            "num_pages": "1",
            "country": "us",
            "date_posted": date_posted,
            "employment_types": "FULLTIME",
            "exclude_job_publishers": (
                "Talent.com,Learn4Good,JobLeads,BeBee,WhatJobs,Jobilize,"
                "Jooble,Adzuna,Ladders,Snagajob,Institute Of Data Jobs,"
                "Tech Engineer Jobs,Allied-IT Jobs,United States Jobs Expertini,"
                "Trigyn Technologies,Trigyn,Resume-Library.com,Sign In"
            ),
        }
        if cursor:
            params["cursor"] = cursor

        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(
                    BASE_URL,
                    headers=self._headers,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                self._last_response = response  # captured for get_usage_stats()

                # 429 — rate limited; back off and retry
                if response.status_code == 429:
                    wait = RETRY_BACKOFF_BASE**attempt
                    log.warning(
                        f"  429 rate limited on attempt {attempt}. "
                        f"Retrying in {wait}s ..."
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()

                body = response.json()

                if body.get("status") != "OK":
                    raise ValueError(
                        f"API returned non-OK status: {body.get('error', body)}"
                    )

                return body.get("data", {})

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as e:
                wait = RETRY_BACKOFF_BASE**attempt
                log.warning(
                    f"  Network error on attempt {attempt}: {e}. "
                    f"Retrying in {wait}s ..."
                )
                last_exception = e
                time.sleep(wait)

            except requests.exceptions.HTTPError as e:
                # 4xx errors (except 429 handled above) are not retryable
                log.error(f"  HTTP {e.response.status_code} — not retrying.")
                raise

        raise RuntimeError(
            f"All {MAX_RETRIES} attempts failed for query {query!r}. "
            f"Last error: {last_exception}"
        )

    def _to_snowflake_rows(
        self,
        jobs: list[dict],
        query: str,
    ) -> list[dict]:
        """
        Wrap each raw job dict into the standard Snowflake landing row shape:
            SOURCE       — which client/query produced this row
            RAW_PAYLOAD  — the complete raw job dict, untouched
            INGESTED_AT  — ISO 8601 UTC timestamp for this pipeline run
        """
        return [
            {
                "SOURCE": f"jsearch:{query.replace(' in New York', '')}",
                "RAW_PAYLOAD": job,
                "INGESTED_AT": self._ingested_at,
            }
            for job in jobs
        ]
