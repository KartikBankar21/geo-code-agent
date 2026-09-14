import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point, LineString  # noqa: E402

from packages.tools.geospatial import list_layers, inspect_layer  # noqa: E402


@pytest.fixture
def sample_gpkg(tmp_path):
    path = tmp_path / "sample.gpkg"

    points = gpd.GeoDataFrame(
        {"name": ["a", "b"]},
        geometry=[Point(0, 0), Point(1, 1)],
        crs="EPSG:4326",
    )
    lines = gpd.GeoDataFrame(
        {"waterway": ["river"]},
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:4326",
    )

    points.to_file(path, layer="points", driver="GPKG")
    lines.to_file(path, layer="lines", driver="GPKG")

    return path


def test_list_layers_returns_all_layer_names(sample_gpkg):
    layers = list_layers(str(sample_gpkg))

    assert set(layers) == {"points", "lines"}


def test_list_layers_missing_dataset_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list_layers(str(tmp_path / "missing.gpkg"))


def test_inspect_layer_reports_expected_metadata(sample_gpkg):
    result = inspect_layer(str(sample_gpkg), layer="points")

    assert result["rows"] == 2
    assert "name" in result["columns"]
    assert "EPSG:4326" in result["crs"] or "4326" in result["crs"]
    assert result["geometry_type"] == {"Point": 2}
    assert len(result["bounds"]) == 4


def test_inspect_layer_missing_dataset_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_layer(str(tmp_path / "missing.gpkg"), layer="points")
