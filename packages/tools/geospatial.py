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
    Inspect a geospatial layer and return useful metadata.
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
    }


if __name__ == "__main__":
    path = (
        "data/raw/"
        "mula-pavana-river/"
        "mula-pavana-river.gpkg"
    )

    print("Layers:")
    print(list_layers(path))

    print()
    print("Inspecting buildings:")

    print(
        inspect_layer(
            path,
            layer="multipolygons",
        )
    )
