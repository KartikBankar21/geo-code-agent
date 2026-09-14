from packages.agent.llm import get_llm_provider
from packages.agent.tools import ToolRegistry
from packages.execution.executor import Executor
from packages.execution.validator import validate_code


llm = get_llm_provider()
registry = ToolRegistry()


def _format_docs(docs: list[dict]) -> str:
    if not docs:
        return "No documentation has been retrieved yet."

    sections = []

    for index, doc in enumerate(docs, start=1):
        sections.append(
            f"""
DOCUMENT {index}
Library: {doc.get("library", "")}
Title: {doc.get("title", "")}
Score: {doc.get("score", "")}
Source: {doc.get("source", "")}

{doc.get("text", "")}
"""
        )

    return "\n".join(sections)


def _format_observations(observations: list[dict]) -> str:
    if not observations:
        return "No dataset observations have been collected yet."

    sections = []

    for index, observation in enumerate(observations, start=1):
        sections.append(
            f"""
OBSERVATION {index}
Type: {observation.get("type", "")}
Path: {observation.get("path", "")}
Layer: {observation.get("layer", "")}
Result:
{observation.get("result", observation.get("layers", ""))}
"""
        )

    return "\n".join(sections)


def agent_decide(state):
    """
    Central autonomous reasoning node.

    The LLM decides what information or action is required next.
    """

    task = state["task"]
    dataset_host_path = state["dataset_host_path"]
    dataset_sandbox_path = state["dataset_sandbox_path"]

    docs = state.get("retrieved_docs", [])
    observations = state.get("dataset_observations", [])

    execution = state.get("execution_result")
    validation = state.get("validation_result")

    iteration = state.get("iteration", 0)

    prompt = f"""
You are the DECISION-MAKING NODE of an autonomous geospatial code agent.

Your ONLY responsibility is to decide what the agent should do NEXT.

You do NOT generate Python code in this node.
You do NOT write pseudocode.
You do NOT design the implementation.
You do NOT execute GIS operations.

A separate node named "generate_code" is responsible for generating Python code.

USER TASK:
{task}

AUTHORITATIVE DATASET:

Host path:
{dataset_host_path}

Sandbox path:
{dataset_sandbox_path}

PATH RULES:
- list_layers and inspect_layer operate on the HOST path.
- Generated Python code operates inside the sandbox and must use the SANDBOX path.
- Never change or invent either path.

AVAILABLE INFORMATION-GATHERING ACTIONS:

1. search_docs

Search the indexed official GIS documentation.

Use this when you need information about:
- GeoPandas APIs
- Shapely APIs
- PyProj or CRS handling
- Rasterio
- spatial operations
- parameters
- file formats
- library behavior
- deprecated or changed APIs

2. list_layers

List the layers contained in the authoritative dataset.

Use this when you do not yet know which dataset layers are relevant.

3. inspect_layer

Inspect one specific dataset layer.

Use this when you need to know:
- columns
- CRS
- geometry type
- bounds
- row count
- available attributes

CODE GENERATION:

The action "generate_code" means:

"Sufficient information has been collected. Delegate the actual GIS implementation to the generate_code node."

When selecting "generate_code":

- DO NOT generate Python code.
- DO NOT write pseudocode.
- DO NOT describe the implementation.
- DO NOT add a "code" field.
- DO NOT include code inside any JSON field.
- ONLY return the decision JSON.

The separate generate_code node will:
1. use the available documentation and dataset observations
2. generate the Python implementation
3. use the sandbox path
4. produce the actual GIS code

The generated code will then be statically validated and executed inside a Docker sandbox.

After execution, the result or error will be returned to this decision node.

If execution fails, decide whether to:
- search documentation
- inspect more data
- generate corrected code
- finish if the result is nevertheless sufficient

IMPORTANT ARCHITECTURAL RULE:

There are NO predefined GIS operation tools.

Do NOT select or reason about operations such as:
- vector.buffer
- vector.reproject
- vector.spatial_intersection
- vector.filter_features

The actual GIS operations are implemented dynamically by the separate generate_code node.

AVAILABLE ACTIONS:

You must select EXACTLY ONE of:

- search_docs
- list_layers
- inspect_layer
- generate_code
- finish

DECISION RULES:

1. If you do not know which layers exist:
   choose "list_layers".

2. If the relevant layer is known but its schema or attributes are unknown:
   choose "inspect_layer".

3. If you need technical GIS/API knowledge:
   choose "search_docs".

4. If you have enough information to implement the user's task:
   choose "generate_code".

5. If the task has already been successfully completed:
   choose "finish".

6. Do not request information that is already available in the dataset observations or retrieved documentation.

7. Do not repeatedly inspect the same information unless the previous result was insufficient.

8. If validation or execution failed, use the failure information to decide the next action.

CURRENT ITERATION:
{iteration}

RETRIEVED DOCUMENTATION:
{_format_docs(docs)}

DATASET OBSERVATIONS:
{_format_observations(observations)}

LATEST VALIDATION RESULT:
{validation if validation else "None"}

LATEST EXECUTION RESULT:
{execution if execution else "None"}

OUTPUT FORMAT:

Return EXACTLY ONE JSON OBJECT.

Do not return:
- <think> tags
- chain-of-thought
- markdown
- explanations outside JSON
- Python code
- pseudocode
- a "code" field
- any additional fields

The JSON MUST contain exactly these five fields:

{{
    "action": "search_docs | list_layers | inspect_layer | generate_code | finish",
    "reason": "one short sentence explaining the decision",
    "query": "documentation query if action is search_docs, otherwise empty string",
    "path": "HOST dataset path if action is list_layers or inspect_layer, otherwise empty string",
    "layer": "layer name if action is inspect_layer, otherwise empty string"
}}

FIELD RULES:

- search_docs:
  - action = "search_docs"
  - query = the required documentation query
  - path = ""
  - layer = ""

- list_layers:
  - action = "list_layers"
  - query = ""
  - path = "{dataset_host_path}"
  - layer = ""

- inspect_layer:
  - action = "inspect_layer"
  - query = ""
  - path = "{dataset_host_path}"
  - layer = the layer that needs inspection

- generate_code:
  - action = "generate_code"
  - query = ""
  - path = ""
  - layer = ""

- finish:
  - action = "finish"
  - query = ""
  - path = ""
  - layer = ""

Remember:

YOU ARE ONLY THE DECISION NODE.

If the next step is code generation, output only:

{{
    "action": "generate_code",
    "reason": "Sufficient information is available to implement the task.",
    "query": "",
    "path": "",
    "layer": ""
}}

Do not generate the code yourself.
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
        raise RuntimeError(
            f"Invalid agent action: {action}"
        )

    print()
    print("[AGENT]")
    print(f"Action: {action}")
    print(f"Reason: {decision.get('reason', '')}")

    return {
        "agent_decision": decision,
        "next_action": action,
        "iteration": iteration + 1,
    }


def search_docs(state):
    """Search RAG when requested by the LLM."""

    decision = state["agent_decision"]

    query = decision.get("query", "").strip()

    if not query:
        raise RuntimeError(
            "Agent selected search_docs without a query."
        )

    print()
    print("[RAG]")
    print(f"Query: {query}")

    result = registry.search_docs(
        query=query,
        limit=8,
    )

    new_docs = result.get("results", [])

    existing = state.get("retrieved_docs", [])

    existing_ids = {
        doc.get("chunk_id")
        for doc in existing
    }

    unique_new_docs = [
        doc
        for doc in new_docs
        if doc.get("chunk_id") not in existing_ids
    ]

    print(
        f"Retrieved: {len(new_docs)} | "
        f"New: {len(unique_new_docs)}"
    )

    return {
        "retrieved_docs": existing + unique_new_docs,
    }


def list_dataset_layers(state):
    """List dataset layers when requested by the LLM."""

    path = state["dataset_host_path"]

    print()
    print("[DATA]")
    print(f"Listing layers: {path}")

    layers = registry.list_layers(path)

    print(f"Layers: {layers}")

    observations = state.get(
        "dataset_observations",
        [],
    )

    return {
        "dataset_observations": observations + [
            {
                "type": "layer_listing",
                "path": path,
                "layers": layers,
            }
        ]
    }


def inspect_dataset(state):
    """Inspect a dataset layer when requested by the LLM."""

    path = state["dataset_host_path"]

    decision = state["agent_decision"]

    layer = decision.get("layer", "").strip()

    if not layer:
        raise RuntimeError(
            "Agent selected inspect_layer without a layer."
        )

    print()
    print("[DATA]")
    print(f"Inspecting: {path}")
    print(f"Layer: {layer}")

    result = registry.inspect_layer(
        path=path,
        layer=layer,
    )

    observations = state.get(
        "dataset_observations",
        [],
    )

    return {
        "dataset_observations": observations + [
            {
                "type": "layer_inspection",
                "path": path,
                "layer": layer,
                "result": result,
            }
        ]
    }


def generate_code(state):
    """Generate the actual Python GIS action."""

    task = state["task"]
    dataset_path = state["dataset_sandbox_path"]

    docs = state.get("retrieved_docs", [])
    observations = state.get(
        "dataset_observations",
        [],
    )

    execution = state.get("execution_result")
    validation = state.get("validation_result")

    prompt = f"""
