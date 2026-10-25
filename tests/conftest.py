import csv
import os

import pytest

from graph_schema import REQUIRED_COLUMNS
from knowledge_graph import KnowledgeGraphGenerator

# Unit tests must never connect to a user's configured database during import.
os.environ.pop("NEO4J_PASSWORD", None)


@pytest.fixture
def write_csv(tmp_path):
    def write(rows=None, *, encoding="utf-8", headers=None):
        path = tmp_path / "input.csv"
        with path.open("w", encoding=encoding, newline="") as source:
            writer = csv.DictWriter(
                source, fieldnames=headers or sorted(REQUIRED_COLUMNS)
            )
            writer.writeheader()
            for index, changes in enumerate(rows if rows is not None else [{}], 1):
                row = dict.fromkeys(REQUIRED_COLUMNS, "")
                row.update(
                    {
                        "Record ID": str(index),
                        "Title": f"Paper {index}",
                        "RetractionNature": "Retraction",
                        "Author": "Nele Krüger;Alice",
                        "Institution": "University A;University B",
                        "Country": "Germany;France",
                        "Journal": "Journal",
                        "Reason": "Reason",
                    }
                )
                row.update(changes)
                writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
        return path

    return write


@pytest.fixture
def snapshot(write_csv, tmp_path):
    path = write_csv(
        [
            {"RetractionNature": nature}
            for nature in (
                "Retraction",
                "Correction",
                "Expression of concern",
                "Reinstatement",
            )
        ]
    )
    generator = KnowledgeGraphGenerator(path)
    generator.parse_csv()
    result = tmp_path / "graph.json"
    generator.export_to_json(result)
    return result


@pytest.fixture
def aura_snapshot(write_csv, tmp_path):
    rows = [
        {
            "Author": "Shared Name;Singleton;Shared Name",
            "Institution": "Shared Uni;Solo Uni",
            "Reason": "Reason A;Reason A;Reason B",
            "RetractionPubMedID": "123",
        },
        {
            "Author": "Shared Name;Other",
            "Institution": "Shared Uni",
            "Reason": "Reason A",
            "RetractionNature": "Correction",
        },
        {"Author": "Shared Name", "Institution": "Another Uni", "Reason": "Reason A"},
    ]
    path = write_csv(
        rows,
        headers=sorted(
            REQUIRED_COLUMNS
            | {"RetractionPubMedID", "OriginalPaperPubMedID", "Extra field"}
        ),
    )
    generator = KnowledgeGraphGenerator(path, profile="aura")
    generator.parse_csv()
    output = tmp_path / "aura.json"
    generator.export_to_json(output)
    return output
