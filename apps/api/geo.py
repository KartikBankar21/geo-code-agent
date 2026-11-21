import tempfile
from pathlib import Path
from urllib.parse import urlparse
import boto3
from fastapi import APIRouter, HTTPException, Response

from apps.api.config import (
    resolve_data_path,
    UnsafePathError,
    MAX_GEOJSON_FEATURES,
)
from packages.tools.geospatial import list_layers as _list_layers

router = APIRouter(prefix="/api/geo", tags=["geo"])


def _download_s3_to_temp(s3_uri: str) -> Path:
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    suffix = Path(key).suffix or ".gpkg"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    s3 = boto3.client("s3")
    s3.download_file(bucket, key, tmp.name)
    return Path(tmp.name)


@router.get("")
def geojson(path: str, layer: str | None = None):
    import geopandas as gpd

    temp_file: Path | None = None

    if path.startswith("s3://"):
        try:
            temp_file = _download_s3_to_temp(path)
            resolved = temp_file
        except Exception as e:
            raise HTTPException(404, f"Could not fetch S3 artifact '{path}': {e}")
    else:
        try:
            resolved = resolve_data_path(path)
        except UnsafePathError as e:
            raise HTTPException(400, str(e))

        if not resolved.exists():
            raise HTTPException(404, f"File not found: {path}")

    try:
        read_kwargs = {"layer": layer} if layer else {}
        gdf = gpd.read_file(resolved, **read_kwargs)
    except Exception as e:
        raise HTTPException(400, f"Could not read '{path}': {e}")
    finally:
        if temp_file is not None:
            temp_file.unlink(missing_ok=True)

    truncated = False
    if len(gdf) > MAX_GEOJSON_FEATURES:
        gdf = gdf.iloc[:MAX_GEOJSON_FEATURES]
        truncated = True

    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    body = gdf.to_json()
    if truncated:
        body = body[:-1] + f', "truncated": true, "feature_limit": {MAX_GEOJSON_FEATURES}}}'

    return Response(content=body, media_type="application/geo+json")