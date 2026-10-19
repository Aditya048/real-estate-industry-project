# MAST30034 — Real Estate Industry Project (Group 4)

> **Summary Notebooks**
>
> These **three** notebooks are the project’s **summary of outcomes**. They are the  
> modelling / analysis deliverables for clients and stakeholders.
>
> 1. [`modelling/rfr.ipynb`](modelling/rfr.ipynb) : model training and projected rent analysis
> 2. [`modelling/liveability/liveability_exploration.ipynb`](modelling/liveability/liveability_exploration.ipynb) : amenity access vs rent / CBD tradeoff
> 3. [`modelling/liveability/rent_location_exploration.ipynb`](modelling/liveability/rent_location_exploration.ipynb) : rent patterns by SA2 / suburb

Victorian rental listings pipeline: scrape rent.com.au → enrich with ABS geospatial /
demographic data (and optional amenity route distances) → clean for modelling.

**Run all Python commands from the repository root**

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` is a full venv freeze for reproducibility. Docker Desktop is only
needed for the optional amenity / OSRM stage.

---

## Data layout

All regenerable artefacts live under `data/`. Do **not** commit large local files.

| Path | Tracked? | Role |
|---|---|---|
| `data/VIC_postcodes.csv` | yes | Scrape input (suburb / postcode list) |
| `data/samples/` | yes | Sample listing HTML for parser tests |
| `data/properties_db/` | no | Scrape SQLite DB + `properties.csv` export |
| `data/geospatial_data/` | no | ABS SA2 2021 shapefile (+ optional Vic extract) |
| `data/sa2_panel/` | no | ABS SDMX long panel CSVs |
| `data/amenity_data/` | no | Schools / GTFS caches + amenity distance outputs |
| `data/osrm/` | no | OSM extract + OSRM routing graphs |
| `data/forecasting/` | no | Forecasting notebook downloads / cleaned exports |
| `data/preprocessed_data/` | no | Cleaned modelling table |

Empty folders are kept in git via `.gitkeep`.

---

## End-to-end pipeline

### 1. Scrape listings → `data/properties_db/`

```bash
python -m data_retrieval.scraping_pipeline.orchestrator
# smoke test a few suburbs first:
python -m data_retrieval.scraping_pipeline.orchestrator --limit 5
```

Writes `properties.db` and exports `properties.csv`.

### 2. Download SA2 boundaries → `data/geospatial_data/`

```bash
python -m data_retrieval.sa2_data
```

### 3. Fetch ABS SA2 panel → `data/sa2_panel/`

```bash
python data_retrieval/time_varying_data/fetch_time_varying_data.py
```

See [data_retrieval/time_varying_data/README.md](data_retrieval/time_varying_data/README.md).

### 4. (Optional) Amenity route distances → `data/amenity_data/`

Requires local OSRM (car + foot). One-time setup:

→ [data_retrieval/amenity_data_constructor/OSRM_SETUP.md](data_retrieval/amenity_data_constructor/OSRM_SETUP.md)

```bash
python data_retrieval/amenity_data_constructor/add_amenity_distances.py --sample 50
python data_retrieval/amenity_data_constructor/add_amenity_distances.py
```

Reads `data/properties_db/properties.csv`. Schools and GTFS download automatically if missing.

### 5. Preprocess → `data/preprocessed_data/`

Open `preprocessing/properties_data_cleaning.ipynb` (kernel cwd = that folder).
It reads `../data/properties_db/properties.csv` and writes
`../data/preprocessed_data/cleaned_properties.csv`.

### 6. EDA (exploratory)

- `exploratory_data_analysis/geospatial_eda.ipynb`
- `exploratory_data_analysis/geospatial_demo.ipynb`

(`geospatial.ipynb` is stale — use the notebooks above.)

### 7. Forecasting notebooks → `data/forecasting/`

Notebooks under `data_retrieval/Forecasting_Data/` write downloads and cleaned
CSVs to `data/forecasting/`.

---

## What not to commit

- `venv/`, `__pycache__/`, `*.log`
- Anything under `data/properties_db/`, `data/geospatial_data/`, `data/sa2_panel/`,
`data/amenity_data/`, `data/osrm/`, `data/forecasting/`, `data/preprocessed_data/`
except `.gitkeep`
- `*.osm.pbf`, `*.osrm*`

---

## Module docs

| Module | Doc |
|---|---|
| HTML scraper | [data_retrieval/scraping_pipeline/html_retrieval/documentation.md](data_retrieval/scraping_pipeline/html_retrieval/documentation.md) |
| ABS panel | [data_retrieval/time_varying_data/README.md](data_retrieval/time_varying_data/README.md) |
| Amenity / OSRM | [data_retrieval/amenity_data_constructor/OSRM_SETUP.md](data_retrieval/amenity_data_constructor/OSRM_SETUP.md) |

### Scrape pipeline owners (historical)

| Module | Owner |
|---|---|
| `url_retrieval` | Sean |
| `html_retrieval` | Aydin |
| `html_parser` | Aditya |
| geospatial EDA | Ben |
