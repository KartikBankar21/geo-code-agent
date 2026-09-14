from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibraryConfig:
    name: str
    base_url: str
    version: str


LIBRARIES = {
    "geopandas": LibraryConfig(
        name="geopandas",
        version="1.1.4",
        base_url="https://geopandas.org/en/v1.1.4/",
    ),
    "shapely": LibraryConfig(
        name="shapely",
        version="2.1.2",
        base_url="https://shapely.readthedocs.io/en/2.1.2/",
    ),
    "rasterio": LibraryConfig(
        name="rasterio",
        version="1.5.1",
        base_url="https://rasterio.readthedocs.io/en/1.5.1/",
    ),
    "pyproj": LibraryConfig(
        name="pyproj",
        version="3.7.2",
        base_url="https://pyproj4.github.io/pyproj/3.7.2/",
    ),
    "gdal": LibraryConfig(
        name="gdal",
        version="3.8.4",
        base_url="https://gdal.org/en/3.8.4/",
    ),
}


def get_library(name: str) -> LibraryConfig:
    try:
        return LIBRARIES[name]
    except KeyError:
        available = ", ".join(sorted(LIBRARIES))
        raise ValueError(
            f"Unknown library '{name}'. "
            f"Available libraries: {available}"
        )


def raw_dir(library: str) -> Path:
    return Path("rag/raw") / library


def cleaned_dir(library: str) -> Path:
    return Path("rag/cleaned") / library


def chunks_dir(library: str) -> Path:
    return Path("rag/chunks") / library
