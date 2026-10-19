"""
add_amenity_distances.py

WHAT THIS SCRIPT DOES
----------------------
Takes rent.com.au listings dataset (data/properties.csv) and, for
every listing, computes ROUTE distance (actual road/path distance, not
straight-line) in kilometres to the nearest:

  - school               -> CAR routing
  - train station        -> CAR routing   (metro + regional combined)
  - tram stop             -> WALKING routing
  - bus stop               -> WALKING routing
  - park                  -> CAR routing
  - supermarket           -> CAR routing

Also adds a count-within-radius for schools, parks and supermarkets.

OUTPUT: a CSV with id, url, latitude, longitude, suburb, plus all the
amenity distance/count columns below - same shape as the earlier
straight-line version, just with route distances instead:

  nearest_school_km, school_count_2km,
  nearest_train_station_km,
  nearest_tram_stop_km, tram_stop_capped,
  nearest_bus_stop_km, bus_stop_capped,
  nearest_park_km, park_count_1km,
  nearest_supermarket_km, supermarket_count_1km

REQUIRES A LOCAL OSRM ROUTING SERVER - see OSRM_SETUP.md for one-time
setup. Expects a car-routing OSRM server on http://localhost:5000 and a
foot-routing OSRM server on http://localhost:5001.

WALKING-DISTANCE SKIP OPTIMIZATION (tram/bus only)
------------------------------------------------------
A tram stop 15km away isn't a useful "walking distance" feature no matter
how precisely we compute it - and since route distance can never be
SHORTER than straight-line distance, a property whose straight-line
distance to the nearest tram/bus stop already exceeds a threshold is
guaranteed to have a true route distance beyond that threshold too. So for
tram and bus specifically (both walking-routed), we do one cheap straight-
line nearest-neighbour pass first, skip the OSRM call entirely for
properties already beyond the threshold (TRAM_SKIP_THRESHOLD_KM=3.0,
BUS_SKIP_THRESHOLD_KM=5.0), and record them as a capped "at least this
far" value with a companion boolean column (tram_stop_capped /
bus_stop_capped) rather than pretending it's an exact figure. This does
NOT apply to school/train/park/supermarket - those are car-routed, where a
5km distance is still a completely normal, informative feature rather than
something to discard.

We deliberately did NOT add a separate "distance from CBD" shortcut for
this (an idea worth considering but not implementing): checking straight-
line distance to the ACTUAL nearest tram/bus stop is strictly more
accurate than a CBD-distance proxy (the tram network follows corridors,
not a uniform circle around the CBD) and costs the same to compute, making
a CBD-based heuristic redundant.


PERFORMANCE DESIGN
--------------------
A naive one-HTTP-call-per-property approach means up to 60,000 sequential
requests (10,000 properties x 6 amenity categories) - roughly 1.5+ hours
even at an optimistic 100ms/call, and local OSRM under many small /table/
calls is often slower than that per call. Three things fix this:

  1. BATCHING: OSRM's /table/ endpoint supports many sources and many
     destinations in a single call. Instead of 1 property + K candidates
     per request, we send ~BATCH_SIZE properties + the UNION of their
     shortlisted candidates as one request. This cuts request count by
     roughly BATCH_SIZE-fold.

  2. PARALLELISM: batches are dispatched through a thread pool
     (concurrent.futures), since a local OSRM server isn't rate-limited
     and can serve multiple connections concurrently.

  3. COORDINATE DEDUPLICATION: many rental listings share a building (same
     lat/long, different units). We compute route distances once per
     UNIQUE rounded coordinate, then broadcast the result back to every
     listing at that address - this can meaningfully cut work before
     batching/parallelism even come into play, and it's essentially free.


CORRECTNESS OF NEAREST-DISTANCE SEARCH
-----------------------------------------
nearest_route_km uses an expanding-radius search, not a fixed shortlist,
because that's the only way to GUARANTEE correctness rather than
approximate it: a road route can never be shorter than the straight-line
distance between two points, so if the best route distance found among
candidates within straight-line radius r is itself <= r, it is guaranteed
to be the true global nearest (anything outside r has straight-line
distance > r, hence route distance > r too). If not, r expands and we
retry - now batched and parallelised across whichever properties still
need it.

count_within_route_km doesn't need expansion: a straight-line prefilter of
radius exactly R is already a guaranteed superset of the true "route
distance <= R" answer, for the same reason.

Requires: pip install pandas numpy scikit-learn requests
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.neighbors import BallTree

EARTH_RADIUS_KM = 6371.0088

# paths and settings

PROPERTIES_PATH = "data/properties_db/properties.csv"
SCHOOLS_CSV_PATH = "data/amenity_data/dv346-schoollocations2023.csv"
GTFS_ZIP_PATH = "data/amenity_data/gtfs.zip"
OUTPUT_PATH = "data/amenity_data/listings_with_amenity_distances.csv"

SCHOOLS_CSV_URL = "https://www.education.vic.gov.au/Documents/about/research/datavic/dv346-schoollocations2023.csv"
GTFS_ZIP_URL = "https://opendata.transport.vic.gov.au/dataset/3f4e292e-7f8a-4ffe-831f-1953be0fe448/resource/fb152201-859f-4882-9206-b768060b50ad/download/gtfs.zip"

MELBOURNE_BBOX = (-38.50, 144.50, -37.50, 145.60)  # (south, west, north, east), for OSM Overpass queries

SCHOOL_RADIUS_KM = 2.0
PARK_RADIUS_KM = 2.0
SUPERMARKET_RADIUS_KM = 4.0
COUNT_MAX_CANDIDATES = 50  # per-property cap on candidates sent to the router when counting

# --- OSRM local server settings ---
OSRM_CAR_URL = "http://localhost:5000"
OSRM_FOOT_URL = "http://localhost:5001"
OSRM_REQUEST_TIMEOUT_SECONDS = 30  # bigger than before - batched requests do more work per call

# --- Expanding-radius search settings for nearest_route_km ---
INITIAL_SEARCH_RADIUS_KM = 2.0
MAX_SEARCH_RADIUS_KM = 30.0
MAX_SEARCH_ITERATIONS = 6

# --- Batching / parallelism settings ---
BATCH_SIZE = 40                 # properties per /table/ call
MAX_DESTINATIONS_PER_BATCH = 300  # safety cap on matrix width; batch is auto-split if exceeded
MAX_WORKERS = 8                 # concurrent requests to the local OSRM server

# --- Coordinate deduplication ---
COORD_ROUND_DECIMALS = 5  # ~1.1m precision - listings at the same building collapse to one lookup

# --- Walking-distance skip thresholds ---
# For WALKING-routed amenities only (tram, bus) - beyond these distances the
# amenity isn't realistically walkable anyway, so there's no point spending
# an OSRM call finding the exact route distance. Since route distance can
# never be SHORTER than straight-line distance, a straight-line distance
# already beyond the threshold guarantees the true route distance is too -
# so we can skip the routing call entirely and safely report "at least this
# far" instead. This does NOT apply to car-routed amenities (school, train,
# park, supermarket) - a school 5km away by car is still a normal, useful
# feature, not something to discard.
TRAM_SKIP_THRESHOLD_KM = 3.0
BUS_SKIP_THRESHOLD_KM = 5.0

# =============================================================================


# Download + load amenity data

def download_if_missing(url: str, dest_path: str) -> None:
    """
    Download a file from a URL if it does not already exist locally.
    
    If the destination file exists, this function returns early without
    downloading. Otherwise, it downloads the file with a progress indicator,
    writes it to a temporary .part file during download, and renames it to
    the final destination path upon successful completion. Parent directories
    are created as needed.
    
    Args:
        url: The URL to download from.
        dest_path: The local file path where the downloaded file should be saved.
    
    Returns:
        None
    
    Raises:
        requests.exceptions.RequestException: If the HTTP request fails.
        IOError: If file operations fail.
    """
    dest = Path(dest_path)
    if dest.exists():
        print(f"  Using cached file: {dest_path}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {url} -> {dest_path} ...")
    headers = {"User-Agent": "MAST30034-real-estate-project/1.0"}
    with requests.get(url, headers=headers, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total_bytes = int(resp.headers.get("content-length", 0))
        downloaded = 0
        tmp_path = dest.with_suffix(dest.suffix + ".part")
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total_bytes:
                    pct = 100 * downloaded / total_bytes
                    print(f"\r  {downloaded / 1e6:.1f} / {total_bytes / 1e6:.1f} MB ({pct:.0f}%)", end="")
        print()
        tmp_path.rename(dest)
    print(f"  Saved to {dest_path}")


def load_schools_csv(path: str) -> pd.DataFrame:
    """
    Load school location data from a CSV file and clean the coordinates.
    
    Reads a CSV file encoded in cp1252, renames X and Y columns to longitude
    and latitude, converts them to numeric types, and filters out rows with
    missing or zero-valued coordinates.
    
    Args:
        path: Path to the schools CSV file.
    
    Returns:
        A DataFrame with columns ['latitude', 'longitude'] containing valid
        school coordinate pairs.
    """
    df = pd.read_csv(path, encoding="cp1252")
    df = df.rename(columns={"X": "longitude", "Y": "latitude"})
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]
    return df[["latitude", "longitude"]].reset_index(drop=True)


def load_gtfs_stops(gtfs_zip_path: str, mode_folder: str, stations_only: bool = True) -> pd.DataFrame:
    """
    Load transit stop coordinates from a GTFS ZIP file.
    
    Extracts stop data from a GTFS (General Transit Feed Specification) archive,
    which may contain stops.txt directly or nested within mode-specific subdirectory
    ZIPs. Renames stop_lat and stop_lon columns to latitude and longitude, filters
    out missing coordinates, and optionally extracts only parent/station records
    (location_type == 1) if available.
    
    Args:
        gtfs_zip_path: Path to the GTFS ZIP file.
        mode_folder: The mode folder name within the ZIP (e.g., "2" for metro trains,
                     "1" for regional trains, "3" for trams, "4" for buses).
        stations_only: If True and a location_type column exists, extract only
                       records where location_type == 1 (parent stations). Defaults
                       to True.
    
    Returns:
        A DataFrame with columns ['latitude', 'longitude'] containing valid
        transit stop coordinate pairs.
    
    Raises:
        FileNotFoundError: If stops.txt cannot be found for the specified mode.
    """
    import zipfile

    with zipfile.ZipFile(gtfs_zip_path) as outer_zip:
        names = outer_zip.namelist()
        direct_matches = [n for n in names if n.startswith(f"{mode_folder}/") and n.endswith("stops.txt")]
        if direct_matches:
            with outer_zip.open(direct_matches[0]) as f:
                stops = pd.read_csv(f)
        else:
            inner_zip_matches = [n for n in names if n.startswith(f"{mode_folder}") and n.endswith(".zip")]
            if not inner_zip_matches:
                raise FileNotFoundError(
                    f"Could not find stops.txt for mode folder '{mode_folder}' inside {gtfs_zip_path}."
                )
            with outer_zip.open(inner_zip_matches[0]) as inner_bytes:
                with zipfile.ZipFile(inner_bytes) as inner_zip:
                    with inner_zip.open("stops.txt") as f:
                        stops = pd.read_csv(f)

    stops = stops.rename(columns={"stop_lat": "latitude", "stop_lon": "longitude"})
    stops = stops.dropna(subset=["latitude", "longitude"])
    if stations_only and "location_type" in stops.columns:
        parents = stops[stops["location_type"] == 1]
        stops = parents if len(parents) > 0 else stops
    return stops[["latitude", "longitude"]].reset_index(drop=True)


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
OVERPASS_QUERY_TIMEOUT_SECONDS = 180
OVERPASS_HTTP_TIMEOUT_SECONDS = 200
OVERPASS_MAX_RETRIES = 3


def fetch_osm_points(tag_filter: str, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    """
    Query OpenStreetMap (via Overpass API) for points matching a tag filter
    within a bounding box.
    
    Constructs and sends an Overpass QL query for nodes and ways matching
    the specified tag filter within the given bbox. Retries across multiple
    Overpass endpoints with exponential backoff if a request fails. Extracts
    center coordinates from the response and returns them as a DataFrame.
    
    Args:
        tag_filter: An OSM tag filter string (e.g., '["leisure"="park"]' or
                    '["shop"="supermarket"]').
        bbox: A tuple of (south, west, north, east) latitude/longitude bounds.
    
    Returns:
        A DataFrame with columns ['latitude', 'longitude'] containing all
        matched point coordinates.
    
    Raises:
        RuntimeError: If all retry attempts fail.
    """
    south, west, north, east = bbox
    query = f"""
    [out:json][timeout:{OVERPASS_QUERY_TIMEOUT_SECONDS}];
    (
      node{tag_filter}({south},{west},{north},{east});
      way{tag_filter}({south},{west},{north},{east});
    );
    out center;
    """
    headers = {"User-Agent": "MAST30034-real-estate-project/1.0"}
    last_error = None
    for attempt in range(OVERPASS_MAX_RETRIES):
        endpoint = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            print(f"  Querying {endpoint} (attempt {attempt + 1}/{OVERPASS_MAX_RETRIES})...")
            resp = requests.post(endpoint, data={"data": query}, headers=headers, timeout=OVERPASS_HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            elements = resp.json()["elements"]
            break
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            last_error = e
            wait = 10 * (attempt + 1)
            print(f"  Attempt {attempt + 1} failed ({e}); waiting {wait}s before retrying...")
            time.sleep(wait)
    else:
        raise RuntimeError(f"All Overpass attempts failed for tag_filter={tag_filter}. Last error: {last_error}")

    rows = []
    for el in elements:
        if el["type"] == "node":
            rows.append((el["lat"], el["lon"]))
        elif "center" in el:
            rows.append((el["center"]["lat"], el["center"]["lon"]))
    return pd.DataFrame(rows, columns=["latitude", "longitude"])


# -----------------------------------------------------------------------
# Straight-line pre-filter
# -----------------------------------------------------------------------

def build_tree(df: pd.DataFrame) -> BallTree:
    """
    Build a BallTree spatial index from latitude and longitude coordinates.
    
    Converts DataFrame latitude and longitude columns to radians and constructs
    a BallTree using the haversine (great-circle distance) metric. The resulting
    tree supports efficient nearest-neighbor queries on a sphere.
    
    Args:
        df: A DataFrame with 'latitude' and 'longitude' columns.
    
    Returns:
        A BallTree object configured for haversine distance queries.
    """
    coords_rad = np.radians(df[["latitude", "longitude"]].values)
    return BallTree(coords_rad, metric="haversine")


# -----------------------------------------------------------------------
# OSRM routing (batched many-to-many)
# -----------------------------------------------------------------------

def osrm_table_km_batch(base_url: str, profile: str, source_latlons: np.ndarray, dest_latlons: np.ndarray) -> np.ndarray:
    """
    Query the OSRM /table/ endpoint for route distances between multiple sources
    and multiple destinations in a single HTTP request.
    
    Constructs a single many-to-many routing request covering all source-destination
    pairs for the given profile (e.g., "driving" or "foot"). Returns an (S x D)
    matrix of route distances in kilometers, with NaN for any pairs that cannot
    be routed or if the entire request fails.
    
    Args:
        base_url: The base URL of the OSRM server (e.g., "http://localhost:5000").
        profile: The routing profile (e.g., "driving", "foot").
        source_latlons: An (S x 2) NumPy array of [latitude, longitude] source
                        coordinates.
        dest_latlons: A (D x 2) NumPy array of [latitude, longitude] destination
                      coordinates.
    
    Returns:
        An (S x D) NumPy array of route distances in kilometers. NaN values
        indicate pairs that could not be routed or a request failure.
    """
    s = len(source_latlons)
    d = len(dest_latlons)
    if s == 0 or d == 0:
        return np.full((s, d), np.nan)

    coord_parts = [f"{lon},{lat}" for lat, lon in source_latlons] + [f"{lon},{lat}" for lat, lon in dest_latlons]
    coords_str = ";".join(coord_parts)
    sources_str = ";".join(str(i) for i in range(s))
    dest_str = ";".join(str(s + i) for i in range(d))
    url = f"{base_url}/table/v1/{profile}/{coords_str}?sources={sources_str}&destinations={dest_str}&annotations=distance"

    try:
        resp = requests.get(url, timeout=OSRM_REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        distances_m = resp.json()["distances"]  # S x D
    except (requests.exceptions.RequestException, KeyError, IndexError, ValueError):
        return np.full((s, d), np.nan)

    return np.array([[v / 1000.0 if v is not None else np.nan for v in row] for row in distances_m])


def _split_batch_if_too_wide(batch_idx: list[int], candidate_lookup) -> list[int] | None:
    """
    Check if a batch will exceed the maximum number of destinations when sent
    to OSRM, and return a smaller batch to retry with if necessary.
    
    Examines the union of all candidates for properties in the batch. If the
    union exceeds MAX_DESTINATIONS_PER_BATCH and the batch has more than one
    property, returns the first half of the batch for retry; otherwise returns
    None to indicate the batch is acceptable as-is.
    
    Args:
        batch_idx: A list of property indices to check.
        candidate_lookup: A callable that takes a property index and returns
                          an iterable of candidate indices for that property.
    
    Returns:
        A smaller batch (first half of batch_idx) if splitting is needed, or
        None if the batch is acceptable.
    """
    union = set()
    for i in batch_idx:
        union.update(candidate_lookup(i))
    if len(union) > MAX_DESTINATIONS_PER_BATCH and len(batch_idx) > 1:
        return batch_idx[: len(batch_idx) // 2]
    return None


def nearest_route_km(properties: pd.DataFrame, candidates: pd.DataFrame, osrm_url: str, profile: str,
                      label: str = "", batch_size: int = BATCH_SIZE, max_workers: int = MAX_WORKERS) -> np.ndarray:
    """
    Compute the true nearest route distance (in kilometers) for every property
    to its nearest candidate amenity using an expanding-radius search strategy.
    
    Searches for the nearest candidate to each property using an expanding-radius
    approach: the search radius starts at INITIAL_SEARCH_RADIUS_KM and doubles
    each iteration until the true nearest is found (guaranteed by the property
    that route distance >= straight-line distance). Route distances are computed
    via batched, parallelised OSRM /table/ requests, and the search continues
    across multiple iterations until all properties are resolved or MAX_SEARCH_ITERATIONS
    is reached.
    
    Args:
        properties: A DataFrame with 'latitude' and 'longitude' columns for
                    each property.
        candidates: A DataFrame with 'latitude' and 'longitude' columns for
                    each candidate amenity location.
        osrm_url: The base URL of the OSRM server.
        profile: The routing profile (e.g., "driving", "foot").
        label: A descriptive label for logging (default "").
        batch_size: Number of properties per OSRM /table/ request (default BATCH_SIZE).
        max_workers: Number of concurrent threads for OSRM requests (default MAX_WORKERS).
    
    Returns:
        A NumPy array of length len(properties) containing the nearest route
        distance in kilometers for each property. NaN indicates no route could
        be found.
    """
    tree = build_tree(candidates)
    candidate_coords = candidates[["latitude", "longitude"]].values
    property_coords = properties[["latitude", "longitude"]].values
    n = len(properties)

    best = np.full(n, np.inf)
    radius = np.full(n, INITIAL_SEARCH_RADIUS_KM)
    active = np.ones(n, dtype=bool)

    def local_candidates(i: int, r: float) -> np.ndarray:
        return tree.query_radius(np.radians([property_coords[i]]), r=r / EARTH_RADIUS_KM)[0]

    def process_batch(batch_idx: list[int]) -> dict[int, tuple[float, bool]]:
        union = set()
        per_property = {}
        for i in batch_idx:
            idx_arr = local_candidates(i, radius[i])
            per_property[i] = idx_arr
            union.update(idx_arr.tolist())

        if len(union) > MAX_DESTINATIONS_PER_BATCH and len(batch_idx) > 1:
            mid = len(batch_idx) // 2
            out = process_batch(batch_idx[:mid])
            out.update(process_batch(batch_idx[mid:]))
            return out

        result = {}
        if not union:
            for i in batch_idx:
                result[i] = (np.inf, True)
            return result

        union_list = sorted(union)
        dest_coords = candidate_coords[union_list]
        source_coords = property_coords[batch_idx]
        dist_matrix = osrm_table_km_batch(osrm_url, profile, source_coords, dest_coords)

        for row, i in enumerate(batch_idx):
            row_dists = dist_matrix[row]
            finite = row_dists[np.isfinite(row_dists)]
            m = finite.min() if len(finite) else np.inf
            result[i] = (m, m > radius[i])
        return result

    iteration = 0
    while active.any() and iteration < MAX_SEARCH_ITERATIONS:
        iteration += 1
        active_idx = np.where(active)[0].tolist()
        batches = [active_idx[i:i + batch_size] for i in range(0, len(active_idx), batch_size)]

        batch_results: dict[int, tuple[float, bool]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_batch, b) for b in batches]
            for f in as_completed(futures):
                batch_results.update(f.result())

        for i in active_idx:
            old_r = radius[i]
            m, needs_expand = batch_results[i]
            if m < best[i]:
                best[i] = m
            if not needs_expand:
                active[i] = False
            elif old_r >= MAX_SEARCH_RADIUS_KM:
                active[i] = False  # already tried at the cap - give up gracefully
            else:
                radius[i] = min(max(best[i], old_r * 2), MAX_SEARCH_RADIUS_KM)

        resolved = int((~active).sum())
        print(f"  [{label}] iteration {iteration}: {resolved}/{n} resolved")

    return np.where(np.isfinite(best), best, np.nan)


def nearest_route_km_capped(properties: pd.DataFrame, candidates: pd.DataFrame, osrm_url: str, profile: str,
                             skip_threshold_km: float, label: str = "", batch_size: int = BATCH_SIZE,
                             max_workers: int = MAX_WORKERS) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute nearest route distances with a straight-line pre-filter to skip
    expensive routing calls for distant amenities.
    
    For properties whose straight-line distance to the nearest candidate
    already exceeds skip_threshold_km, the true route distance is guaranteed
    to exceed the threshold as well (since route distance >= straight-line
    distance). This function skips the routing call for such properties and
    reports them as capped at skip_threshold_km. For closer properties, it
    computes true route distances via nearest_route_km. This optimization is
    most useful for walking-based amenities (tram, bus) where distances beyond
    the threshold are not realistically walkable anyway.
    
    Args:
        properties: A DataFrame with 'latitude' and 'longitude' columns.
        candidates: A DataFrame with 'latitude' and 'longitude' columns for
                    candidate amenity locations.
        osrm_url: The base URL of the OSRM server.
        profile: The routing profile (e.g., "foot" for walking).
        skip_threshold_km: The distance threshold (in km) beyond which to skip
                           routing and report a capped value.
        label: A descriptive label for logging (default "").
        batch_size: Number of properties per OSRM request (default BATCH_SIZE).
        max_workers: Number of concurrent threads (default MAX_WORKERS).
    
    Returns:
        A tuple of two NumPy arrays:
            - distances_km: Route distances for each property. For capped properties,
                            this is exactly skip_threshold_km (an "at least" value).
                            For routed properties, this is the computed true route
                            distance (which may slightly exceed the threshold).
            - capped_flags: Boolean array where True indicates the distance is
                            a capped "at least" value rather than a true computed
                            route distance.
    """
    tree = build_tree(candidates)
    property_coords = properties[["latitude", "longitude"]].values
    n = len(properties)

    dist_rad, _ = tree.query(np.radians(property_coords), k=1)
    straight_km = dist_rad[:, 0] * EARTH_RADIUS_KM
    capped = straight_km > skip_threshold_km

    n_capped = int(capped.sum())
    print(f"  [{label}] {n_capped:,}/{n:,} properties are >{skip_threshold_km}km away by straight-line - "
          f"skipping route calculation for these, capping at {skip_threshold_km}km")

    results = np.full(n, np.nan)
    results[capped] = skip_threshold_km

    if n_capped < n:
        near_properties = properties[~capped].reset_index(drop=True)
        near_results = nearest_route_km(near_properties, candidates, osrm_url, profile, label=label,
                                         batch_size=batch_size, max_workers=max_workers)
        results[~capped] = near_results

    return results, capped


