from pathlib import Path
import json
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

from packages.rag.config import get_library, chunks_dir

load_dotenv()

QDRANT_DIR = Path("rag/qdrant")
LOCAL_MODEL_NAME = "BAAI/bge-small-en-v1.5"
CLOUD_MODEL_NAME = os.getenv(
    "QDRANT_CLOUD_MODEL", "sentence-transformers/all-minilm-l6-v2"
)
VECTOR_DIM = 384  # Both all-minilm-l6-v2 and bge-small-en-v1.5 output 384 dimensions
UPSERT_BATCH_SIZE = 50


def load_chunks(chunks_directory: Path):
    chunks = []
    files = sorted(chunks_directory.rglob("*.json"))
    print(f"Chunk files: {len(files)}")

    for file in files:
        with file.open("r", encoding="utf-8") as f:
            file_chunks = json.load(f)
        chunks.extend(file_chunks)

    return chunks


def main():
    if len(sys.argv) != 2:
        print("Usage: python packages/rag/embed_docs.py <library>")
        sys.exit(1)

    library_name = sys.argv[1]
    library = get_library(library_name)

    chunks_directory = chunks_dir(library_name)
    collection_name = f"{library_name}_docs"

    print(f"Library: {library.name} v{library.version}")
    chunks = load_chunks(chunks_directory)
    print(f"Total chunks: {len(chunks)}")

    if not chunks:
        raise RuntimeError(f"No chunks found in {chunks_directory}")

    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    cloud_inference = os.getenv("QDRANT_CLOUD_INFERENCE", "true").lower() == "true"

    if qdrant_url:
        print(
            f"Connecting to Qdrant Cloud ({qdrant_url}) | "
            f"cloud_inference={cloud_inference} | model={CLOUD_MODEL_NAME}"
        )
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            cloud_inference=cloud_inference,
            timeout=60,
        )
    else:
        QDRANT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Opening local Qdrant at {QDRANT_DIR}")
        client = QdrantClient(path=str(QDRANT_DIR))

    if client.collection_exists(collection_name):
        print(f"Recreating existing collection '{collection_name}'...")
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )

    if qdrant_url and cloud_inference:
        points = [
            models.PointStruct(
                id=index,
                vector=models.Document(text=chunk["text"], model=CLOUD_MODEL_NAME),
                payload={
                    "library": library.name,
                    "version": library.version,
                    "chunk_id": chunk["id"],
                    "source": chunk["source"],
                    "title": chunk["title"],
                    "text": chunk["text"],
                },
            )
            for index, chunk in enumerate(chunks)
        ]
    else:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(LOCAL_MODEL_NAME, device="cpu")
        embeddings = model.encode(
            [c["text"] for c in chunks],
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        points = [
            models.PointStruct(
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
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]

    print(f"Uploading {len(points)} chunks in batches of {UPSERT_BATCH_SIZE}...")
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[start : start + UPSERT_BATCH_SIZE]
        client.upsert(collection_name=collection_name, points=batch)

    info = client.get_collection(collection_name)
    print(f"Indexing complete: {collection_name} ({info.points_count} vectors)")
    client.close()


if __name__ == "__main__":
    main()
