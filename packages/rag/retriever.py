import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

from packages.rag.config import get_library, LIBRARIES

load_dotenv()

QDRANT_DIR = Path("rag/qdrant")
LOCAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"
CLOUD_MODEL_NAME = os.getenv(
    "QDRANT_CLOUD_MODEL", "sentence-transformers/all-minilm-l6-v2"
)

# Kept at module level so unit tests can monkeypatch SentenceTransformer in local mode
try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # Tier 2 production image omits sentence-transformers/torch
    SentenceTransformer = None


def _qdrant_cloud_config() -> tuple[str, str | None, bool]:
    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    cloud_inference = os.getenv("QDRANT_CLOUD_INFERENCE", "true").lower() == "true"
    return url, api_key, cloud_inference


def _build_qdrant_client() -> tuple[QdrantClient, bool]:
    """Return (QdrantClient, is_cloud_inference)."""
    url, api_key, cloud_inference = _qdrant_cloud_config()
    if url:
        client = QdrantClient(
            url=url,
            api_key=api_key,
            cloud_inference=cloud_inference,
            timeout=30,
        )
        return client, cloud_inference

    return QdrantClient(path=str(QDRANT_DIR)), False


class GeoRetriever:
    """Semantic retriever for geospatial documentation."""

    def __init__(
        self,
        library_name: str,
        model_name: str | None = None,
    ):
        self.library = get_library(library_name)
        self.collection_name = f"{library_name}_docs"

        self.client, self.cloud_inference = _build_qdrant_client()
        self.model_name = model_name or (
            CLOUD_MODEL_NAME if self.cloud_inference else LOCAL_MODEL_NAME
        )

        if not self.client.collection_exists(self.collection_name):
            raise RuntimeError(
                f"Qdrant collection '{self.collection_name}' does not exist. "
                f"Run embed_docs.py first."
            )

        self.model = None
        if not self.cloud_inference:
            if SentenceTransformer is None:
                raise RuntimeError(
                    "sentence-transformers is not installed and QDRANT_URL is not set."
                )
            self.model = SentenceTransformer(self.model_name, device="cpu")

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Search documentation using semantic similarity."""
        if not query.strip():
            raise ValueError("Query cannot be empty.")

        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        if self.cloud_inference:
            qdrant_query = models.Document(text=query, model=self.model_name)
        else:
            qdrant_query = self.model.encode(
                query,
                normalize_embeddings=True,
            ).tolist()

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=qdrant_query,
            limit=limit,
        ).points

        return [
            {
                "score": result.score,
                "library": result.payload["library"],
                "version": result.payload["version"],
                "chunk_id": result.payload["chunk_id"],
                "title": result.payload["title"],
                "source": result.payload["source"],
                "text": result.payload["text"],
            }
            for result in results
        ]

    def close(self) -> None:
        """Close the Qdrant client."""
        self.client.close()


class MultiLibraryRetriever:
    """
    Searches documentation across every indexed library in Qdrant.
    Uses Qdrant Cloud Inference over HTTPS when QDRANT_URL is configured
    (zero local PyTorch/SentenceTransformer RAM overhead on EC2).
    """

    def __init__(self, model_name: str | None = None):
        self.client, self.cloud_inference = _build_qdrant_client()
        self.model_name = model_name or (
            CLOUD_MODEL_NAME if self.cloud_inference else LOCAL_MODEL_NAME
        )

        self.model = None
        if not self.cloud_inference:
            if SentenceTransformer is None:
                raise RuntimeError(
                    "sentence-transformers is not installed and QDRANT_URL is not set."
                )
            self.model = SentenceTransformer(self.model_name, device="cpu")

        self.available_libraries = [
            name
            for name in LIBRARIES
            if self.client.collection_exists(f"{name}_docs")
        ]

        if not self.available_libraries:
            raise RuntimeError(
                "No documentation collections found in Qdrant. "
                "Run embed_docs.py for at least one library first."
            )

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Search every indexed library and return the globally top-`limit`
        results by score.
        """
        if not query.strip():
            raise ValueError("Query cannot be empty.")

        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        if self.cloud_inference:
            qdrant_query = models.Document(text=query, model=self.model_name)
        else:
            qdrant_query = self.model.encode(
                query,
                normalize_embeddings=True,
            ).tolist()

        all_results = []

        for library_name in self.available_libraries:
            points = self.client.query_points(
                collection_name=f"{library_name}_docs",
                query=qdrant_query,
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