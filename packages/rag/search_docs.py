from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

import sys

from packages.rag.config import get_library


QDRANT_DIR = "rag/qdrant"
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python packages/rag/search_docs.py <library>"
        )
        sys.exit(1)

    library_name = sys.argv[1]
    library = get_library(library_name)

    collection_name = f"{library_name}_docs"

    print(f"Library: {library.name}")
    print(f"Version: {library.version}")
    print(f"Collection: {collection_name}")

    client = QdrantClient(
        path=QDRANT_DIR,
    )

    if not client.collection_exists(collection_name):
        raise RuntimeError(
            f"Collection '{collection_name}' does not exist. "
            f"Run embed_docs.py first."
        )

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )

    queries = [
        "How do I read a GeoPackage file?",
        "How do I transform geometries from one CRS to another?",
        "How do I create a buffer around geometries?",
        "How do I perform a spatial join between two GeoDataFrames?",
    ]

    for query in queries:
        print()
        print("=" * 80)
        print(f"QUERY: {query}")
        print("=" * 80)

        query_embedding = model.encode(
            query,
            normalize_embeddings=True,
        )

        results = client.query_points(
            collection_name=collection_name,
            query=query_embedding.tolist(),
            limit=3,
        ).points

        for rank, result in enumerate(results, start=1):
            payload = result.payload

            print()
            print(f"#{rank}")
            print(f"Score: {result.score:.4f}")
            print(f"Title: {payload['title']}")
            print(f"Chunk: {payload['chunk_id']}")
            print(f"Source: {payload['source']}")
            print()
            print(payload["text"][:500])
            print()


if __name__ == "__main__":
    main()