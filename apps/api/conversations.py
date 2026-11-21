import os
import asyncio
import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.api import config, storage
from apps.api.datasets import _discover_dataset
from apps.api.schemas import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetail,
    ConversationListResponse,
    ContinueConversationRequest,
    ContinueConversationResponse,
    TaskEvent,
    TurnSummary,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@dataclass
class LiveTurn:
    """In-memory buffer for a turn's events while it's actively running.

    This exists purely so the SSE endpoint can poll something fast and
    in-process; SQLite (via `storage`) is written through at the same
    time and remains the durable copy used once a turn finishes or the
    server restarts.
    """

    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


LIVE_TURNS: dict[str, LiveTurn] = {}

_job_queue: "queue.Queue[str | None]" = queue.Queue()

_graph = None
_graph_error: str | None = None
_graph_lock = threading.Lock()


def get_graph():
    """Build the compiled LangGraph agent once, lazily.

    Deferred rather than imported at module load, so a missing API key
    or an unreachable Ollama host turns into a clean, catchable error
    the first time a task is submitted, instead of crashing the whole
    API process at startup.
    """

    global _graph, _graph_error

    with _graph_lock:
        if _graph is None and _graph_error is None:
            try:
                from packages.agent.graph import build_graph

                _graph = build_graph()
            except Exception as e:
                _graph_error = str(e)

        return _graph, _graph_error


def graph_already_built() -> bool:
    """Side-effect-free check used at shutdown so closing resources
    never itself triggers building them for the first time."""

    return _graph is not None


def _worker_loop():
    while True:
        turn_id = _job_queue.get()

        if turn_id is None:
            _job_queue.task_done()
            break

        try:
            _run_turn(turn_id)
        finally:
            _job_queue.task_done()


_worker_thread: threading.Thread | None = None


def start_worker():
    """Start the background worker thread if it isn't already running.

    Scoped to the app lifespan (called from main.py's startup) rather
    than at module-import time, so it can be cleanly stopped and
    restarted - both for a real server restart-in-process and so tests
    that spin up multiple TestClient instances each get a live worker
    instead of silently reusing one that already exited.
    """

    global _worker_thread

    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()


def shutdown_worker():
    global _worker_thread

    if _worker_thread is not None:
        _job_queue.put(None)
        _worker_thread.join(timeout=5)
        _worker_thread = None


def _build_event(
    node_name: str,
    node_output: dict[str, Any],
    prior_docs: int,
    prior_observations: int,
) -> dict[str, Any]:
    """Turn a raw LangGraph node update into a UI-friendly event."""

    if node_name == "agent_decide":
        decision = node_output.get("agent_decision", {})
        return {
            "node": node_name,
            "type": "decision",
            "data": {
                "iteration": node_output.get("iteration"),
                "action": decision.get("action"),
                "reason": decision.get("reason"),
                "query": decision.get("query"),
                "path": decision.get("path"),
                "layer": decision.get("layer"),
            },
        }

    if node_name == "search_docs":
        all_docs = node_output.get("retrieved_docs", [])
        new_docs = all_docs[prior_docs:]
        return {
            "node": node_name,
            "type": "docs_retrieved",
            "data": {
                "new_docs": [
                    {
                        "title": d.get("title"),
                        "score": d.get("score"),
                        "source": d.get("source"),
                        "library": d.get("library"),
                    }
                    for d in new_docs
                ],
                "total_docs": len(all_docs),
            },
        }

    if node_name == "list_layers":
        new_obs = node_output.get("dataset_observations", [])[prior_observations:]
        latest = new_obs[-1] if new_obs else {}
        return {
            "node": node_name,
            "type": "layers_listed",
            "data": {"layers": latest.get("layers", [])},
        }

    if node_name == "inspect_layer":
        new_obs = node_output.get("dataset_observations", [])[prior_observations:]
        latest = new_obs[-1] if new_obs else {}
        return {
            "node": node_name,
            "type": "layer_inspected",
            "data": {
                "layer": latest.get("layer"),
                "result": latest.get("result", {}),
            },
        }

    if node_name == "generate_code":
        return {
            "node": node_name,
            "type": "code_generated",
            "data": {"code": node_output.get("generated_code", "")},
        }

    if node_name == "validate_code":
        return {
            "node": node_name,
            "type": "validation_result",
            "data": node_output.get("validation_result", {}),
        }

    if node_name == "execute_code":
        execution_result = node_output.get("execution_result")

        if execution_result is None:
            data = {
                "skipped": True,
                "reason": "Validation failed; execution was skipped.",
            }
        else:
            data = execution_result

        return {"node": node_name, "type": "execution_result", "data": data}

    if node_name == "finish":
        return {"node": node_name, "type": "finished", "data": {}}

    return {"node": node_name, "type": "update", "data": node_output}


