import json
from unittest.mock import MagicMock, Mock

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from rdflib import Graph

import api
from aura_import import AuraImporter
from graph_schema import check_aura_quota, validate_snapshot
from knowledge_graph import KnowledgeGraphGenerator, main


def test_complete_source_and_compact_topology(aura_snapshot):
    data = validate_snapshot(json.loads(aura_snapshot.read_text()))
    assert data["metadata"]["profile"] == "aura"
    assert data["metadata"]["schema_version"] == 3
    nodes = {n["id"]: n["properties"] for n in data["nodes"]}
    assert {key for key in nodes if key.startswith("Article:")} == {
        "Article:1",
        "Article:2",
        "Article:3",
    }
    assert {key for key in nodes if key.startswith("Author:")} == {"Author:Shared Name"}
    assert {key for key in nodes if key.startswith("Institution:")} == {
        "Institution:Shared Uni"
    }
    assert not any(key.startswith("Reason:") for key in nodes)
    article = nodes["Article:1"]
    assert article["author_names"] == ["Shared Name", "Singleton", "Shared Name"]
    assert article["institution_names"] == ["Shared Uni", "Solo Uni"]
    assert article["reason_names"] == ["Reason A", "Reason A", "Reason B"]
    source = json.loads(article["source_record"])
    assert source["RetractionPubMedID"] == "123"
    assert source["Author"] == "Shared Name;Singleton;Shared Name"
    assert "Extra field" in source
    assert nodes["Author:Shared Name"]["record_count"] == "3"
    assert nodes["Author:Shared Name"]["identity_basis"] == "exact_name_string"
    assert len(data["edges"]) == 8  # 3 journals, 3 shared author, 2 shared institution
    assert "not verified people" in data["metadata"]["identity_note"]


def test_single_record_duplicates_do_not_create_shared_nodes(write_csv):
    g = KnowledgeGraphGenerator(
        write_csv([{"Author": "Solo;Solo", "Institution": "Only;Only"}]), profile="aura"
    )
    g.parse_csv()
    assert not any(
        p["type"] in ("Author", "Institution") for _, p in g.graph.nodes(data=True)
    )


def test_promotion_and_demotion_on_rebuild(write_csv):
    g = KnowledgeGraphGenerator(
        write_csv([{"Author": "Person"}, {"Author": "Person"}]), profile="aura"
    )
    g.parse_csv()
    assert "Author:Person" in g.graph
    g.csv_path = write_csv([{"Author": "Person"}, {"Author": "Different"}])
    g.parse_csv()
    assert "Author:Person" not in g.graph
    assert g.graph.nodes["Article:1"]["author_names"] == ["Person"]


@pytest.mark.parametrize(
    "damage",
    [
        "lists",
        "source",
        "frequency",
        "missing_edge",
        "missing_node",
        "singleton",
        "reason_node",
        "threshold",
    ],
)
def test_rejects_inconsistent_projections(aura_snapshot, damage):
    data = json.loads(aura_snapshot.read_text())
    if damage == "lists":
        data["nodes"][0]["properties"]["author_names"] = ["Someone else"]
    if damage == "source":
        data["nodes"][0]["properties"]["source_record"] = "{}"
    if damage == "frequency":
        next(n for n in data["nodes"] if n["id"].startswith("Author:"))["properties"][
            "record_count"
        ] = "99"
    if damage == "missing_edge":
        data["edges"].pop()
    if damage == "missing_node":
        data["nodes"] = [n for n in data["nodes"] if not n["id"].startswith("Author:")]
        data["edges"] = [
            e for e in data["edges"] if not e["source"].startswith("Author:")
        ]
    if damage == "singleton":
        data["nodes"].append(
            {
                "id": "Author:Singleton",
                "properties": {
                    "name": "Singleton",
                    "type": "Author",
                    "record_count": "2",
                    "identity_basis": "exact_name_string",
                },
            }
        )
    if damage == "reason_node":
        data["nodes"].append(
            {
                "id": "Reason:Reason A",
                "properties": {"name": "Reason A", "type": "Reason"},
            }
        )
    if damage == "threshold":
        data["metadata"]["min_shared_records"] = 1
    with pytest.raises(ValueError):
        validate_snapshot(data)


