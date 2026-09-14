import geopandas as gpd


def load_layer(path: str, layer: str) -> gpd.GeoDataFrame:
    """Load a GeoPackage layer."""
    return gpd.read_file(path, layer=layer)


def select_rivers(
    rivers: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Select Mula and Pavana river segments."""
    return rivers[
        (rivers["waterway"] == "river")
        & rivers["name"].isin(["Mula", "Pavana", "Pavana River"])
    ].copy()


def select_buildings(
    buildings: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Select mapped building features."""
    return buildings[buildings["building"].notna()].copy()


def reproject_to_metric(
    gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Reproject geographic data to an appropriate metric CRS."""
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS")

    metric_crs = gdf.estimate_utm_crs()

    if metric_crs is None:
        raise ValueError("Could not determine a suitable metric CRS")

    return gdf.to_crs(metric_crs)


def buffer_geometry(
    gdf: gpd.GeoDataFrame,
    distance_m: float,
) -> gpd.GeoDataFrame:
    """Create a metric buffer around geometries."""
    if distance_m < 0:
        raise ValueError("Buffer distance must be non-negative")

    result = gdf.copy()
    result["geometry"] = result.geometry.buffer(distance_m)

    return result


def spatial_intersection(
    target: gpd.GeoDataFrame,
    mask: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Return target features intersecting the mask geometry."""
    mask_geometry = mask.geometry.union_all()

    return target[target.geometry.intersects(mask_geometry)].copy()