def _summarize_turn_for_context(turn: dict) -> str:
    """One compact block describing a prior turn, for the follow-up prompt."""

    execution = turn.get("execution_result") or {}
    status = execution.get("status", turn.get("status", "unknown"))

    lines = [
        f'Step {turn["turn_index"] + 1} task: "{turn["task"]}"',
        f"Step {turn['turn_index'] + 1} outcome: {status}",
    ]

    artifacts = turn.get("artifacts") or []
    if artifacts:
        lines.append(f"Step {turn['turn_index'] + 1} produced: {', '.join(artifacts)}")

    stdout = (execution.get("stdout") or "").strip()
    if stdout:
        lines.append(f"Step {turn['turn_index'] + 1} output: {stdout[:500]}")

    error_message = execution.get("error_message") or turn.get("error")
    if error_message:
        lines.append(f"Step {turn['turn_index'] + 1} error: {error_message}")

    return "\n".join(lines)


def _build_composite_task(conversation_id: str, current_turn_id: str, current_task: str) -> str:
    """
    Prepend a short summary of prior turns to the new task text, so the
    agent understands what "the previous result" or "that layer" refers
    to when a conversation is continued. The first turn in a
    conversation is unaffected (no prior turns to summarize).
    """

    conversation = storage.get_conversation(conversation_id)

    prior_turns = [
        t for t in conversation["turns"] if t["id"] != current_turn_id
    ]

    if not prior_turns:
        return current_task

    summary_blocks = [_summarize_turn_for_context(t) for t in prior_turns]

    return (
        "CONVERSATION SO FAR (earlier steps in this same session, on the "
        "same dataset):\n\n"
        + "\n\n".join(summary_blocks)
        + "\n\nCURRENT TASK (what to do now, possibly building on the "
        "above):\n"
        + current_task
    )


def _run_turn(turn_id: str):
    turn = storage.get_turn(turn_id)
    conversation = storage.get_conversation(turn["conversation_id"])

    live = LIVE_TURNS[turn_id]

    graph, error = get_graph()

    if graph is None:
        message = f"Agent could not be initialized: {error}"
        storage.update_turn(turn_id, status="failed", error=message)
        with live.lock:
            live.status = "failed"
            live.error = message
        return

    storage.update_turn(turn_id, status="running")
    with live.lock:
        live.status = "running"

    composite_task = _build_composite_task(
        conversation["id"], turn_id, turn["task"]
    )

    initial_state = {
        "task": composite_task,
        "dataset_host_path": conversation["dataset_host_path"],
        "dataset_sandbox_path": conversation["dataset_sandbox_path"],
        "messages": [],
        "retrieved_docs": turn["retrieved_docs"],
        "dataset_observations": turn["dataset_observations"],
        "iteration": 0,
        "conversation_id": conversation["id"],
        "turn_id": turn_id
    }

    accumulated: dict[str, Any] = dict(initial_state)

    try:
        for update in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in update.items():
                if node_output is None:
                    node_output = {}

                prior_docs = len(accumulated.get("retrieved_docs", []))
                prior_observations = len(accumulated.get("dataset_observations", []))

                accumulated.update(node_output)

                event = _build_event(
                    node_name, node_output, prior_docs, prior_observations
                )

                with live.lock:
                    live.events.append(event)

                turn_updates: dict[str, Any] = {"events": live.events}

                if "generated_code" in accumulated:
                    turn_updates["generated_code"] = accumulated["generated_code"]
                if "validation_result" in accumulated:
                    turn_updates["validation_result"] = accumulated["validation_result"]
                if accumulated.get("execution_result") is not None:
                    turn_updates["execution_result"] = accumulated["execution_result"]
                    if accumulated["execution_result"].get("artifacts"):
                        turn_updates["artifacts"] = accumulated["execution_result"]["artifacts"]
                if "retrieved_docs" in accumulated:
                    turn_updates["retrieved_docs"] = accumulated["retrieved_docs"]
                if "dataset_observations" in accumulated:
                    turn_updates["dataset_observations"] = accumulated["dataset_observations"]

                storage.update_turn(turn_id, **turn_updates)

        storage.update_turn(turn_id, status="completed")
        with live.lock:
            live.status = "completed"

    except Exception as e:
        message = str(e)
        storage.update_turn(turn_id, status="failed", error=message, events=live.events)
        with live.lock:
            live.status = "failed"
            live.error = message
            live.events.append({"node": "server", "type": "error", "data": {"message": message}})


