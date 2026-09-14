import ast

from packages.execution.dangerous_policy import validate_dangerous_operations


def _violations(code: str) -> list[str]:
    return validate_dangerous_operations(ast.parse(code))


def test_safe_code_has_no_violations():
    code = """
import geopandas as gpd

gdf = gpd.read_file("/sandbox/input/data.gpkg")
gdf = gdf.buffer(500)
print(len(gdf))
"""
    assert _violations(code) == []


def test_bare_dangerous_builtins_are_flagged():
    assert _violations("eval('1+1')") == ["eval"]
    assert _violations("exec('x = 1')") == ["exec"]
    assert _violations("open('/etc/passwd')") == ["open"]


def test_direct_os_system_is_flagged():
    code = "import os\nos.system('rm -rf /')"
    assert _violations(code) == ["os.system"]


def test_direct_subprocess_call_is_flagged():
    code = "import subprocess\nsubprocess.run(['ls'])"
    assert _violations(code) == ["subprocess.run"]


def test_direct_path_unlink_is_flagged():
    code = "from pathlib import Path\nPath('/tmp/x').unlink()"
    assert _violations(code) == ["Path.unlink"]


# ---------------------------------------------------------------------
# Regression tests: these bypass the *old* implementation, which matched
# only on the literal source-code name and ignored import aliasing.
# ---------------------------------------------------------------------

def test_aliased_module_import_is_still_flagged():
    code = "import os as x\nx.system('rm -rf /')"
    assert _violations(code) == ["os.system"]


def test_from_import_of_dangerous_function_is_still_flagged():
    code = "from os import system\nsystem('rm -rf /')"
    assert _violations(code) == ["os.system"]


def test_from_import_with_rename_is_still_flagged():
    code = "from os import system as run_command\nrun_command('rm -rf /')"
    assert _violations(code) == ["os.system"]


def test_aliased_pathlib_import_is_still_flagged():
    code = "from pathlib import Path as P\nP('/tmp/x').unlink()"
    assert _violations(code) == ["Path.unlink"]


def test_aliased_subprocess_popen_is_still_flagged():
    code = "import subprocess as sp\nsp.Popen(['ls'])"
    assert _violations(code) == ["subprocess.Popen"]


def test_unrelated_local_name_is_not_a_false_positive():
    # A user-defined function that happens to be named "system" (and is
    # NOT the os.system builtin) must not be flagged.
    code = """
def system(x):
    return x * 2

system(3)
"""
    assert _violations(code) == []


def test_unrelated_attribute_call_is_not_a_false_positive():
    code = """
class Robot:
    def system(self):
        return "ok"

r = Robot()
r.system()
"""
    assert _violations(code) == []
