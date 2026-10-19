# Import the 5 yearly household forecast data by SA2 area

from pathlib import Path
import pandas as pd

# Set up paths

current_path = Path.cwd()
path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "Household_Dwelling_Forecast_2136.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Read in the raw Excel sheet
clean_data = pd.read_excel(
    file_path,
    sheet_name="Total_Dwellings",
    header=None
)

# Save the sheet as an unclean csv
csv_file_path = data_path / "Household_Dwelling_Forecast_2136_Cleaneed.csv"
clean_data.to_csv(csv_file_path)

# Read the csv back in
unclean_data = pd.read_csv(csv_file_path)

# Remove the metadata rows and the old index column
dwelling_data = (
    unclean_data
    .iloc[11:, 1:]
    .copy()
)

# Rename the columns
dwelling_data.columns = [
    "gccsa",
    "sa4_code",
    "sa3_code",
    "sa2_code",
    "region_type",
    "sa2_name",
    "dwellings_2021",
    "dwellings_2026",
    "dwellings_2031",
    "dwellings_2036",
]

# Keep only SA2 rows
dwelling_data = dwelling_data[
    dwelling_data["region_type"] == "SA2"
].copy()

# Convert the code columns to text
code_columns = [
    "sa4_code",
    "sa3_code",
    "sa2_code",
]

dwelling_data[code_columns] = (
    dwelling_data[code_columns]
    .astype(str)
)

# Convert the dwelling columns to numeric
dwelling_columns = [
    "dwellings_2021",
    "dwellings_2026",
    "dwellings_2031",
    "dwellings_2036",
]

dwelling_data[dwelling_columns] = (
    dwelling_data[dwelling_columns]
    .apply(
        pd.to_numeric,
        errors="coerce",
    )
)

# Reset the index after filtering
dwelling_data = (
    dwelling_data
    .reset_index(drop=True)
)

# Write the cleaned data to a csv
csv2_file_path = data_path / "Household_Dwelling_Forecast_2136_CleanedV2.csv"
dwelling_data.to_csv(csv2_file_path)