"""Parse a real sample and verify exports without modifying tracked outputs."""

import csv
import json
import tempfile
from pathlib import Path

import networkx as nx
from rdflib import Graph

from graph_schema import validate_snapshot
from knowledge_graph import KnowledgeGraphGenerator


def test_with_sample(tmp_path):
    source = Path(__file__).parent / "retraction_watch.csv"
    sample = tmp_path / "sample.csv"
    with (
        source.open(encoding="utf-8-sig", newline="") as infile,
        sample.open("w", encoding="utf-8", newline="") as outfile,
    ):
        reader, writer = csv.reader(infile), csv.writer(outfile)
        for index, row in enumerate(reader):
            writer.writerow(row)
            if index == 100:
                break
    generator = KnowledgeGraphGenerator(sample)
    generator.parse_csv()
    generator.export_to_json(tmp_path / "graph.json")
    generator.export_to_graphml(tmp_path / "graph.graphml")
    generator.export_to_rdf(tmp_path / "graph.rdf")
    generator.visualize(tmp_path / "graph.png", sample_size=20)
    data = validate_snapshot(json.loads((tmp_path / "graph.json").read_text()))
    assert data["metadata"]["statistics"]["articles"] == 100
    assert len(nx.read_graphml(tmp_path / "graph.graphml")) == len(generator.graph)
    assert len(Graph().parse(tmp_path / "graph.rdf")) > len(generator.graph)
    assert (tmp_path / "graph.png").stat().st_size > 0
    assert not any(e["properties"]["type"] == "Affiliated_With" for e in data["edges"])


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_with_sample(Path(directory))
