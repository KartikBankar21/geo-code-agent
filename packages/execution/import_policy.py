import ast


ALLOWED_IMPORTS = {
    "geopandas",
    "shapely",
    "pyproj",
    "rasterio",
    "packages.geo_tools",

    # Safe filesystem/path utilities.
    # Actual filesystem access is restricted separately.
    "os",
    "pathlib",
}


def validate_imports(tree: ast.AST) -> list[str]:
    """Return a list of disallowed imports."""
    violations = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name

                if not _is_allowed(module):
                    violations.append(module)

        elif isinstance(node, ast.ImportFrom):
            module = node.module

            if module is None or not _is_allowed(module):
                violations.append(module or "<relative-import>")

    return violations


def _is_allowed(module: str) -> bool:
    """Check whether a module belongs to the allowed import surface."""
    return any(
        module == allowed or module.startswith(allowed + ".")
        for allowed in ALLOWED_IMPORTS
    )