def count_within_route_km(properties: pd.DataFrame, candidates: pd.DataFrame, osrm_url: str, profile: str,
                           radius_km: float, max_candidates: int = COUNT_MAX_CANDIDATES, label: str = "",
                           batch_size: int = BATCH_SIZE, max_workers: int = MAX_WORKERS) -> np.ndarray:
    """
    Count the number of candidate amenities within a specified route distance
    for each property.
    
    Uses a straight-line pre-filter to identify candidates within radius_km
    (which is guaranteed to be a superset of the true "route distance <= radius_km"
    set, since route distance >= straight-line distance). For each property,
    sends the filtered candidates to OSRM for true route distance computation,
    then counts how many are actually within the threshold. Results are computed
    via batched, parallelised OSRM /table/ requests.
    
    Args:
        properties: A DataFrame with 'latitude' and 'longitude' columns.
        candidates: A DataFrame with 'latitude' and 'longitude' columns for
                    candidate amenity locations.
        osrm_url: The base URL of the OSRM server.
        profile: The routing profile (e.g., "driving", "foot").
        radius_km: The distance threshold (in km) for counting.
        max_candidates: Maximum number of pre-filtered candidates per property
                        to send to OSRM (default COUNT_MAX_CANDIDATES).
        label: A descriptive label for logging (default "").
        batch_size: Number of properties per OSRM request (default BATCH_SIZE).
        max_workers: Number of concurrent threads (default MAX_WORKERS).
    
    Returns:
        A NumPy array of length len(properties) containing the count of candidates
        within route distance radius_km for each property.
    """
    tree = build_tree(candidates)
    candidate_coords = candidates[["latitude", "longitude"]].values
    property_coords = properties[["latitude", "longitude"]].values
    n = len(properties)

    radius_rad = radius_km / EARTH_RADIUS_KM
    idx_arrays, _ = tree.query_radius(np.radians(property_coords), r=radius_rad, return_distance=True, sort_results=True)
    idx_arrays = [arr[:max_candidates] for arr in idx_arrays]

    def process_batch(batch_idx: list[int]) -> dict[int, int]:
        union = set()
        for i in batch_idx:
            union.update(idx_arrays[i].tolist())

        if len(union) > MAX_DESTINATIONS_PER_BATCH and len(batch_idx) > 1:
            mid = len(batch_idx) // 2
            out = process_batch(batch_idx[:mid])
            out.update(process_batch(batch_idx[mid:]))
            return out

        result = {}
        if not union:
            for i in batch_idx:
                result[i] = 0
            return result

        union_list = sorted(union)
        union_pos = {c: p for p, c in enumerate(union_list)}
        dest_coords = candidate_coords[union_list]
        source_coords = property_coords[batch_idx]
        dist_matrix = osrm_table_km_batch(osrm_url, profile, source_coords, dest_coords)

        for row, i in enumerate(batch_idx):
            local_positions = [union_pos[c] for c in idx_arrays[i]]
            if not local_positions:
                result[i] = 0
                continue
            local_dists = dist_matrix[row][local_positions]
            result[i] = int(np.sum(local_dists <= radius_km))
        return result

    all_idx = list(range(n))
    batches = [all_idx[i:i + batch_size] for i in range(0, n, batch_size)]

    results_map: dict[int, int] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_batch, b) for b in batches]
        completed = 0
        for f in as_completed(futures):
            results_map.update(f.result())
            completed += 1
            if completed % 10 == 0 or completed == len(batches):
                print(f"  [{label}] {completed}/{len(batches)} batches done")

    return np.array([results_map[i] for i in range(n)])


