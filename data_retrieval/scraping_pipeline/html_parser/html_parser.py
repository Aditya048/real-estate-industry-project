# import the required modules
import json, re
from bs4 import BeautifulSoup

# decoder and signature
DEC = json.JSONDecoder()
SIGNATURE = {"id", "bedrooms", "bathrooms", "suburb", "postcode",
            "weekly_rent_number", "latitude", "longitude", "property_type"}

# keys that we want to collect from the html
keys = [
    "id", "url", "latitude", "longitude", "street_address", "suburb", "postcode",
    "state", "activated_at", "weekly_rent_number", "property_type", "bedrooms",
    "bathrooms", "ensuites", "car_spaces", "furnished", "partially_furnished",
    "pets_allowed", "long_term_lease", "is_build_to_rent", "features",
]

def flight_payload(soup):
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
    for m in re.finditer(r'"property"\s*:', payload):
        try:
            obj, _ = DEC.raw_decode(payload, payload.index("{", m.end() - 1))
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and len(SIGNATURE & obj.keys()) >= 4:
            return obj
    raise ValueError(f"no listing found in {len(payload):,} chars of payload")


"""
function takes input of a html string and parses it with
beautifulsoup, outputting a dictionary of key value pairs
with the attributes 
"""
def parse_html(html_str):
    soup = BeautifulSoup(html_str, "html.parser")

    payload = flight_payload(soup)
    listing = get_listing(payload)

    record = {k: listing.get(k) for k in keys}
    record["n_photos"] = len(listing.get("gallery") or [])
    record["external_links"] = listing.get("external_links")
    record["walkability_score"] = listing.get("walkability_score")
    record["top_4_features"] = listing.get("top_4_features")

    return record