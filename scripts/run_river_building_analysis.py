from pathlib import Path

from packages.geo_tools.vector import (
    load_layer,
    select_rivers,
    select_buildings,
    reproject_to_metric,
    buffer_geometry,
    spatial_intersection,
)


DATASET = Path(
    "data/raw/mula-pavana-river/mula-pavana-river.gpkg"
)

OUTPUT_DIR = Path("data/processed/mula-pavana")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("Loading rivers...")
    rivers = load_layer(
        str(DATASET),
        "lines",
    )

    print("Selecting Mula + Pavana...")
    rivers = select_rivers(rivers)

    print(f"River segments: {len(rivers)}")

    print("Loading buildings...")
    buildings = load_layer(
        str(DATASET),
        "multipolygons",
    )

    print("Selecting buildings...")
    buildings = select_buildings(buildings)

    print(f"Buildings: {len(buildings)}")

    print("Reprojecting to metric CRS...")
    rivers_metric = reproject_to_metric(rivers)
    buildings_metric = buildings.to_crs(rivers_metric.crs)

    print(f"Metric CRS: {rivers_metric.crs}")

    print("Creating 500m river buffer...")
    river_buffer = buffer_geometry(
        rivers_metric,
        500,
    )

    print("Finding buildings inside buffer...")
    nearby_buildings = spatial_intersection(
        buildings_metric,
        river_buffer,
    )

    print(
        f"Buildings within 500m: "
        f"{len(nearby_buildings)}"
    )

    output = OUTPUT_DIR / "buildings_within_500m.gpkg"

    nearby_buildings.to_file(
        output,
        driver="GPKG",
    )

    print(f"Saved: {output}")


if __name__ == "__main__":
    main()