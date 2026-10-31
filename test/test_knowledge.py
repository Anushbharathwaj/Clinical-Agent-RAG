from unittest.mock import Mock

from pinecone import ScoredVector

from app import knowledge


def test_search_returns_serializable_match_dicts(monkeypatch):
    match = ScoredVector(
        id="vector-1",
        score=0.9,
        metadata={"text": "A skin patch", "page": 3},
    )
    index = Mock()
    index.query.return_value = {"matches": [match]}
    monkeypatch.setattr(knowledge, "ensure_index", lambda: index)
    monkeypatch.setattr(knowledge, "embed", lambda query: [[0.1, 0.2]])

    results = knowledge.search("skin patch")

    assert results == [
        {
            "id": "vector-1",
            "score": 0.9,
            "metadata": {"text": "A skin patch", "page": 3},
        }
    ]
    assert results[0] is not match
