import requests
import zipfile
from pathlib import Path
import logging 

# Our data will be stored here
data_destination = Path("data/geospatial_data/")

# Our logs for audit will be stored here
log_dir = "data_retrieval/retrieval_info.log"

logging.basicConfig(
    filename=log_dir,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Create a directory specifically for the SA2 shapefile
sa2_directory = data_destination / "SA2_2021_AUST_GDA2020"
sa2_directory.mkdir(parents=True, exist_ok=True)

logging.info('Creating SA2 directory if not already there...')

url = "https://www.abs.gov.au/statistics/" \
"standards/australian-statistical-geography-standard-asgs/" \
"edition-3-july-2021-june-2026/access-and-downloads/" \
"digital-boundary-files/SA2_2021_AUST_SHP_GDA2020.zip"


# Download the ZIP file
response = requests.get(url)
response.raise_for_status()


# Save ZIP temporarily
zip_path = data_destination / "SA2_2021_AUST_SHP_GDA2020.zip"
logging.info('Saved zip file temporarily to: %s', zip_path)
with open(zip_path, "wb") as f:
    f.write(response.content)


# Extract the ZIP into the SA2 directory
with zipfile.ZipFile(zip_path, "r") as zip_ref:
    zip_ref.extractall(sa2_directory)
logging.info('Extracted zip file to: %s', sa2_directory)

# Remove the ZIP after extraction
zip_path.unlink()

logging.info('Removed zip file: %s', zip_path)

# Rename the extracted files to data.<extension>
for file in sa2_directory.iterdir():
    if file.is_file():
        new_name = sa2_directory / f"data{file.suffix}"
        file.rename(new_name)
