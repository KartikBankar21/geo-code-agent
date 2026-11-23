import os

from packages.agent.llm import get_llm_provider
from packages.agent.tools import ToolRegistry
from packages.execution.executor import Executor
from packages.execution.validator import validate_code
from packages.observability.otel import get_meter, traced_span

llm = get_llm_provider()
registry = ToolRegistry()

MAX_AGENT_ITERATIONS = 15

_agent_meter = get_meter("geo-agent.graph")
_validation_failures = _agent_meter.create_counter(
    name="geo_agent.validation.failures",
    description="Count of generated scripts rejected by AST/security policy",
)
_sandbox_duration = _agent_meter.create_histogram(
    name="geo_agent.sandbox.duration_seconds",
    description="End-to-end sandbox execution latency in seconds",
    unit="s",
)

# Reusable local executor so variables persist across multi-step chunks
_local_executor: Executor | None = None


def _get_local_executor() -> Executor:
    global _local_executor
    if _local_executor is None:
        _local_executor = Executor()
        _local_executor.start()
    return _local_executor


def reset_local_executor() -> None:
    global _local_executor
    if _local_executor is not None:
        _local_executor.stop()
        _local_executor = None


def _format_docs(docs: list[dict], max_docs: int = 4, max_chars_per_doc: int = 1200) -> str:
    if not docs:
        return "No documentation has been retrieved yet."

    top_docs = sorted(docs, key=lambda d: d.get("score", 0), reverse=True)[:max_docs]
    sections = []

    for index, doc in enumerate(top_docs, start=1):
        snippet = (doc.get("text", "") or "")[:max_chars_per_doc]
        sections.append(
            f"DOCUMENT {index} [{doc.get('library', '')} - {doc.get('title', '')}]:\n{snippet}"
        )

    return "\n\n".join(sections)


def _format_observations(observations: list[dict]) -> str:
    if not observations:
        return "No dataset observations have been collected yet."

    sections = []
    for index, observation in enumerate(observations, start=1):
        sections.append(
            f"OBSERVATION {index} ({observation.get('type', '')} | layer={observation.get('layer', '')}):\n"
            f"{observation.get('result', observation.get('layers', ''))}"
        )

    return "\n\n".join(sections)


def _format_execution_history(history: list[dict]) -> str:
    if not history:
        return "No code chunks have been executed yet in this session."

    sections = []
    for idx, item in enumerate(history, start=1):
        sections.append(
            f"--- CHUNK {idx} (status={item.get('status')}) ---\n"
            f"Code:\n{item.get('code', '')}\n"
            f"Stdout: {item.get('stdout', '').strip() or '(none)'}\n"
            f"Artifacts: {item.get('artifacts', [])}\n"
            f"Error: {item.get('error_message') or 'None'}"
        )
    return "\n\n".join(sections)


