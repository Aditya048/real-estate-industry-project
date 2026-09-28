"""
Main orchestration script for scraping Victorian rental property listings.
"""


import requests
import pandas as pd
from .url_retrieval.url_retrieval import get_listing_urls
from .html_retrieval.html_retrieval import WebScraper
from .html_parser.html_parser import parse_html
import logging

from property_database.property_database import PropertyDatabase

# Configure logging
logging.basicConfig(
    filename='data_retrieval/scraping_pipeline/scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Load postcodes
postcodes = pd.read_csv("data/VIC_postcodes.csv")

# Initialize the database (this creates the table automatically)
DB_PATH = "data/properties_db/properties.db"
property_db = PropertyDatabase(db_path=DB_PATH)

logger.info(f"Starting property scrape. Current count: {property_db.get_count()}")

# Loop through each postcode and suburb
for row in postcodes.iloc:
    suburb = row["Suburb"]
    postcode = row["Postcode"]
    
    logger.info(f"Processing {suburb}, {postcode}")
    
    # Get the list of URLs
    try:
        urls = get_listing_urls(suburb, postcode)
    except requests.exceptions.HTTPError:
        logger.warning(f"Skipping {suburb}, {postcode} due to HTTPError")
        continue
    
    # Scrape all URLs for this suburb
    scraper = WebScraper(db_path=DB_PATH)
    scraper.scrape_urls(urls, delay_between_requests=2.0)
    
    # Parse and store each URL
    for url in urls:
        html_str = scraper.retrieve_page(url)
        if html_str:
            data = parse_html(html_str)
            property_db.save(data)  # ← That's it. One line per listing.

logger.info(f"Scraping complete. Total stored: {property_db.get_count()}")
