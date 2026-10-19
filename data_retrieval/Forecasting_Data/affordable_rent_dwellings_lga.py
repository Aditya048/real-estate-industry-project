# Download and clean the affordable rental dwellings dataset for LGAs

from pathlib import Path
import pandas as pd
import requests

# Set up paths

current_path = Path.cwd()
path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "AffordableRentalsLGA0025.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Download the data

url = (
    "https://www.dffh.vic.gov.au/affordable-lettings-"
    "local-government-area-september-quarter-2025-excel"
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

# Read in the raw data

raw_data = pd.read_excel(
    file_path,
    sheet_name="lga aff total",
    header=None
)

# Extract the amount and proportion of affordable dwellings

# Dates are stored in row 2
dates = raw_data.iloc[2, 1:].copy()

# Measure types are stored in row 3
measure_types = raw_data.iloc[3, 1:].copy()

# Data rows start at row 4
affordable_data = (
    raw_data
    .iloc[4:, :]
    .copy()
)

affordable_data = affordable_data.rename(
    columns={
        0: "lga_name",
    }
)

# Find the column positions of the amount measure
affordable_positions = [
    i + 1
    for i, measure in enumerate(measure_types)
    if measure == "Affordable"
]

# Find the column positions of the percent measure
percent_positions = [
    i + 1
    for i, measure in enumerate(measure_types)
    if measure == "Percent"
]

# Build the amount of affordable dwellings dataframe

affordable_dwellings = affordable_data.iloc[
    :,
    [0] + affordable_positions,
].copy()

affordable_dates = [
    dates.iloc[i - 1]
    for i in affordable_positions
]

affordable_dwellings.columns = (
    ["lga_name"]
    + affordable_dates
)

# Build the proportion of affordable dwellings dataframe

affordable_percent = affordable_data.iloc[
    :,
    [0] + percent_positions,
].copy()

percent_dates = [
    dates.iloc[i - 1]
    for i in percent_positions
]

affordable_percent.columns = (
    ["lga_name"]
    + percent_dates
)

# Convert the column labels to dates

affordable_dates = pd.to_datetime(
    affordable_dwellings.columns[1:],
    errors="coerce",
)

percent_dates = pd.to_datetime(
    affordable_percent.columns[1:],
    errors="coerce",
)

# Rename the date columns to a year and month format

affordable_dwellings.columns = (
    ["lga_name"]
    + affordable_dates.strftime("%Y_%m").tolist()
)

affordable_percent.columns = (
    ["lga_name"]
    + percent_dates.strftime("%Y_%m").tolist()
)

# Write both dataframes to csv files

csv_dwellings_amt = data_path / "AffordableRentalsLGA0025_Amt.csv"
csv_dwellings_prp = data_path / "AffordableRentalsLGA0025_Prp.csv"

affordable_dwellings.to_csv(csv_dwellings_amt)
affordable_percent.to_csv(csv_dwellings_prp)