def agent_decide(state):
    task = state["task"]
    dataset_host_path = state["dataset_host_path"]
    dataset_sandbox_path = state["dataset_sandbox_path"]

    docs = state.get("retrieved_docs", [])
    observations = state.get("dataset_observations", [])
    execution_history = state.get("execution_history", [])
    execution = state.get("execution_result")
    validation = state.get("validation_result")
    iteration = state.get("iteration", 0)

    with traced_span(
        "agent.decide",
        {
            "conversation.id": state.get("conversation_id", ""),
            "turn.id": state.get("turn_id", ""),
            "agent.iteration": iteration,
        },
    ) as span:
        if iteration >= MAX_AGENT_ITERATIONS:
            span.set_attribute("agent.next_action", "finish")
            print(f"\n[AGENT] Action: finish | Reason: Reached max iterations ({MAX_AGENT_ITERATIONS}).")
            return {
                "agent_decision": {
                    "action": "finish",
                    "reason": f"Reached maximum iterations ({MAX_AGENT_ITERATIONS}).",
                    "query": "",
                    "path": "",
                    "layer": "",
                },
                "next_action": "finish",
                "iteration": iteration + 1,
            }

        listed_paths = {
            obs.get("path")
            for obs in observations
            if obs.get("type") == "layer_listing"
        }
        inspected_layers = {
            (obs.get("path"), obs.get("layer"))
            for obs in observations
            if obs.get("type") == "layer_inspection"
        }

        prompt = f"""
You are the DECISION-MAKING NODE of an autonomous geospatial code agent.
Your ONLY responsibility is to decide what the agent should do NEXT.

USER TASK:
{task}

AUTHORITATIVE DATASET:
Host path: {dataset_host_path}
Sandbox path: {dataset_sandbox_path}

ALREADY COMPLETED OBSERVATIONS (DO NOT REPEAT THESE):
- Layers already listed for paths: {sorted(p for p in listed_paths if p)}
- Layers already inspected (path, layer): {sorted((p, l) for p, l in inspected_layers if p and l)}

MULTI-STEP EXECUTION MODEL:
- The Python sandbox is STATEFUL: variables, imports, and GeoDataFrames created in earlier chunks stay in memory for subsequent chunks!
- Break complex geospatial tasks into 2-4 small, verifiable steps (e.g., Chunk 1: load & filter features, print counts/CRS; Chunk 2: reproject & compute spatial buffer/join; Chunk 3: save final output to /sandbox/output/<filename>.gpkg).
- Only choose "finish" AFTER the requested output file has been saved to /sandbox/output and verified via stdout.

AVAILABLE ACTIONS (choose EXACTLY ONE):
1. "list_layers": List layers in the dataset (ONLY if not already listed).
2. "inspect_layer": Inspect schema, CRS, geometry type, columns, and sample rows of a layer (ONLY if that layer has NOT been inspected yet).
3. "search_docs": Search official GIS documentation (GeoPandas, Shapely, PyProj, Rasterio) to verify exact method names and parameters before coding.
4. "generate_code": Generate the NEXT small Python code chunk to execute in the stateful sandbox.
5. "finish": End the workflow once all steps are complete and output artifacts are generated.

DECISION RULES:
- NEVER call "list_layers" or "inspect_layer" for a path/layer already listed above. To inspect specific feature values (like river names), use "generate_code" to filter/print inside Python.
- Consult "search_docs" at least once before generating code to confirm API signatures.
- If previous chunks succeeded, inspect their stdout and decide whether another code chunk is needed or if the task is complete ("finish").

CURRENT ITERATION: {iteration}

DATASET OBSERVATIONS:
{_format_observations(observations)}

RETRIEVED DOCUMENTATION:
{_format_docs(docs)}

EXECUTED CODE CHUNKS SO FAR:
{_format_execution_history(execution_history)}

LATEST VALIDATION RESULT:
{validation if validation else "None"}

LATEST EXECUTION RESULT:
{execution if execution else "None"}

Return EXACTLY ONE JSON object with these five keys:
{{
    "action": "search_docs | list_layers | inspect_layer | generate_code | finish",
    "reason": "one short sentence explaining the decision",
    "query": "documentation query if action is search_docs, otherwise empty string",
    "path": "{dataset_host_path} if action is list_layers or inspect_layer, otherwise empty string",
    "layer": "layer name if action is inspect_layer, otherwise empty string"
}}
"""

        decision = llm.generate_json(prompt)
        action = decision.get("action")

        valid_actions = {
            "search_docs",
            "list_layers",
            "inspect_layer",
            "generate_code",
            "finish",
        }

        if action not in valid_actions:
            raise RuntimeError(f"Invalid agent action: {action}")

        # ANTI-LOOP GUARDRAIL
        if action == "list_layers" and dataset_host_path in listed_paths:
            action = "generate_code"
            decision["action"] = "generate_code"
            decision["reason"] = "Harness policy: dataset layers already listed; proceeding to code generation."
            decision["path"] = ""
            decision["layer"] = ""

        elif action == "inspect_layer":
            target_layer = decision.get("layer", "").strip()
            if (dataset_host_path, target_layer) in inspected_layers:
                action = "generate_code"
                decision["action"] = "generate_code"
                decision["reason"] = (
                    f"Harness policy: layer '{target_layer}' already inspected; proceeding to code generation."
                )
                decision["path"] = ""
                decision["layer"] = ""

        # DETERMINISTIC RAG HARNESSING GUARDRAIL
        if action == "generate_code" and len(docs) == 0:
            action = "search_docs"
            decision["action"] = "search_docs"
            decision["query"] = f"geopandas spatial operations buffer sjoin to_crs for: {task[:120]}"
            decision["reason"] = (
                "Harness policy: verifying official GIS API documentation before first code generation."
            )
            decision["path"] = ""
            decision["layer"] = ""

        span.set_attribute("agent.next_action", action)
        print(f"\n[AGENT] Action: {action} | Reason: {decision.get('reason', '')}")

        return {
            "agent_decision": decision,
            "next_action": action,
            "iteration": iteration + 1,
        }