You are the ACTION GENERATION component of an autonomous
geospatial CODE AGENT.

USER TASK:
{task}

AUTHORITATIVE DATASET:
{dataset_path}

The reasoning phase has determined that enough information
has been collected to generate the actual GIS action.

Write executable Python code that solves the user's task.

IMPORTANT:

You are a CODE AGENT.

Do NOT call predefined GIS capabilities.

Do NOT write JSON describing operations.

Do NOT describe what should be done.

Write the actual Python code.

The code may use appropriate libraries such as:
- geopandas
- shapely
- pyproj
- rasterio

Use the retrieved documentation as the technical reference.

Use the dataset observations to understand the actual
dataset structure.

Do not invent columns, layer names, APIs, or parameters
when the available information/documentation establishes them.

The code will execute inside a controlled Docker sandbox.

Security restrictions:
- no subprocess
- no os.system
- no eval
- no exec
- no network access
- no filesystem traversal

The dataset is available under the authoritative path above.

If a persistent result is required, write it to:

/sandbox/output

Print concise useful result information.

RETRIEVED DOCUMENTATION:
{_format_docs(docs)}

DATASET OBSERVATIONS:
{_format_observations(observations)}

LATEST EXECUTION RESULT:
{execution if execution else "None"}

LATEST VALIDATION RESULT:
{validation if validation else "None"}

