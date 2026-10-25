"""Small environment checks; run all regression tests with python -m pytest."""

import subprocess
import sys
from pathlib import Path


def test_imports():
    import matplotlib.pyplot
    import networkx
    import rdflib

    import api
    import neo4j_integration

    assert networkx and matplotlib.pyplot and rdflib and neo4j_integration and api.app


def test_csv_exists():
    assert (Path(__file__).parent / "retraction_watch.csv").stat().st_size > 0


def test_graph_generation(tmp_path):
    import csv

    from graph_schema import REQUIRED_COLUMNS
    from knowledge_graph import KnowledgeGraphGenerator

    path = tmp_path / "input.csv"
    row = dict.fromkeys(REQUIRED_COLUMNS, "")
    row.update({"Record ID": "1", "Title": "Sample", "RetractionNature": "Retraction"})
    with path.open("w", encoding="utf-8", newline="") as source:
        writer = csv.DictWriter(source, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerow(row)
    generator = KnowledgeGraphGenerator(path)
    generator.parse_csv()
    assert generator.graph.nodes["Article:1"]["name"] == "Sample"
    assert generator.get_statistics()["articles"] == 1


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"]))
