import pytest

import packages.rag.retriever as retriever_module
from packages.rag.retriever import MultiLibraryRetriever


class FakePoint:
    def __init__(self, score, payload):
        self.score = score
        self.payload = payload


class FakeQueryResult:
    def __init__(self, points):
        self.points = points


class FakeQdrantClient:
    """Stands in for QdrantClient - one collection per fake library."""

    def __init__(self, *args, **kwargs):
        self.collections = {
            "geopandas_docs": [
                FakePoint(0.91, {
                    "library": "geopandas", "version": "1.1.4",
                    "chunk_id": "gpd-1", "title": "sjoin", "source": "s1", "text": "t1",
                }),
                FakePoint(0.40, {
                    "library": "geopandas", "version": "1.1.4",
                    "chunk_id": "gpd-2", "title": "buffer", "source": "s2", "text": "t2",
                }),
            ],
            "shapely_docs": [
                FakePoint(0.95, {
                    "library": "shapely", "version": "2.1.2",
                    "chunk_id": "shp-1", "title": "shapely.buffer", "source": "s3", "text": "t3",
                }),
            ],
        }

    def collection_exists(self, name):
        return name in self.collections

    def query_points(self, collection_name, query, limit):
        points = self.collections.get(collection_name, [])
        return FakeQueryResult(points[:limit])

    def close(self):
        pass


class FakeEmbedding:
    def tolist(self):
        return [0.0, 0.0, 0.0]


class FakeSentenceTransformer:
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, text, normalize_embeddings=True):
        return FakeEmbedding()


@pytest.fixture
def patched_retriever_deps(monkeypatch):
    monkeypatch.setattr(retriever_module, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(retriever_module, "SentenceTransformer", FakeSentenceTransformer)


def test_only_libraries_with_existing_collections_are_searched(patched_retriever_deps):
    retriever = MultiLibraryRetriever()

    # geopandas and shapely collections exist in the fake client;
    # rasterio/pyproj/gdal don't yet.
    assert set(retriever.available_libraries) == {"geopandas", "shapely"}


def test_results_are_merged_and_sorted_by_score_across_libraries(patched_retriever_deps):
    retriever = MultiLibraryRetriever()

    results = retriever.search("buffer a river", limit=5)

    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    libraries_seen = {r["library"] for r in results}
    assert libraries_seen == {"geopandas", "shapely"}

    # The single highest-scoring result overall (0.95) is from shapely,
    # not geopandas - proves it's a true cross-library merge, not just
    # concatenation in library order.
    assert results[0]["library"] == "shapely"
    assert results[0]["chunk_id"] == "shp-1"


def test_limit_is_applied_to_the_global_merged_results(patched_retriever_deps):
    retriever = MultiLibraryRetriever()

    results = retriever.search("buffer", limit=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "shp-1"


def test_empty_query_is_rejected(patched_retriever_deps):
    retriever = MultiLibraryRetriever()

    with pytest.raises(ValueError):
        retriever.search("   ")


def test_raises_clearly_when_nothing_is_indexed(monkeypatch):
    class EmptyQdrantClient(FakeQdrantClient):
        def __init__(self, *a, **k):
            self.collections = {}

    monkeypatch.setattr(retriever_module, "QdrantClient", EmptyQdrantClient)
    monkeypatch.setattr(retriever_module, "SentenceTransformer", FakeSentenceTransformer)

    with pytest.raises(RuntimeError, match="No documentation collections"):
        MultiLibraryRetriever()
