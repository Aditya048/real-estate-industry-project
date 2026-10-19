"""ABS Data API -> long SA2 panel. Add a fetch_* function per source.

Panel schema: sa2_code_2021, sa2_name, year, feature, value, status
All sources are filtered to Victoria (SA2 codes starting with "2") inside tidy().
sa2_code_2021 is a STRING everywhere -- always read it back with dtype=str or
it becomes an int and stops joining against the other teams' tables.
"""

import io
from pathlib import Path

import pandas as pd
import requests

BASE = "https://data.api.abs.gov.au/rest"
HEADERS = {"Accept": "application/vnd.sdmx.data+csv;labels=both"}
# Repo-root relative -- run from the project root so outputs land in data/
OUT = Path("data/sa2_panel")
OUT.mkdir(parents=True, exist_ok=True)

DTYPES = {"sa2_code_2021": str}


def abs_data(flow, key, **params):
    """
    Fetch data from the ABS Data API using SDMX-CSV format.
    
    Constructs and executes a single SDMX Data API request to retrieve statistical
    data in CSV format. The flow parameter specifies the data structure definition
    (AGENCY, ID, VERSION), and the key parameter specifies the data key constraints
    (use blank segments to match all values for a dimension).
    
    Args:
        flow: A string in the format 'AGENCY,ID,VERSION' that identifies the data
              structure definition (e.g., 'ABS,ABS_ANNUAL_ERP_ASGS2021,1.2.0').
        key: A period-separated string specifying dimension constraints
             (e.g., '.SA2..A' where blank segments match all values). Each segment
             corresponds to a dimension in the data structure.
        **params: Additional query parameters passed to the API (e.g., startPeriod,
                  endPeriod, etc.).
    
    Returns:
        A pandas DataFrame containing the raw API response parsed as CSV.
    
    Raises:
        requests.exceptions.HTTPError: If the API request fails.
    """
    r = requests.get(f"{BASE}/data/{flow}/{key}", headers=HEADERS,
                     params=params, timeout=300)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def _col(raw, dim):
    """
    Find a column name in a DataFrame by dimension ID, with or without label suffix.
    
    The ABS API can return columns either as plain dimension IDs or with appended
    labels in the format 'ID: Label'. This helper finds the column matching the
    requested dimension by checking both the exact name and the name-with-label
    variant.
    
    Args:
        raw: A pandas DataFrame with column names from the ABS API response.
        dim: The dimension ID to search for (e.g., 'ASGS_2021', 'TIME_PERIOD').
    
    Returns:
        The actual column name found in raw.columns that matches dim.
    
    Raises:
        KeyError: If no column matching dim or dim with a label suffix is found.
    """
    for c in raw.columns:
        if c == dim or c.startswith(dim + ":"):
            return c
    raise KeyError(f"{dim} not found in {list(raw.columns)}")


def _code(s):
    """
    Extract the code portion from a Series that may contain 'code: label' pairs.
    
    Many ABS API responses include both codes and labels in a single column, formatted
    as 'CODE: Label'. This function extracts just the code portion. If a value does
    not contain a colon, it is passed through unchanged.
    
    Args:
        s: A pandas Series where each element is either a code, or a string in the
           format 'code: label'.
    
    Returns:
        A pandas Series containing only the code portions, with leading/trailing
        whitespace removed.
    """
    return s.astype(str).str.split(":", n=1).str[0].str.strip()


def _label(s):
    """
    Extract the label portion from a Series that may contain 'code: label' pairs.
    
    The inverse of _code: extracts the label portion (after the colon) from values
    in the format 'code: label'. If no colon is present, returns the entire value.
    
    Args:
        s: A pandas Series where each element is either a label, or a string in the
           format 'code: label'.
    
    Returns:
        A pandas Series containing only the label portions, with leading/trailing
        whitespace removed.
    """
    return s.astype(str).str.split(":", n=1).str[-1].str.strip()


