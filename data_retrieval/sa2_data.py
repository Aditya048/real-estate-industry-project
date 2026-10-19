"""Download and extract ABS SA2 2021 digital boundary shapefile.

Run from the repository root:
    python -m data_retrieval.sa2_data

Output: data/geospatial_data/SA2_2021_AUST_GDA2020/data.*
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import requests

DATA_DESTINATION = Path("data/geospatial_data/")
LOG_PATH = "data_retrieval/retrieval_info.log"
SA2_URL = (
    "https://www.abs.gov.au/statistics/"
    "standards/australian-statistical-geography-standard-asgs/"
    "edition-3-july-2021-june-2026/access-and-downloads/"
    "digital-boundary-files/SA2_2021_AUST_SHP_GDA2020.zip"
)


def download_sa2(data_destination: Path = DATA_DESTINATION) -> Path:
    """
    Download, extract, and standardize ABS SA2 2021 shapefile digital boundaries.
    
    Fetches the SA2 2021 digital boundary shapefile from the ABS website as a ZIP
    archive, extracts it to a destination directory, renames all extracted files
    to a standard naming scheme (data.*), and cleans up the temporary ZIP file.
    
    Logs all operations to a log file specified by LOG_PATH. Creates the output
    directory hierarchy if it does not already exist.
    
    Args:
        data_destination: The base directory where the SA2 shapefile directory
                          and temporary files will be stored (default DATA_DESTINATION).
                          The function creates a subdirectory 'SA2_2021_AUST_GDA2020'
                          within this path.
    
    Returns:
        A Path object pointing to the SA2 directory containing the extracted and
        renamed shapefile layers (e.g., data.shp, data.dbf, data.shx, data.prj, etc.).
    
    Raises:
        requests.exceptions.RequestException: If the HTTP download fails.
        zipfile.BadZipFile: If the downloaded file is not a valid ZIP archive.
        IOError: If file operations (write, extract, rename) fail.
    """
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    sa2_directory = data_destination / "SA2_2021_AUST_GDA2020"
    sa2_directory.mkdir(parents=True, exist_ok=True)
    logging.info("Creating SA2 directory if not already there...")

    response = requests.get(SA2_URL, timeout=300)
    response.raise_for_status()

    zip_path = data_destination / "SA2_2021_AUST_SHP_GDA2020.zip"
    logging.info("Saved zip file temporarily to: %s", zip_path)
    with open(zip_path, "wb") as f:
        f.write(response.content)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(sa2_directory)
    logging.info("Extracted zip file to: %s", sa2_directory)

    zip_path.unlink()
    logging.info("Removed zip file: %s", zip_path)

    for file in sa2_directory.iterdir():
        if file.is_file():
            new_name = sa2_directory / f"data{file.suffix}"
            file.rename(new_name)

    print(f"SA2 shapefile ready at {sa2_directory}")
    return sa2_directory


if __name__ == "__main__":
    download_sa2()