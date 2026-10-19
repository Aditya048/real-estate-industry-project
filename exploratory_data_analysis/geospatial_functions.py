import geopandas as gpd
from shapely.geometry import Point


def find_SA2(data, latitude, longitude):
    """Return the SA2 name containing the given coordinates.

    Args:
        data: GeoDataFrame of SA2 polygons.
        latitude: Latitude as a decimal.
        longitude: Longitude as a decimal.

    Returns:
        SA2 name string, or None if no match.
    """
    # Create point from longitude and latitude
    point = gpd.GeoDataFrame(
        geometry=[Point(longitude, latitude)],
        crs="EPSG:4326"
    )

    # Make sure the point uses the same CRS as the SA2 polygons
    point = point.to_crs(data.crs)

    # Find the SA2 containing the point
    match = gpd.sjoin(
        point,
        data[["SA2_NAME21", "geometry"]],
        how="left",
        predicate="within"
    )

    # Return SA2 name
    if match["SA2_NAME21"].notna().any():
        return match["SA2_NAME21"].iloc[0]
    else:
        return None
