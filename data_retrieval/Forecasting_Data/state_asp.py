# Download and clean the population projections to 2071 by age and sex

from pathlib import Path
import pandas as pd
import requests

# Set up paths

current_path = Path.cwd()

path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "MediumSeries_ASPData_2171.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Download the data

url = (
    "https://www.abs.gov.au/statistics/people/population/"
    "population-projections-australia/2022-base-2071/"
    "3222_Table_B2.xlsx"
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

# Read the Data1 and Data2 sheets

data1 = pd.read_excel(
    file_path,
    sheet_name="Data1",
    header=None,
)

data2 = pd.read_excel(
    file_path,
    sheet_name="Data2",
    header=None,
)

# Combine the two sheets side by side

# Drop the first two columns of Data2 since Data1 already has them
data2 = data2.iloc[:, 2:]

combined_data = pd.concat(
    [data1, data2],
    axis=1,
)

# Save the combined data as an uncleaned csv

csv1_data_path = path_root / "data" / "forecasting"
csv1_file_path = csv1_data_path / "MediumSeries_ASPData_2171_Uncleaned.csv"

csv1_data_path.mkdir(parents=True, exist_ok=True)

combined_data.to_csv(
    csv1_file_path,
    index=False,
    header=False,
)

print(f"Saved combined data to: {csv1_file_path}")
print(f"Shape: {combined_data.shape}")

# Read the uncleaned csv back in

uncleaned_data = pd.read_csv(csv1_file_path)

# Build clean column names from the series headers

series_headers = uncleaned_data.columns[1:]

clean_headers = ["year"]

for header in series_headers:

    parts = [
        part.strip()
        for part in str(header).split(";")
        if part.strip()
    ]

    sex = parts[3]

    age = parts[4].replace(
        " ",
        "_",
    )

    column_name = f"{sex}_age_{age}"

    clean_headers.append(column_name)

# Apply the new column names
uncleaned_data.columns = clean_headers

# Remove the metadata rows
cleaned_data = uncleaned_data.iloc[9:].copy()

# Convert full dates to years, for example 2022-06-30 becomes 2022
cleaned_data["year"] = (
    pd.to_datetime(cleaned_data["year"])
    .dt.year
)

# Convert the population columns to numeric
population_columns = cleaned_data.columns.drop(
    "year"
)

cleaned_data[population_columns] = (
    cleaned_data[population_columns]
    .apply(
        pd.to_numeric,
        errors="coerce",
    )
)

# Reset the index after removing rows
cleaned_data = cleaned_data.reset_index(
    drop=True
)

# Save the cleaned data

csv2_file_path = csv1_data_path / "MediumSeries_ASPData_2171_Cleaned.csv"

cleaned_data.to_csv(
    csv2_file_path,
    index=False,
)

# Print a quick summary of the cleaned data

print(f"Cleaned data saved to: {csv2_file_path}")

print(f"Rows: {len(cleaned_data)}")

print(f"Columns: {len(cleaned_data.columns)}")

print(
    f"Years: "
    f"{cleaned_data['year'].min()}-"
    f"{cleaned_data['year'].max()}"
)

print(cleaned_data.head())