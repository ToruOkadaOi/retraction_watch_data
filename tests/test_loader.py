import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from neo4j_integration import Neo4jLoader


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "missing_node",
        "duplicate_node",
        "duplicate_edge",
        "direction",
        "label_injection",
        "relationship_injection",
        "reserved_id",
        "property_type",
        "errors",
        "empty",
    ],
)
def test_invalid_snapshot_is_rejected_before_database_writes(snapshot, damage):
    data = json.loads(snapshot.read_text())
    if damage == "version":
        data["metadata"]["schema_version"] = 1
    if damage == "missing_node":
        data["edges"][0]["target"] = "Journal:missing"
    if damage == "duplicate_node":
        data["nodes"].append(deepcopy(data["nodes"][0]))
    if damage == "duplicate_edge":
        data["edges"].append(deepcopy(data["edges"][0]))
    if damage == "direction":
        data["edges"][0]["source"], data["edges"][0]["target"] = (
            data["edges"][0]["target"],
            data["edges"][0]["source"],
        )
    if damage == "label_injection":
        data["nodes"][0]["properties"]["type"] = "Article) DETACH DELETE n"
    if damage == "relationship_injection":
        data["edges"][0]["properties"]["type"] = "Bad`"
    if damage == "reserved_id":
        data["nodes"][0]["properties"]["id"] = "override"
    if damage == "property_type":
        data["nodes"][0]["properties"]["notes"] = {"nested": "map"}
    if damage == "errors":
        data["metadata"]["statistics"]["errors"] = ["bad row"]
    if damage == "empty":
        data["nodes"] = []
    snapshot.write_text(json.dumps(data))
    loader = Neo4jLoader.__new__(Neo4jLoader)
    loader.driver = Mock()
    with pytest.raises(ValueError):
        loader.load_from_json(snapshot)
    loader.driver.session.assert_not_called()


def test_missing_snapshot_does_not_touch_database(tmp_path):
    loader = Neo4jLoader.__new__(Neo4jLoader)
    loader.driver = Mock()
    with pytest.raises(FileNotFoundError):
        loader.load_from_json(tmp_path / "missing.json")
    loader.driver.session.assert_not_called()


def test_loader_requires_credentials(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="required"):
        Neo4jLoader()


def test_cli_failure_is_nonzero():
    env = dict(os.environ, NEO4J_PASSWORD="")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "neo4j_integration.py")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "required" in result.stderr


def test_main_closes_driver_on_failed_import(monkeypatch):
    import neo4j_integration

    loader = Mock()
    loader.load_from_json.side_effect = ValueError("invalid file")
    monkeypatch.setattr(neo4j_integration, "Neo4jLoader", lambda: loader)
    assert neo4j_integration.main() == 1
    loader.close.assert_called_once()
