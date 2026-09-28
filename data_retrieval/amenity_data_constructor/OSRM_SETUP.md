# One-time OSRM setup (car + foot routing)

## 1. Get an OSM extract covering Melbourne/Victoria

Geofabrik only publishes Australia at the whole-country level, which is a
large file and slow to process on a laptop. Get a smaller, Victoria-sized
extract instead from BBBike's custom extract service:
https://extract.bbbike.org/  -> choose "Melbourne" as a preset, or draw a
box covering all your suburbs -> request the .osm.pbf format -> you'll get
an email with a download link once it's ready (usually a few minutes).

Save the file as `data/melbourne.osm.pbf`.

## 2. Build the CAR routing engine (port 5000)

Run these four commands in your project folder (needs Docker Desktop installed
and running):

```bash
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/melbourne.osm.pbf
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-partition /data/melbourne.osrm
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-customize /data/melbourne.osrm
docker run -t -i -p 5000:5000 -v "${PWD}/data:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/melbourne.osrm
```

Leave that last command running in its own terminal tab - it's your car
routing server. Test it:
```bash
curl "http://localhost:5000/route/v1/driving/144.9631,-37.8136;144.9670,-37.7999"
```

## 3. Build the FOOT (walking) routing engine (port 5001)

The extract/partition/customize steps modify the .pbf in place with a
profile-specific graph, so build the foot version into a SEPARATE copy of
the file to avoid clobbering the car one:

```bash
cp data/melbourne.osm.pbf data/melbourne-foot.osm.pbf
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-extract -p /opt/foot.lua /data/melbourne-foot.osm.pbf
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-partition /data/melbourne-foot.osrm
docker run -t -v "${PWD}/data:/data" osrm/osrm-backend osrm-customize /data/melbourne-foot.osrm
docker run -t -i -p 5001:5000 -v "${PWD}/data:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/melbourne-foot.osrm
```

Note the `-p 5001:5000` - inside the container it's still port 5000, we're
just mapping it to 5001 on your machine so it doesn't clash with the car
server. Test it:
```bash
curl "http://localhost:5001/route/v1/foot/144.9631,-37.8136;144.9670,-37.7999"
```

## 4. One setting to add now that the script batches requests

The Python script now sends up to ~40 properties x ~300 candidate
destinations in a single request (rather than 1 property at a time), so
raise OSRM's table-size limit when starting the routed servers - the
default is usually fine, but it's worth being explicit:

```bash
docker run -t -i -p 5000:5000 -v "${PWD}/data:/data" osrm/osrm-backend osrm-routed --algorithm mld --max-table-size 10000 /data/melbourne.osrm
docker run -t -i -p 5001:5000 -v "${PWD}/data:/data" osrm/osrm-backend osrm-routed --algorithm mld --max-table-size 10000 /data/melbourne-foot.osrm
```

## 5. Leave both running while you run the Python script

You'll have two terminal tabs occupied by the car and foot servers. Open a
THIRD terminal tab to actually run `add_amenity_distances.py`.

Both servers need to stay up for the whole run - if either one isn't
responding, the Python script will fail on that amenity category.

## 6. Test small before running the full dataset

Before committing to the full 10,000-row run, smoke-test the whole
pipeline (download -> load -> route -> output) against a small random
sample:

```bash
python add_amenity_distances.py --sample 50
```

This writes to a separate `*_sample50.csv` file, so it can't clobber your
real output. Check that file looks sane (plausible distances, no columns
full of NaN) before running the full thing:

```bash
python add_amenity_distances.py
```

If you want to tune performance, `--workers` (thread pool size, default
8) and `--batch-size` (properties per OSRM call, default 40) are both
adjustable from the command line, e.g.:

```bash
python add_amenity_distances.py --sample 200 --workers 12 --batch-size 60
```

