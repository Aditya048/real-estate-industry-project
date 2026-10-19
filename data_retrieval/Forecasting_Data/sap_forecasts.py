# Read and clean the 5 yearly population projections by SA2 district

from pathlib import Path
import pandas as pd

# Set up paths

current_path = Path.cwd()
path_root = current_path.parent.parent

data_path = path_root / "data" / "forecasting"
file_path = data_path / "SAP_Forecast_2136.xlsx"

# Create the data folder if it does not exist
data_path.mkdir(parents=True, exist_ok=True)

# Read in the raw data for each sex

uncleaned_males = pd.read_excel(
    file_path,
    sheet_name="ERP_by_Age_Males",
    header=None
)

uncleaned_females = pd.read_excel(
    file_path,
    sheet_name="ERP_by_Age_Females",
    header=None
)

uncleaned_persons = pd.read_excel(
    file_path,
    sheet_name="ERP_by_Age_Persons",
    header=None
)


# Define the cleaning function

def clean_age_data(data, sex):
    """Clean age-group projection rows and tag them with a sex label.

    Args:
        data: Raw Excel sheet as a DataFrame.
        sex: Sex label to attach (e.g. "Males").

    Returns:
        Cleaned long-format DataFrame for that sex.
    """
    # Get the years and age groups from the header rows
    years = data.iloc[8].copy()
    headers = data.iloc[9].copy()

    column_names = [
        "gccsa",
        "sa4_code",
        "sa3_code",
        "sa2_code",
        "region_type",
        "region",
    ]

    for i in range(6, len(data.columns)):

        year = years.iloc[i]

        age_group = str(
            headers.iloc[i]
        )

        # Clean the age group names
        age_group = (
            age_group
            .replace("\n", " ")
            .replace(f"{sex}s ", "")
            .strip()
            .replace(" ", "_")
        )

        column_names.append(
            f"{int(year)}_{age_group}"
        )

    # Remove the metadata rows
    data = data.iloc[11:].copy()

    data.columns = column_names

    # Keep SA2 areas only
    data = data[
        data["region_type"] == "SA2"
    ].copy()

    data["sa2_code"] = (
        data["sa2_code"]
        .astype(str)
    )

    # Convert the population columns to numeric
    population_columns = data.columns[6:]

    data[population_columns] = (
        data[population_columns]
        .apply(
            pd.to_numeric,
            errors="coerce",
        )
    )

    # Add a sex column
    data["sex"] = sex

    data = data.reset_index(
        drop=True
    )

    return data


# Clean the data for each sex

male_data = clean_age_data(uncleaned_males, "Males")
female_data = clean_age_data(uncleaned_females, "Females")
person_data = clean_age_data(uncleaned_persons, "Persons")

# Prefix the population columns by sex so the dataframes can be merged

id_columns = [
    "gccsa",
    "sa4_code",
    "sa3_code",
    "sa2_code",
    "region_type",
    "region",
]

male_data = male_data.rename(
    columns={
        column: f"male_{column}"
        for column in male_data.columns
        if column not in id_columns
        and column != "sex"
    }
)

female_data = female_data.rename(
    columns={
        column: f"female_{column}"
        for column in female_data.columns
        if column not in id_columns
        and column != "sex"
    }
)

person_data = person_data.rename(
    columns={
        column: f"persons_{column}"
        for column in person_data.columns
        if column not in id_columns
        and column != "sex"
    }
)

# Drop the sex column since it is not needed

male_data = male_data.drop(
    columns=["sex"],
    errors="ignore",
)

female_data = female_data.drop(
    columns=["sex"],
    errors="ignore",
)

person_data = person_data.drop(
    columns=["sex"],
    errors="ignore",
)

# Merge the three dataframes on SA2 code

clean_data = male_data.merge(
    female_data.drop(
        columns=[
            "gccsa",
            "sa4_code",
            "sa3_code",
            "region_type",
            "region",
        ],
    ),
    on="sa2_code",
    how="inner",
)

clean_data = clean_data.merge(
    person_data.drop(
        columns=[
            "gccsa",
            "sa4_code",
            "sa3_code",
            "region_type",
            "region",
        ],
    ),
    on="sa2_code",
    how="inner",
)

# Tidy up the column names

clean_data.columns = (
    clean_data.columns
    .str.replace("_Males__", "_", regex=False)
    .str.replace("_Females__", "_", regex=False)
    .str.replace("_Persons__", "_", regex=False)
)

# Write the cleaned data to a csv file

csv_file_path = data_path / "SAP_Forecast_2136_Cleaned.csv"

clean_data.to_csv(csv_file_path, index=False)