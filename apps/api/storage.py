"""
Persistent storage for conversations (GIS workflow chats) and their
turns (individual task runs within a chat).

SQLite is used deliberately rather than an in-memory-only structure:
this is a local, single-user tool (see README - no authentication, not
meant for multi-tenant deployment), so a single file database is the
simplest thing that actually survives a server restart, which is the
whole point of "see your previous chats."

Writes are serialized with a lock since SQLite's default journal mode
only allows one writer at a time; reads don't need it. WAL mode is
enabled so reads aren't blocked by the occasional write.
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apps.api import config

DB_PATH = config.DATA_DIR / "geo_agent.db"

_write_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn


def init_db() -> None:
    with _write_lock, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                dataset_host_path TEXT NOT NULL,
                dataset_sandbox_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                turn_index INTEGER NOT NULL,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                generated_code TEXT,
                validation_result TEXT,
                execution_result TEXT,
                artifacts TEXT NOT NULL DEFAULT '[]',
                retrieved_docs TEXT NOT NULL DEFAULT '[]',
                dataset_observations TEXT NOT NULL DEFAULT '[]',
                events TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turns_conversation
                ON turns(conversation_id);
            """
        )


def _row_to_conversation(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "dataset_host_path": row["dataset_host_path"],
        "dataset_sandbox_path": row["dataset_sandbox_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_turn(row: sqlite3.Row, include_seed_fields: bool = True) -> dict:
    turn = {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "turn_index": row["turn_index"],
        "task": row["task"],
        "status": row["status"],
        "generated_code": row["generated_code"],
        "validation_result": json.loads(row["validation_result"])
        if row["validation_result"]
        else None,
        "execution_result": json.loads(row["execution_result"])
        if row["execution_result"]
        else None,
        "artifacts": json.loads(row["artifacts"]),
        "events": json.loads(row["events"]),
        "error": row["error"],
        "created_at": row["created_at"],
    }

    if include_seed_fields:
        turn["retrieved_docs"] = json.loads(row["retrieved_docs"])
        turn["dataset_observations"] = json.loads(row["dataset_observations"])

    return turn


def create_conversation(
    dataset_host_path: str,
    dataset_sandbox_path: str,
    title: str,
) -> dict:
    conversation_id = uuid.uuid4().hex
    now = _now()

    with _write_lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations
                (id, title, dataset_host_path, dataset_sandbox_path,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, title, dataset_host_path, dataset_sandbox_path, now, now),
        )

    return get_conversation(conversation_id)


def touch_conversation(conversation_id: str) -> None:
    with _write_lock, _connect() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now(), conversation_id),
        )


def list_conversations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        ).fetchall()

        conversations = []

        for row in rows:
            conversation = _row_to_conversation(row)

            turn_rows = conn.execute(
                """
                SELECT task, status, turn_index FROM turns
                WHERE conversation_id = ?
                ORDER BY turn_index DESC
                LIMIT 1
                """,
                (row["id"],),
            ).fetchall()

            if turn_rows:
                conversation["turn_count"] = turn_rows[0]["turn_index"] + 1
                conversation["last_task"] = turn_rows[0]["task"]
                conversation["last_status"] = turn_rows[0]["status"]
            else:
                conversation["turn_count"] = 0
                conversation["last_task"] = None
                conversation["last_status"] = None

            conversations.append(conversation)

    return conversations


def get_conversation(conversation_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if row is None:
            return None

        conversation = _row_to_conversation(row)

        turn_rows = conn.execute(
            """
            SELECT * FROM turns
            WHERE conversation_id = ?
            ORDER BY turn_index ASC
            """,
            (conversation_id,),
        ).fetchall()

        conversation["turns"] = [
            _row_to_turn(turn_row, include_seed_fields=False)
            for turn_row in turn_rows
        ]

    return conversation


def delete_conversation(conversation_id: str) -> None:
    with _write_lock, _connect() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )


def create_turn(conversation_id: str, task: str) -> dict:
    """
    Start a new turn in a conversation, seeding its starting
    documentation/dataset-observation context from the most recent
    prior turn (if any) - this is what lets "continue this
    conversation" skip re-discovering layers/docs already gathered.
    """

    with _connect() as conn:
        previous = conn.execute(
            """
            SELECT turn_index, retrieved_docs, dataset_observations
            FROM turns
            WHERE conversation_id = ?
            ORDER BY turn_index DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()

    turn_index = (previous["turn_index"] + 1) if previous else 0
    seed_docs = previous["retrieved_docs"] if previous else "[]"
    seed_observations = previous["dataset_observations"] if previous else "[]"

    turn_id = uuid.uuid4().hex
    now = _now()

    with _write_lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO turns
                (id, conversation_id, turn_index, task, status,
                 artifacts, retrieved_docs, dataset_observations,
                 events, created_at)
            VALUES (?, ?, ?, ?, 'queued', '[]', ?, ?, '[]', ?)
            """,
            (turn_id, conversation_id, turn_index, task, seed_docs, seed_observations, now),
        )

    touch_conversation(conversation_id)

    return get_turn(turn_id)


def get_turn(turn_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM turns WHERE id = ?",
            (turn_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_turn(row)


_UPDATABLE_JSON_FIELDS = {
    "validation_result",
    "execution_result",
    "artifacts",
    "retrieved_docs",
    "dataset_observations",
    "events",
}

_UPDATABLE_FIELDS = _UPDATABLE_JSON_FIELDS | {
    "status",
    "generated_code",
    "error",
}


def update_turn(turn_id: str, **fields) -> None:
    """Update one or more columns of a turn. JSON-serializable fields
    (events, artifacts, etc.) are serialized automatically."""

    unknown = set(fields) - _UPDATABLE_FIELDS

    if unknown:
        raise ValueError(f"Not updatable: {sorted(unknown)}")

    if not fields:
        return

    columns = []
    values = []

    for key, value in fields.items():
        columns.append(f"{key} = ?")

        if key in _UPDATABLE_JSON_FIELDS:
            values.append(json.dumps(value))
        else:
            values.append(value)

    values.append(turn_id)

    with _write_lock, _connect() as conn:
        conn.execute(
            f"UPDATE turns SET {', '.join(columns)} WHERE id = ?",
            values,
        )