IMPORTANT VALIDATION FEEDBACK:

If the latest validation result is invalid, you MUST correct
the previously generated code.

For every item in "import_violations":
- Do NOT import that module.
- Do NOT use that module in the generated code.

For every item in "dangerous_operations":
- Remove or replace that operation.

If validation failed only because of forbidden imports or
dangerous operations, do not repeat the same violation.

Return ONLY Python code.
"""

    print()
    print("[AGENT] Generating Python action...")

    code = llm.generate_code(prompt)

    print()
    print("[CODE]")
    print("=" * 80)
    print(code)
    print("=" * 80)

    return {
        "generated_code": code,
    }


def validate_generated_code(state):
    """Validate generated Python before execution."""

    code = state["generated_code"]

    result = validate_code(code)

    validation = {
        "valid": result.valid,
        "syntax_valid": result.syntax_valid,
        "syntax_error": result.syntax_error,
        "import_violations": result.import_violations,
        "dangerous_operations": result.dangerous_operations,
    }

    print()
    print("[VALIDATOR]")
    print(validation)

    return {
        "validation_result": validation,
    }


def execute_code(state):
    """Execute validated Python inside the Docker sandbox."""

    if not state["validation_result"]["valid"]:
        return {}

    executor = Executor()

    print()
    print("[SANDBOX] Starting...")

    executor.start()

    try:
        result = executor.execute(
            state["generated_code"]
        )
    finally:
        executor.stop()

    execution = {
        "status": result.status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "execution_time": result.execution_time,
        "artifacts": result.artifacts,
    }

    print()
    print("[SANDBOX RESULT]")
    print(execution)

    return {
        "execution_result": execution,
    }


def finish(state):
    """Terminate the current task."""

    execution = state.get("execution_result", {})

    print()
    print("[AGENT] Finished.")
    print(f"Status: {execution.get('status', 'completed')}")

    return {
        "status": "completed",
    }

def close_resources():
    """Close resources owned by the agent."""
    registry.close()