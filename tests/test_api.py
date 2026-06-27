from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.load_pn_tree import PNNode


pytestmark = pytest.mark.slow

_MOD = None


def _reimport():
    global _MOD
    import app as m
    _MOD = m
    return m


class TestHealth:
    def test_health_returns_ok(self):
        m = _reimport()
        client = TestClient(m.app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestRecommendAuth:
    def test_no_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "real-key")
        m = _reimport()
        m._index = MagicMock()
        m._client = MagicMock()
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "laptop"})  # no header
        assert resp.status_code == 401

    def test_unconfigured_key_returns_503(self, monkeypatch):
        monkeypatch.delenv("APP_API_KEY", raising=False)
        m = _reimport()
        m._index = MagicMock()
        m._client = MagicMock()
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "laptop"}, headers={"X-API-Key": "anything"})
        assert resp.status_code == 503

    def test_wrong_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "real-key")
        m = _reimport()
        m._index = MagicMock()
        m._client = MagicMock()
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "laptop"}, headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_valid_key_returns_not_401(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "real-key")
        m = _reimport()
        m._index = MagicMock()
        m._client = MagicMock()
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "laptop"}, headers={"X-API-Key": "real-key"})
        assert resp.status_code != 401


class TestRecommendInput:
    def test_empty_query_returns_topk_list(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        mock_index = MagicMock()
        mock_index.recall.return_value = []
        m._index = mock_index
        m._client = MagicMock()
        m._nodes = []
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": ""}, headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "topk" in data
        assert isinstance(data["topk"], list)


class TestRecommendIntegration:
    def test_valid_query_returns_top3_with_expected_structure(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_nodes = [
            PNNode(name="AI Managed Service", level=3, path=["L1", "AI", "AI Managed Service"], pn_count=5, sampled_pn_descs=["AI deployment", "ML ops"]),
            PNNode(name="Professional Service", level=3, path=["L1", "Services", "Professional Service"], pn_count=10, sampled_pn_descs=["Consulting"]),
        ]

        mock_index.recall.return_value = [1, 0]
        mock_client.rerank.return_value = [
            {"product_id": "0", "score": 0.92},
            {"product_id": "1", "score": 0.85},
        ]
        m._index = mock_index
        m._client = mock_client
        m._nodes = mock_nodes
        client = TestClient(m.app)

        resp = client.post("/recommend", json={"query": "AI service for deployment"}, headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        data = resp.json()
        assert "topk" in data
        assert len(data["topk"]) == 2

        slot = data["topk"][0]
        assert "name" in slot
        assert "level" in slot
        assert "path" in slot
        assert "path_str" in slot
        assert "score" in slot
        assert "level_label" in slot
        assert slot["name"] == "AI Managed Service"
        assert slot["score"] == 0.92
        assert slot["level_label"] == "High"

    def test_no_recall_results_returns_empty(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        mock_index = MagicMock()
        mock_index.recall.return_value = []
        m._index = mock_index
        m._client = MagicMock()
        m._nodes = []
        client = TestClient(m.app)

        resp = client.post("/recommend", json={"query": "some query"}, headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert resp.json() == {"topk": []}

    def test_not_initialized_returns_503(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        m._index = None
        m._client = None
        m._nodes = None
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "test"}, headers={"X-API-Key": "test-key"})
        assert resp.status_code == 503
