"""
Shared configuration and path-safety helpers for the API layer.

The API is expected to run with the project root as the current working
directory (same assumption `packages/execution/sandbox.py` and the RAG
scripts already make), so that relative paths like `data/raw/...` match
what the agent itself uses.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(os.path.abspath(".")).resolve()

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUTS_DIR = DATA_DIR / "outputs"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

VECTOR_EXTENSIONS = {".gpkg", ".geojson", ".json", ".fgb", ".gml", ".kml"}

# Hard cap on how many features get sent to the browser in one response.
# The UI can page or filter further; this just protects the browser tab
# (and the person's patience) from a multi-hundred-thousand-feature OSM
# layer landing in one JSON blob.
MAX_GEOJSON_FEATURES = 20_000


class UnsafePathError(ValueError):
    """Raised when a client-supplied path tries to escape the data dir."""


def resolve_data_path(relative_path: str) -> Path:
    """
    Resolve a client-supplied path, rejecting any attempt to escape the
    data/ directory (e.g. via `..`).

    The expected input is project-root-relative, e.g. 'data/raw/x/y.gpkg'
    or 'data/outputs/z.gpkg' - the same convention already used by
    `DatasetFile.host_path` and `execution_result["artifacts"]`, so
    callers can pass those values straight through without reformatting.
    """

    candidate = (PROJECT_ROOT / relative_path).resolve()

    if candidate != DATA_DIR and DATA_DIR not in candidate.parents:
        raise UnsafePathError(
            f"Path '{relative_path}' resolves outside of the data "
            f"directory."
        )

    return candidate


def to_sandbox_path(host_path: Path) -> str | None:
    """
    Map a host path under data/raw/ to the path the same file will have
    inside the sandbox container (see packages/execution/sandbox.py,
    which bind-mounts data/raw -> /sandbox/input read-only).

    Returns None if the path isn't under data/raw (e.g. an output
    artifact, which isn't visible inside the sandbox by design).
    """

    try:
        relative = host_path.resolve().relative_to(RAW_DIR)
    except ValueError:
        return None

    return "/sandbox/input/" + relative.as_posix()
