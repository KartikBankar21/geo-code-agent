from pathlib import Path

import geopandas as gpd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REFERENCE = (
    PROJECT_ROOT
    / "data/processed/mula-pavana/buildings_within_500m.gpkg"
)

AGENT_OUTPUT = (
    PROJECT_ROOT
    / "data/outputs/buildings_near_mula_river.gpkg"
)


def load_first_layer(path: Path):
    layers = gpd.list_layers(path)

    if len(layers) == 0:
        raise RuntimeError(f"No layers found in {path}")

    layer_name = layers.iloc[0]["name"]

    gdf = gpd.read_file(path, layer=layer_name)

    return layer_name, gdf


def main():
    print("=" * 75)
    print("REFERENCE vs AGENT OUTPUT COMPARISON")
    print("=" * 75)

    # ------------------------------------------------------------
    # 1. Check files
    # ------------------------------------------------------------

    print("\n[1] Files")

    if not REFERENCE.exists():
        raise FileNotFoundError(f"Reference file not found:\n{REFERENCE}")

    if not AGENT_OUTPUT.exists():
        raise FileNotFoundError(f"Agent output not found:\n{AGENT_OUTPUT}")

    print(f"Reference : {REFERENCE}")
    print(f"Agent     : {AGENT_OUTPUT}")

    # ------------------------------------------------------------
    # 2. Load datasets
    # ------------------------------------------------------------

    print("\n[2] Loading datasets")

    reference_layer, reference = load_first_layer(REFERENCE)
    agent_layer, agent = load_first_layer(AGENT_OUTPUT)

    print(f"Reference layer: {reference_layer}")
    print(f"Agent layer    : {agent_layer}")

    # ------------------------------------------------------------
    # 3. Basic statistics
    # ------------------------------------------------------------

    print("\n[3] Basic statistics")

    print(f"Reference features : {len(reference):,}")
    print(f"Agent features     : {len(agent):,}")

    print(f"Reference CRS      : {reference.crs}")
    print(f"Agent CRS          : {agent.crs}")

    print(f"Reference geometry : {reference.geometry.geom_type.value_counts().to_dict()}")
    print(f"Agent geometry     : {agent.geometry.geom_type.value_counts().to_dict()}")

    # ------------------------------------------------------------
    # 4. Normalize CRS
    # ------------------------------------------------------------

    print("\n[4] Normalizing CRS")

    if reference.crs is None:
        raise RuntimeError("Reference dataset has no CRS.")

    if agent.crs is None:
        raise RuntimeError("Agent dataset has no CRS.")

    if agent.crs != reference.crs:
        print("CRS differs. Reprojecting agent output to reference CRS.")
        agent = agent.to_crs(reference.crs)

    print(f"Comparison CRS: {reference.crs}")

    # ------------------------------------------------------------
    # 5. Geometry validity
    # ------------------------------------------------------------

    print("\n[5] Geometry validity")

    reference_invalid = (~reference.geometry.is_valid).sum()
    agent_invalid = (~agent.geometry.is_valid).sum()

    print(f"Reference invalid geometries: {reference_invalid:,}")
    print(f"Agent invalid geometries    : {agent_invalid:,}")

    # ------------------------------------------------------------
    # 6. Spatial extents
    # ------------------------------------------------------------

    print("\n[6] Spatial extents")

    print(f"Reference bounds: {reference.total_bounds}")
    print(f"Agent bounds    : {agent.total_bounds}")

    # ------------------------------------------------------------
    # 7. Spatial comparison
    # ------------------------------------------------------------

    print("\n[7] Spatial comparison")

    # Spatial equality is usually not a simple row-by-row comparison
    # because the two GeoPackages may have different feature ordering
    # and different attribute columns.
    #
    # We therefore use spatial joins to determine:
    #
    #   A = buildings in reference
    #   B = buildings in agent output
    #
    # Then:
    #
    #   A ∩ B = common buildings
    #   A - B = reference-only buildings
    #   B - A = agent-only buildings

    reference_geom = reference[["geometry"]].copy()
    agent_geom = agent[["geometry"]].copy()

    reference_geom["reference_id"] = range(len(reference_geom))
    agent_geom["agent_id"] = range(len(agent_geom))

    # ------------------------------------------------------------
    # 8. Reference -> Agent
    # ------------------------------------------------------------

    print("\n[8] Finding reference buildings represented in agent output")

    ref_matches = gpd.sjoin(
        reference_geom,
        agent_geom,
        how="left",
        predicate="intersects",
    )

    reference_matched = (
        ref_matches["agent_id"]
        .notna()
        .groupby(ref_matches["reference_id"])
        .any()
    )

    reference_matched_count = int(reference_matched.sum())
    reference_only_count = len(reference) - reference_matched_count

    print(f"Reference buildings matched by agent: {reference_matched_count:,}")
    print(f"Reference-only buildings            : {reference_only_count:,}")

    # ------------------------------------------------------------
    # 9. Agent -> Reference
    # ------------------------------------------------------------

    print("\n[9] Finding agent buildings represented in reference")

    agent_matches = gpd.sjoin(
        agent_geom,
        reference_geom,
        how="left",
        predicate="intersects",
    )

    agent_matched = (
        agent_matches["reference_id"]
        .notna()
        .groupby(agent_matches["agent_id"])
        .any()
    )

    agent_matched_count = int(agent_matched.sum())
    agent_only_count = len(agent) - agent_matched_count

    print(f"Agent buildings matched by reference: {agent_matched_count:,}")
    print(f"Agent-only buildings               : {agent_only_count:,}")

    # ------------------------------------------------------------
    # 10. Calculate overlap percentages
    # ------------------------------------------------------------

    print("\n[10] Agreement")

    if len(reference) > 0:
        reference_recall = (
            reference_matched_count / len(reference)
        ) * 100
    else:
        reference_recall = 0

    if len(agent) > 0:
        agent_precision = (
            agent_matched_count / len(agent)
        ) * 100
    else:
        agent_precision = 0

    print(
        f"Reference coverage by agent : "
        f"{reference_recall:.2f}%"
    )

    print(
        f"Agent output supported by reference: "
        f"{agent_precision:.2f}%"
    )

    # ------------------------------------------------------------
    # 11. Exact geometry comparison
    # ------------------------------------------------------------

    print("\n[11] Exact geometry comparison")

    # Normalize geometry representation before comparing.
    reference_wkb = set(reference.geometry.to_wkb())
    agent_wkb = set(agent.geometry.to_wkb())

    exact_common = reference_wkb & agent_wkb

    print(f"Exact common geometries: {len(exact_common):,}")

    reference_exact_only = reference_wkb - agent_wkb
    agent_exact_only = agent_wkb - reference_wkb

    print(
        f"Reference exact-only geometries: "
        f"{len(reference_exact_only):,}"
    )

    print(
        f"Agent exact-only geometries: "
        f"{len(agent_exact_only):,}"
    )

    # ------------------------------------------------------------
    # 12. Final verdict
    # ------------------------------------------------------------

    print("\n" + "=" * 75)
    print("FINAL RESULT")
    print("=" * 75)

    if (
        reference_only_count == 0
        and agent_only_count == 0
        and reference_invalid == 0
        and agent_invalid == 0
    ):
        print("PASS")
        print()
        print("The agent output spatially matches the manually")
        print("validated reference dataset.")
    else:
        print("DIFFERENCE DETECTED")
        print()
        print(
            "The agent output is not identical to the reference."
        )
        print(
            "This does NOT automatically mean the agent is wrong."
        )
        print(
            "The two workflows may have selected different river"
        )
        print(
            "features or applied different filtering criteria."
        )

    print("=" * 75)


if __name__ == "__main__":
    main()