def tidy(raw, feature, region_dim="ASGS_2021"):
    """
    Transform raw SDMX-CSV API response into long-format Victoria-only rows.
    
    Converts a raw ABS API response (wide format with one row per observation) into
    a long-format panel structure with one row per (sa2, year, feature) combination.
    Automatically filters to Victoria only (SA2 codes starting with "2"). Extracts
    codes and labels from mixed 'code: label' formatted columns, and ensures the
    sa2_code_2021 column is treated as a string (not integer) to preserve leading
    zeros for correct joins.
    
    Args:
        raw: A pandas DataFrame containing raw output from abs_data().
        feature: A string name for the feature/measure being extracted (e.g.,
                 'population', 'median_income', 'seifa_irsad'). This becomes the
                 value in the 'feature' column for all output rows.
        region_dim: The name of the regional dimension column in raw (default
                    'ASGS_2021'). Some datasets use 'REGION' instead; this parameter
                    allows flexibility.
    
    Returns:
        A pandas DataFrame in long format with columns:
            - sa2_code_2021: SA2 code as a string (Victoria codes start with "2")
            - sa2_name: SA2 name
            - year: Year as an integer
            - feature: The feature name passed as input
            - value: The observation value
            - status: Always "observed" (placeholder for future use with imputed/projected values)
        
        Only rows with sa2_code_2021 starting with "2" (Victoria) are included.
    """
    region = raw[_col(raw, region_dim)]
    df = pd.DataFrame({
        "sa2_code_2021": _code(region),
        "sa2_name": _label(region),
        "year": _code(raw[_col(raw, "TIME_PERIOD")]).astype(int),
        "feature": feature,
        "value": raw["OBS_VALUE"],
        "status": "observed",
    })
    return df[df.sa2_code_2021.str.startswith("2")].reset_index(drop=True)


def fetch(name, flow, key, feature, region_dim="ASGS_2021", refresh=False, **params):
    """
    Fetch and cache a single data source from the ABS API.
    
    Fetches data from the ABS Data API, transforms it to the panel format, and
    saves it to a CSV file. If the file already exists and refresh=False, reads
    from cache instead of refetching. Prints summary statistics on fetch/read.
    
    Args:
        name: A short name for this data source (used as the output filename,
              e.g., 'erp' -> 'erp.csv').
        flow: The SDMX flow ID (e.g., 'ABS,ABS_ANNUAL_ERP_ASGS2021,1.2.0').
        key: The SDMX data key constraints (e.g., '.SA2..A').
        feature: The feature name for the 'feature' column in the output (e.g.,
                 'population', 'median_income').
        region_dim: The dimension name for regions in the API response (default
                    'ASGS_2021', but some datasets use 'REGION').
        refresh: If True, refetch from the API even if a cached file exists
                 (default False).
        **params: Additional query parameters for the API (e.g., startPeriod=2011).
    
    Returns:
        A pandas DataFrame in the panel format (sa2_code_2021, sa2_name, year,
        feature, value, status). sa2_code_2021 is dtype str.
    """
    path = OUT / f"{name}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype=DTYPES)
    df = tidy(abs_data(flow, key, **params), feature, region_dim)
    df.to_csv(path, index=False)
    print(f"{name}: {len(df)} rows, {df.sa2_code_2021.nunique()} SA2s, "
          f"{df.year.min()}-{df.year.max()}")
    return df


# --- sources ---------------------------------------------------------------

def fetch_erp(refresh=False):
    """
    Fetch Estimated Resident Population (ERP) by SA2 for 2001-2025.
    
    Retrieves annual ERP estimates at the SA2 level from the ABS. ERP values are
    as at 30 June of each calendar year. The time series covers 2001 to 2025.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='population'.
    """
    return fetch("erp", "ABS,ABS_ANNUAL_ERP_ASGS2021,1.2.0", ".SA2..A",
                 "population", refresh=refresh, startPeriod=2001)


def fetch_income(refresh=False):
    """
    Fetch median total income by SA2 from ATO/LEED series.
    
    Retrieves median total income (excluding government pensions and allowances)
    from the Australian Taxation Office Linked Employee-Employer Data (LEED).
    Year denotes the financial year ending 30 June (e.g., 2023 means FY 2022-23).
    Data available 2011-2023 only. Values are in plain AUD with no unit multiplier.
    Some SA2s may be suppressed for confidentiality.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='median_income'.
    """
    return fetch("income", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "INCOME_17.SA2..A",
                 "median_income", refresh=refresh, startPeriod=2011)


def fetch_seifa(refresh=False):
    """
    Fetch SEIFA 2021 IRSAD (Index of Relative Socio-Economic Advantage and
    Disadvantage) scores by SA2.
    
    Retrieves the SEIFA 2021 IRSAD scores for all SA2 areas. This is a single
    point-in-time measure from the 2021 Census (not an annual time series) -- it
    is a static feature and not suitable for time-series projection. Higher scores
    indicate greater relative advantage. Scores have a mean of 1000 and standard
    deviation of 100 by construction.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='seifa_irsad', containing
        a single year (2021).
    """
    return fetch("seifa", "ABS,ABS_SEIFA2021_SA2,1.0.0", ".IRSAD.SCORE",
                 "seifa_irsad", refresh=refresh, startPeriod=2021)


