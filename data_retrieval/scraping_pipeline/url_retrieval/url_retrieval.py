"""
rent_listing_urls.py

Given a Melbourne suburb name and postcode, fetch the URLs of every current
rental listing for that suburb from rent.com.au.

Requires: pip install requests beautifulsoup4

Usage as a script:
    python rent_listing_urls.py "Wyndham Vale" 3024
    python rent_listing_urls.py "Melbourne" 3000 --state vic --out melbourne_3000.csv

Usage as a library:
    from rent_listing_urls import get_listing_urls
    urls = get_listing_urls("Wyndham Vale", 3024)

Notes on scope / responsible use:
- This targets rent.com.au's public suburb search pages, e.g.
  https://www.rent.com.au/properties/wyndham-vale-vic-3024
  These paths are NOT disallowed in rent.com.au's robots.txt (checked
  2026-09-06).
- A short delay is added between requests (REQUEST_DELAY_SECONDS) to avoid
  hammering their servers.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.rent.com.au"
REQUEST_DELAY_SECONDS = 1.5  # be polite - don't hammer their servers
RESULTS_PER_PAGE = 25  # observed on the site; used as a fallback

HEADERS = {
    # Identify the bot honestly - good practice per rent.com.au's own
    # "fair use" style expectations for automated tools.
    "User-Agent": "Mozilla/5.0 (compatible; MelbRentalResearchBot/1.0; "
                  "Uni data science project; contact: sjalfred@student.unimelb.edu.au)"
}

# Fallback regex, only used if BeautifulSoup finds no <a> tags matching -
# in case listing paths are embedded in a JSON blob rather than a plain
# anchor tag. Matches e.g. /property/1006-135-abeckett-st-melbourne-6477270
PROPERTY_PATH_RE = re.compile(r'/property/[a-z0-9][a-z0-9\-]*-\d{5,}')

# Matches "Showing 1 - 25 of 1710 rental properties"
TOTAL_COUNT_RE = re.compile(r"of\s+([\d,]+)\s+rental propert")


@dataclass
class SuburbQuery:
    """Suburb search parameters for rent.com.au listing pages."""

    suburb: str
    postcode: str
    state: str = "vic"

    @property
    def slug(self) -> str:
        """URL slug for this suburb, postcode, and state."""
        # "Wyndham Vale" -> "wyndham-vale"
        slug_suburb = re.sub(r"[^a-z0-9]+", "-", self.suburb.strip().lower()).strip("-")
        return f"{slug_suburb}-{self.state.lower()}-{self.postcode}"

    def page_url(self, page: int) -> str:
        """Build the suburb search URL for a 1-based page number."""
        if page <= 1:
            path = f"{BASE_URL}/properties/{self.slug}"
        else:
            path = f"{BASE_URL}/properties/{self.slug}/p{page}"
        return f"{path}?surrounding_suburbs=0"


def _fetch(url: str) -> str:
    """Fetch a page and return its HTML body."""
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def _extract_property_urls(html: str) -> list[str]:
    """Extract unique listing URLs from a suburb search page."""
    soup = BeautifulSoup(html, "html.parser")

    # Primary approach: find real <a> tags whose href points to a listing.
    # This is the robust way to do it - we're reading the actual parsed
    # HTML structure rather than guessing at string patterns.
    paths = [
        a["href"] for a in soup.find_all("a", href=True)
        if a["href"].startswith("/property/")
    ]

    # Fallback: if BeautifulSoup found no matching anchor tags, the paths
    # might be embedded in a JSON blob (e.g. a Next.js __NEXT_DATA__
    # script tag) rather than plain <a> tags. Regex over the raw text
    # catches that case too.
    if not paths:
        paths = PROPERTY_PATH_RE.findall(html)

    # De-duplicate while preserving order
    seen = set()
    urls = []
    for path in paths:
        full_url = BASE_URL + path if path.startswith("/") else path
        if full_url not in seen:
            seen.add(full_url)
            urls.append(full_url)
    return urls


def _extract_total_pages(html: str) -> int:
    """Infer total result pages from the 'Showing 1 - N of M' text."""
    match = TOTAL_COUNT_RE.search(html)
    if not match:
        return 1
    total_listings = int(match.group(1).replace(",", ""))
    return max(1, math.ceil(total_listings / RESULTS_PER_PAGE))


def get_listing_urls(suburb: str, postcode: str, state: str = "vic", verbose: bool = True) -> list[str]:
    """Return every current rental listing URL for a suburb and postcode.

    Args:
        suburb: Suburb name.
        postcode: Postcode.
        state: State abbreviation (default "vic").
        verbose: If True, print per-page progress.

    Returns:
        Deduplicated list of listing URLs.
    """
    query = SuburbQuery(suburb=suburb, postcode=str(postcode), state=state)

    first_page_html = _fetch(query.page_url(1))
    total_pages = _extract_total_pages(first_page_html)
    all_urls = _extract_property_urls(first_page_html)

    if verbose:
        print(f"[{query.slug}] page 1/{total_pages}: {len(all_urls)} listings so far")

    if not all_urls:
        # Something's off - dump a bit of diagnostic info instead of
        # silently returning an empty list.
        print("WARNING: no listing links found on page 1. Diagnostics:")
        print(f"  - Response length: {len(first_page_html)} characters")
        print(f"  - Contains '/property/': {'/property/' in first_page_html}")
        print(f"  - Contains '__NEXT_DATA__': {'__NEXT_DATA__' in first_page_html}")
        print("  - First 500 characters of response:")
        print(first_page_html[:500])

    for page in range(2, total_pages + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        html = _fetch(query.page_url(page))
        page_urls = _extract_property_urls(html)
        if not page_urls:
            # Safety net: stop early if a page unexpectedly has no listings
            break
        all_urls.extend(page_urls)
        if verbose:
            print(f"[{query.slug}] page {page}/{total_pages}: "
                  f"{len(page_urls)} listings ({len(all_urls)} total so far)")

    # Final de-dup in case a listing appeared on two pages (can happen if
    # results shift between page loads)
    return list(dict.fromkeys(all_urls))


def main():
    """CLI entry point for fetching listing URLs for one suburb."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suburb", help='Suburb name, e.g. "Wyndham Vale"')
    parser.add_argument("postcode", help="Postcode, e.g. 3024")
    parser.add_argument("--state", default="vic", help="State abbreviation (default: vic)")
    parser.add_argument("--out", default=None, help="Optional CSV file to save URLs to")
    args = parser.parse_args()

    urls = get_listing_urls(args.suburb, args.postcode, args.state)

    print(f"\nFound {len(urls)} current listings for {args.suburb} {args.postcode}:")
    for url in urls:
        print(url)

    if args.out:
        with open(args.out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["listing_url"])
            for url in urls:
                writer.writerow([url])
        print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
