import pytest

import apps.api.storage as storage_module


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_module, "DB_PATH", tmp_path / "test.db")
    storage_module.init_db()
    return storage_module


def test_create_and_get_conversation_roundtrip(storage):
    conversation = storage.create_conversation(
        dataset_host_path="data/raw/mula-pavana-river/mula-pavana-river.gpkg",
        dataset_sandbox_path="/sandbox/input/mula-pavana-river/mula-pavana-river.gpkg",
        title="Buildings near the river",
    )

    fetched = storage.get_conversation(conversation["id"])

    assert fetched["id"] == conversation["id"]
    assert fetched["title"] == "Buildings near the river"
    assert fetched["turns"] == []


def test_list_conversations_orders_by_most_recently_updated(storage):
    first = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "First")
    second = storage.create_conversation("data/raw/b.gpkg", "/sandbox/input/b.gpkg", "Second")

    storage.touch_conversation(first["id"])

    listing = storage.list_conversations()

    assert listing[0]["id"] == first["id"]
    assert listing[1]["id"] == second["id"]


def test_list_conversations_reports_last_task_and_turn_count(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")

    storage.create_turn(conversation["id"], "Find buildings near the river")
    storage.create_turn(conversation["id"], "Now compute their area")

    listing = storage.list_conversations()

    assert listing[0]["turn_count"] == 2
    assert listing[0]["last_task"] == "Now compute their area"


def test_create_turn_increments_turn_index(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")

    first_turn = storage.create_turn(conversation["id"], "task one")
    second_turn = storage.create_turn(conversation["id"], "task two")

    assert first_turn["turn_index"] == 0
    assert second_turn["turn_index"] == 1


def test_create_turn_seeds_context_from_previous_turn(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")

    first_turn = storage.create_turn(conversation["id"], "task one")

    storage.update_turn(
        first_turn["id"],
        retrieved_docs=[{"chunk_id": "x", "title": "buffer"}],
        dataset_observations=[{"type": "layer_listing", "layers": ["points"]}],
        status="completed",
    )

    second_turn = storage.create_turn(conversation["id"], "task two")

    assert second_turn["retrieved_docs"] == [{"chunk_id": "x", "title": "buffer"}]
    assert second_turn["dataset_observations"] == [
        {"type": "layer_listing", "layers": ["points"]}
    ]


def test_first_turn_in_a_conversation_has_empty_seed_context(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")

    turn = storage.create_turn(conversation["id"], "task one")

    assert turn["retrieved_docs"] == []
    assert turn["dataset_observations"] == []


def test_update_turn_persists_json_fields_correctly(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")
    turn = storage.create_turn(conversation["id"], "task one")

    storage.update_turn(
        turn["id"],
        status="completed",
        generated_code="print(1)",
        execution_result={"status": "success", "stdout": "1\n"},
        artifacts=["data/outputs/x.gpkg"],
        events=[{"node": "finish", "type": "finished", "data": {}}],
    )

    fetched = storage.get_turn(turn["id"])

    assert fetched["status"] == "completed"
    assert fetched["generated_code"] == "print(1)"
    assert fetched["execution_result"] == {"status": "success", "stdout": "1\n"}
    assert fetched["artifacts"] == ["data/outputs/x.gpkg"]
    assert fetched["events"][0]["node"] == "finish"


def test_update_turn_rejects_unknown_fields(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")
    turn = storage.create_turn(conversation["id"], "task one")

    with pytest.raises(ValueError):
        storage.update_turn(turn["id"], not_a_real_column="x")


def test_get_conversation_includes_turns_in_order_without_bloating_payload(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")

    storage.create_turn(conversation["id"], "task one")
    storage.create_turn(conversation["id"], "task two")

    fetched = storage.get_conversation(conversation["id"])

    assert [t["task"] for t in fetched["turns"]] == ["task one", "task two"]
    # The conversation-level listing shouldn't carry the (potentially
    # large) seed context fields - those are only needed internally by
    # create_turn(), not by API consumers browsing history.
    assert "retrieved_docs" not in fetched["turns"][0]


def test_get_conversation_returns_none_when_missing(storage):
    assert storage.get_conversation("does-not-exist") is None


def test_delete_conversation_cascades_to_turns(storage):
    conversation = storage.create_conversation("data/raw/a.gpkg", "/sandbox/input/a.gpkg", "Chat")
    storage.create_turn(conversation["id"], "task one")

    storage.delete_conversation(conversation["id"])

    assert storage.get_conversation(conversation["id"]) is None
