from packages.agent.graph import build_graph


def main():
    graph = build_graph()

    graph_image = graph.get_graph().draw_mermaid_png()

    output_path = "agent_graph.png"

    with open(output_path, "wb") as f:
        f.write(graph_image)

    print(f"\nGraph image saved to: {output_path}")


if __name__ == "__main__":
    main()