def fetch_working_age(refresh=False):
    """
    Fetch working-age population share (15-64 years) by SA2, annual.
    
    Retrieves the percentage of the population aged 15-64 years (working age)
    for each SA2, on an annual basis from 2011 onwards. Based on ERP estimates.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='working_age_pct'.
    """
    return fetch("working_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_17.SA2..A",
                 "working_age_pct", refresh=refresh, startPeriod=2011)


def fetch_median_age(refresh=False):
    """
    Fetch median age (in years) by SA2, annual.
    
    Retrieves the median age of the population for each SA2 on an annual basis
    from 2011 onwards. Based on ERP estimates.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='median_age'.
    """
    return fetch("median_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_23.SA2..A",
                 "median_age", refresh=refresh, startPeriod=2011)


def fetch_rented(refresh=False):
    """
    Fetch count of rented dwellings (all structures) by SA2 from Census 2021.
    
    Retrieves data from Census 2021 question G37 on dwelling tenure. Reports the
    total number of dwellings rented (all structure types: separate house, flat,
    apartment, etc.) for each SA2. This is a single point-in-time measure
    (2021 Census only), not a time series. Note: uses the 'REGION' dimension
    instead of 'ASGS_2021' in the API structure.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='dwellings_rented', containing
        a single year (2021).
    """
    return fetch("rented", "ABS,C21_G37_SA2,1.0.0", "R_T._T..SA2.",
                 "dwellings_rented", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


def fetch_dwellings_total(refresh=False):
    """
    Fetch total occupied private dwellings (all tenures) by SA2 from Census 2021.
    
    Retrieves data from Census 2021 question G37 on dwelling tenure. Reports the
    total number of occupied private dwellings (across all tenure types: owned,
    rented, etc., and all structure types) for each SA2. This is a single
    point-in-time measure (2021 Census only), not a time series. Note: uses the
    'REGION' dimension instead of 'ASGS_2021' in the API structure.
    
    Args:
        refresh: If True, refetch from the API even if cached. Default False.
    
    Returns:
        A pandas DataFrame in panel format with feature='dwellings_total', containing
        a single year (2021).
    """
    return fetch("dwellings_total", "ABS,C21_G37_SA2,1.0.0", "_T._T..SA2.",
                 "dwellings_total", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


SOURCES = [fetch_erp, fetch_income, fetch_seifa, fetch_working_age, fetch_median_age, fetch_rented, fetch_dwellings_total]


def build(refresh=False):
    """
    Fetch and concatenate all data sources into a single long-format panel.
    
    Calls each fetch_* function in SOURCES to retrieve or read cached data,
    concatenates all results into a single long-format DataFrame, and saves
    the combined panel to 'sa2_panel.csv'. Checks for and reports duplicate
    (sa2, year, feature) rows if any are found.
    
    Args:
        refresh: If True, refetch all sources from the API even if cached files
                 exist (default False). Passed to each fetch_* function.
    
    Returns:
        A pandas DataFrame combining all sources in long format, with all columns:
            - sa2_code_2021 (dtype str)
            - sa2_name
            - year
            - feature
            - value
            - status
        
        The returned DataFrame is also saved to OUT / 'sa2_panel.csv'.
    """
    panel = pd.concat([f(refresh=refresh) for f in SOURCES], ignore_index=True)
    panel.to_csv(OUT / "sa2_panel.csv", index=False)

    dupes = panel.duplicated(["sa2_code_2021", "year", "feature"]).sum()
    if dupes:
        print(f"WARNING: {dupes} duplicate (sa2, year, feature) rows")

    return panel


def load_panel():
    """
    Read the built panel from disk without refetching from the API.
    
    Loads 'sa2_panel.csv' from the output directory. Ensures sa2_code_2021 is
    read as a string to preserve leading zeros and enable correct joins.
    
    Returns:
        A pandas DataFrame in long panel format (sa2_code_2021, sa2_name, year,
        feature, value, status), with sa2_code_2021 dtype=str.
    """
    return pd.read_csv(OUT / "sa2_panel.csv", dtype=DTYPES)


if __name__ == "__main__":
    panel = build()

    print(f"{len(panel)} rows, {panel.sa2_code_2021.nunique()} SA2s")
    print(panel.groupby("feature").agg(
        rows=("value", "size"),
        sa2s=("sa2_code_2021", "nunique"),
        first=("year", "min"),
        last=("year", "max"),
        nulls=("value", lambda s: s.isna().sum()),
    ))