# ingestion/builtin_client.py
#
# Scrapes job listings from Built In NYC using a two-stage approach:
#
#   Stage 1 — Crawl: paginate through the search index, extract job
#             URLs and titles from the JSON-LD ItemList schema block.
#             Stops when a page returns no JSON-LD (past last page).
#
#   Stage 2 — Scrape: fetch each individual job page, extract the
#             JobPosting schema block raw and untouched.
#
# Returns a flat list of Snowflake-ready row dicts:
#     { "SOURCE": str, "RAW_PAYLOAD": dict, "INGESTED_AT": str }
#
# No parsing or flattening of nested fields — that's dbt's job.

import logging
import random
import time
import json
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Constants
# ------------------------------------------------------------------ #

SEARCH_URL = (
    "https://www.builtinnyc.com/jobs/entry-level/junior/mid-level"
    "?search=Data+Analyst"
    "&daysSinceUpdated=3"
    "&city=New+York+City"
    "&state=New+York"
    "&country=USA"
    "&allLocations=true"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;"
    "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.builtinnyc.com/",
}

MAX_PAGES = 10  # hard ceiling; early exit handles real stop
MIN_CRAWL_DELAY = 1.5  # seconds between index page requests
MAX_CRAWL_DELAY = 3.5
MIN_SCRAPE_DELAY = 2.0  # seconds between job page requests
MAX_SCRAPE_DELAY = 4.5
REQUEST_TIMEOUT = 15  # seconds


class BuiltInNYCScraper:
    """
    Scraper for Built In NYC job listings.

    Usage:
        scraper = BuiltInNYCScraper()
        rows = scraper.fetch_all()

    On each run the scraper:
      1. Crawls the search index pages to collect job URLs
      2. Scrapes each job page to extract the raw JobPosting schema
      3. Returns Snowflake-ready rows with RAW_PAYLOAD untouched

    Delays between requests are randomized to avoid rate limiting.
    A failure on any individual job page is logged and skipped —
    the scraper will not abort the full run for a single bad URL.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._ingested_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def fetch_all(self) -> list[dict]:
        """
        Run the full crawl → scrape pipeline.
        Returns a flat list of Snowflake-ready row dicts.
        """
        # Stage 1 — crawl index pages
        job_records = self._crawl_index()
        log.info(f"Crawl complete — {len(job_records)} unique job URLs discovered.")

        if not job_records:
            log.warning("No job URLs found — returning empty list.")
            return []

        # Stage 2 — scrape individual job pages
        scraped = self._scrape_jobs(job_records)
        log.info(
            f"Scrape complete — {len(scraped)} succeeded, "
            f"{len(job_records) - len(scraped)} failed/skipped."
        )

        return self._to_snowflake_rows(scraped)

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _crawl_index(self) -> list[dict]:
        """
        Paginate through search index pages and collect job URLs + titles.
        Stops when a page returns no JSON-LD block (past the last real page).
        Deduplicates by URL in case the same job appears on multiple pages.
        """
        discovered: list[dict] = []
        seen_urls: set[str] = set()

        for page_num in range(1, MAX_PAGES + 1):
            url = SEARCH_URL if page_num == 1 else f"{SEARCH_URL}&page={page_num}"

            if page_num > 1:
                delay = random.uniform(MIN_CRAWL_DELAY, MAX_CRAWL_DELAY)
                log.info(f"Crawl: sleeping {delay:.2f}s before page {page_num}...")
                time.sleep(delay)

            log.info(f"Crawl: fetching index page {page_num}...")

            try:
                response = self._session.get(url, timeout=REQUEST_TIMEOUT)

                if response.status_code != 200:
                    log.warning(
                        f"Crawl: page {page_num} returned "
                        f"HTTP {response.status_code} — skipping."
                    )
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                script_tag = soup.find("script", type="application/ld+json")

                # No JSON-LD means we've gone past the last real page
                if not script_tag:
                    log.info(
                        f"Crawl: no JSON-LD on page {page_num} — " f"end of results."
                    )
                    break

                payload = json.loads(script_tag.string)
                graph = payload.get("@graph", [])
                item_list = next(
                    (item for item in graph if item.get("@type") == "ItemList"), None
                )

                # JSON-LD exists but job list is empty — also past last page
                if not item_list or not item_list.get("itemListElement"):
                    log.info(
                        f"Crawl: empty ItemList on page {page_num} — "
                        f"end of results."
                    )
                    break

                new_count = 0
                for el in item_list["itemListElement"]:
                    job_url = el.get("url")
                    job_title = el.get("name")

                    if job_url and job_url not in seen_urls:
                        seen_urls.add(job_url)
                        discovered.append(
                            {
                                "title": job_title,
                                "url": job_url,
                            }
                        )
                        new_count += 1

                log.info(
                    f"Crawl: page {page_num} — {new_count} new jobs "
                    f"(total: {len(discovered)})."
                )

            except Exception as e:
                log.error(f"Crawl: error on page {page_num}: {e}", exc_info=True)

        return discovered

    def _scrape_jobs(self, job_records: list[dict]) -> list[dict]:
        """
        Fetch each job page and extract the raw JobPosting schema node.
        Failed pages are logged and skipped — they do not abort the run.
        """

        scraped: list[dict] = []

        for i, record in enumerate(job_records):
            url = record["url"]
            delay = random.uniform(MIN_SCRAPE_DELAY, MAX_SCRAPE_DELAY)

            log.info(
                f"Scrape [{i+1}/{len(job_records)}]: " f"sleeping {delay:.2f}s ..."
            )
            time.sleep(delay)

            log.info(f"Scrape [{i+1}/{len(job_records)}]: {url}")

            try:
                response = self._session.get(url, timeout=REQUEST_TIMEOUT)

                if response.status_code != 200:
                    log.warning(f"  HTTP {response.status_code} — skipping.")
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                script_tag = soup.find("script", type="application/ld+json")

                if not script_tag:
                    log.warning("  No JSON-LD found — skipping.")
                    continue

                raw = json.loads(script_tag.string)
                graph = raw.get("@graph", [])
                job_posting = next(
                    (node for node in graph if node.get("@type") == "JobPosting"), None
                )

                if not job_posting:
                    log.warning("  No JobPosting node — skipping.")
                    continue

                scraped.append(
                    {
                        "source_url": url,
                        "crawl_title": record["title"],
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "job_posting": job_posting,
                    }
                )

                log.info(f"  ✓ {job_posting.get('title', 'N/A')}")

            except Exception as e:
                log.error(f"  Error scraping {url}: {e}", exc_info=True)

        return scraped

    def _to_snowflake_rows(self, scraped: list[dict]) -> list[dict]:
        """
        Wrap each scraped job into the standard Snowflake landing row shape.

        RAW_PAYLOAD contains:
          - Scraper metadata: source_url, crawl_title, scraped_at
          - Full raw JobPosting node spread in, all nested dicts intact
            (hiringOrganization, jobLocation, baseSalary, etc.)
          - dbt handles all flattening downstream via dot notation:
            RAW_PAYLOAD:hiringOrganization:name::string
            RAW_PAYLOAD:baseSalary:value:minValue::integer
            etc.
        """
        return [
            {
                "SOURCE": "builtin",
                "RAW_PAYLOAD": {
                    "source_url": record["source_url"],
                    "crawl_title": record["crawl_title"],
                    "scraped_at": record["scraped_at"],
                    **record["job_posting"],
                },
                "INGESTED_AT": self._ingested_at,
            }
            for record in scraped
        ]
