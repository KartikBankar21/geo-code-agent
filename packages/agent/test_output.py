from pathlib import Path

import geopandas as gpd


SOURCE = Path("data/raw/mula-pavana-river/mula-pavana-river.gpkg")
OUTPUT = Path("data/outputs/buildings_near_mula_river.gpkg")

OUTPUT_LAYER = "buildings_near_mula_river"

# The agent-generated result is supposed to contain buildings
# within 500 m of the Mula River.


def main():
    print("=" * 70)
    print("GEOPACKAGE OUTPUT VALIDATION")
    print("=" * 70)

    # ------------------------------------------------------------
    # 1. Check files exist
    # ------------------------------------------------------------

    print("\n[1] Checking files...")

    if not SOURCE.exists():
        raise FileNotFoundError(f"Source dataset not found: {SOURCE}")

    if not OUTPUT.exists():
        raise FileNotFoundError(f"Output dataset not found: {OUTPUT}")

    print(f"Source: {SOURCE}")
    print(f"Output: {OUTPUT}")

    # ------------------------------------------------------------
    # 2. Inspect output layers
    # ------------------------------------------------------------

    print("\n[2] Inspecting output layers...")

    output_layers = gpd.list_layers(OUTPUT)

    print(output_layers)

    if len(output_layers) == 0:
        raise RuntimeError("Output GeoPackage contains no layers.")

    # The agent may use a different layer name depending on the code.
    # Use the first layer rather than assuming the name.
    output_layer = output_layers.iloc[0]["name"]

    print(f"Using output layer: {output_layer}")

    buildings = gpd.read_file(
        OUTPUT,
        layer=output_layer,
    )

    # ------------------------------------------------------------
    # 3. Basic output information
    # ------------------------------------------------------------

    print("\n[3] Output information...")

    print(f"Feature count : {len(buildings):,}")
    print(f"CRS           : {buildings.crs}")
    print(f"Geometry types: {buildings.geometry.geom_type.value_counts().to_dict()}")

    print("\nColumns:")
    print(list(buildings.columns))

    print("\nBounds:")
    print(buildings.total_bounds)

    # ------------------------------------------------------------
    # 4. Geometry validity
    # ------------------------------------------------------------

    print("\n[4] Checking geometry validity...")

    invalid = (~buildings.geometry.is_valid).sum()
    empty = buildings.geometry.is_empty.sum()
    null = buildings.geometry.isna().sum()

    print(f"Invalid geometries : {invalid:,}")
    print(f"Empty geometries   : {empty:,}")
    print(f"Null geometries    : {null:,}")

    if invalid == 0 and empty == 0 and null == 0:
        print("✓ All output geometries are valid and non-empty.")
    else:
        print("⚠ Geometry problems detected.")

    # ------------------------------------------------------------
    # 5. Load source river layer
    # ------------------------------------------------------------

    print("\n[5] Loading source river data...")

    lines = gpd.read_file(
        SOURCE,
        layer="lines",
    )

    print(f"Source line features: {len(lines):,}")
    print(f"Source CRS          : {lines.crs}")

    # ------------------------------------------------------------
    # 6. Identify Mula River
    # ------------------------------------------------------------

    print("\n[6] Identifying Mula River features...")

    if "waterway" not in lines.columns:
        raise RuntimeError(
            "Expected 'waterway' column not found in source lines layer."
        )

    if "name" not in lines.columns:
        raise RuntimeError(
            "Expected 'name' column not found in source lines layer."
        )

    mula = lines[
        lines["waterway"].notna()
        & lines["name"].fillna("").str.contains(
            "Mula",
            case=False,
            na=False,
        )
    ].copy()

    print(f"Mula River features found: {len(mula):,}")

    if mula.empty:
        raise RuntimeError("Could not identify any Mula River features.")

    # ------------------------------------------------------------
    # 7. Reproject both datasets to metric CRS
    # ------------------------------------------------------------

    print("\n[7] Reprojecting to EPSG:32643...")

    mula = mula.to_crs(epsg=32643)
    buildings_metric = buildings.to_crs(epsg=32643)

    print(f"Mula CRS      : {mula.crs}")
    print(f"Buildings CRS : {buildings_metric.crs}")

    # ------------------------------------------------------------
    # 8. Create independent 500 m buffer
    # ------------------------------------------------------------

    print("\n[8] Creating independent 500 m river buffer...")

    river_geometry = mula.geometry.union_all()

    buffer_500m = river_geometry.buffer(500)

    print(f"Buffer area: {buffer_500m.area:,.2f} m²")

    # ------------------------------------------------------------
    # 9. Independently test every output building
    # ------------------------------------------------------------

    print("\n[9] Testing output buildings against 500 m buffer...")

    within_buffer = buildings_metric.geometry.within(buffer_500m)

    inside_count = within_buffer.sum()
    outside_count = (~within_buffer).sum()

    print(f"Buildings inside 500 m : {inside_count:,}")
    print(f"Buildings outside 500 m: {outside_count:,}")

    if outside_count == 0:
        print("✓ Every output building is within 500 m of the Mula River.")
    else:
        print("⚠ Some output buildings are outside the 500 m buffer.")

        outside = buildings_metric.loc[~within_buffer]

        print("\nFirst outside features:")
        print(outside.head())

    # ------------------------------------------------------------
    # 10. Compare output count with independent calculation
    # ------------------------------------------------------------

    print("\n[10] Comparing counts...")

    independent_count = int(within_buffer.sum())
    output_count = len(buildings)

    print(f"Output feature count       : {output_count:,}")
    print(f"Independent buffer count   : {independent_count:,}")

    if output_count == independent_count:
        print("✓ Counts match exactly.")
    else:
        print("⚠ Counts do not match.")

    # ------------------------------------------------------------
    # 11. Check that output looks like buildings
    # ------------------------------------------------------------

    print("\n[11] Checking building attributes...")

    if "building" in buildings.columns:
        building_values = buildings["building"].notna().sum()

        print(
            f"Features with non-null 'building' attribute: "
            f"{building_values:,}"
        )

        if building_values == len(buildings):
            print("✓ All output features have a building attribute.")
        else:
            print("⚠ Some output features do not have a building attribute.")
    else:
        print("⚠ Output does not contain a 'building' column.")

    # ------------------------------------------------------------
    # 12. Final verdict
    # ------------------------------------------------------------

    print("\n" + "=" * 70)
    print("FINAL VALIDATION")
    print("=" * 70)

    checks = {
        "Output exists": OUTPUT.exists(),
        "Output has features": len(buildings) > 0,
        "Geometries valid": invalid == 0,
        "Geometries non-empty": empty == 0,
        "Mula River found": not mula.empty,
        "All buildings within 500 m": outside_count == 0,
        "Counts match": output_count == independent_count,
    }

    for name, passed in checks.items():
        print(f"{'✓' if passed else '✗'} {name}")

    if all(checks.values()):
        print("\nRESULT: PASS")
        print("The generated GeoPackage is internally consistent with")
        print("the independently computed 500 m Mula River buffer.")
    else:
        print("\nRESULT: REVIEW REQUIRED")
        print("One or more validation checks failed.")

    print("=" * 70)


if __name__ == "__main__":
    main()