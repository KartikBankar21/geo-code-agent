from packages.agent.graph import build_graph
from packages.agent.nodes import close_resources

def main():
    graph = build_graph()

    task = (
        "Find all buildings within 500 meters of the Mula River "
        "using the available geospatial dataset."
    )

    try:

        result = graph.invoke(
            {
                "task": task,

                # Host-side path.
                # Used by list_layers / inspect_layer.
                "dataset_host_path":
                    "data/raw/mula-pavana-river/"
                    "mula-pavana-river.gpkg",

                # Sandbox-side path.
                # Used by generated code after Docker starts.
                "dataset_sandbox_path":
                    "/sandbox/input/mula-pavana-river/"
                    "mula-pavana-river.gpkg",

                "retrieved_docs": [],
                "dataset_observations": [],
                "iteration": 0,
            }
        )

        print()
        print("=" * 80)
        print("FINAL RESULT")
        print("=" * 80)

        print(f"Status: {result.get('status')}")
        print(f"Iterations: {result.get('iteration')}")

        if result.get("execution_result"):
            print()
            print("Execution result:")
            print(result["execution_result"])

        if result.get("generated_code"):
            print()
            print("Generated code:")
            print("=" * 80)
            print(result["generated_code"])
    finally:
        close_resources()

if __name__ == "__main__":
    main()