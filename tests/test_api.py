import json
from unittest.mock import Mock

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
