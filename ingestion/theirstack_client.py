# ingestion/theirstack_client.py
#
# Fetches job listings from the TheirStack API.
#
# Two-stage architecture per search config:
#   Stage 1 — Free sweep: paginate through ALL matching jobs with
#             blur_company_data=True (zero credits). Deduplicate in
#             memory using a (title, location, tech_slugs) fingerprint.
#   Stage 2 — Paid fetch: request only the deduplicated IDs with
#             blur_company_data=False (1 credit per job). Capped at
#             PRODUCTION_LIMIT_PER_QUERY per archetype to ensure equal
#             representation across role types.
#
# Each archetype gets its own search config and its own cap, so no
# single role type can crowd out the others. This mirrors the per-query
# pattern used in jsearch_client.py for consistency.
#
# Returns a flat list of Snowflake-ready row dicts:
#     { "SOURCE": str, "RAW_PAYLOAD": dict, "INGESTED_AT": str }

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

BASE_URL = "https://api.theirstack.com/v1/jobs/search"

# 200 credits/month, runs every 3 days (~10 runs/month).
# 10 credits/query × 3 queries × 10 runs = 300 credits theoretical max.
# In practice each window won't saturate all three caps — total will
# be well under 200. Monitor usage and adjust if needed.
# PRODUCTION_LIMIT_PER_QUERY = 10
PRODUCTION_LIMIT_PER_QUERY = 40

FREE_SWEEP_PAGE_SIZE = 25  # max TheirStack returns per page
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds; doubles each retry (2, 4, 8)
REQUEST_TIMEOUT = 30  # seconds

# Shared filters applied to every search config
_BASE_FILTERS: dict[str, Any] = {
    "job_title_pattern_not": [
        "(?i)senior",
        "(?i)\\bsr\\b",
        "(?i)\\bii\\b",
        "(?i)\\biii\\b",
        "(?i)\\biv\\b",
        "(?i)lead",
        "(?i)principal",
        "(?i)staff",
        "(?i)manager",
        "(?i)director",
        "(?i)head of",
        "(?i)unpaid",
        "(?i)non.paid",
        "(?i)volunteer",
    ],
    "job_seniority_or": ["junior", "mid_level"],
    "job_country_code_or": ["US"],
    "job_location_pattern_or": [
        "(?i)^new york,",
        "(?i)new york city",
        "(?i)manhattan",
        "(?i)brooklyn",
    ],
    # "posted_at_max_age_days": 7,
    "posted_at_max_age_days": 30,
    "order_by": [{"field": "discovered_at", "desc": True}],
}

