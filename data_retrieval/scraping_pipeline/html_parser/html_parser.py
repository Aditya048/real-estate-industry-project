import json
import re

from bs4 import BeautifulSoup

JSON_DECODER = json.JSONDecoder()
SIGNATURE = {
    "id", "bedrooms", "bathrooms", "suburb", "postcode",
    "weekly_rent_number", "latitude", "longitude", "property_type",
}

# Fields collected from each listing payload.
LISTING_KEYS = [
    "id", "url", "latitude", "longitude", "street_address", "suburb", "postcode",
    "state", "activated_at", "weekly_rent_number", "property_type", "bedrooms",
    "bathrooms", "ensuites", "car_spaces", "furnished", "partially_furnished",
    "pets_allowed", "long_term_lease", "is_build_to_rent", "features",
]


def flight_payload(soup):
    """Extract concatenated Next.js flight payload strings from script tags.

    Args:
        soup: BeautifulSoup document for a listing page.

    Returns:
        Joined flight payload text from matching script tags.
    """
    chunks = []
    for tag in soup.find_all("script"):
        txt = tag.string or ""
        if "__next_f.push" not in txt:
            continue
        m = re.search(r"__next_f\.push\((\[.*\])\)", txt, re.DOTALL)
        if not m:
            continue
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            chunks.append(arr[1])
    return "".join(chunks)


def get_listing(payload):
    """Find the property listing object inside a flight payload.

    Args:
        payload: Concatenated flight payload text.

    Returns:
        Listing dictionary matching enough SIGNATURE keys.

    Raises:
        ValueError: If no listing object is found.
    """
    for m in re.finditer(r'"property"\s*:', payload):
        try:
            obj, _ = JSON_DECODER.raw_decode(payload, payload.index("{", m.end() - 1))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and len(SIGNATURE & obj.keys()) >= 4:
            return obj
    raise ValueError(f"no listing found in {len(payload):,} chars of payload")


def parse_html(html_str):
    """Parse a listing HTML page into a flat attribute dictionary.

    Args:
        html_str: Raw HTML for a rent.com.au listing page.

    Returns:
        Dictionary of listing fields plus photo count and a few extras.
    """
    soup = BeautifulSoup(html_str, "html.parser")

    payload = flight_payload(soup)
    listing = get_listing(payload)

    record = {k: listing.get(k) for k in LISTING_KEYS}
    record["n_photos"] = len(listing.get("gallery") or [])
    record["external_links"] = listing.get("external_links")
    record["walkability_score"] = listing.get("walkability_score")
    record["top_4_features"] = listing.get("top_4_features")

    return record
