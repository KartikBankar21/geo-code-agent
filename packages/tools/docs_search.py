from packages.rag.retriever import GeoRetriever, MultiLibraryRetriever


class DocumentationSearchTool:
    """
    Search official documentation for geospatial libraries.

    By default this searches across every library currently indexed
    in Qdrant (see packages.rag.config.LIBRARIES) and merges results
    by relevance, so the agent isn't limited to whichever library
    happens to be relevant to a given task. Pass a specific `library`
    name to restrict the search to just that one instead.
    """

    def __init__(self, library: str | None = None):
        self.library = library

        if library is None:
            self.retriever = MultiLibraryRetriever()
        else:
            self.retriever = GeoRetriever(library)

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> dict:
        """
        Search documentation and return agent-friendly results.
        """

        if not query.strip():
            raise ValueError("Search query cannot be empty.")

        results = self.retriever.search(
            query=query,
            limit=limit,
        )

        return {
            "library": self.library or "all",
            "query": query,
            "results": [
                {
                    "title": result["title"],
                    "score": round(result["score"], 4),
                    "source": result["source"],
                    "chunk_id": result["chunk_id"],
                    "library": result["library"],
                    "text": result["text"],
                }
                for result in results
            ],
        }

    def close(self) -> None:
        """Close the underlying documentation retriever."""
        self.retriever.close()


if __name__ == "__main__":
    tool = DocumentationSearchTool()

    result = tool.search(
        "How do I create a buffer around a river?",
        limit=3,
    )

    print()
    print("Library:", result["library"])
    print("Query:", result["query"])
    print("Results:", len(result["results"]))

    for index, item in enumerate(
        result["results"],
        start=1,
    ):
        print()
        print("=" * 80)
        print(f"RESULT {index}")
        print("=" * 80)
        print("Title:", item["title"])
        print("Library:", item["library"])
        print("Score:", item["score"])
        print("Chunk:", item["chunk_id"])
        print("Source:", item["source"])
        print()
        print(item["text"][:1000])
