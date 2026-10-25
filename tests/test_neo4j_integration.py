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
        session.run('CREATE (:RegressionSentinel {id: "keep-me"})').consume()
    yield loader
    with loader.driver.session() as session:
        session.run("MATCH (n:RWGraph) DETACH DELETE n").consume()
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
