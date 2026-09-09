from url_retrieval import get_listing_urls
from html_retrival.html_retrieval import WebScraper
from html_parser.html_parser import parse_html

import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional

import requests
import pandas as pd

# get a list of all the postcodes
postcodes = pd.read_csv("data/VIC_postcodes.csv")

logger = logging.getLogger(__name__)

# Column name -> SQLite type, derived from the parsed listing dictionary.
# List-valued keys (external_links, top_4_features) are deliberately excluded.
PROPERTY_DETAILS_SCHEMA = {
    'id': 'INTEGER PRIMARY KEY',
    'url': 'TEXT',
    'latitude': 'REAL',
    'longitude': 'REAL',
    'street_address': 'TEXT',
    'suburb': 'TEXT',
    'postcode': 'TEXT',
    'state': 'TEXT',
    'activated_at': 'TEXT',
    'weekly_rent_number': 'INTEGER',
    'property_type': 'TEXT',
    'bedrooms': 'INTEGER',
    'bathrooms': 'INTEGER',
    'ensuites': 'INTEGER',
    'car_spaces': 'INTEGER',
    'furnished': 'INTEGER',
    'partially_furnished': 'INTEGER',
    'pets_allowed': 'INTEGER',
    'long_term_lease': 'INTEGER',
    'is_build_to_rent': 'INTEGER',
    'features': 'TEXT',
    'n_photos': 'INTEGER',
    'walkability_score': 'TEXT',
}


def setup_property_details_table(db_path: str) -> None:
    """
    Create the property_details table if it doesn't exist

    Args:
        db_path: Path to SQLite database (same one used by WebScraper)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        columns = ', '.join(
            f'{name} {dtype}' for name, dtype in PROPERTY_DETAILS_SCHEMA.items()
        )
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS property_details (
                {columns},
                added_at TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        logger.info(f"property_details table ready in {db_path}")
    except sqlite3.Error as e:
        logger.error(f"Database setup error for property_details: {e}")
        raise


def _encode_value(value):
    """Convert a parsed value into something SQLite can store"""
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, bool):
        return int(value)
    return value


def _sqlite_type(value) -> str:
    """Best-guess SQLite type for a value not covered by the schema"""
    if isinstance(value, bool) or isinstance(value, int):
        return 'INTEGER'
    if isinstance(value, float):
        return 'REAL'
    return 'TEXT'


def store_property_details(db_path: str, data: Optional[dict]) -> bool:
    """
    Store one parsed listing dictionary in the property_details table

    List values are skipped, dict values are stored as JSON text.

    Args:
        db_path: Path to SQLite database
        data: Dictionary returned by parse_html

    Returns:
        True if successful, False otherwise
    """
    if not data or not data.get('id'):
        logger.warning("Skipping listing with no id")
        return False

    row = {k: _encode_value(v) for k, v in data.items() if not isinstance(v, list)}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Add any columns this listing has that the table doesn't know about yet,
        # so unexpected fields aren't silently dropped.
        cursor.execute('PRAGMA table_info(property_details)')
        existing = {info[1] for info in cursor.fetchall()}
        for key in row:
            if key not in existing:
                logger.info(f"Adding new column to property_details: {key}")
                cursor.execute(
                    f'ALTER TABLE property_details '
                    f'ADD COLUMN {key} {_sqlite_type(data[key])}'
                )

        row['added_at'] = datetime.now()
        columns = ', '.join(row)
        placeholders = ', '.join('?' for _ in row)

        cursor.execute(f'''
            INSERT OR REPLACE INTO property_details ({columns})
            VALUES ({placeholders})
        ''', tuple(row.values()))

        conn.commit()
        conn.close()
        logger.info(f"Stored property details: {data['id']}")
        return True

    except sqlite3.Error as e:
        logger.error(f"Database error storing property {data.get('id')}: {e}")
        return False

DB_PATH = "data/properties_db/properties.db"
setup_property_details_table(DB_PATH)

# loop through each postcode and suburb
for row in postcodes.iloc:

    # get the suburb name and postocde
    suburb = row["Suburb"]
    postcode = row["Postcode"]

    # get the list of urls
    try:
        urls = get_listing_urls(suburb, postcode)
    except requests.exceptions.HTTPError:
        print(f"Skipping {suburb}, {postcode} due to HTTPError")
        continue

    # set up the scraper and a database
    scraper = WebScraper(db_path=DB_PATH)
    scraper.scrape_urls(urls, delay_between_requests=2.0)

    # for each url, scrape the html for the required attributes
    for url in urls:
        html_str = scraper.retrieve_page(url)
        data = parse_html(html_str)
        store_property_details(DB_PATH, data)

