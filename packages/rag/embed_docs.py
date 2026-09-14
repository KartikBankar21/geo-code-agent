from pathlib import Path
import json
import sys

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from packages.rag.config import get_library, chunks_dir


QDRANT_DIR = Path("rag/qdrant")
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def load_chunks(chunks_directory: Path):
    """Load all chunk JSON files recursively."""

    chunks = []

    files = sorted(chunks_directory.rglob("*.json"))

    print(f"Chunk files: {len(files)}")

    for file in files:
        with file.open("r", encoding="utf-8") as f:
            file_chunks = json.load(f)

        chunks.extend(file_chunks)

        print(
            f"Loaded: {file} -> {len(file_chunks)} chunks"
        )

    return chunks


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python packages/rag/embed_docs.py <library>"
        )
        sys.exit(1)

    library_name = sys.argv[1]
    library = get_library(library_name)

    chunks_directory = chunks_dir(library_name)
    collection_name = f"{library_name}_docs"

    print(f"Library: {library.name}")
    print(f"Version: {library.version}")
    print(f"Chunks: {chunks_directory}")
    print(f"Collection: {collection_name}")

    print()
    print("Loading chunks...")

    chunks = load_chunks(chunks_directory)

    print(f"Total chunks: {len(chunks)}")

    if not chunks:
        raise RuntimeError(
            f"No chunks found in {chunks_directory}"
        )

    print()
    print("Loading embedding model...")

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )

    print("Embedding model loaded.")

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    print()
    print("Generating embeddings...")

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    print(f"Embedding shape: {embeddings.shape}")

    QDRANT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("Opening Qdrant...")

    client = QdrantClient(
        path=str(QDRANT_DIR),
    )

    if client.collection_exists(collection_name):
        print("Existing collection found. Recreating it.")

        client.delete_collection(
            collection_name
        )

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=embeddings.shape[1],
            distance=Distance.COSINE,
        ),
    )

    points = []

    for index, (chunk, embedding) in enumerate(
        zip(chunks, embeddings)
    ):
        points.append(
            PointStruct(
                id=index,
                vector=embedding.tolist(),
                payload={
                    "library": library.name,
                    "version": library.version,
                    "chunk_id": chunk["id"],
                    "source": chunk["source"],
                    "title": chunk["title"],
                    "text": chunk["text"],
                },
            )
        )

    print()
    print("Uploading vectors...")

    client.upsert(
        collection_name=collection_name,
        points=points,
    )

    info = client.get_collection(
        collection_name
    )

    print()
    print("================================")
    print("Indexing complete")
    print("================================")
    print(f"Library: {library.name}")
    print(f"Collection: {collection_name}")
    print(f"Vectors: {info.points_count}")
    print(f"Vector dimension: {embeddings.shape[1]}")


if __name__ == "__main__":
    main()