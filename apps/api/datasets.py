import os
import re
import shutil
import zipfile
from pathlib import Path

import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from apps.api import config
from apps.api.schemas import Dataset, DatasetFile, DatasetListResponse, LayersResponse
from packages.tools.geospatial import list_layers as _list_layers

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _sanitize_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    name = name.strip("-")

    if not name:
        raise HTTPException(400, "Could not derive a valid dataset name.")

    return name


def _discover_dataset(entry: Path) -> Dataset:
    files = []

    for f in sorted(entry.rglob("*")):
        if f.is_file() and f.suffix.lower() in config.VECTOR_EXTENSIONS:
            files.append(
                DatasetFile(
                    filename=str(f.relative_to(entry)),
                    host_path=str(f.relative_to(config.PROJECT_ROOT)),
                    sandbox_path=config.to_sandbox_path(f),
                    size_bytes=f.stat().st_size,
                )
            )

    return Dataset(name=entry.name, files=files)


@router.get("", response_model=DatasetListResponse)
def list_datasets():
    """List every dataset directory under data/raw/, with its vector files."""

    if not config.RAW_DIR.exists():
        return DatasetListResponse(datasets=[])

    datasets = [
        _discover_dataset(entry)
        for entry in sorted(config.RAW_DIR.iterdir())
        if entry.is_dir()
    ]

    return DatasetListResponse(datasets=datasets)


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    """Extract a zip file, refusing any entry that would escape target_dir."""

    resolved_target = target_dir.resolve()

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = (target_dir / member.filename).resolve()

            if (
                resolved_target not in member_path.parents
                and member_path != resolved_target
            ):
                raise HTTPException(
                    400,
                    f"Refusing to extract unsafe zip entry: {member.filename}",
                )

        archive.extractall(target_dir)

def _sync_dataset_to_executor(dataset: Dataset) -> None:
    """Forward newly uploaded vector files to Tier 3's /sandbox/input directory."""
    executor_url = os.getenv("SANDBOX_EXECUTOR_URL", "").strip().rstrip("/")
    if not executor_url:
        return

    secret = os.getenv("EXECUTOR_SHARED_SECRET", "").strip()
    headers = {"X-Executor-Secret": secret} if secret else {}

    for item in dataset.files:
        host_file = config.PROJECT_ROOT / item.host_path
        if not host_file.exists():
            continue

        rel_to_raw = f"{dataset.name}/{item.filename}"
        with host_file.open("rb") as fh:
            resp = requests.post(
                f"{executor_url}/datasets/sync",
                data={"relative_path": rel_to_raw},
                files={"file": (host_file.name, fh, "application/octet-stream")},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()

@router.post("", response_model=Dataset)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
):
    """
    Upload a dataset for the agent to work with.

    Accepts either a single vector file (.gpkg, .geojson, ...) or a
    .zip archive containing one (e.g. a BBBike GIS extract) - this is
    generalizable to any GIS extract, not just the one used during
    development.
    """

    original_name = file.filename or "dataset"
    dataset_name = _sanitize_name(name or Path(original_name).stem)

    target_dir = config.RAW_DIR / dataset_name
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(original_name).suffix.lower()

    if suffix == ".zip":
        tmp_zip = target_dir / "_upload.zip"

        with tmp_zip.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        try:
            _safe_extract_zip(tmp_zip, target_dir)
        finally:
            tmp_zip.unlink(missing_ok=True)
    else:
        destination = target_dir / Path(original_name).name

        with destination.open("wb") as out:
            shutil.copyfileobj(file.file, out)

    dataset = _discover_dataset(target_dir)

    if not dataset.files:
        raise HTTPException(
            422,
            "No supported vector file "
            f"({', '.join(sorted(config.VECTOR_EXTENSIONS))}) was found "
            "in the upload.",
        )

    try:
        _sync_dataset_to_executor(dataset)
    except Exception as e:
        raise HTTPException(
            502,
            f"Dataset saved on API node, but failed to sync to execution node: {e}",
        )

    return dataset


@router.get("/{name}/layers", response_model=LayersResponse)
def dataset_layers(name: str, file: str | None = None):
    """List the layers inside one file of a dataset."""

    dataset_dir = config.RAW_DIR / name

    if not dataset_dir.exists():
        raise HTTPException(404, f"Dataset '{name}' not found.")

    dataset = _discover_dataset(dataset_dir)

    if not dataset.files:
        raise HTTPException(404, f"Dataset '{name}' has no vector files.")

    if file:
        matches = [f for f in dataset.files if f.filename == file]

        if not matches:
            raise HTTPException(
                404, f"File '{file}' not found in dataset '{name}'."
            )

        target = matches[0]
    else:
        target = dataset.files[0]

    try:
        layers = _list_layers(target.host_path)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found on disk: {target.host_path}")

    return LayersResponse(layers=layers)
