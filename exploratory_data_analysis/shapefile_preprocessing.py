"""Extract Victorian SA2 boundaries from the national ABS shapefile.

Reads the Australia-wide 2021 Statistical Area Level 2 (SA2) boundaries
published by the Australian Bureau of Statistics (ABS), keeps only the zones
located in Victoria, removes columns that are not needed downstream and writes
the result to a new shapefile.

Processing steps
----------------
1. Load the national SA2 shapefile.
2. Filter to rows where ``STE_NAME21`` is "Victoria".
3. Drop administrative columns (change flag and label) and columns that hold a
   single repeated value once the data is limited to Victoria (state and
   country codes and names).
4. Drop rows with a missing ``AREASQKM21``. This is intended to exclude the
   non-geographic categories "Migratory - Offshore - Shipping (Vic.)" and
   "No usual address (Vic.)".
5. Write the cleaned zones to ``Vic_Area_Zones/Vic_Area_Zones.shp``.

Usage
-----
    python preprocess_vic_zones.py
    python preprocess_vic_zones.py --input path/to/data.shp --output-dir path/to/out

By default, paths are resolved relative to a ``data`` folder in the parent
directory of this script's folder (``<project>/data/geospatial_data/...``).
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "geospatial_data"
DEFAULT_INPUT_PATH = DATA_DIR / "SA2_2021_AUST_GDA2020" / "data.shp"
DEFAULT_OUTPUT_DIR = DATA_DIR / "Vic_Area_Zones"
OUTPUT_FILENAME = "Vic_Area_Zones.shp"

STATE_COLUMN = "STE_NAME21"
STATE_NAME = "Victoria"
AREA_COLUMN = "AREASQKM21"

COLUMNS_TO_DROP = [
    "CHG_FLAG21",
    "CHG_LBL21",
    "STE_CODE21",
    "STE_NAME21",
    "AUS_CODE21",
    "AUS_NAME21",
]


def load_zones(path: Path) -> gpd.GeoDataFrame:
    """Read the national SA2 boundaries from a shapefile."""
    return gpd.read_file(path)


def filter_victoria(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only the zones located in Victoria."""
    is_victoria = zones[STATE_COLUMN] == STATE_NAME
    return zones[is_victoria]


def trim_zones(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop unneeded columns and rows with no area value."""
    zones = zones.drop(columns=COLUMNS_TO_DROP)
    return zones.dropna(subset=[AREA_COLUMN])


def export_zones(zones: gpd.GeoDataFrame, output_dir: Path) -> Path:
    """Write the zones to a shapefile, creating the output folder if needed.

    The folder is created explicitly because the data directory is excluded
    from version control, so it may not exist on a fresh clone.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    zones.to_file(output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for input and output paths."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to the national SA2 shapefile.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder in which to write the Victorian shapefile.",
    )
    return parser.parse_args()


def main() -> None:
    """Load national SA2 zones, filter to Victoria, and write the shapefile."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    zones = load_zones(args.input)
    LOGGER.info("Loaded %d SA2 zones from %s", len(zones), args.input)

    vic_zones = filter_victoria(zones)
    LOGGER.info("Filtered to %d Victorian zones", len(vic_zones))

    vic_zones = trim_zones(vic_zones)
    LOGGER.info("Kept %d zones with an area value", len(vic_zones))

    output_path = export_zones(vic_zones, args.output_dir)
    LOGGER.info("Wrote %s", output_path)


if __name__ == "__main__":
    main()