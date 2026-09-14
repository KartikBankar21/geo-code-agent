from fastapi import APIRouter, HTTPException, Response

from apps.api.config import (
    resolve_data_path,
    UnsafePathError,
    MAX_GEOJSON_FEATURES,
)
from packages.tools.geospatial import list_layers as _list_layers

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("/layers")
def geo_layers(path: str):
    """List layers for any file under data/ (raw input or output artifact)."""

    try:
        resolved = resolve_data_path(path)
    except UnsafePathError as e:
        raise HTTPException(400, str(e))

    if not resolved.exists():
        raise HTTPException(404, f"File not found: {path}")

    try:
        return {"layers": _list_layers(str(resolved))}
    except Exception as e:
        # Single-layer formats (e.g. plain GeoJSON) don't have named
        # layers - report a single implicit layer instead of erroring.
        if resolved.suffix.lower() in {".geojson", ".json"}:
            return {"layers": [resolved.stem]}

        raise HTTPException(400, f"Could not list layers: {e}")


@router.get("")
def geojson(path: str, layer: str | None = None):
    """
    Convert a vector file (or one layer of it) to GeoJSON in EPSG:4326,
    ready for a Leaflet map.

    `path` is project-root-relative, e.g.
    'data/raw/mula-pavana-river/mula-pavana-river.gpkg' or
    'data/outputs/buildings_near_mula_river.gpkg' - the same strings
    returned by GET /api/datasets (host_path) and in a task's
    execution_result.artifacts.
    """

    try:
        resolved = resolve_data_path(path)
    except UnsafePathError as e:
        raise HTTPException(400, str(e))

    if not resolved.exists():
        raise HTTPException(404, f"File not found: {path}")

    # Imported lazily: geopandas is a heavy import and most API endpoints
    # (task submission, dataset listing) don't need it.
    import geopandas as gpd

    try:
        read_kwargs = {"layer": layer} if layer else {}
        gdf = gpd.read_file(resolved, **read_kwargs)
    except Exception as e:
        raise HTTPException(400, f"Could not read '{path}': {e}")

    truncated = False

    if len(gdf) > MAX_GEOJSON_FEATURES:
        gdf = gdf.iloc[:MAX_GEOJSON_FEATURES]
        truncated = True

    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    body = gdf.to_json()

    if truncated:
        # to_json() returns a plain GeoJSON string; splice in a property
        # noting the truncation rather than re-parsing/re-serializing it.
        body = body[:-1] + f', "truncated": true, "feature_limit": {MAX_GEOJSON_FEATURES}}}'

    return Response(content=body, media_type="application/geo+json")
