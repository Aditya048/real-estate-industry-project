"""
Main orchestration script for scraping Victorian rental property listings.

Run from the repository root:
    python -m data_retrieval.scraping_pipeline.orchestrator

Writes SQLite + CSV export under data/properties_db/.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd
import requests

from property_database.property_database import PropertyDatabase

from .html_parser.html_parser import parse_html
from .html_retrieval.html_retrieval import WebScraper
from .url_retrieval.url_retrieval import get_listing_urls

DB_PATH = "data/properties_db/properties.db"
CSV_PATH = "data/properties_db/properties.csv"
POSTCODES_PATH = "data/VIC_postcodes.csv"
LOG_PATH = "data_retrieval/scraping_pipeline/scraper.log"


def main(limit: int | None = None) -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    postcodes = pd.read_csv(POSTCODES_PATH)
    if limit is not None:
        postcodes = postcodes.head(limit)

    property_db = PropertyDatabase(db_path=DB_PATH)
    logger.info("Starting property scrape. Current count: %s", property_db.get_count())

    scraper = WebScraper(db_path=DB_PATH)

    for row in postcodes.itertuples(index=False):
        suburb = row.Suburb
        postcode = row.Postcode

        logger.info("Processing %s, %s", suburb, postcode)

        try:
            urls = get_listing_urls(suburb, postcode)
        except requests.exceptions.HTTPError:
            logger.warning("Skipping %s, %s due to HTTPError", suburb, postcode)
            continue

        scraper.scrape_urls(urls, delay_between_requests=2.0)

        for url in urls:
            html_str = scraper.retrieve_page(url)
            if html_str:
                data = parse_html(html_str)
                property_db.save(data)

    export_path = property_db.export_csv(CSV_PATH)
    logger.info(
        "Scraping complete. Total stored: %s. CSV export: %s",
        property_db.get_count(),
        export_path,
    )
    print(f"Scraping complete. {property_db.get_count()} listings -> {export_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N suburbs (smoke test).",
    )
    args = parser.parse_args()
    main(limit=args.limit)
