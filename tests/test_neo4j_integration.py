"""Run only against an explicitly supplied disposable database."""

import json
import os

import pytest
from fastapi.testclient import TestClient

import api
from neo4j_integration import Neo4jLoader

pytestmark = pytest.mark.integration


@pytest.fixture
def database():
    uri = os.getenv("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("Set TEST_NEO4J_URI to a disposable Neo4j instance")
    password = os.environ["TEST_NEO4J_PASSWORD"]
    loader = Neo4jLoader(uri=uri, user="neo4j", password=password)
    with loader.driver.session() as session:
        session.run("MATCH (n:RWGraph) DETACH DELETE n").consume()
        session.run("MATCH (s:RWImportState) DETACH DELETE s").consume()
        session.run('CREATE (:RegressionSentinel {id: "keep-me"})').consume()
    yield loader
    with loader.driver.session() as session:
        session.run("MATCH (n:RWGraph) DETACH DELETE n").consume()
        session.run("MATCH (s:RWImportState) DETACH DELETE s").consume()
        session.run("MATCH (n:RegressionSentinel) DELETE n").consume()
    loader.close()


def test_atomic_scoped_replacement_and_real_api(database, snapshot, monkeypatch):
    database.load_from_json(snapshot)
    expected = database.get_statistics()
    assert expected["nodes"]["Article"] == 4
    assert expected["relationships"]["Has_Institution"] == 8
    database.load_from_json(snapshot)
    assert database.get_statistics() == expected
    with database.driver.session() as session:
        assert (
            session.run(
                "MATCH (n:RegressionSentinel) RETURN count(n) AS count"
            ).single()["count"]
            == 1
        )
    # A failure after all writes must roll back both deletion and creation.
    replacement = json.loads(snapshot.read_text())
    replacement["nodes"][0]["properties"]["name"] = "Replacement title"
    snapshot.write_text(json.dumps(replacement))

    class FailingLoader(Neo4jLoader):
        @staticmethod
        def _replace_graph(tx, data):
            Neo4jLoader._replace_graph(tx, data)
            raise ValueError("Simulated failure after writes")

    failing = FailingLoader.__new__(FailingLoader)
    failing.driver = database.driver
    with pytest.raises(ValueError, match="Simulated"):
        failing.load_from_json(snapshot)
    with database.driver.session() as session:
        assert (
            session.run(
                'MATCH (n:RWGraph {id: "Article:1"}) RETURN n.name AS name'
            ).single()["name"]
            == "Paper 1"
        )
    assert database.get_statistics() == expected
    monkeypatch.setattr(api, "neo4j_driver", database.driver)
    monkeypatch.setattr(api, "json_data", None)
    with TestClient(api.app) as client:
        assert (
            client.post(
                "/api/cypher", json={"query": "MATCH (n) DETACH DELETE n"}
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/nodes/Article) SET n.bad = true WITH n MATCH (n:Article"
            ).status_code
            == 422
        )
        assert client.get("/api/journals/top").json()["journals"] == [
            {"journal": "Journal", "retraction_count": 1}
        ]
        assert client.get("/api/reasons/top").json()["reasons"] == [
            {"reason": "Reason", "count": 1}
        ]
        nodes = client.get("/api/nodes/Article").json()["nodes"]
        assert len(nodes) == 4
        assert nodes[0]["id"] == "Article:1"
        assert nodes[0]["type"] == "Article"
        assert (
            client.get(
                "/api/search", params={"q": "KRÜGER", "node_type": "Author"}
            ).json()["count"]
            == 1
        )
        assert len(client.get("/api/articles/1").json()["institutions"]) == 2
        assert client.get("/api/articles/missing").status_code == 404
        assert client.get("/api/statistics").json()["total_nodes"] == sum(
            expected["nodes"].values()
        )
        # Keep fixture ownership of the driver; lifespan shutdown needn't close it here.
        monkeypatch.setattr(api, "neo4j_driver", None)
    # Replace with a smaller graph and ensure removed records disappear.
    data = json.loads(snapshot.read_text())
    data["nodes"] = [n for n in data["nodes"] if n["id"] != "Article:4"]
    data["edges"] = [
        e
        for e in data["edges"]
        if e["source"] != "Article:4" and e["target"] != "Article:4"
    ]
    snapshot.write_text(json.dumps(data))
    database.load_from_json(snapshot)
    assert database.get_statistics()["nodes"]["Article"] == 3


def test_bounded_aura_import_recovery_and_real_queries(
    database, aura_snapshot, monkeypatch
):
    from aura_import import STATE_ID, AuraImporter

    data = json.loads(aura_snapshot.read_text())

    # Every read endpoint must refuse partial data, even if a JSON fallback exists.
    class FailingImporter(AuraImporter):
        def _finish(self, tx, data):
            raise ValueError("Injected failure after committed batches")

    with pytest.raises(ValueError, match="Injected failure"):
        FailingImporter(database.driver, batch_size=2).load(data, "failed-snapshot")
    monkeypatch.setattr(api, "neo4j_driver", database.driver)
    monkeypatch.setattr(api, "json_data", data)
    with TestClient(api.app) as client:
        for path in (
            "/ready",
            "/api/statistics",
            "/api/nodes/Article",
            "/api/articles/1",
            "/api/reasons/top",
            "/api/name-records?name=Singleton",
        ):
            assert client.get(path).status_code == 503
        monkeypatch.setattr(api, "neo4j_driver", None)
    # Retrying a failed import rebuilds safely, including clearing committed data.
    database.load_from_json(aura_snapshot, batch_size=2)
    expected = database.get_statistics()
    assert expected["nodes"]["Article"] == 3
    assert expected["nodes"]["Author"] == 1
    assert "Reason" not in expected["nodes"]
    assert sum(expected["relationships"].values()) == 8
    database.load_from_json(aura_snapshot, batch_size=2)
    assert database.get_statistics() == expected
    monkeypatch.setattr(api, "neo4j_driver", database.driver)
    monkeypatch.setattr(api, "json_data", None)
    with TestClient(api.app) as client:
        assert client.get("/ready").status_code == 200
        detail = client.get("/api/articles/1").json()
        assert detail["listed_authors"] == ["Shared Name", "Singleton", "Shared Name"]
        assert detail["connected_entities"] == "shared_names_only"
        assert (
            client.get(
                "/api/name-records", params={"kind": "Author", "name": "Singleton"}
            ).json()["count"]
            == 1
        )
        assert (
            client.get(
                "/api/name-records", params={"kind": "Institution", "name": "Solo Uni"}
            ).json()["count"]
            == 1
        )
        assert (
            client.get(
                "/api/name-records", params={"kind": "Reason", "name": "Reason A"}
            ).json()["count"]
            == 3
        )
        assert (
            client.get(
                "/api/search", params={"node_type": "Article", "q": "Singleton"}
            ).json()["count"]
            == 1
        )
        assert client.get("/api/reasons/top").json()["reasons"] == [
            {"reason": "Reason A", "count": 2},
            {"reason": "Reason B", "count": 1},
        ]
        assert client.get("/api/journals/top").json()["journals"] == [
            {"journal": "Journal", "retraction_count": 2}
        ]
        assert (
            client.get("/api/nodes/Author").json()["nodes"][0]["properties"][
                "identity_basis"
            ]
            == "exact_name_string"
        )
        assert client.get("/api/statistics").json()["total_nodes"] == 6
        monkeypatch.setattr(api, "neo4j_driver", None)
    with database.driver.session() as session:
        assert (
            session.run(
                "MATCH (n:RegressionSentinel) RETURN count(n) AS count"
            ).single()["count"]
            == 1
        )
        # Expired leases can be reclaimed after an abrupt process crash.
        session.run(
            'MATCH (s:RWImportState {id: $id}) SET s.status="loading", s.owner="crashed", s.lease_until=0',
            id=STATE_ID,
        ).consume()
    database.load_from_json(aura_snapshot, batch_size=2)
    assert database.get_statistics() == expected


def test_aura_import_lease_and_unowned_quota(database, aura_snapshot):
    from aura_import import STATE_ID, AuraImporter

    data = json.loads(aura_snapshot.read_text())
    importer = AuraImporter(database.driver, batch_size=2)
    # The sentinel also consumes quota: this budget fits the artifact alone, not the database.
    with pytest.raises(ValueError, match="unowned"):
        AuraImporter(database.driver, max_nodes=len(data["nodes"]) + 1).load(
            data, "hash"
        )
    with database.driver.session() as session:
        session.execute_write(importer._claim, data, "first-worker")
    with pytest.raises(ValueError, match="active lease"):
        AuraImporter(database.driver).load(data, "second-worker")
    with database.driver.session() as session:
        row = session.run(
            "MATCH (s:RWImportState {id:$id}) RETURN s.owner AS owner", id=STATE_ID
        ).single()
        assert row["owner"] == importer.owner
        # A displaced worker must not continue or mark the new owner's job failed.
        session.run(
            'MATCH (s:RWImportState {id:$id}) SET s.owner="replacement"', id=STATE_ID
        ).consume()
        with pytest.raises(ValueError, match="lost"):
            importer._run(session, "RETURN 1 AS count")
        session.execute_write(importer._fail)
        assert (
            session.run(
                "MATCH (s:RWImportState {id:$id}) RETURN s.status AS status",
                id=STATE_ID,
            ).single()["status"]
            == "loading"
        )


def test_dashboard_queries_on_real_neo4j(database, aura_snapshot, monkeypatch):
    database.load_from_json(aura_snapshot, batch_size=2)
    monkeypatch.setattr(api, "neo4j_driver", database.driver)
    monkeypatch.setattr(api, "json_data", None)
    with TestClient(api.app) as client:
        overview = client.get("/api/dashboard/overview")
        assert overview.status_code == 200, overview.text
        assert overview.json()["total_nodes"] == 6
        assert overview.json()["notice_counts"]["Retraction"] == 2
        assert overview.json()["top_reasons"] == [
            {"name": "Reason A", "count": 2},
            {"name": "Reason B", "count": 1},
        ]
        assert overview.json()["snapshot"]["imported_at"]
        records = client.get(
            "/api/dashboard/records",
            params={"reason": "Reason A", "notice": "Retraction", "journal": "Journal"},
        )
        assert records.status_code == 200, records.text
        assert [n["record_id"] for n in records.json()["records"]] == ["3", "1"]
        assert (
            client.get("/api/dashboard/records", params={"q": "Singleton"}).json()[
                "records"
            ][0]["record_id"]
            == "1"
        )
        entities = client.get(
            "/api/dashboard/entities", params={"q": "Shared", "kind": "Author"}
        )
        assert entities.status_code == 200, entities.text
        assert entities.json()["nodes"][0]["id"] == "Author:Shared Name"
        page = client.get(
            "/api/dashboard/neighborhood",
            params={
                "node_id": "Author:Shared Name",
                "reason": "Reason B",
                "notice": "Retraction",
                "limit": 1,
            },
        )
        assert page.status_code == 200, page.text
        assert page.json()["total_neighbors"] == 1
        assert page.json()["nodes"][1]["id"] == "Article:1"
        empty = client.get(
            "/api/dashboard/neighborhood",
            params={"node_id": "Author:Shared Name", "skip": 999},
        )
        assert empty.status_code == 200, empty.text
        assert empty.json()["nodes"] == [empty.json()["center"]]
        with database.driver.session() as session:
            session.run('MATCH (s:RWImportState) SET s.status="loading"').consume()
        assert client.get("/api/dashboard/overview").status_code == 503
        assert (
            client.get(
                "/api/dashboard/neighborhood", params={"node_id": "Article:1"}
            ).status_code
            == 503
        )
        monkeypatch.setattr(api, "neo4j_driver", None)
