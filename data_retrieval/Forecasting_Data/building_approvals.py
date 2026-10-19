# Download and clean the ABS dwelling stock dataset for SA2 zones
import geopandas as gpd
from pathlib import Path
import pandas as pd
import requests
import openpyxl

# Set up paths

current_path = Path.cwd()
path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "DwellingStock_1626.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Download the data

url = (
    "https://www.abs.gov.au/statistics/industry/"
    "building-and-construction/estimated-dwelling-stock/"
    "jun-quarter-2022/ASGS21_2016q2-2022q2.xlsx"
)

response = requests.get(
    url,
    timeout=60
)

# Stop if the download failed
response.raise_for_status()

# Save the raw Excel file
with open(file_path, "wb") as file:
    file.write(response.content)

print(f"Downloaded successfully to: {file_path}")

# Convert the Excel sheet to an unclean csv

excel_data = pd.read_excel(
    file_path,
    sheet_name="Table 1",
    header=None
)

csv_unclean_path = data_path / "DwellingStock_1626_Unclean.csv"
excel_data.to_csv(csv_unclean_path)

# Clean the data

# Read the unclean csv with every value as text
unclean_data = pd.read_csv(
    csv_unclean_path,
    header=None,
    dtype=str
)

# Quarterly dates are stored in row 7
quarter_labels = (
    pd.to_datetime(
        unclean_data.iloc[7, 11:36],
        errors="coerce"
    )
    .dt.strftime("%Y-%m-%d")
    .tolist()
)

# SA2 observations begin at row 10, with code in column 9, name in column 10 and quarters in columns 11 to 35
dwelling_stock = unclean_data.iloc[
    10:,
    [9, 10] + list(range(11, 36))
].copy()

# Rename the columns
dwelling_stock.columns = (
    ["sa2_code", "sa2_name"]
    + [f"dwelling_stock_{date}" for date in quarter_labels]
)

# Remove extra whitespace from the SA2 columns
dwelling_stock["sa2_code"] = dwelling_stock["sa2_code"].str.strip()
dwelling_stock["sa2_name"] = dwelling_stock["sa2_name"].str.strip()

# Keep only rows with a numeric SA2 code
dwelling_stock = dwelling_stock[
    dwelling_stock["sa2_code"].str.fullmatch(
        r"\d+",
        na=False
    )
]

# Convert the dwelling stock columns to numeric
for column in dwelling_stock.columns[2:]:
    dwelling_stock[column] = pd.to_numeric(
        dwelling_stock[column],
        errors="coerce"
    ).astype("Int64")

# Reset the index after filtering
dwelling_stock = dwelling_stock.reset_index(drop=True)

# Save the clean data
csv_clean_path = data_path / "DwellingStock1626_Clean.csv"
dwelling_stock.to_csv(csv_clean_path)