def search_docs(state):
    decision = state["agent_decision"]
    query = decision.get("query", "").strip()

    if not query:
        raise RuntimeError("Agent selected search_docs without a query.")

    with traced_span(
        "tool.search_docs",
        {"rag.query": query, "conversation.id": state.get("conversation_id", "")},
    ) as span:
        print(f"\n[RAG] Query: {query}")
        result = registry.search_docs(query=query, limit=4)

        new_docs = result.get("results", [])
        existing = state.get("retrieved_docs", [])
        existing_ids = {doc.get("chunk_id") for doc in existing}

        unique_new_docs = [
            doc for doc in new_docs if doc.get("chunk_id") not in existing_ids
        ]

        span.set_attribute("rag.retrieved_count", len(new_docs))
        span.set_attribute("rag.new_count", len(unique_new_docs))
        print(f"Retrieved: {len(new_docs)} | New: {len(unique_new_docs)}")

        return {
            "retrieved_docs": existing + unique_new_docs,
            "docs_searched": True,
        }


def list_dataset_layers(state):
    path = state["dataset_host_path"]
    with traced_span("tool.list_layers", {"dataset.path": path}):
        print(f"\n[DATA] Listing layers: {path}")
        layers = registry.list_layers(path)
        observations = state.get("dataset_observations", [])

        return {
            "dataset_observations": observations
            + [{"type": "layer_listing", "path": path, "layers": layers}]
        }


def inspect_dataset(state):
    path = state["dataset_host_path"]
    layer = state["agent_decision"].get("layer", "").strip()

    if not layer:
        raise RuntimeError("Agent selected inspect_layer without a layer.")

    with traced_span("tool.inspect_layer", {"dataset.path": path, "dataset.layer": layer}):
        print(f"\n[DATA] Inspecting {path} -> layer={layer}")
        result = registry.inspect_layer(path=path, layer=layer)
        observations = state.get("dataset_observations", [])

        return {
            "dataset_observations": observations
            + [
                {
                    "type": "layer_inspection",
                    "path": path,
                    "layer": layer,
                    "result": result,
                }
            ]
        }