def _resolve_dataset_file(dataset_name: str, filename: str | None):
    dataset_dir = config.RAW_DIR / dataset_name

    if not dataset_dir.exists():
        raise HTTPException(404, f"Dataset '{dataset_name}' not found.")

    dataset = _discover_dataset(dataset_dir)

    if not dataset.files:
        raise HTTPException(404, f"Dataset '{dataset_name}' has no vector files.")

    if filename:
        matches = [f for f in dataset.files if f.filename == filename]

        if not matches:
            raise HTTPException(
                404, f"File '{filename}' not found in dataset '{dataset_name}'."
            )

        return matches[0]

    return dataset.files[0]


def _title_from_task(task: str, max_length: int = 60) -> str:
    task = " ".join(task.split())

    if len(task) <= max_length:
        return task

    return task[: max_length - 1].rstrip() + "…"


@router.post("", response_model=ConversationCreateResponse)
def create_conversation(payload: ConversationCreateRequest):
    """Start a new GIS workflow chat against a dataset."""

    target = _resolve_dataset_file(payload.dataset, payload.file)

    if target.sandbox_path is None:
        raise HTTPException(
            400,
            "Selected file is not under data/raw and is not reachable "
            "from inside the sandbox.",
        )

    conversation = storage.create_conversation(
        dataset_host_path=target.host_path,
        dataset_sandbox_path=target.sandbox_path,
        title=_title_from_task(payload.task),
    )

    turn = storage.create_turn(conversation["id"], payload.task)

    LIVE_TURNS[turn["id"]] = LiveTurn()
    _job_queue.put(turn["id"])

    return ConversationCreateResponse(
        conversation_id=conversation["id"], turn_id=turn["id"]
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations():
    """List past and in-progress GIS workflow chats, most recent first."""

    return ConversationListResponse(conversations=storage.list_conversations())


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str):
    conversation = storage.get_conversation(conversation_id)

    if conversation is None:
        raise HTTPException(404, "Conversation not found.")

    return conversation


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: str):
    if storage.get_conversation(conversation_id) is None:
        raise HTTPException(404, "Conversation not found.")

    storage.delete_conversation(conversation_id)

    executor_url = os.getenv("SANDBOX_EXECUTOR_URL", "").strip()
    if executor_url:
        from packages.execution.remote_executor import RemoteExecutor

        secret = os.getenv("EXECUTOR_SHARED_SECRET", "").strip()
        RemoteExecutor(executor_url, secret).delete_session(conversation_id)

    return {"deleted": True}


@router.post("/{conversation_id}/turns", response_model=ContinueConversationResponse)
def continue_conversation(conversation_id: str, payload: ContinueConversationRequest):
    """Continue an existing chat with a follow-up task."""

    conversation = storage.get_conversation(conversation_id)

    if conversation is None:
        raise HTTPException(404, "Conversation not found.")

    turn = storage.create_turn(conversation_id, payload.task)

    LIVE_TURNS[turn["id"]] = LiveTurn()
    _job_queue.put(turn["id"])

    return ContinueConversationResponse(turn_id=turn["id"])


@router.get("/{conversation_id}/turns/{turn_id}/stream")
async def stream_turn(conversation_id: str, turn_id: str):
    """
    Server-Sent Events stream of a turn's live reasoning trace.

    Works for a currently-running turn. For a turn that already
    finished (e.g. the page was reloaded), replays its persisted
    events once and immediately sends "done" - callers can also just
    use GET /api/conversations/{id} for that case instead.
    """

    live = LIVE_TURNS.get(turn_id)

    if live is None:
        stored = storage.get_turn(turn_id)

        if stored is None or stored["conversation_id"] != conversation_id:
            raise HTTPException(404, "Turn not found.")

        async def replay_generator():
            for event in stored["events"]:
                yield f"data: {json.dumps(event)}\n\n"

            done_event = {
                "node": "server",
                "type": "done",
                "data": {"status": stored["status"], "error": stored["error"]},
            }
            yield f"data: {json.dumps(done_event)}\n\n"

        return StreamingResponse(
            replay_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    async def event_generator():
        sent = 0

        while True:
            with live.lock:
                pending = live.events[sent:]
                status = live.status
                error = live.error
                sent = len(live.events)

            for event in pending:
                yield f"data: {json.dumps(event)}\n\n"

            if status in ("completed", "failed"):
                done_event = {
                    "node": "server",
                    "type": "done",
                    "data": {"status": status, "error": error},
                }
                yield f"data: {json.dumps(done_event)}\n\n"
                LIVE_TURNS.pop(turn_id, None)
                break

            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
