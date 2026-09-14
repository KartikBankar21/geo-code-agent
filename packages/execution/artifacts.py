from pathlib import Path


ARTIFACT_DIR = Path("data/outputs")


def collect_artifacts() -> list[str]:
    """Return files produced in the agent output directory."""
    if not ARTIFACT_DIR.exists():
        return []

    return sorted(
        str(path)
        for path in ARTIFACT_DIR.iterdir()
        if path.is_file()
    )

def snapshot_artifacts() -> set[str]:
    """Capture the current artifact paths."""
    return set(collect_artifacts())

def collect_new_artifacts(before: set[str]) -> list[str]:
    """Return artifacts that appeared after an execution."""
    after = snapshot_artifacts()

    return sorted(after - before)