# -----------------------------------------------------------------------
# Coordinate deduplication wrapper
# -----------------------------------------------------------------------

def dedupe_and_compute(properties: pd.DataFrame, compute_fn, *args, **kwargs):
    """
    Deduplicate property coordinates, compute a metric once per unique location,
    and broadcast results back to all original rows.
    
    Many rental listings share a building (same latitude and longitude but
    different units). This function rounds coordinates to COORD_ROUND_DECIMALS
    precision, identifies unique locations, calls compute_fn on just those
    unique locations, then broadcasts the results back to every original row.
    This avoids redundant routing computations while maintaining a 1-to-1 mapping
    with the input properties DataFrame.
    
    Works with compute_fn returning either a single array or a tuple of arrays
    (e.g., nearest_route_km_capped returns a tuple of (distances, capped_flags)).
    Each array in the tuple is broadcast back independently.
    
    Args:
        properties: A DataFrame with 'latitude' and 'longitude' columns.
        compute_fn: A callable that takes (unique_properties_df, *args, **kwargs)
                    and returns either a single NumPy array or a tuple of arrays.
        *args: Positional arguments to pass to compute_fn.
        **kwargs: Keyword arguments to pass to compute_fn.
    
    Returns:
        If compute_fn returns a single array, returns a NumPy array broadcast
        to match the original properties length. If compute_fn returns a tuple,
        returns a tuple of broadcast arrays.
    """
    rounded = properties[["latitude", "longitude"]].round(COORD_ROUND_DECIMALS)
    unique_df = rounded.drop_duplicates().reset_index(drop=True)
    print(f"    ({len(properties):,} properties -> {len(unique_df):,} unique locations "
          f"after rounding to {COORD_ROUND_DECIMALS} decimal places)")

    key_to_pos = {(row.latitude, row.longitude): i for i, row in unique_df.iterrows()}
    inverse = np.array([key_to_pos[(lat, lon)] for lat, lon in zip(rounded["latitude"], rounded["longitude"])])

    values = compute_fn(unique_df, *args, **kwargs)
    if isinstance(values, tuple):
        return tuple(np.asarray(v)[inverse] for v in values)
    return np.asarray(values)[inverse]


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main():
    """
    Main entry point for the amenity distance computation pipeline.
    
    Parses command-line arguments, loads rental property and amenity datasets,
    computes route distances and counts for all amenity types, and outputs
    a CSV file with results. Supports optional sampling for testing and
    configurable batch size and worker count for performance tuning.
    
    Command-line arguments:
        --sample N: Process only a random sample of N properties and write to
                    a separate *_sample{N}.csv file.
        --workers N: Number of concurrent threads for OSRM requests (default MAX_WORKERS).
        --batch-size N: Properties per OSRM /table/ call (default BATCH_SIZE).
    
    Returns:
        None (writes results to OUTPUT_PATH or a sample variant thereof).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=None,
                         help="Process only a random sample of N properties (for a quick end-to-end smoke test "
                              "before committing to the full dataset). Output is written to a separate "
                              "*_sample{N}.csv file so it can't overwrite your real results.")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Thread pool size for OSRM requests")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Properties per OSRM /table/ call")
    args = parser.parse_args()

    properties = pd.read_csv(PROPERTIES_PATH)
    if properties.columns[0].startswith("Unnamed"):
        # Some exports have a stray leading index column with no header
        # name (pandas labels it "Unnamed: 0") - drop it if present, but
        # don't assume it's there, since not every properties.csv has one.
        properties = properties.drop(columns=properties.columns[0])
    properties = properties.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)

    output_path = OUTPUT_PATH
    if args.sample:
        properties = properties.sample(n=min(args.sample, len(properties)), random_state=42).reset_index(drop=True)
        output_path = str(Path(OUTPUT_PATH).with_name(Path(OUTPUT_PATH).stem + f"_sample{args.sample}.csv"))
        print(f"SAMPLE MODE: processing {len(properties):,} randomly sampled properties -> {output_path}\n")

    result = properties[["id", "url", "latitude", "longitude", "suburb"]].copy()

    print("Checking data files...")
    download_if_missing(SCHOOLS_CSV_URL, SCHOOLS_CSV_PATH)
    download_if_missing(GTFS_ZIP_URL, GTFS_ZIP_PATH)

    schools = load_schools_csv(SCHOOLS_CSV_PATH)
    print(f"Schools: {len(schools):,}")

    metro_train = load_gtfs_stops(GTFS_ZIP_PATH, mode_folder="2")
    regional_train = load_gtfs_stops(GTFS_ZIP_PATH, mode_folder="1")
    train_stations = pd.concat([metro_train, regional_train], ignore_index=True)
    print(f"Train stations (metro + regional): {len(train_stations):,}")

    tram_stops = load_gtfs_stops(GTFS_ZIP_PATH, mode_folder="3")
    print(f"Tram stops: {len(tram_stops):,}")

    bus_stops = load_gtfs_stops(GTFS_ZIP_PATH, mode_folder="4")
    print(f"Bus stops: {len(bus_stops):,}")

    parks = fetch_osm_points('["leisure"="park"]', MELBOURNE_BBOX)
    time.sleep(2)
    supermarkets = fetch_osm_points('["shop"="supermarket"]', MELBOURNE_BBOX)
    print(f"OSM parks: {len(parks):,} | OSM supermarkets: {len(supermarkets):,}")

    common_kwargs = dict(batch_size=args.batch_size, max_workers=args.workers)

    print("\nComputing CAR route distances...")
    result["nearest_school_km"] = dedupe_and_compute(
        properties, nearest_route_km, schools, OSRM_CAR_URL, "driving", label="school (nearest)", **common_kwargs
    )
    result[f"school_count_{SCHOOL_RADIUS_KM:g}km"] = dedupe_and_compute(
        properties, count_within_route_km, schools, OSRM_CAR_URL, "driving", SCHOOL_RADIUS_KM,
        label="school (count)", **common_kwargs
    )

    result["nearest_train_station_km"] = dedupe_and_compute(
        properties, nearest_route_km, train_stations, OSRM_CAR_URL, "driving", label="train station", **common_kwargs
    )

    result["nearest_park_km"] = dedupe_and_compute(
        properties, nearest_route_km, parks, OSRM_CAR_URL, "driving", label="park (nearest)", **common_kwargs
    )
    result[f"park_count_{PARK_RADIUS_KM:g}km"] = dedupe_and_compute(
        properties, count_within_route_km, parks, OSRM_CAR_URL, "driving", PARK_RADIUS_KM,
        label="park (count)", **common_kwargs
    )

    result["nearest_supermarket_km"] = dedupe_and_compute(
        properties, nearest_route_km, supermarkets, OSRM_CAR_URL, "driving", label="supermarket (nearest)", **common_kwargs
    )
    result[f"supermarket_count_{SUPERMARKET_RADIUS_KM:g}km"] = dedupe_and_compute(
        properties, count_within_route_km, supermarkets, OSRM_CAR_URL, "driving", SUPERMARKET_RADIUS_KM,
        label="supermarket (count)", **common_kwargs
    )

    print("\nComputing WALKING route distances (with straight-line pre-filter skip)...")
    result["nearest_tram_stop_km"], result["tram_stop_capped"] = dedupe_and_compute(
        properties, nearest_route_km_capped, tram_stops, OSRM_FOOT_URL, "foot", TRAM_SKIP_THRESHOLD_KM,
        label="tram stop", **common_kwargs
    )
    result["nearest_bus_stop_km"], result["bus_stop_capped"] = dedupe_and_compute(
        properties, nearest_route_km_capped, bus_stops, OSRM_FOOT_URL, "foot", BUS_SKIP_THRESHOLD_KM,
        label="bus stop", **common_kwargs
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(f"\nSaved {len(result):,} rows to {output_path}")
    print(result.head())


if __name__ == "__main__":
    main()