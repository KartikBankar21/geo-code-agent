import io
import zipfile

import pytest

gpd = pytest.importorskip("geopandas")
from shapely.geometry import Point  # noqa: E402

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    raw_dir = tmp_path / "data" / "raw"
    outputs_dir = tmp_path / "data" / "outputs"
    raw_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)

    import apps.api.config as config
    import apps.api.storage as storage

    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "RAW_DIR", raw_dir)
    monkeypatch.setattr(config, "OUTPUTS_DIR", outputs_dir)
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "geo_agent.db")

    from apps.api.main import app

    with fastapi_testclient.TestClient(app) as client:
        yield client, raw_dir


def test_health_endpoint_reports_structure(api_client):
    client, _ = api_client

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert "agent_ready" in body


def test_empty_dataset_list(api_client):
    client, _ = api_client

    response = client.get("/api/datasets")

    assert response.status_code == 200
    assert response.json() == {"datasets": []}


def test_upload_single_gpkg_dataset(api_client, tmp_path):
    client, raw_dir = api_client

    gdf = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:4326"
    )
    gpkg_path = tmp_path / "sample.gpkg"
    gdf.to_file(gpkg_path, driver="GPKG")

    with gpkg_path.open("rb") as f:
        response = client.post(
            "/api/datasets",
            files={"file": ("sample.gpkg", f, "application/geopackage+sqlite3")},
            data={"name": "my-dataset"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "my-dataset"
    assert len(body["files"]) == 1
    assert body["files"][0]["sandbox_path"] == "/sandbox/input/my-dataset/sample.gpkg"

    listing = client.get("/api/datasets").json()
    assert listing["datasets"][0]["name"] == "my-dataset"


def test_upload_zip_dataset_extracts_contents(api_client):
    client, _ = api_client

    gdf = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[Point(1, 1)], crs="EPSG:4326"
    )

    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w")
    inner_gpkg = io.BytesIO()
    # GeoPandas needs a real path to write GPKG, so write to a temp file
    # via a nested approach: use fiona/pyogrio's in-memory support is
    # more trouble than it's worth here - write, read bytes, zip them.
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "river.gpkg")
        gdf.to_file(p, driver="GPKG")
        with open(p, "rb") as fh:
            zf.writestr("river.gpkg", fh.read())

    zf.writestr("README.txt", "extract metadata")
    zf.close()
    buf.seek(0)

    response = client.post(
        "/api/datasets",
        files={"file": ("extract.zip", buf, "application/zip")},
        data={"name": "zipped-extract"},
    )

    assert response.status_code == 200
    body = response.json()
    filenames = {f["filename"] for f in body["files"]}
    assert filenames == {"river.gpkg"}


def test_geojson_endpoint_reprojects_to_4326(api_client, tmp_path):
    client, raw_dir = api_client

    dataset_dir = raw_dir / "utm-data"
    dataset_dir.mkdir()

    gdf = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[Point(500000, 2000000)], crs="EPSG:32643"
    )
    gpkg_path = dataset_dir / "utm.gpkg"
    gdf.to_file(gpkg_path, driver="GPKG")

    response = client.get(
        "/api/geo", params={"path": "data/raw/utm-data/utm.gpkg"}
    )

    assert response.status_code == 200
    geojson = response.json()
    assert geojson["type"] == "FeatureCollection"
    lon, lat = geojson["features"][0]["geometry"]["coordinates"]
    # Reprojected to WGS84 - should land somewhere sane, not raw UTM meters.
    assert -180 <= lon <= 180
    assert -90 <= lat <= 90


def test_geojson_endpoint_rejects_path_escape(api_client):
    client, _ = api_client

    response = client.get("/api/geo", params={"path": "../../etc/passwd"})

    assert response.status_code == 400


def test_conversation_creation_rejects_unknown_dataset(api_client):
    client, _ = api_client

    response = client.post(
        "/api/conversations",
        json={"task": "buffer the rivers by 500m", "dataset": "does-not-exist"},
    )

    assert response.status_code == 404


def test_empty_conversation_list(api_client):
    client, _ = api_client

    response = client.get("/api/conversations")

    assert response.status_code == 200
    assert response.json() == {"conversations": []}


class FakeGraph:
    """Stands in for the compiled LangGraph agent - yields canned
    per-node updates instead of actually calling an LLM or Docker."""

    def __init__(self, updates):
        self._updates = updates

    def stream(self, initial_state, stream_mode="updates"):
        yield from self._updates


def _fake_success_updates(dataset_sandbox_path):
    return [
        {
            "agent_decide": {
                "agent_decision": {
                    "action": "generate_code",
                    "reason": "Enough info.",
                    "query": "",
                    "path": "",
                    "layer": "",
                },
                "next_action": "generate_code",
                "iteration": 1,
            }
        },
        {"generate_code": {"generated_code": "print(1)"}},
        {
            "validate_code": {
                "validation_result": {
                    "valid": True,
                    "syntax_valid": True,
                    "syntax_error": None,
                    "import_violations": [],
                    "dangerous_operations": [],
                }
            }
        },
        {
            "execute_code": {
                "execution_result": {
                    "status": "success",
                    "stdout": "1\n",
                    "stderr": "",
                    "error_type": None,
                    "error_message": None,
                    "execution_time": 0.1,
                    "artifacts": ["data/outputs/result.gpkg"],
                }
            }
        },
        {"finish": {"status": "completed"}},
    ]


