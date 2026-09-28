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
OUT = Path(__file__).parent / "landing"
OUT.mkdir(parents=True, exist_ok=True)

DTYPES = {"sa2_code_2021": str}


def abs_data(flow, key, **params):
    """One SDMX-CSV pull. flow='AGENCY,ID,VERSION', key='.SA2..A' (blank=all)."""
    r = requests.get(f"{BASE}/data/{flow}/{key}", headers=HEADERS,
                     params=params, timeout=300)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def _col(raw, dim):
    """Column for a dimension id, with or without the ': Label' suffix."""
    for c in raw.columns:
        if c == dim or c.startswith(dim + ":"):
            return c
    raise KeyError(f"{dim} not found in {list(raw.columns)}")


def _code(s):
    """'206041122: Brunswick' -> '206041122'. Passes through unlabelled values."""
    return s.astype(str).str.split(":", n=1).str[0].str.strip()


def _label(s):
    return s.astype(str).str.split(":", n=1).str[-1].str.strip()


def tidy(raw, feature, region_dim="ASGS_2021"):
    """SDMX-CSV -> long VICTORIA-ONLY rows."""
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
    """ERP by SA2, 2001-2025. Dims: MEASURE.REGION_TYPE.ASGS_2021.FREQ
    year = calendar year, ERP as at 30 June."""
    return fetch("erp", "ABS,ABS_ANNUAL_ERP_ASGS2021,1.2.0", ".SA2..A",
                 "population", refresh=refresh, startPeriod=2001)


def fetch_income(refresh=False):
    """Median total income (excl. govt pensions/allowances), ATO/LEED series.
    Dims: MEASURE.REGIONTYPE.ASGS_2021.FREQUENCY
    year = financial year ENDING 30 June, i.e. 2023 means 2022-23. 2019-2023 only.
    Values in plain AUD (no unit multiplier). Some SA2s suppressed."""
    return fetch("income", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "INCOME_17.SA2..A",
                 "median_income", refresh=refresh, startPeriod=2011)


def fetch_seifa(refresh=False):
    """SEIFA 2021 IRSAD score by SA2. Dims: SEIFA_MEASURE.SEIFAINDEXTYPE.ASGS_2021
    Single point (2021 Census) -- static feature, not projectable.
    Higher score = more advantaged. Mean 1000, SD 100 by construction."""
    return fetch("seifa", "ABS,ABS_SEIFA2021_SA2,1.0.0", ".IRSAD.SCORE",
                 "seifa_irsad", refresh=refresh, startPeriod=2021)


def fetch_working_age(refresh=False):
    """Working age population (15-64) as % of total, by SA2, annual. ERP_17."""
    return fetch("working_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_17.SA2..A",
                 "working_age_pct", refresh=refresh, startPeriod=2011)


def fetch_median_age(refresh=False):
    """Median age: Persons (years), by SA2, annual. ERP_23."""
    return fetch("median_age", "ABS,ABS_REGIONAL_ASGS2021,1.6.0", "ERP_23.SA2..A",
                 "median_age", refresh=refresh, startPeriod=2011)


def fetch_rented(refresh=False):
    """Census 2021 G37: dwellings Rented (total), all structures, SA2 only.
    Dims: TENLLD.STRD.REGION.REGION_TYPE.STATE — region dim is REGION, not ASGS_2021.
    Single point (2021 Census)."""
    return fetch("rented", "ABS,C21_G37_SA2,1.0.0", "R_T._T..SA2.",
                 "dwellings_rented", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


def fetch_dwellings_total(refresh=False):
    """Census 2021 G37: total occupied private dwellings, all tenures, SA2 only."""
    return fetch("dwellings_total", "ABS,C21_G37_SA2,1.0.0", "_T._T..SA2.",
                 "dwellings_total", region_dim="REGION",
                 refresh=refresh, startPeriod=2021)


SOURCES = [fetch_erp, fetch_income, fetch_seifa, fetch_working_age, fetch_median_age, fetch_rented, fetch_dwellings_total]


def build(refresh=False):
    """Concat every source into the panel."""
    panel = pd.concat([f(refresh=refresh) for f in SOURCES], ignore_index=True)
    panel.to_csv(OUT / "sa2_panel.csv", index=False)

    dupes = panel.duplicated(["sa2_code_2021", "year", "feature"]).sum()
    if dupes:
        print(f"WARNING: {dupes} duplicate (sa2, year, feature) rows")

    return panel


def load_panel():
    """Read the built panel without refetching."""
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