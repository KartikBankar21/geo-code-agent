import pytest

from packages.rag.config import (
    LIBRARIES,
    get_library,
    raw_dir,
    cleaned_dir,
    chunks_dir,
)


EXPECTED_LIBRARIES = {"geopandas", "shapely", "rasterio", "pyproj", "gdal"}


def test_all_expected_libraries_are_registered():
    assert set(LIBRARIES) == EXPECTED_LIBRARIES


def test_every_library_has_a_well_formed_base_url():
    for name, config in LIBRARIES.items():
        assert config.name == name
        assert config.base_url.startswith("https://")
        assert config.base_url.endswith("/")
        assert config.version


def test_get_library_returns_matching_config():
    config = get_library("shapely")

    assert config.name == "shapely"
    assert config.version == "2.1.2"


def test_get_library_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown library"):
        get_library("not-a-real-library")


def test_directory_helpers_are_scoped_per_library():
    assert str(raw_dir("shapely")).endswith("rag/raw/shapely")
    assert str(raw_dir("rasterio")).endswith("rag/raw/rasterio")
    assert str(cleaned_dir("pyproj")).endswith("rag/cleaned/pyproj")
    assert str(chunks_dir("gdal")).endswith("rag/chunks/gdal")
