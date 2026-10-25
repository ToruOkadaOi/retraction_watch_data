import json
from collections import Counter

import pytest

from graph_schema import validate_snapshot
from knowledge_graph import KnowledgeGraphGenerator


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_unicode_and_bom(write_csv, encoding):
    generator = KnowledgeGraphGenerator(write_csv(encoding=encoding))
    generator.parse_csv()
    assert "Author:Nele Krüger" in generator.graph
    assert generator.get_statistics()["articles"] == 1


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"Record ID": ""}, "Record ID"),
        ({"Record ID": "１２"}, "ASCII"),
        ({"Title": " "}, "Title"),
        ({"RetractionNature": "Unknown"}, "RetractionNature"),
    ],
)
def test_invalid_record_is_not_exportable(write_csv, tmp_path, changes, message):
    generator = KnowledgeGraphGenerator(write_csv([{}, changes]))
    with pytest.raises(ValueError, match=message):
        generator.parse_csv()
    assert len(generator.graph) == 0
    assert generator.get_statistics()["errors"]
    for method in (
        generator.export_to_json,
        generator.export_to_graphml,
        generator.export_to_rdf,
        generator.visualize,
    ):
        with pytest.raises(ValueError, match="Cannot export"):
            method(tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()


def test_duplicate_id_is_rejected(write_csv):
    generator = KnowledgeGraphGenerator(write_csv([{}, {"Record ID": "1"}]))
    with pytest.raises(ValueError, match="Duplicate Record ID"):
        generator.parse_csv()


@pytest.mark.parametrize(
    "contents,message",
    [
        ("Record ID,Title\n1,Title\n", "Missing required columns"),
        ("", "Missing required columns"),
    ],
)
def test_missing_schema(tmp_path, contents, message):
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    with pytest.raises(ValueError, match=message):
        KnowledgeGraphGenerator(path).parse_csv()


@pytest.mark.parametrize(
    "damage,message",
    [
        ("short", "Row width"),
        ("extra", "Row width"),
        ("duplicate_header", "Duplicate column"),
        ("empty", "no records"),
        ("bad_quote", "unexpected end"),
        ("encoding", "decode"),
    ],
)
def test_malformed_csv(write_csv, damage, message):
    path = write_csv()
    lines = path.read_text().splitlines()
    if damage == "short":
        lines[1] = lines[1].rsplit(",", 1)[0]
    if damage == "extra":
        lines[1] += ",extra"
    if damage == "duplicate_header":
        lines[0] += ",Title"
        lines[1] += ",duplicate"
    if damage == "empty":
        lines = lines[:1]
    if damage == "bad_quote":
        lines[1] = '"unterminated'
    path.write_text("\n".join(lines) + "\n")
    if damage == "encoding":
        path.write_bytes(path.read_bytes() + b"\xff")
    with pytest.raises(ValueError, match=message):
        KnowledgeGraphGenerator(path).parse_csv()


def test_article_affiliations_and_unique_edge_counts(write_csv, tmp_path):
    path = write_csv(
        [
            {
                "Author": "Alice;Alice;Bob",
                "Institution": "University A;University A;University B",
            },
            {},
        ]
    )
    generator = KnowledgeGraphGenerator(path)
    generator.parse_csv()
    assert not any(
        data["type"] == "Affiliated_With"
        for _, _, data in generator.graph.edges(data=True)
    )
    assert generator.graph.has_edge("Article:1", "Institution:University A")
    assert not generator.graph.has_edge("Author:Alice", "Institution:University A")
    assert generator.graph.nodes["Article:1"]["countries"] == "Germany;France"
    assert "country" not in generator.graph.nodes["Institution:University A"]
    counts = Counter(
        data["type"].lower() for _, _, data in generator.graph.edges(data=True)
    )
    stats = generator.get_statistics()
    assert all(stats[key] == value for key, value in counts.items())
    assert stats["has_institution"] == 4
    before = stats.copy()
    generator.parse_csv()
    assert generator.get_statistics() == before
    generator.export_to_json(tmp_path / "out.json")
    data = json.loads((tmp_path / "out.json").read_text())
    assert validate_snapshot(data) is data
    assert data["metadata"]["statistics"] == stats


def test_failed_reparse_preserves_previous_graph_but_blocks_export(write_csv, tmp_path):
    path = write_csv()
    generator = KnowledgeGraphGenerator(path)
    generator.parse_csv()
    previous = set(generator.graph)
    path.write_text("wrong\n")
    with pytest.raises(ValueError):
        generator.parse_csv()
    assert set(generator.graph) == previous
    with pytest.raises(ValueError):
        generator.export_to_json(tmp_path / "invalid.json")


def test_cli_does_not_publish_failed_build(tmp_path, monkeypatch, write_csv):
    import knowledge_graph

    path = write_csv([{"Title": ""}])
    (tmp_path / "retraction_watch.csv").write_bytes(path.read_bytes())
    output = tmp_path / "outputs"
    output.mkdir()
    existing = output / "knowledge_graph.json"
    existing.write_text("previous snapshot")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        knowledge_graph.main()
    assert existing.read_text() == "previous snapshot"
    assert not list(output.glob(".build-*"))


def test_export_failure_preserves_published_files(write_csv, tmp_path, monkeypatch):
    import knowledge_graph

    path = write_csv()
    (tmp_path / "retraction_watch.csv").write_bytes(path.read_bytes())
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "knowledge_graph.json").write_text("previous")
    monkeypatch.chdir(tmp_path)

    def fail(*args):
        raise RuntimeError("RDF export failure")

    monkeypatch.setattr(KnowledgeGraphGenerator, "export_to_rdf", fail)
    with pytest.raises(RuntimeError):
        knowledge_graph.main()
    assert (output / "knowledge_graph.json").read_text() == "previous"
    assert list(output.iterdir()) == [output / "knowledge_graph.json"]
