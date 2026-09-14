from typing import TypedDict


class AgentState(TypedDict, total=False):
    # User request
    task: str

    # Dataset paths
    # Host path is used by information-gathering operations.
    dataset_host_path: str

    # Sandbox path is used by generated code during execution.
    dataset_sandbox_path: str

    # Agent conversation / reasoning history
    messages: list[dict]

    # Knowledge retrieved from RAG
    retrieved_docs: list[dict]

    # Information discovered from the dataset
    dataset_observations: list[dict]

    # LLM-generated Python action
    generated_code: str

    # Static validation result
    validation_result: dict

    # Actual sandbox execution result
    execution_result: dict

    # LLM's latest decision
    agent_decision: dict
    next_action: str

    # Control
    iteration: int
    status: str