class TheirStackClient:
    """
    Client for the TheirStack API.

    Usage:
        client = TheirStackClient()
        rows = client.fetch_all()

    On each run, for each search config the client:
      1. Sweeps all matching pages for free to collect job IDs
      2. Deduplicates using (title, location, tech_slugs) fingerprint
      3. Fetches only the top PRODUCTION_LIMIT_PER_QUERY unique IDs
         via the paid endpoint
      4. Combines results across all configs and returns Snowflake rows

    Each archetype gets its own cap so no role type crowds out another.
    For incremental runs, pass discovered_at_gte to skip already-ingested
    jobs:
        rows = client.fetch_all(discovered_at_gte="2026-05-20T00:00:00Z")
    """

    def __init__(self) -> None:
        api_key = os.getenv("THEIRSTACK_KEY")
        if not api_key:
            raise EnvironmentError(
                "THEIRSTACK_KEY is not set. Add it to your .env file or "
                "GitHub Actions secrets."
            )
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        self._ingested_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_usage_stats(self) -> dict:
        """
        Fetch current credit balance from the TheirStack billing endpoint.
        """
        response = requests.get(
            "https://api.theirstack.com/v0/billing/credit-balance",
            headers=self._headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "api_credits": data.get("api_credits"),
            "used_api_credits": data.get("used_api_credits"),
            "earliest_expiration": data.get("earliest_expiration"),
        }

    def fetch_all(
        self,
        configs: list[dict],
        discovered_at_gte: str | None = None,
    ) -> list[dict]:
        """
        Run the full two-stage pipeline for each search config and
        return a combined flat list of Snowflake-ready rows.
        """
        all_rows: list[dict] = []

        for config in configs:
            label = config["label"]
            log.info(f"Starting fetch for config: {label!r}")
            try:
                rows = self._fetch_config(
                    config=config,
                    discovered_at_gte=discovered_at_gte,
                )
                all_rows.extend(rows)
                log.info(
                    f"Config {label!r} complete — {len(rows)} jobs collected."
                )
            except Exception as e:
                # Log and continue — one bad config shouldn't abort the others
                log.error(f"Config {label!r} failed: {e}", exc_info=True)

        log.info(f"fetch_all complete — {len(all_rows)} total rows.")
        return all_rows

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _fetch_config(
        self,
        config: dict[str, Any],
        discovered_at_gte: str | None = None,
    ) -> list[dict]:
        """
        Run the full two-stage pipeline for a single search config.
        """
        # Build the search body by merging base filters with config-specific ones
        search_body = {
            **_BASE_FILTERS,
            "job_title_pattern_or": config["job_title_pattern_or"],
        }

        # Stage 1 — free sweep
        all_jobs = self._free_sweep(
            search_body=search_body,
            discovered_at_gte=discovered_at_gte,
        )
        log.info(
            f"  [{config['label']}] Free sweep complete — "
            f"{len(all_jobs)} jobs collected."
        )

        # Stage 2 — deduplicate in memory
        unique_jobs = self._deduplicate(all_jobs)
        log.info(
            f"  [{config['label']}] Deduplication complete — "
            f"{len(unique_jobs)} unique jobs "
            f"({len(all_jobs) - len(unique_jobs)} duplicates removed)."
        )

        # Stage 3 — cap and extract IDs for paid fetch
        production_jobs = unique_jobs[:PRODUCTION_LIMIT_PER_QUERY]
        production_ids = [job["id"] for job in production_jobs]
        log.info(
            f"  [{config['label']}] Paying for {len(production_ids)} jobs "
            f"(cap={PRODUCTION_LIMIT_PER_QUERY}, "
            f"{len(unique_jobs) - len(production_ids)} left on table)."
        )

        if not production_ids:
            log.info(f"  [{config['label']}] No new jobs — skipping paid fetch.")
            return []

        # Stage 4 — paid fetch
        paid_jobs = self._paid_fetch(production_ids, label=config["label"])
        log.info(
            f"  [{config['label']}] Paid fetch complete — "
            f"{len(paid_jobs)} jobs returned."
        )

        return self._to_snowflake_rows(paid_jobs, label=config["label"])

    def _free_sweep(
        self,
        search_body: dict[str, Any],
        discovered_at_gte: str | None = None,
    ) -> list[dict]:
        """
        Paginate through ALL matching jobs with blur_company_data=True.
        Costs zero credits regardless of how many pages are fetched.
        """
        all_jobs: list[dict] = []
        page = 0

        while True:
            body: dict[str, Any] = {
                **search_body,
                "blur_company_data": True,
                "include_total_results": page == 0,
                "limit": FREE_SWEEP_PAGE_SIZE,
                "page": page,
            }

            if discovered_at_gte:
                body["discovered_at_gte"] = discovered_at_gte

            log.info(f"    Free sweep page {page} — zero credits.")
            data = self._post(body)

            if page == 0:
                total = data.get("metadata", {}).get("total_results", "?")
                log.info(f"    TheirStack reports {total} total matching jobs.")

            page_jobs = data.get("data", [])

            if not page_jobs:
                log.info("    Empty page — sweep complete.")
                break

            all_jobs.extend(page_jobs)
            log.info(
                f"    Page {page}: {len(page_jobs)} jobs collected "
                f"(running total: {len(all_jobs)})."
            )

            if len(page_jobs) < FREE_SWEEP_PAGE_SIZE:
                log.info("    Partial page — reached last page.")
                break

            page += 1

        return all_jobs

    def _deduplicate(self, jobs: list[dict]) -> list[dict]:
        """
        Remove duplicate listings using a deterministic fingerprint.
        Fingerprint: (job_title, short_location, frozenset(technology_slugs))
        """
        fingerprint_groups: dict[tuple, list[dict]] = defaultdict(list)

        for job in jobs:
            fingerprint = (
                job.get("job_title", "").lower().strip(),
                job.get("short_location", "").lower().strip(),
                frozenset(job.get("technology_slugs", [])),
            )
            fingerprint_groups[fingerprint].append(job)

        unique = [group[0] for group in fingerprint_groups.values()]

        dupes_found = len(jobs) - len(unique)
        if dupes_found:
            log.info(f"    {dupes_found} duplicate records removed.")

        return unique

    def _paid_fetch(self, job_ids: list[int], label: str = "") -> list[dict]:
        """
        Fetch full unblurred job records for the given IDs.
        Costs 1 credit per job returned.
        """
        body: dict[str, Any] = {
            "job_id_or": job_ids,
            "blur_company_data": False,
            "include_total_results": False,
            "limit": len(job_ids),
        }

        log.info(
            f"    [{label}] Paid fetch — requesting {len(job_ids)} jobs "
            f"({len(job_ids)} credits)."
        )

        data = self._post(body)
        jobs = data.get("data", [])

        if len(jobs) != len(job_ids):
            log.warning(
                f"    [{label}] Expected {len(job_ids)} jobs, got {len(jobs)}. "
                f"Some listings may have expired or been removed."
            )

        return jobs

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        POST to the TheirStack API with retry/backoff.
        Returns the full parsed response dict.
        Raises on non-recoverable errors.
        """
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(
                    BASE_URL,
                    json=body,
                    headers=self._headers,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 429:
                    wait = RETRY_BACKOFF_BASE**attempt
                    log.warning(
                        f"    429 rate limited on attempt {attempt}. "
                        f"Retrying in {wait}s ..."
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response.json()

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as e:
                wait = RETRY_BACKOFF_BASE**attempt
                log.warning(
                    f"    Network error on attempt {attempt}: {e}. "
                    f"Retrying in {wait}s ..."
                )
                last_exception = e
                time.sleep(wait)

            except requests.exceptions.HTTPError as e:
                log.error(f"    HTTP {e.response.status_code} — not retrying.")
                raise

        raise RuntimeError(
            f"All {MAX_RETRIES} attempts failed. "
            f"Last error: {last_exception}"
        )

    def _to_snowflake_rows(self, jobs: list[dict], label: str) -> list[dict]:
        return [
            {
                "SOURCE": f"theirstack:{label}",
                "RAW_PAYLOAD": job,
                "INGESTED_AT": self._ingested_at,
            }
            for job in jobs
        ]
