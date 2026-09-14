import ast

from packages.execution.import_policy import validate_imports


def _violations(code: str) -> list[str]:
    return validate_imports(ast.parse(code))


def test_allowed_geospatial_imports_pass():
    code = """
import geopandas as gpd
import shapely
from shapely.geometry import Point
import pyproj
import rasterio
from packages.geo_tools.vector import load_layer
"""
    assert _violations(code) == []


def test_allowed_os_and_pathlib_pass():
    code = """
import os
from pathlib import Path
"""
    assert _violations(code) == []


def test_disallowed_import_is_flagged():
    code = "import subprocess"
    assert _violations(code) == ["subprocess"]


def test_disallowed_from_import_is_flagged():
    code = "from socket import socket"
    assert _violations(code) == ["socket"]


def test_relative_import_is_flagged():
    code = "from . import something"
    assert _violations(code) == ["<relative-import>"]


def test_multiple_violations_are_all_reported():
    code = """
import subprocess
import ctypes
import geopandas
"""
    violations = _violations(code)
    assert set(violations) == {"subprocess", "ctypes"}


def test_submodule_of_allowed_package_passes():
    code = "import shapely.geometry"
    assert _violations(code) == []


def test_lookalike_module_name_is_not_allowed():
    # "osprocess" is not "os" - must not match via a naive substring check.
    code = "import osprocess"
    assert _violations(code) == ["osprocess"]