@pytest.fixture
def dataset_and_fake_agent(api_client, tmp_path, monkeypatch):
    client, raw_dir = api_client

    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    dataset_dir = raw_dir / "demo"
    dataset_dir.mkdir()
    gdf.to_file(dataset_dir / "demo.gpkg", driver="GPKG")

    import apps.api.conversations as conversations

    fake_graph = FakeGraph(_fake_success_updates("/sandbox/input/demo/demo.gpkg"))
    monkeypatch.setattr(conversations, "get_graph", lambda: (fake_graph, None))

    return client


def _wait_for_turn(client, conversation_id, turn_id, timeout=5.0):
    import time

    deadline = time.time() + timeout

    while time.time() < deadline:
        detail = client.get(f"/api/conversations/{conversation_id}").json()
        turn = next(t for t in detail["turns"] if t["id"] == turn_id)

        if turn["status"] in ("completed", "failed"):
            return turn

        time.sleep(0.05)

    raise AssertionError("Turn did not finish in time")


def test_create_conversation_runs_first_turn_to_completion(dataset_and_fake_agent):
    client = dataset_and_fake_agent

    response = client.post(
        "/api/conversations",
        json={"task": "print one", "dataset": "demo", "file": "demo.gpkg"},
    )

    assert response.status_code == 200
    body = response.json()

    turn = _wait_for_turn(client, body["conversation_id"], body["turn_id"])

    assert turn["status"] == "completed"
    assert turn["generated_code"] == "print(1)"
    assert turn["execution_result"]["status"] == "success"
    assert turn["artifacts"] == ["data/outputs/result.gpkg"]


def test_conversation_appears_in_listing_with_last_task(dataset_and_fake_agent):
    client = dataset_and_fake_agent

    response = client.post(
        "/api/conversations",
        json={"task": "print one", "dataset": "demo", "file": "demo.gpkg"},
    )
    body = response.json()
    _wait_for_turn(client, body["conversation_id"], body["turn_id"])

    listing = client.get("/api/conversations").json()["conversations"]

    assert len(listing) == 1
    assert listing[0]["last_task"] == "print one"
    assert listing[0]["turn_count"] == 1


def test_continuing_a_conversation_adds_a_second_turn(dataset_and_fake_agent):
    client = dataset_and_fake_agent

    created = client.post(
        "/api/conversations",
        json={"task": "print one", "dataset": "demo", "file": "demo.gpkg"},
    ).json()
    _wait_for_turn(client, created["conversation_id"], created["turn_id"])

    continued = client.post(
        f"/api/conversations/{created['conversation_id']}/turns",
        json={"task": "now print it again"},
    )

    assert continued.status_code == 200
    turn_id = continued.json()["turn_id"]
    turn = _wait_for_turn(client, created["conversation_id"], turn_id)

    assert turn["status"] == "completed"
    assert turn["turn_index"] == 1

    detail = client.get(f"/api/conversations/{created['conversation_id']}").json()
    assert len(detail["turns"]) == 2


def test_continuing_an_unknown_conversation_404s(api_client):
    client, _ = api_client

    response = client.post(
        "/api/conversations/does-not-exist/turns",
        json={"task": "anything"},
    )

    assert response.status_code == 404


def test_deleting_a_conversation_removes_it_from_listing(dataset_and_fake_agent):
    client = dataset_and_fake_agent

    created = client.post(
        "/api/conversations",
        json={"task": "print one", "dataset": "demo", "file": "demo.gpkg"},
    ).json()
    _wait_for_turn(client, created["conversation_id"], created["turn_id"])

    delete_response = client.delete(f"/api/conversations/{created['conversation_id']}")
    assert delete_response.status_code == 200

    listing = client.get("/api/conversations").json()["conversations"]
    assert listing == []


def test_stream_replays_persisted_events_for_an_already_finished_turn(
    dataset_and_fake_agent,
):
    client = dataset_and_fake_agent

    created = client.post(
        "/api/conversations",
        json={"task": "print one", "dataset": "demo", "file": "demo.gpkg"},
    ).json()
    _wait_for_turn(client, created["conversation_id"], created["turn_id"])

    with client.stream(
        "GET",
        f"/api/conversations/{created['conversation_id']}/turns/{created['turn_id']}/stream",
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"type": "decision"' in body
    assert '"type": "finished"' in body
    assert '"type": "done"' in body
    assert '"status": "completed"' in body


def test_stream_404s_for_a_turn_that_never_existed(api_client):
    client, _ = api_client

    response = client.get(
        "/api/conversations/no-such-conversation/turns/no-such-turn/stream"
    )

    assert response.status_code == 404
