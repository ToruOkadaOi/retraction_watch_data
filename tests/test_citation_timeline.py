import json

import pytest
from fastapi.testclient import TestClient

import api
import citation_timeline as source
from graph_schema import REQUIRED_COLUMNS
from knowledge_graph import KnowledgeGraphGenerator


@pytest.fixture
def timeline_client(write_csv, tmp_path, monkeypatch):
    path = write_csv(
        [
            {
                "OriginalPaperDOI": "10.1159/000443123",
                "RetractionDate": "8/1/2020 0:00",
            },
            {
                "OriginalPaperDOI": "10.1159/000443123",
                "RetractionDate": "9/1/2020 0:00",
                "RetractionNature": "Reinstatement",
            },
            {"OriginalPaperPubMedID": "42"},
            {},
        ],
        headers=sorted(REQUIRED_COLUMNS | {"OriginalPaperPubMedID"}),
    )
    generator = KnowledgeGraphGenerator(path, profile="aura")
    generator.parse_csv()
    snapshot = tmp_path / "citation-timeline.json"
    generator.export_to_json(snapshot)
    monkeypatch.setattr(api, "neo4j_driver", None)
    monkeypatch.setattr(api, "json_data", json.loads(snapshot.read_text()))
    source.indexed_citations.cache_clear()
    source.work_titles.cache_clear()
    with TestClient(api.app) as client:
        yield client
    source.indexed_citations.cache_clear()
    source.work_titles.cache_clear()


def test_timeline_classifies_partial_dates_and_filters_all_citations(
    timeline_client, monkeypatch
):
    requested = []
    dates = ["2019", "2020-08-14", "2020-09-01", "2020-10", "2020", "", "2020-08"]

    def rows(path):
        requested.append(path)
        if path.startswith("/meta/"):
            return [{"id": "omid:br/2", "title": "A citing study"}]
        works = [
            {
                "oci": f"{i}-1",
                "citing": f"omid:br/{i} doi:10.1159/test{i}",
                "creation": value,
            }
            for i, value in enumerate(dates, 1)
        ]
        return works + [works[1]]

    monkeypatch.setattr(source, "provider_rows", rows)
    url = "/api/articles/1/citation-timeline"
    page = timeline_client.get(url, params={"period": "interval-1", "limit": 1})
    assert page.status_code == 200, page.text
    data = page.json()
    assert data["source_sha256"] == api.json_data["metadata"]["source_csv_sha256"]
    assert data["citation_retrieved_at"]
    assert data["indexed_count"] == len(dates)
    assert [notice["timeline_date"] for notice in data["notices"]] == [
        "2020-08-01",
        "2020-09-01",
    ]
    assert {item["id"]: item["count"] for item in data["periods"]} == {
        "interval-0": 1,
        "interval-1": 1,
        "interval-2": 1,
        "notice-date": 1,
        "uncertain": 3,
    }
    assert data["citations"] == [
        {
            "doi": "10.1159/test2",
            "pmid": None,
            "oci": "2-1",
            "publication_date": "2020-08-14",
            "period": "interval-1",
            "title": "A citing study",
        }
    ]
    assert (
        timeline_client.get(url, params={"period": "interval-1", "skip": 1}).json()[
            "citations"
        ]
        == []
    )
    assert requested == [
        "/index/v2/citations/doi:10.1159/000443123",
        "/meta/v1/metadata/omid:br/2",
    ]


def test_pmid_fallback_and_empty_coverage_are_distinct_from_provider_failure(
    timeline_client, monkeypatch
):
    def rows(path):
        assert path == "/index/v2/citations/pmid:42"
        return []

    monkeypatch.setattr(source, "provider_rows", rows)
    assert (
        timeline_client.get("/api/articles/3/citation-timeline").json()["indexed_count"]
        == 0
    )
    assert timeline_client.get("/api/articles/4/citation-timeline").status_code == 422
    assert timeline_client.get("/api/articles/999/citation-timeline").status_code == 404
    assert (
        timeline_client.get(
            "/api/articles/1/citation-timeline", params={"limit": 21}
        ).status_code
        == 422
    )

    def unavailable(path):
        raise source.CitationSourceError("provider timed out")

    monkeypatch.setattr(source, "provider_rows", unavailable)
    assert timeline_client.get("/api/articles/1/citation-timeline").status_code == 502
