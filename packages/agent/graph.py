from langgraph.graph import StateGraph, START, END

from packages.agent.state import AgentState
from packages.agent.nodes import (
    agent_decide,
    search_docs,
    list_dataset_layers,
    inspect_dataset,
    generate_code,
    validate_generated_code,
    execute_code,
    finish,
)

MAX_ITERATIONS = 15


def route_after_decision(state):
    action = state["next_action"]

    if state.get("iteration", 0) > MAX_ITERATIONS:
        return "finish"

    routes = {
        "search_docs": "search_docs",
        "list_layers": "list_layers",
        "inspect_layer": "inspect_layer",
        "generate_code": "generate_code",
        "finish": "finish",
    }

    if action not in routes:
        raise RuntimeError(f"Unknown agent action: {action}")

    return routes[action]


def route_after_validation(state):
    validation = state["validation_result"]
    if validation["valid"]:
        return "execute_code"
    return "agent_decide"


def route_after_execution(state):
    # Always return to agent_decide so the agent can verify stdout/artifacts
    # and either execute the next code chunk or call "finish".
    return "agent_decide"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("agent_decide", agent_decide)
    graph.add_node("search_docs", search_docs)
    graph.add_node("list_layers", list_dataset_layers)
    graph.add_node("inspect_layer", inspect_dataset)
    graph.add_node("generate_code", generate_code)
    graph.add_node("validate_code", validate_generated_code)
    graph.add_node("execute_code", execute_code)
    graph.add_node("finish", finish)

    graph.add_edge(START, "agent_decide")

    graph.add_conditional_edges(
        "agent_decide",
        route_after_decision,
        {
            "search_docs": "search_docs",
            "list_layers": "list_layers",
            "inspect_layer": "inspect_layer",
            "generate_code": "generate_code",
            "finish": "finish",
        },
    )

    graph.add_edge("search_docs", "agent_decide")
    graph.add_edge("list_layers", "agent_decide")
    graph.add_edge("inspect_layer", "agent_decide")
    graph.add_edge("generate_code", "validate_code")

    graph.add_conditional_edges(
        "validate_code",
        route_after_validation,
        {
            "execute_code": "execute_code",
            "agent_decide": "agent_decide",
        },
    )

    graph.add_conditional_edges(
        "execute_code",
        route_after_execution,
        {
            "agent_decide": "agent_decide",
        },
    )

    graph.add_edge("finish", END)

    return graph.compile()
