from pathlib import Path

import geopandas as gpd
import pyogrio


DATA_DIR = Path("data/raw")


def list_layers(path: str) -> list[str]:
    """
    List available layers in a geospatial dataset.
    """

    dataset_path = Path(path)

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {dataset_path}"
        )

    layers = pyogrio.list_layers(dataset_path)

    return [
        layer[0]
        for layer in layers
    ]


def inspect_layer(
    path: str,
    layer: str | None = None,
) -> dict:
    """
    Inspect a geospatial layer and return useful metadata plus a few
    compact sample attribute rows so the agent sees actual column values.
    """

    dataset_path = Path(path)

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {dataset_path}"
        )

    kwargs = {}

    if layer is not None:
        kwargs["layer"] = layer

    gdf = gpd.read_file(
        dataset_path,
        **kwargs,
    )

    non_geom_cols = [c for c in gdf.columns if c != gdf.geometry.name]
    sample_df = gdf[non_geom_cols].head(3)
    sample_rows = []
    for record in sample_df.to_dict(orient="records"):
        compact = {
            k: (str(v)[:80] if v is not None else None)
            for k, v in record.items()
        }
        sample_rows.append(compact)

    return {
        "rows": len(gdf),
        "columns": list(gdf.columns),
        "crs": str(gdf.crs),
        "geometry_type": (
            gdf.geometry.geom_type
            .value_counts()
            .to_dict()
        ),
        "bounds": gdf.total_bounds.tolist(),
        "sample_rows": sample_rows,
    }
