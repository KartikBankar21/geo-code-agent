from typing import TypedDict


class AgentState(TypedDict, total=False):
    # User request
    task: str

    # Dataset paths
    dataset_host_path: str
    dataset_sandbox_path: str

    # Agent conversation / reasoning history
    messages: list[dict]

    # Knowledge retrieved from RAG
    retrieved_docs: list[dict]
    docs_searched: bool

    # Information discovered from the dataset
    dataset_observations: list[dict]

    # Multi-step chunked code execution state
    generated_code: str
    code_history: list[str]
    execution_history: list[dict]
    conversation_id: str
    turn_id:str

    # Static validation result
    validation_result: dict

    # Latest sandbox execution result
    execution_result: dict

    # LLM's latest decision
    agent_decision: dict
    next_action: str

    # Control
    iteration: int
    status: str