import geopandas as gpd
from shapely.geometry import Point
def find_SA2(data, latitude, longitude):
    """
    This function takes in latitude and longitude coordinates 
    and outputs the Statistical Area Level 2 (SA2) that contains 
    the point.

    Args:
        data: The geospatial data containing the SA2 polygons
        latitude: Latitude coordinate as a decimal
        longitude: Longitidue coordinate as a decimal

    Returns:
        String containing name of SA2 area according to ABS.
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
