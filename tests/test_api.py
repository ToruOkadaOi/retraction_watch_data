import json
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def client(monkeypatch, snapshot):
    monkeypatch.setattr(api, "neo4j_driver", None)
    monkeypatch.setattr(api, "json_data", json.loads(snapshot.read_text()))
    with TestClient(api.app) as client:
        yield client


def test_custom_cypher_removed(client, monkeypatch):
    driver = Mock()
    monkeypatch.setattr(api, "neo4j_driver", driver)
    assert (
        client.post(
            "/api/cypher", json={"query": "MATCH (n) DETACH DELETE n"}
        ).status_code
        == 404
    )
    driver.session.assert_not_called()
    assert "/api/cypher" not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(
    "label",
    [
        "Article) SET n.pwned = true WITH n MATCH (n:Article",
        "Unknown",
        "Article`",
        "article",
    ],
)
def test_untrusted_labels_never_reach_database(client, monkeypatch, label):
    driver = Mock()
    monkeypatch.setattr(api, "neo4j_driver", driver)
    assert client.get(f"/api/nodes/{label}").status_code == 422
    assert (
        client.get("/api/search", params={"q": "x", "node_type": label}).status_code
        == 422
    )
    driver.session.assert_not_called()


def test_json_rankings_only_count_retraction_notices(client):
    assert client.get("/api/journals/top").json()["journals"] == [
        {"journal": "Journal", "retraction_count": 1}
    ]
    assert client.get("/api/reasons/top").json()["reasons"] == [
        {"reason": "Reason", "count": 1}
    ]
    stats = client.get("/api/statistics").json()
    assert stats["nodes"]["Article"] == 4
    assert stats["edges"]["Has_Institution"] == 8
    assert "Affiliated_With" not in stats["edges"]


def test_json_articles_and_search(client):
    article = client.get("/api/articles/1").json()
    assert {n["name"] for n in article["institutions"]} == {
        "University A",
        "University B",
    }
    assert client.get("/api/articles/missing").status_code == 404
    assert (
        client.get("/api/search", params={"q": "KRÜGER", "node_type": "Author"}).json()[
            "count"
        ]
        == 1
    )
    page = client.get("/api/nodes/Article", params={"skip": 1, "limit": 2}).json()
    assert [n["id"] for n in page["nodes"]] == ["Article:2", "Article:3"]
    assert page["nodes"][0]["type"] == "Article"


def test_database_failure_uses_fallback(client, monkeypatch):
    driver = Mock()
    driver.session.side_effect = RuntimeError("database unavailable")
    monkeypatch.setattr(api, "neo4j_driver", driver)
    assert client.get("/api/nodes/Article").json()["count"] == 4
    assert (
        client.get("/api/journals/top").json()["journals"][0]["retraction_count"] == 1
    )
    monkeypatch.setattr(api, "json_data", None)
    assert client.get("/api/nodes/Article").status_code == 503


@pytest.mark.parametrize(
    "path",
    [
        "/api/nodes/Article?limit=0",
        "/api/search?q=x&limit=501",
        "/api/nodes/Article?skip=-1",
        "/api/journals/top?limit=101",
    ],
)
def test_request_limits(client, path):
    assert client.get(path).status_code == 422


def test_lazy_driver_recovers_after_initial_and_later_outages(monkeypatch):
    from neo4j.exceptions import ServiceUnavailable

    candidate = MagicMock()
    candidate.verify_connectivity.side_effect = ServiceUnavailable("Aura paused")
    factory = Mock(return_value=candidate)
    monkeypatch.setenv("NEO4J_PASSWORD", "regression-only-password")
    monkeypatch.setattr(api.GraphDatabase, "driver", factory)
    driver = api.create_neo4j_driver()
    assert driver is candidate
    candidate.verify_connectivity.assert_not_called()
    candidate.close.assert_not_called()
    monkeypatch.setattr(api, "neo4j_driver", driver)
    monkeypatch.setattr(api, "neo4j_available", False)
    monkeypatch.setattr(api, "json_data", None)
    session = candidate.session.return_value.__enter__.return_value
    session.run.side_effect = lambda cypher, *args, **kwargs: Mock(
        data=lambda: [] if "RWImportState" in cypher else [{"count": 4}]
    )
    session_context = candidate.session.return_value
    with TestClient(api.app) as client:
        assert client.get("/").json()["neo4j_configured"] is True
        assert client.get("/").json()["neo4j_connected"] is False
        for _ in range(2):
            candidate.session.side_effect = ServiceUnavailable("Aura paused")
            failed = client.get("/ready")
            assert failed.status_code == 503
            assert failed.headers["retry-after"] == "15"
            assert client.get("/").json()["neo4j_connected"] is False
            assert client.get("/api/nodes/Article").status_code == 503
            candidate.close.assert_not_called()
            candidate.session.side_effect = None
            candidate.session.return_value = session_context
            recovered = client.get("/ready")
            assert recovered.status_code == 200, recovered.text
            assert recovered.json() == {"ready": True, "source": "neo4j"}
            assert client.get("/").json()["neo4j_connected"] is True
        assert api.neo4j_driver is driver
        factory.assert_called_once()
    candidate.close.assert_called_once()


def test_ready_uses_json_during_transport_failure_but_not_import_maintenance(
    client, monkeypatch
):
    from neo4j.exceptions import ServiceUnavailable

    driver = MagicMock()
    monkeypatch.setattr(api, "neo4j_driver", driver)
    monkeypatch.setattr(api, "neo4j_available", False)
    driver.session.side_effect = ServiceUnavailable("unreachable")
    result = client.get("/ready")
    assert result.status_code == 200
    assert result.json()["source"] == "json"
    assert client.get("/").json()["neo4j_connected"] is False
    driver.session.side_effect = None
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value.data.return_value = [
        {"status": "loading", "generation": "incomplete"}
    ]
    maintenance = client.get("/ready")
    assert maintenance.status_code == 503
    assert "refresh incomplete" in maintenance.json()["detail"]
    assert client.get("/").json()["neo4j_connected"] is True
    driver.close.assert_not_called()