def generate_code(state):
    task = state["task"]
    dataset_path = state["dataset_sandbox_path"]
    docs = state.get("retrieved_docs", [])
    observations = state.get("dataset_observations", [])
    execution_history = state.get("execution_history", [])
    execution = state.get("execution_result")
    validation = state.get("validation_result")

    prompt = f"""
You are the ACTION GENERATION component of an autonomous geospatial CODE AGENT.

USER TASK:
{task}

AUTHORITATIVE DATASET (SANDBOX PATH):
{dataset_path}

STATEFUL MULTI-STEP EXECUTION RULES:
- The Docker Python worker keeps all variables and imports in memory across steps!
- Write ONLY the NEXT focused step (keep it concise: 15-35 lines of clean Python).
- Do NOT repeat work already completed in previous successful chunks; reuse variables already in memory.
- Print concise verification info (e.g. row counts, CRS, sample values, saved file path) so the decision node can verify progress.
- When saving the final spatial output, write it inside `/sandbox/output/` (e.g. `/sandbox/output/result.gpkg`).

ALLOWED LIBRARIES:
- geopandas, shapely, pyproj, rasterio, os, pathlib

SECURITY RESTRICTIONS:
- No subprocess, no os.system, no eval/exec, no open(), no network access.

DATASET OBSERVATIONS:
{_format_observations(observations)}

RETRIEVED DOCUMENTATION:
{_format_docs(docs)}

PREVIOUSLY EXECUTED CHUNKS (ALREADY IN SANDBOX MEMORY):
{_format_execution_history(execution_history)}

LATEST VALIDATION RESULT:
{validation if validation else "None"}

LATEST EXECUTION RESULT:
{execution if execution else "None"}

Return ONLY valid Python code (no explanations outside code fences).
"""

    with traced_span(
        "agent.generate_code",
        {"conversation.id": state.get("conversation_id", "")},
    ) as span:
        print("\n[AGENT] Generating Python chunk...")
        code = llm.generate_code(prompt)
        span.set_attribute("code.line_count", len(code.splitlines()))
        print(f"\n[CODE CHUNK]\n{'=' * 60}\n{code}\n{'=' * 60}")

        return {"generated_code": code}


def validate_generated_code(state):
    code = state["generated_code"]
    with traced_span("tool.validate_code") as span:
        result = validate_code(code)

        validation = {
            "valid": result.valid,
            "syntax_valid": result.syntax_valid,
            "syntax_error": result.syntax_error,
            "import_violations": result.import_violations,
            "dangerous_operations": result.dangerous_operations,
        }

        span.set_attribute("validation.valid", result.valid)
        if not result.valid:
            _validation_failures.add(
                1,
                {
                    "syntax_valid": str(result.syntax_valid),
                    "has_import_violation": str(bool(result.import_violations)),
                    "has_dangerous_op": str(bool(result.dangerous_operations)),
                },
            )

        print(f"\n[VALIDATOR] {validation}")
        return {"validation_result": validation}


def execute_code(state):
    if not state["validation_result"]["valid"]:
        return {}

    code = state["generated_code"]
    executor_url = os.getenv("SANDBOX_EXECUTOR_URL", "").strip()

    with traced_span(
        "tool.execute_code",
        {
            "conversation.id": state.get("conversation_id", "default"),
            "turn.id": state.get("turn_id", "default"),
            "sandbox.mode": "remote" if executor_url else "local",
        },
    ) as span:
        if executor_url:
            from packages.execution.remote_executor import RemoteExecutor

            secret = os.getenv("EXECUTOR_SHARED_SECRET", "").strip()
            conversation_id = state.get("conversation_id", "default")
            turn_id = state.get("turn_id", "default")

            print(f"\n[SANDBOX REMOTE] Executing chunk on Tier 3 (session={conversation_id})...")
            remote = RemoteExecutor(executor_url, secret)
            result = remote.execute(
                code,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
        else:
            executor = _get_local_executor()
            print("\n[SANDBOX LOCAL] Executing chunk in persistent namespace...")
            result = executor.execute(code)

        span.set_attribute("sandbox.status", result.status)
        span.set_attribute("sandbox.artifacts_count", len(result.artifacts))
        _sandbox_duration.record(result.execution_time, {"status": result.status})

        execution = {
            "status": result.status,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "execution_time": result.execution_time,
            "artifacts": result.artifacts,
        }

        print(f"\n[SANDBOX RESULT] {execution}")

        history = state.get("execution_history", [])
        history_entry = {
            "code": code,
            "status": result.status,
            "stdout": result.stdout[:1000],
            "artifacts": result.artifacts,
            "error_message": result.error_message,
        }

        return {
            "execution_result": execution,
            "execution_history": history + [history_entry],
        }


def finish(state):
    execution = state.get("execution_result", {})
    print(f"\n[AGENT] Finished. Latest execution status: {execution.get('status', 'completed')}")
    return {"status": "completed"}


def close_resources():
    reset_local_executor()
    registry.close()
