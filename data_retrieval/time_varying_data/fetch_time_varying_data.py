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
    """Fetch an ABS Data API table as a DataFrame (SDMX-CSV).

    Args:
        flow: Flow id as 'AGENCY,ID,VERSION'.
        key: Period-separated dimension key constraints.
        **params: Extra query parameters (e.g. startPeriod).

    Returns:
        Raw API response as a DataFrame.
    """
    response = requests.get(f"{BASE}/data/{flow}/{key}", headers=HEADERS,
                     params=params, timeout=300)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _col(raw, dim):
    """Find a column name matching a dimension id, with or without a label suffix.

    Args:
        raw: API response DataFrame.
        dim: Dimension id to match.

    Returns:
        Matching column name.

    Raises:
        KeyError: If no matching column exists.
    """
    for c in raw.columns:
        if c == dim or c.startswith(dim + ":"):
            return c
    raise KeyError(f"{dim} not found in {list(raw.columns)}")


def _code(s):
    """Extract the code side of 'code: label' values in a Series."""
    return s.astype(str).str.split(":", n=1).str[0].str.strip()


def _label(s):
    """Extract the label side of 'code: label' values in a Series."""
    return s.astype(str).str.split(":", n=1).str[-1].str.strip()


def tidy(raw, feature, region_dim="ASGS_2021"):
    """Convert a raw ABS response into long-format Victoria SA2 rows.

    Args:
        raw: DataFrame from abs_data().
        feature: Feature name for the output feature column.
        region_dim: Region dimension column name.

    Returns:
        Long-format DataFrame filtered to Victorian SA2s.
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
    """Fetch one ABS source, cache it as CSV, and return the panel rows.

    Args:
        name: Cache filename stem.
        flow: SDMX flow id.
        key: SDMX key constraints.
        feature: Feature name for output rows.
        region_dim: Region dimension column name.
        refresh: If True, ignore the cache and refetch.
        **params: Extra API query parameters.

    Returns:
        Panel-format DataFrame for this source.
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
    """Fetch estimated resident population by SA2 (2001-2025)."""
    return fetch("erp", "ABS,ABS_ANNUAL_ERP_ASGS2021,1.2.0", ".SA2..A",
                 "population", refresh=refresh, startPeriod=2001)


def fetch_income(refresh=False):
    """Fetch median total income by SA2 from ATO/LEED (2011-2023)."""
    return fetch("income", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "INCOME_17.SA2..A",
                 "median_income", refresh=refresh, startPeriod=2011)


def fetch_seifa(refresh=False):
    """Fetch SEIFA 2021 IRSAD scores by SA2."""
    return fetch("seifa", "ABS,ABS_SEIFA2021_SA2,1.0.0", ".IRSAD.SCORE",
                 "seifa_irsad", refresh=refresh, startPeriod=2021)


def fetch_working_age(refresh=False):
    """Fetch working-age population share (15-64) by SA2."""
    return fetch("working_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_17.SA2..A",
                 "working_age_pct", refresh=refresh, startPeriod=2011)


def fetch_median_age(refresh=False):
    """Fetch median age by SA2."""
    return fetch("median_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_23.SA2..A",
                 "median_age", refresh=refresh, startPeriod=2011)


def fetch_rented(refresh=False):
    """Fetch Census 2021 rented dwelling counts by SA2."""
    return fetch("rented", "ABS,C21_G37_SA2,1.0.0", "R_T._T..SA2.",
                 "dwellings_rented", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


def fetch_dwellings_total(refresh=False):
    """Fetch Census 2021 total occupied dwelling counts by SA2."""
    return fetch("dwellings_total", "ABS,C21_G37_SA2,1.0.0", "_T._T..SA2.",
                 "dwellings_total", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


SOURCES = [fetch_erp, fetch_income, fetch_seifa, fetch_working_age, fetch_median_age, fetch_rented, fetch_dwellings_total]


def build(refresh=False):
    """Fetch all sources, concatenate them, and write sa2_panel.csv.

    Args:
        refresh: If True, refetch every source from the API.

    Returns:
        Combined long-format panel DataFrame.
    """
    panel = pd.concat([f(refresh=refresh) for f in SOURCES], ignore_index=True)
    panel.to_csv(OUT / "sa2_panel.csv", index=False)

    dupes = panel.duplicated(["sa2_code_2021", "year", "feature"]).sum()
    if dupes:
        print(f"WARNING: {dupes} duplicate (sa2, year, feature) rows")

    return panel


def load_panel():
    """Read sa2_panel.csv from disk without calling the API."""
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