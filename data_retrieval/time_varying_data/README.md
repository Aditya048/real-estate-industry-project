# Time-varying SA2 data

SA2-level features for Victoria, pulled from the ABS Data API (SDMX) and
written as a long panel.

## Run

```bash
python fetch_time_varying_data.py
```

Writes one CSV per source plus `landing/sa2_panel.csv` (the master). Results are
cached — delete the CSV or pass `refresh=True` to re-fetch. `landing/` is
gitignored; everything is reproducible from this script.

```python
from fetch_time_varying_data import load_panel
panel = load_panel()
```

## Schema

`landing/sa2_panel.csv` — one row per SA2 × year × feature.

| column | notes |
|---|---|
| `sa2_code_2021` | **string**, 9 digits, ASGS Edition 3 (2021). Read with `dtype=str` or it becomes an int and stops joining. |
| `sa2_name` | |
| `year` | int — see year basis below |
| `feature` | see table |
| `value` | |
| `status` | `observed` for everything currently; reserved for `interpolated` / `projected` |

Victoria only (SA2 codes starting with `2`), filtered inside `tidy()`.

## Features

| feature | source | coverage | basis | time-varying? |
|---|---|---|---|---|
| `population` | `ABS_ANNUAL_ERP_ASGS2021` | 2001–2025 annual | calendar yr, ERP at 30 June | yes |
| `median_income` | `ABS_REGIONAL_ASGS2021` `INCOME_17` | 2019–2023 annual | **financial yr ending 30 June** (2023 = 2022-23) | yes |
| `median_age` | `ABS_REGIONAL_ASGS2021` `ERP_23` | 2020–2024 annual | calendar yr | yes |
| `working_age_pct` | `ABS_REGIONAL_ASGS2021` `ERP_17` | 2020–2024 annual | calendar yr | yes |
| `seifa_irsad` | `ABS_SEIFA2021_SA2` | 2021 only | Census | **static** |
| `dwellings_rented` | `C21_G37_SA2` | 2021 only | Census | **static** |
| `dwellings_total` | `C21_G37_SA2` | 2021 only | Census | **static** |

Population is the only long series. The rest are 5 points or fewer — relevant to
what stage-2 forecasting can actually fit.

## Gotchas

- **ASGS Edition 3 (2021) throughout.** Edition 4 (2026) exists — do not use it.
  Every dataset here is published on 2021 SA2s.
- **Dimension names vary by dataflow.** Region is `ASGS_2021` in most flows but
  `REGION` in the Census ones; measure is `MEASURE`, `SEIFA_MEASURE` or `TENLLD`.
  `_col()` matches on prefix so this mostly self-resolves; pass `region_dim=` when
  it doesn't.
- **Key positions follow CSV column order**, ignoring `DATAFLOW`, `OBS_VALUE` and
  attributes. Probe a flow before writing its key.
- **Verify which code is which.** `ERP_17` is working-age %, `ERP_23` is median
  age — the reverse of what the labels suggest. Always print a sample value.

## Known data issues

Drop before modelling — no geography, no properties will geocode there:

- `297979799` Migratory - Offshore - Shipping (Vic.)
- `299999499` No usual address (Vic.)

Real polygons but near-zero residents, so features are patchy (expect NaNs):
Alps - East, Alps - West, Lake King, West Melbourne - Industrial,
Royal Botanic Gardens Victoria, Wilsons Promontory, Essendon Airport,
Moorabbin Airport, Braeside.

11 `seifa_irsad` nulls — ABS suppression for the above. Expected, not an error.

Some SA2s have zero dwellings, so guard `dwellings_rented / dwellings_total`
against divide-by-zero.

## Not done yet

- VIF2023 SA2 population projections to 2036 (xlsx, not API) — no future values
  for anything without this
- 2016/2011 backfill for the Census-point features (needs ABS correspondence files)
- Year-grid decision: interpolation and hold-constant rules, and populating
  `status`. Blocked on what the forecasting models need as input.