from pathlib import Path

import packages.execution.artifacts as artifacts_module
from packages.execution.artifacts import (
    collect_artifacts,
    snapshot_artifacts,
    collect_new_artifacts,
)


def test_collect_artifacts_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        artifacts_module,
        "ARTIFACT_DIR",
        tmp_path / "does-not-exist",
    )

    assert collect_artifacts() == []


def test_collect_artifacts_lists_files_only(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts_module, "ARTIFACT_DIR", tmp_path)

    (tmp_path / "result.gpkg").write_text("data")
    (tmp_path / "subdir").mkdir()

    result = collect_artifacts()

    assert result == [str(tmp_path / "result.gpkg")]


def test_collect_new_artifacts_detects_only_newly_created_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(artifacts_module, "ARTIFACT_DIR", tmp_path)

    (tmp_path / "existing.gpkg").write_text("data")

    before = snapshot_artifacts()

    (tmp_path / "new_output.gpkg").write_text("more data")

    new_artifacts = collect_new_artifacts(before)

    assert new_artifacts == [str(tmp_path / "new_output.gpkg")]


def test_collect_new_artifacts_empty_when_nothing_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts_module, "ARTIFACT_DIR", tmp_path)

    (tmp_path / "existing.gpkg").write_text("data")

    before = snapshot_artifacts()
    after = collect_new_artifacts(before)

    assert after == []
