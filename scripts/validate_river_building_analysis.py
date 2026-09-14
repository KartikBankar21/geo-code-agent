import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import box

from packages.geo_tools.vector import (
    load_layer,
    select_rivers,
    select_buildings,
    reproject_to_metric,
    buffer_geometry,
)


DATASET = "data/raw/mula-pavana-river/mula-pavana-river.gpkg"

AOI = box(
    73.715,
    18.544,
    73.867,
    18.650,
)

OUTPUT = "data/processed/mula-pavana/validation.png"


def main():
    # Load source data
    rivers = load_layer(DATASET, "lines")
    buildings = load_layer(DATASET, "multipolygons")

    # Select semantic features
    rivers = select_rivers(rivers)
    buildings = select_buildings(buildings)

    # Restrict both to our AOI
    rivers = rivers[rivers.geometry.intersects(AOI)].copy()
    buildings = buildings[buildings.geometry.intersects(AOI)].copy()

    # Reproject to metres
    rivers_metric = reproject_to_metric(rivers)
    buildings_metric = buildings.to_crs(rivers_metric.crs)

    # Create 500m buffer
    buffer = buffer_geometry(rivers_metric, 500)

    # Select buildings inside buffer
    river_buffer = buffer.geometry.union_all()

    nearby = buildings_metric[
        buildings_metric.geometry.intersects(river_buffer)
    ]

    # Plot
    fig, ax = plt.subplots(figsize=(12, 10))

    buildings_metric.plot(
        ax=ax,
        linewidth=0.1,
        alpha=0.25,
    )

    nearby.plot(
        ax=ax,
        linewidth=0.2,
        alpha=0.5,
    )

    buffer.plot(
        ax=ax,
        alpha=0.2,
    )

    rivers_metric.plot(
        ax=ax,
        linewidth=2,
    )

    ax.set_title(
        "Mula + Pavana Rivers — 500m Building Analysis"
    )

    ax.set_axis_off()

    plt.tight_layout()
    plt.savefig(
        OUTPUT,
        dpi=200,
        bbox_inches="tight",
    )

    print(f"Saved validation map: {OUTPUT}")


if __name__ == "__main__":
    main()