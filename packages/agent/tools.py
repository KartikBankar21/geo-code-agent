from packages.tools.docs_search import DocumentationSearchTool
from packages.tools.geospatial import (
    list_layers,
    inspect_layer,
)


class ToolRegistry:
    """
    Tools available to the geospatial code agent.

    These tools provide information about the environment and
    documentation. GIS operations themselves are NOT exposed
    as individual tools; the LLM writes Python code to perform
    those operations.
    """

    def __init__(self):
        self.docs = DocumentationSearchTool()

    def search_docs(
        self,
        query: str,
        limit: int = 5,
    ) -> dict:
        return self.docs.search(
            query=query,
            limit=limit,
        )
    
    def close(self) -> None:
        """Close resources owned by the tool registry."""
        self.docs.close()

    def list_layers(
        self,
        path: str,
    ) -> list[str]:
        return list_layers(path)

    def inspect_layer(
        self,
        path: str,
        layer: str | None = None,
    ) -> dict:
        return inspect_layer(
            path=path,
            layer=layer,
        )
