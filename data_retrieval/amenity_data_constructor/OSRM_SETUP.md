# Amenity route distances — setup

Computes road/path distances from each listing to nearby schools, stations,
stops, parks, and supermarkets via a **local OSRM** server.

Script: `add_amenity_distances.py`  
Run from the **repository root**. Outputs land in `data/amenity_data/`.

---

## Prerequisites checklist

| Item | Where it goes | How to get it |
|---|---|---|
| Listings CSV | `data/properties_db/properties.csv` | Run the scrape orchestrator (or export from `properties.db`) |
| Schools CSV | `data/amenity_data/dv346-schoollocations2023.csv` | Auto-downloaded on first run |
| GTFS zip | `data/amenity_data/gtfs.zip` | Auto-downloaded on first run |
| OSM extract | `data/osrm/melbourne.osm.pbf` | BBBike (below) — **not** committed |
| OSRM car server | `localhost:5000` (or remapped) | Docker steps below |
| OSRM foot server | `localhost:5001` (or remapped) | Docker steps below |

Parks and supermarkets are pulled from Overpass at runtime (needs network).

Do **not** commit GTFS, schools, OSM extracts, OSRM graphs, or amenity output CSVs.

---

## 1. Properties CSV

```bash
# After scraping:
ls data/properties_db/properties.csv
```

Required columns: `id`, `url`, `latitude`, `longitude`, `suburb`.

---

## 2. OSM extract → `data/osrm/`

Geofabrik’s Australia extract is huge. Prefer a Victoria/Melbourne extract from
[BBBike](https://extract.bbbike.org/): choose Melbourne (or draw a box covering
your suburbs) → `.osm.pbf` → download when emailed.

```bash
mkdir -p data/osrm
# save the download as:
#   data/osrm/melbourne.osm.pbf
```

---

## 3. Build + run OSRM (car on :5000, foot on :5001)

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) running.
All commands from the **repository root**.

### Car profile

```bash
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-extract -p /opt/car.lua /data/melbourne.osm.pbf
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-partition /data/melbourne.osrm
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-customize /data/melbourne.osrm
```

### Foot profile (separate copy — extract mutates the graph for the profile)

```bash
cp data/osrm/melbourne.osm.pbf data/osrm/melbourne-foot.osm.pbf
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-extract -p /opt/foot.lua /data/melbourne-foot.osm.pbf
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-partition /data/melbourne-foot.osrm
docker run -t -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-customize /data/melbourne-foot.osrm
```

### Start both servers (leave these running)

Use `--max-table-size 10000` so batched `/table/` calls from the script succeed:

```bash
docker run -t -i -p 5000:5000 -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-routed --algorithm mld --max-table-size 10000 /data/melbourne.osrm

docker run -t -i -p 5001:5000 -v "${PWD}/data/osrm:/data" osrm/osrm-backend \
  osrm-routed --algorithm mld --max-table-size 10000 /data/melbourne-foot.osrm
```

**macOS note:** port **5000** is often taken by AirPlay Receiver (`ControlCenter`).
If car routing fails or something non-OSRM answers on `:5000`, either disable
AirPlay Receiver (System Settings → General → AirDrop & Handoff) or map a free
host port, e.g. `-p 5002:5000`, and set in `add_amenity_distances.py`:

```python
OSRM_CAR_URL = "http://localhost:5002"
```

### Smoke-test OSRM

```bash
curl "http://localhost:5000/route/v1/driving/144.9631,-37.8136;144.9670,-37.7999"
curl "http://localhost:5001/route/v1/foot/144.9631,-37.8136;144.9670,-37.7999"
```

Both should return JSON with a `"routes"` key.

---

## 4. Run the Python script

Keep both OSRM containers up. In a third terminal (repo root, venv active):

```bash
# Always smoke-test first — writes a separate sample file
python data_retrieval/amenity_data_constructor/add_amenity_distances.py --sample 50

# Full run
python data_retrieval/amenity_data_constructor/add_amenity_distances.py
```

Tuning:

```bash
python data_retrieval/amenity_data_constructor/add_amenity_distances.py \
  --sample 200 --workers 12 --batch-size 60
```

Output: `data/amenity_data/listings_with_amenity_distances.csv`  
(or `*_sample{N}.csv` in sample mode).

The script preflights the properties CSV and both OSRM endpoints before doing
heavy work. Use `--skip-preflight` only if you know what you’re doing.

---

## Known limitations

- **Count columns** (`school_count_*`, etc.) cap candidates per property at 50
  for router load — dense areas may slightly undercount.
- Schools / parks / supermarkets use **car** routing; tram / bus use **foot**.
- OSM park/supermarket points are node or way centroids, not necessarily
  entrances.
- A Melbourne-sized extract may not cover regional VIC listings → those rows
  can be NaN for route distances.
