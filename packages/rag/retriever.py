from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from packages.rag.config import get_library, LIBRARIES


QDRANT_DIR = Path("rag/qdrant")
MODEL_NAME = "BAAI/bge-small-en-v1.5"


class GeoRetriever:
    """Semantic retriever for geospatial documentation."""

    def __init__(
        self,
        library_name: str,
        model_name: str = MODEL_NAME,
    ):
        self.library = get_library(library_name)

        self.collection_name = (
            f"{library_name}_docs"
        )

        self.client = QdrantClient(
            path=str(QDRANT_DIR)
        )

        if not self.client.collection_exists(
            self.collection_name
        ):
            raise RuntimeError(
                f"Qdrant collection "
                f"'{self.collection_name}' does not exist. "
                f"Run embed_docs.py first."
            )

        print(
            f"Loading embedding model: {model_name}"
        )

        self.model = SentenceTransformer(
            model_name,
            device="cpu",
        )

        print("Embedding model loaded.")

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search documentation using semantic similarity."""

        if not query.strip():
            raise ValueError(
                "Query cannot be empty."
            )

        if limit < 1:
            raise ValueError(
                "Limit must be at least 1."
            )

        query_embedding = self.model.encode(
            query,
            normalize_embeddings=True,
        )

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding.tolist(),
            limit=limit,
        ).points

        documents = []

        for result in results:
            payload = result.payload

            documents.append(
                {
                    "score": result.score,
                    "library": payload["library"],
                    "version": payload["version"],
                    "chunk_id": payload["chunk_id"],
                    "title": payload["title"],
                    "source": payload["source"],
                    "text": payload["text"],
                }
            )

        return documents
    
    def close(self) -> None:
        """Close the Qdrant client."""
        self.client.close()


class MultiLibraryRetriever:
    """
    Searches documentation across every library that has been indexed,
    sharing a single embedding model and Qdrant client instance rather
    than loading one retriever (and one copy of the embedding model)
    per library.

    Libraries listed in packages.rag.config.LIBRARIES that haven't
    been embedded yet (no matching Qdrant collection) are silently
    skipped, so the corpus can grow one library at a time - e.g. only
    GeoPandas indexed today, Shapely/Rasterio/PyProj/GDAL added later -
    without breaking retrieval for what's already there.
    """

    def __init__(self, model_name: str = MODEL_NAME):
        self.client = QdrantClient(path=str(QDRANT_DIR))
        self.model = SentenceTransformer(model_name, device="cpu")

        self.available_libraries = [
            name
            for name in LIBRARIES
            if self.client.collection_exists(f"{name}_docs")
        ]

        if not self.available_libraries:
            raise RuntimeError(
                "No documentation collections found in Qdrant. "
                "Run download_docs.py, clean_docs.py, chunk_docs.py "
                "and embed_docs.py for at least one library first."
            )

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search every indexed library and return the globally top-`limit`
        results by score, regardless of which library they came from.
        """

        if not query.strip():
            raise ValueError("Query cannot be empty.")

        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        query_embedding = self.model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

        all_results = []

        for library_name in self.available_libraries:
            points = self.client.query_points(
                collection_name=f"{library_name}_docs",
                query=query_embedding,
                limit=limit,
            ).points

            for point in points:
                payload = point.payload

                all_results.append(
                    {
                        "score": point.score,
                        "library": payload["library"],
                        "version": payload["version"],
                        "chunk_id": payload["chunk_id"],
                        "title": payload["title"],
                        "source": payload["source"],
                        "text": payload["text"],
                    }
                )

        all_results.sort(
            key=lambda result: result["score"],
            reverse=True,
        )

        return all_results[:limit]

    def close(self) -> None:
        """Close the Qdrant client."""
        self.client.close()


def main():
    """Simple command-line test for the retriever."""

    retriever = GeoRetriever("geopandas")

    query = (
        "How do I create a 500 meter buffer "
        "around a river?"
    )

    print()
    print("=" * 80)
    print(f"QUERY: {query}")
    print("=" * 80)

    results = retriever.search(
        query,
        limit=3,
    )

    for rank, result in enumerate(
        results,
        start=1,
    ):
        print()
        print(f"#{rank}")
        print(
            f"Score: {result['score']:.4f}"
        )
        print(
            f"Title: {result['title']}"
        )
        print(
            f"Chunk: {result['chunk_id']}"
        )
        print(
            f"Source: {result['source']}"
        )
        print()
        print(result["text"][:1000])


if __name__ == "__main__":
    main()