def test_aura_budgets_before_any_db_write(aura_snapshot):
    data = json.loads(aura_snapshot.read_text())
    report = check_aura_quota(data)
    assert report["nodes_including_import_state"] == len(data["nodes"]) + 1
    for kwargs in (
        {"max_nodes": len(data["nodes"])},
        {"max_relationships": 7},
        {"max_nodes": 200001},
        {"max_relationships": 400001},
    ):
        with pytest.raises(ValueError):
            check_aura_quota(data, **kwargs)
    driver = Mock()
    importer = AuraImporter(driver, max_nodes=1)
    with pytest.raises(ValueError):
        importer.load(data, "hash")
    driver.session.assert_not_called()


def test_cli_writes_separate_artifact_and_report(write_csv, tmp_path):
    path = write_csv([{}, {}])
    output = tmp_path / "compact"
    assert (
        main(["--csv", str(path), "--profile", "aura", "--output-dir", str(output)])
        == 0
    )
    data = validate_snapshot(json.loads((output / "knowledge_graph.json").read_text()))
    report = json.loads((output / "aura_report.json").read_text())
    assert report["nodes_including_import_state"] == len(data["nodes"]) + 1
    assert report["json_bytes"] == (output / "knowledge_graph.json").stat().st_size
    assert len(data["metadata"]["source_csv_sha256"]) == 64
    assert not (output / "knowledge_graph.rdf").exists()


def test_over_budget_build_does_not_replace_existing_output(write_csv, tmp_path):
    output = tmp_path / "compact"
    output.mkdir()
    previous = output / "knowledge_graph.json"
    previous.write_text("previous")
    with pytest.raises(ValueError, match="budget exceeded"):
        main(
            [
                "--csv",
                str(write_csv()),
                "--profile",
                "aura",
                "--max-nodes",
                "1",
                "--output-dir",
                str(output),
            ]
        )
    assert previous.read_text() == "previous"


def test_optional_export_formats_preserve_lists(write_csv, tmp_path):
    g = KnowledgeGraphGenerator(write_csv([{}, {}]), profile="aura")
    g.parse_csv()
    g.export_to_graphml(tmp_path / "graph.graphml")
    g.export_to_rdf(tmp_path / "graph.rdf")
    graph = nx.read_graphml(tmp_path / "graph.graphml")
    assert json.loads(graph.nodes["Article:1"]["author_names"]) == [
        "Nele Krüger",
        "Alice",
    ]
    assert len(Graph().parse(tmp_path / "graph.rdf")) > len(g.graph)


def test_api_keeps_singletons_and_property_reasons_searchable(
    aura_snapshot, monkeypatch
):
    monkeypatch.setattr(api, "neo4j_driver", None)
    monkeypatch.setattr(api, "json_data", json.loads(aura_snapshot.read_text()))
    with TestClient(api.app) as client:
        detail = client.get("/api/articles/1").json()
        assert detail["listed_authors"] == ["Shared Name", "Singleton", "Shared Name"]
        assert [p["name"] for p in detail["authors"]] == ["Shared Name"]
        assert detail["connected_entities"] == "shared_names_only"
        assert detail["listed_reasons"] == ["Reason A", "Reason A", "Reason B"]
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
                "/api/name-records", params={"kind": "Author", "name": "shared name"}
            ).json()["count"]
            == 0
        )
        assert (
            client.get(
                "/api/search", params={"node_type": "Article", "q": "singleton"}
            ).json()["count"]
            == 1
        )
        assert client.get("/api/reasons/top").json()["reasons"] == [
            {"reason": "Reason A", "count": 2},
            {"reason": "Reason B", "count": 1},
        ]
        assert client.get("/ready").status_code == 200
        assert "not verified people" in client.get("/").json()["identity_note"]


def test_api_rejects_import_that_starts_during_a_query(monkeypatch):
    driver = MagicMock()
    session = Mock()
    driver.session.return_value.__enter__.return_value = session
    before = Mock()
    before.data.return_value = [{"status": "ready", "generation": "old"}]
    result = Mock()
    result.data.return_value = [{"count": 42}]
    after = Mock()
    after.data.return_value = [{"status": "ready", "generation": "new"}]
    session.run.side_effect = [before, result, after]
    monkeypatch.setattr(api, "neo4j_driver", driver)
    with pytest.raises(api.HTTPException) as error:
        api.query_neo4j("RETURN 42 AS count")
    assert error.value.status_code == 503
