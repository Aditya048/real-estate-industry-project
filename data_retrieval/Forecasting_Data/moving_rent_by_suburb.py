# Download and clean the moving annual rent data by suburb from 2000 to 2025

from pathlib import Path
import pandas as pd
import requests

# Set up paths

current_path = Path.cwd()

path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "MovingRent_0025.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Download the data

url = (
    "https://www.dffh.vic.gov.au/"
    "moving-annual-rent-suburb-september-quarter-2025-excel"
)

response = requests.get(
    url,
    timeout=60,
)

# Stop if the download failed
response.raise_for_status()

# Save the raw Excel file
with open(file_path, "wb") as file:
    file.write(response.content)

print(f"Downloaded successfully to: {file_path}")

# Convert the Excel sheet to an uncleaned csv

moving_rent_data = pd.read_excel(
    file_path
)

csv1_file_path = data_path / "MovingRent_0025_Uncleaned.csv"

moving_rent_data.to_csv(
    csv1_file_path,
    index=False,
    header=False
)

# Read the uncleaned csv back in with a two row header

uncleaned_data = pd.read_csv(csv1_file_path, header=[0, 1])

# Keep the suburb column and the median columns

# The second column holds the suburb names
suburb_column = uncleaned_data.columns[1]

# Find all columns where the second header is "Median"
median_columns = [
    column
    for column in uncleaned_data.columns
    if str(column[1]).strip() == "Median"
]

cleaned_data = uncleaned_data[
    [suburb_column] + median_columns
].copy()

# Rename the first column to suburb and use the top header for the rest
cleaned_data.columns = (
    ["suburb"]
    + [
        column[0]
        for column in median_columns
    ]
)

# Save the cleaned data

csv2_file_path = data_path / "MovingRent_0025_Cleaned.csv"

cleaned_data.to_csv(
    csv2_file_path,
    index=False,
)

print(cleaned_data.head())
print(f"Cleaned data saved to: {csv2_file_path}")