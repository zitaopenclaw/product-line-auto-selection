from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.load_pn_tree import PNNode


pytestmark = pytest.mark.slow


def _pn(name: str, level: int = 3, path: list[str] | None = None) -> PNNode:
    return PNNode(
        name=name,
        level=level,
        path=path or ["Global", "Services", name],
        pn_count=5,
        sampled_pn_descs=["desc1", "desc2"],
    )

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
        data = resp.json()
        assert data["topk"] == []
        assert data["service_recommendations"] == []
        assert "hw_recommendations" not in data  # no BG specified → no HW pipeline

    def test_not_initialized_returns_503(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        m._index = None
        m._client = None
        m._nodes = None
        client = TestClient(m.app)
        resp = client.post("/recommend", json={"query": "test"}, headers={"X-API-Key": "test-key"})
        assert resp.status_code == 503


class TestRecommendDerAuth:
    def test_no_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "real-key")
        m = _reimport()
        client = TestClient(m.app)
        resp = client.post("/recommend_der", json={"query": "laptop", "business_group": "IDG"})
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "real-key")
        m = _reimport()
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "laptop", "business_group": "IDG"},
            headers={"X-API-Key": "wrong"},
        )
        assert resp.status_code == 401

    def test_invalid_business_group_returns_400(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        m._der_client = MagicMock()
        m._nodes = [_pn("Deployment Services")]
        m._index = MagicMock()
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "laptop", "business_group": "INVALID"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 400

    def test_uninitialized_der_client_returns_503(self, monkeypatch):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        m = _reimport()
        m._der_client = None
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "laptop", "business_group": "IDG"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 503


class TestRecommendDerIntegration:
    def _setup(self, monkeypatch, m):
        monkeypatch.setenv("APP_API_KEY", "test-key")
        nodes = [
            _pn("Deployment Services", level=3, path=["Global", "Hardware", "Deployment Services"]),
            _pn("DaaS Premium", level=3, path=["Global", "Services", "DaaS Premium"]),
        ]
        mock_index = MagicMock()
        mock_index.recall.return_value = [0, 1]
        mock_client = MagicMock()
        mock_client.rerank.return_value = [
            {"product_id": "0", "score": 0.92},
            {"product_id": "1", "score": 0.75},
        ]
        m._der_client = mock_client
        m._index = mock_index
        m._nodes = nodes
        return nodes

    def test_valid_request_returns_topk_structure(self, monkeypatch):
        m = _reimport()
        self._setup(monkeypatch, m)
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "deploy laptops for enterprise", "business_group": "IDG"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "topk" in data
        assert isinstance(data["topk"], list)
        if data["topk"]:
            slot = data["topk"][0]
            assert "name" in slot
            assert "path_str" in slot
            assert "node_key" in slot
            assert "level" in slot
            assert "score" in slot
            assert "level_label" in slot

    def test_no_recall_results_returns_empty(self, monkeypatch):
        m = _reimport()
        monkeypatch.setenv("APP_API_KEY", "test-key")
        mock_index = MagicMock()
        mock_index.recall.return_value = []
        m._der_client = MagicMock()
        m._index = mock_index
        m._nodes = [_pn("Some Node")]
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "xyz", "business_group": "IDG"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["topk"] == []
        assert data["service_recommendations"] == []
        assert "hw_recommendations" in data  # IDG → HW pipeline present (even if empty)

    def test_top1_score_and_level_label_correct(self, monkeypatch):
        m = _reimport()
        self._setup(monkeypatch, m)
        client = TestClient(m.app)
        resp = client.post(
            "/recommend_der",
            json={"query": "hardware deployment", "business_group": "IDG"},
            headers={"X-API-Key": "test-key"},
        )
        assert resp.status_code == 200
        top = resp.json()["topk"][0]
        assert top["score"] == 0.92
        assert top["level_label"] == "High"
        assert top["name"] == "Deployment Services"


class TestRecommendDerContract:
    """Contract: RecommendDerRequest must expose all DERRow fields consumed by field_rules."""

    def test_existing_expansion_field_present_and_defaults_none(self):
        from app import RecommendDerRequest
        req = RecommendDerRequest(query="test", business_group="IDG")
        assert hasattr(req, "existing_expansion")
        assert req.existing_expansion is None

    def test_existing_expansion_true_accepted(self):
        from app import RecommendDerRequest
        req = RecommendDerRequest(query="test", business_group="IDG", existing_expansion=True)
        assert req.existing_expansion is True

    def test_existing_expansion_wires_to_der_row(self):
        from app import RecommendDerRequest
        from src.load_data import DERRow
        req = RecommendDerRequest(query="managed services renewal", business_group="IDG", existing_expansion=True)
        row = DERRow(
            opportunity_id="test",
            business_group=req.business_group,
            description=req.query,
            service_model=req.service_model or None,
            is_ars=(req.ars_flag.strip().lower() == "yes") if req.ars_flag else None,
            is_emerging_tech=(req.ai_flag.strip().lower() == "yes") if req.ai_flag else None,
            scope=req.scope or None,
            is_existing_expansion=req.existing_expansion,
        )
        assert row.is_existing_expansion is True
