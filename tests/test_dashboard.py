import json

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture(params=["snapshot", "aura_snapshot"])
def dashboard_client(request, monkeypatch):
    data = json.loads(request.getfixturevalue(request.param).read_text())
    monkeypatch.setattr(api, "neo4j_driver", None)
    monkeypatch.setattr(api, "json_data", data)
    with TestClient(api.app) as client:
        yield client, data


def test_overview_counts_and_provenance(dashboard_client):
    client, data = dashboard_client
    result = client.get("/api/dashboard/overview")
    assert result.status_code == 200
    result = result.json()
    assert result["total_nodes"] == len(data["nodes"])
    assert result["total_relationships"] == len(data["edges"])
    assert result["nodes"]["Article"] == sum(result["notice_counts"].values())
    assert (
        result["snapshot"]["source_csv_sha256"] == data["metadata"]["source_csv_sha256"]
    )
    reasons = {r["name"]: r["count"] for r in result["top_reasons"]}
    if data["metadata"].get("profile") == "aura":
        assert reasons == {"Reason A": 2, "Reason B": 1}
    else:
        assert reasons == {"Reason": 1}
    # A cached overview must still pass backend readiness checks on the next request.
    assert client.get("/api/dashboard/overview").json() == result


def test_record_filters_and_pagination(dashboard_client):
    client, data = dashboard_client
    count = data["metadata"]["statistics"]["articles"]
    result = client.get("/api/dashboard/records", params={"limit": 1}).json()
    assert result["records"][0]["record_id"] == str(count)
    assert result["has_more"] is True
    following = client.get(
        "/api/dashboard/records", params={"limit": 1, "skip": 1}
    ).json()
    assert following["records"][0]["id"] != result["records"][0]["id"]
    assert "source_record" not in result["records"][0]
    assert "author_names" not in result["records"][0]
    result = client.get(
        "/api/dashboard/records", params={"notice": "Correction"}
    ).json()
    assert len(result["records"]) == 1
    assert result["records"][0]["retraction_nature"] == "Correction"
    assert (
        client.get("/api/dashboard/records", params={"journal": "missing"}).json()[
            "records"
        ]
        == []
    )
    reason = "Reason A" if data["metadata"].get("profile") == "aura" else "Reason"
    matches = client.get(
        "/api/dashboard/records",
        params={"reason": reason, "journal": "Journal", "notice": "Retraction"},
    ).json()
    assert len(matches["records"]) == (
        2 if data["metadata"].get("profile") == "aura" else 1
    )
    name = "Singleton" if data["metadata"].get("profile") == "aura" else "Nele Krüger"
    assert client.get("/api/dashboard/records", params={"q": name}).json()["records"]
    assert (
        client.get(
            "/api/dashboard/records", params={"q": "') DETACH DELETE n //"}
        ).json()["records"]
        == []
    )


def test_bounded_directional_neighborhood(dashboard_client):
    client, data = dashboard_client
    page = client.get(
        "/api/dashboard/neighborhood", params={"node_id": "Article:1", "limit": 1}
    ).json()
    assert len(page["nodes"]) == 2
    assert len(page["edges"]) == 1
    assert page["has_more"] and page["next_skip"] == 1
    edge = page["edges"][0]
    assert any(
        e["source"] == edge["source"]
        and e["target"] == edge["target"]
        and e["properties"]["type"] == edge["type"]
        for e in data["edges"]
    )
    next_page = client.get(
        "/api/dashboard/neighborhood",
        params={"node_id": "Article:1", "limit": 1, "skip": 1},
    ).json()
    assert next_page["edges"] != page["edges"]
    exhausted = client.get(
        "/api/dashboard/neighborhood", params={"node_id": "Article:1", "skip": 999}
    ).json()
    assert exhausted["nodes"] == [exhausted["center"]]
    assert exhausted["edges"] == [] and not exhausted["has_more"]
    assert all("source_record" not in n for n in page["nodes"])
    assert (
        client.get(
            "/api/dashboard/neighborhood", params={"node_id": "Article:missing"}
        ).status_code
        == 404
    )


def test_neighborhood_filters_and_singleton_semantics(monkeypatch, aura_snapshot):
    monkeypatch.setattr(api, "neo4j_driver", None)
    monkeypatch.setattr(api, "json_data", json.loads(aura_snapshot.read_text()))
    with TestClient(api.app) as client:
        path = "/api/dashboard/neighborhood"
        params = {
            "node_id": "Author:Shared Name",
            "notice": "Retraction",
            "reason": "Reason B",
            "journal": "Journal",
        }
        result = client.get(path, params=params).json()
        assert result["total_neighbors"] == 1
        assert result["nodes"][1]["id"] == "Article:1"
        assert (
            client.get(path, params={"node_id": "Author:Singleton"}).status_code == 404
        )
        assert (
            client.get("/api/dashboard/records", params={"q": "Singleton"}).json()[
                "records"
            ][0]["id"]
            == "Article:1"
        )
        assert (
            client.get(
                "/api/dashboard/entities", params={"q": "Singleton", "kind": "Author"}
            ).json()["nodes"]
            == []
        )
        assert (
            client.get(
                "/api/dashboard/entities", params={"q": "shared", "kind": "Author"}
            ).json()["nodes"][0]["identity_basis"]
            == "exact_name_string"
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard/neighborhood?node_id=Article:1&limit=101",
        "/api/dashboard/neighborhood?node_id=Article:1&skip=-1",
        "/api/dashboard/neighborhood?node_id=Bad:1",
        "/api/dashboard/neighborhood?node_id=Article:1&notice=Bad",
        "/api/dashboard/records?limit=51",
        "/api/dashboard/records?notice=Bad",
        "/api/dashboard/entities?q=x&kind=Article)%20DELETE%20n",
    ],
)
def test_request_bounds(dashboard_client, path):
    client, _ = dashboard_client
    assert client.get(path).status_code == 422


def test_cors_and_static_dashboard(dashboard_client):
    client, _ = dashboard_client
    result = client.options(
        "/api/dashboard/overview",
        headers={
            "Origin": "https://toruokadaoi.github.io",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert result.status_code == 200
    assert (
        result.headers["access-control-allow-origin"] == "https://toruokadaoi.github.io"
    )
    denied = client.options(
        "/api/dashboard/overview",
        headers={
            "Origin": "https://unapproved.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in denied.headers
    assert client.get("/dashboard/").status_code == 200
    assert "Follow the connections." in client.get("/dashboard/").text
    assert client.get("/dashboard/app.mjs").status_code == 200
    assert client.get("/dashboard/vendor/cytoscape.min.js").status_code == 200
