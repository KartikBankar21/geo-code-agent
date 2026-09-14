from dataclasses import dataclass
from pathlib import Path
import numpy as np
import geopandas as gpd


REFERENCE = Path(
    "data/processed/mula-pavana/buildings_within_500m.gpkg"
)


@dataclass
class BenchmarkResult:
    passed: bool

    reference_features: int
    candidate_features: int

    reference_crs: str | None
    candidate_crs: str | None

    same_feature_count: bool
    same_crs: bool
    same_geometry_types: bool
    same_bounds: bool

    same_feature_ids: bool | None
    geometry_match_ratio: float

    message: str


def evaluate_candidate(candidate: str | Path) -> BenchmarkResult:
    """Compare a candidate GIS result against the locked reference."""

    candidate = Path(candidate)

    if not REFERENCE.exists():
        raise FileNotFoundError(
            f"Reference output not found: {REFERENCE}"
        )

    if not candidate.exists():
        return BenchmarkResult(
            passed=False,
            reference_features=0,
            candidate_features=0,
            reference_crs=None,
            candidate_crs=None,
            same_feature_count=False,
            same_crs=False,
            same_geometry_types=False,
            same_bounds=False,
            same_feature_ids=None,
            geometry_match_ratio=0.0,
            message=f"Candidate output not found: {candidate}",
        )

    reference = gpd.read_file(REFERENCE)
    result = gpd.read_file(candidate)

    # ---------------------------------------------------------
    # Structural checks
    # ---------------------------------------------------------

    reference_crs = (
        reference.crs.to_string()
        if reference.crs is not None
        else None
    )

    candidate_crs = (
        result.crs.to_string()
        if result.crs is not None
        else None
    )

    same_feature_count = len(reference) == len(result)

    same_crs = reference_crs == candidate_crs

    reference_geometry_types = sorted(
        reference.geometry.geom_type.unique()
    )

    candidate_geometry_types = sorted(
        result.geometry.geom_type.unique()
    )

    same_geometry_types = (
        reference_geometry_types == candidate_geometry_types
    )

    same_bounds = np.allclose(
        reference.total_bounds,
        result.total_bounds,
        rtol=0.0,
        atol=1e-6,
    )

    # ---------------------------------------------------------
    # Feature identity check
    # ---------------------------------------------------------

    if "osm_id" in reference.columns and "osm_id" in result.columns:
        reference_ids = set(reference["osm_id"].dropna())
        candidate_ids = set(result["osm_id"].dropna())

        same_feature_ids = reference_ids == candidate_ids

    else:
        same_feature_ids = None

    # ---------------------------------------------------------
    # Geometry comparison
    # ---------------------------------------------------------

    geometry_match_ratio = 0.0

    if (
        same_feature_count
        and same_crs
        and len(reference) > 0
    ):
        try:
            reference_sorted = reference.sort_values(
                by="osm_id"
            ).reset_index(drop=True)

            result_sorted = result.sort_values(
                by="osm_id"
            ).reset_index(drop=True)

            matches = reference_sorted.geometry.geom_equals(
                result_sorted.geometry
            )

            geometry_match_ratio = matches.mean()

        except (KeyError, ValueError):
            geometry_match_ratio = 0.0

    # ---------------------------------------------------------
    # Final benchmark decision
    # ---------------------------------------------------------

    passed = (
        same_feature_count
        and same_crs
        and same_geometry_types
        and same_bounds
        and (
            same_feature_ids is None
            or same_feature_ids
        )
        and geometry_match_ratio == 1.0
    )

    if passed:
        message = "Benchmark passed."
    else:
        message = "Benchmark failed."

    return BenchmarkResult(
        passed=passed,
        reference_features=len(reference),
        candidate_features=len(result),
        reference_crs=reference_crs,
        candidate_crs=candidate_crs,
        same_feature_count=same_feature_count,
        same_crs=same_crs,
        same_geometry_types=same_geometry_types,
        same_bounds=same_bounds,
        same_feature_ids=same_feature_ids,
        geometry_match_ratio=geometry_match_ratio,
        message=message,
    )