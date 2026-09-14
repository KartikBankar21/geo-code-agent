from packages.execution.validator import validate_code


def test_valid_geospatial_code_passes():
    code = """
import geopandas as gpd

gdf = gpd.read_file("/sandbox/input/data.gpkg", layer="lines")
gdf = gdf.to_crs(epsg=32643)
buffered = gdf.buffer(500)
print(len(buffered))
"""
    result = validate_code(code)

    assert result.valid is True
    assert result.syntax_valid is True
    assert result.syntax_error is None
    assert result.import_violations == []
    assert result.dangerous_operations == []


def test_syntax_error_is_reported_and_short_circuits():
    code = "def broken(:\n    pass"

    result = validate_code(code)

    assert result.valid is False
    assert result.syntax_valid is False
    assert result.syntax_error is not None
    assert result.import_violations == []
    assert result.dangerous_operations == []


def test_import_violation_makes_code_invalid():
    code = "import subprocess\nprint('hi')"

    result = validate_code(code)

    assert result.valid is False
    assert result.syntax_valid is True
    assert "subprocess" in result.import_violations


def test_dangerous_operation_makes_code_invalid():
    code = "import os\nos.system('rm -rf /')"

    result = validate_code(code)

    assert result.valid is False
    assert result.import_violations == []
    assert "os.system" in result.dangerous_operations


def test_both_violation_types_reported_together():
    code = "import subprocess\nsubprocess.run(['ls'])"

    result = validate_code(code)

    assert result.valid is False
    assert "subprocess" in result.import_violations
    assert "subprocess.run" in result.dangerous_operations
