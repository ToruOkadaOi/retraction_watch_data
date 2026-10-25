"""Small, read-only query surfaces for the public dashboard."""

import logging
import time
from collections import Counter
from threading import Lock
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from aura_import import STATE_ID
from graph_schema import EDGE_TYPES, IDENTITY_NOTE, NODE_TYPES, NOTICE_TYPES

logger = logging.getLogger(__name__)
Notice = Literal["Retraction", "Correction", "Expression of concern", "Reinstatement"]
Kind = Literal["Article", "Author", "Institution", "Journal"]
# No source_record, narrative notes, or complete name lists in graph/search payloads.
PROJECTION = "{.id, .type, .name, .record_id, .retraction_nature, .original_paper_doi, .retraction_date, .record_count, .identity_basis}"
REASON_LIST = """OPTIONAL MATCH (a)-[:Retracted_For]->(r:RWGraph:Reason)
    WITH a, collect(DISTINCT r.name) AS connected_reasons
    WITH a, CASE WHEN a.graph_profile = 'aura' THEN a.reason_names ELSE connected_reasons END AS reasons"""


def compact_node(props, identity=None):
    keys = (
        "type",
        "name",
        "record_id",
        "retraction_nature",
        "original_paper_doi",
        "retraction_date",
        "record_count",
        "identity_basis",
    )
    return {
        "id": identity or props["id"],
        **{key: props[key] for key in keys if props.get(key) is not None},
    }


def index_snapshot(data):
    nodes = {n["id"]: n["properties"] for n in data["nodes"]}
    adjacency = {}
    for edge in data["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
        adjacency.setdefault(edge["target"], []).append(edge)
    return nodes, adjacency


def source_lists(identity, props, nodes, adjacency):
    result = {
        field: list(props.get(field, []))
        for field in ("author_names", "institution_names", "reason_names")
    }
    journal = ""
    for edge in adjacency.get(identity, []):
        kind = edge["properties"]["type"]
        other = edge["target"] if edge["source"] == identity else edge["source"]
        if kind == "Published_In":
            journal = nodes[other]["name"]
        elif props.get("graph_profile") != "aura":
            field = {
                "Authored_By": "author_names",
                "Has_Institution": "institution_names",
                "Retracted_For": "reason_names",
            }.get(kind)
            if field:
                result[field].append(nodes[other]["name"])
    return result, journal


def validate_notice(value):
    if value and value not in NOTICE_TYPES:
        raise HTTPException(422, "Unknown notice type")


def create_dashboard_router(run, get_data):
    """Bind to the existing maintenance-aware query helper and JSON fallback."""
    router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
    cache = {}
    cache_lock = Lock()

    def json_data():
        data = get_data()
        if not data:
            raise HTTPException(503, "No data source available")
        return data

    @router.get("/overview")
    def overview():
        marker = run(
            """OPTIONAL MATCH (s:RWImportState {id: $state_id})
            RETURN s {.generation, .profile, .source_csv_sha256, .imported_at, .status} AS snapshot""",
            {"state_id": STATE_ID},
        )
        data = json_data() if marker is None else None
        snapshot = marker[0]["snapshot"] if marker else None
        # Keep a strong JSON reference in the key guard to prevent object-id reuse.
        key = (
            ("json", id(data))
            if data is not None
            else ("neo4j", (snapshot or {}).get("generation"))
        )
        with cache_lock:
            if cache.get("key") == key and cache.get("expires", 0) > time.monotonic():
                return cache["value"]
        if data is not None:
            nodes, adjacency = index_snapshot(data)
            node_counts = Counter(p["type"] for p in nodes.values())
            edge_counts = Counter(e["properties"]["type"] for e in data["edges"])
            notice_counts, journals, reasons = Counter(), Counter(), Counter()
            for identity, props in nodes.items():
                if props["type"] != "Article":
                    continue
                notice_counts[props["retraction_nature"]] += 1
                if props["retraction_nature"] == "Retraction":
                    lists, journal = source_lists(identity, props, nodes, adjacency)
                    if journal:
                        journals[journal] += 1
                    reasons.update(set(lists["reason_names"]))

            def top(counter):
                return [
                    {"name": name, "count": count}
                    for name, count in sorted(
                        counter.items(), key=lambda item: (-item[1], item[0])
                    )[:10]
                ]

            meta = data["metadata"]
            response = {
                "source": "json",
                "profile": meta.get("profile", "full"),
                "snapshot": {
                    "source_csv_sha256": meta.get("source_csv_sha256"),
                    "generation": meta.get("generated_at"),
                    "imported_at": None,
                },
                "nodes": dict(node_counts),
                "relationships": dict(edge_counts),
                "notice_counts": dict(notice_counts),
                "top_journals": top(journals),
                "top_reasons": top(reasons),
            }
        else:
            records = run(
                f"""CALL {{ MATCH (n:RWGraph)
                    WITH n.type AS type, count(n) AS count RETURN collect({{type:type, count:count}}) AS nodes }}
                CALL {{ MATCH (:RWGraph)-[r]->(:RWGraph)
                    WITH type(r) AS type, count(r) AS count RETURN collect({{type:type, count:count}}) AS relationships }}
                CALL {{ MATCH (a:RWGraph:Article)
                    WITH a.retraction_nature AS type, count(a) AS count RETURN collect({{type:type, count:count}}) AS notices }}
                CALL {{ MATCH (a:RWGraph:Article)-[:Published_In]->(j:RWGraph:Journal)
                    WHERE a.retraction_nature = 'Retraction'
                    WITH j.name AS name, count(DISTINCT a) AS count ORDER BY count DESC, name LIMIT 10
                    RETURN collect({{name:name, count:count}}) AS journals }}
                CALL {{ MATCH (a:RWGraph:Article) WHERE a.retraction_nature = 'Retraction'
                    {REASON_LIST}
                    UNWIND reasons AS name WITH name, count(DISTINCT a) AS count ORDER BY count DESC, name LIMIT 10
                    RETURN collect({{name:name, count:count}}) AS reasons }}
                OPTIONAL MATCH (s:RWImportState {{id:$state_id}})
                RETURN nodes, relationships, notices, journals, reasons,
                    s {{.generation, .profile, .source_csv_sha256, .imported_at, .status}} AS snapshot""",
                {"state_id": STATE_ID},
            )
            if records is None:
                # A backend failure switched to JSON during this request; retry normally.
                raise HTTPException(503, "Data source changed; retry")
            row = records[0]
            if snapshot != row["snapshot"]:
                raise HTTPException(503, "Snapshot changed during overview; retry")
            response = {
                "source": "neo4j",
                "profile": (row["snapshot"] or {}).get("profile", "full"),
                "snapshot": row["snapshot"] or {},
                "nodes": {r["type"]: r["count"] for r in row["nodes"]},
                "relationships": {r["type"]: r["count"] for r in row["relationships"]},
                "notice_counts": {r["type"]: r["count"] for r in row["notices"]},
                "top_journals": row["journals"],
                "top_reasons": row["reasons"],
            }
        if not response["nodes"].get("Article"):
            raise HTTPException(503, "No imported article records")
        response["notice_counts"] = {
            kind: response["notice_counts"].get(kind, 0)
            for kind in (
                "Retraction",
                "Expression of concern",
                "Correction",
                "Reinstatement",
            )
        }
        response.update(
            total_nodes=sum(response["nodes"].values()),
            total_relationships=sum(response["relationships"].values()),
            identity_note=IDENTITY_NOTE,
        )
        with cache_lock:
            cache.update(
                key=key, value=response, expires=time.monotonic() + 60, data=data
            )
        return response

    @router.get("/records")
    def records(
        q: str = Query("", max_length=500),
        notice: str = "",
        journal: str = Query("", max_length=5000),
        reason: str = Query("", max_length=5000),
        limit: int = Query(20, ge=1, le=50),
        skip: int = Query(0, ge=0, le=1000000),
    ):
        validate_notice(notice)
        parameters = {
            "query": q,
            "notice": notice,
            "journal": journal,
            "reason": reason,
            "skip": skip,
            "fetch": limit + 1,
            "state_id": STATE_ID,
        }
        rows = run(
            f"""MATCH (a:RWGraph:Article)
            WHERE ($notice = '' OR a.retraction_nature = $notice)
            AND ($query = '' OR toLower(a.name) CONTAINS toLower($query)
                 OR a.record_id = $query OR toLower(coalesce(a.original_paper_doi,'')) CONTAINS toLower($query)
                 OR any(name IN coalesce(a.author_names,[]) WHERE toLower(name) CONTAINS toLower($query))
                 OR any(name IN coalesce(a.institution_names,[]) WHERE toLower(name) CONTAINS toLower($query))
                 OR EXISTS {{ MATCH (author:RWGraph:Author)-[:Authored_By]->(a) WHERE toLower(author.name) CONTAINS toLower($query) }}
                 OR EXISTS {{ MATCH (a)-[:Has_Institution]->(institution:RWGraph:Institution) WHERE toLower(institution.name) CONTAINS toLower($query) }})
            OPTIONAL MATCH (a)-[:Published_In]->(j:RWGraph:Journal)
            WITH a, j WHERE $journal = '' OR j.name = $journal
            {REASON_LIST}
            WITH a, reasons WHERE $reason = '' OR $reason IN reasons
            OPTIONAL MATCH (state:RWImportState {{id:$state_id}})
            RETURN a {PROJECTION} AS node, state.generation AS generation
            ORDER BY toInteger(a.record_id) DESC, a.id SKIP $skip LIMIT $fetch""",
            parameters,
        )
        if rows is not None:
            result = [r["node"] for r in rows]
        else:
            nodes, adjacency = index_snapshot(json_data())
            result = []
            for identity, props in nodes.items():
                if (
                    props["type"] != "Article"
                    or notice
                    and props["retraction_nature"] != notice
                ):
                    continue
                lists, journal_name = source_lists(identity, props, nodes, adjacency)
                if (
                    journal
                    and journal != journal_name
                    or reason
                    and reason not in lists["reason_names"]
                ):
                    continue
                haystack = [
                    props["name"],
                    props.get("original_paper_doi", ""),
                    *lists["author_names"],
                    *lists["institution_names"],
                ]
                if (
                    q
                    and props["record_id"] != q
                    and not any(q.lower() in value.lower() for value in haystack)
                ):
                    continue
                result.append(compact_node(props, identity))
            result.sort(key=lambda n: (-int(n["record_id"]), n["id"]))
            result = result[skip : skip + limit + 1]
        return {
            "snapshot_generation": (
                rows[0].get("generation")
                if rows
                else (
                    json_data()["metadata"].get("generated_at")
                    if rows is None
                    else None
                )
            ),
            "records": result[:limit],
            "has_more": len(result) > limit,
            "skip": skip,
            "limit": limit,
            "order": "record_id_desc",
            "filters": {"q": q, "notice": notice, "journal": journal, "reason": reason},
        }

    @router.get("/entities")
    def entities(
        q: str = Query(..., min_length=1, max_length=500),
        kind: Literal["Author", "Institution", "Journal"] = "Author",
        limit: int = Query(20, ge=1, le=50),
    ):
        rows = run(
            f"""MATCH (n:RWGraph:{kind}) WHERE toLower(n.name) CONTAINS toLower($query)
            OPTIONAL MATCH (state:RWImportState {{id:$state_id}})
            RETURN n {PROJECTION} AS node, state.generation AS generation ORDER BY n.name, n.id LIMIT $fetch""",
            {"query": q, "fetch": limit + 1, "state_id": STATE_ID},
        )
        if rows is not None:
            result = [r["node"] for r in rows]
        else:
            result = [
                compact_node(n["properties"], n["id"])
                for n in json_data()["nodes"]
                if n["properties"]["type"] == kind
                and q.lower() in n["properties"]["name"].lower()
            ]
            result.sort(key=lambda n: (n["name"], n["id"]))
        return {
            "snapshot_generation": (
                rows[0].get("generation")
                if rows
                else (
                    json_data()["metadata"].get("generated_at")
                    if rows is None
                    else None
                )
            ),
            "nodes": result[:limit],
            "has_more": len(result) > limit,
            "identity_note": IDENTITY_NOTE,
        }

    @router.get("/neighborhood")
    def neighborhood(
        node_id: str = Query(..., min_length=1, max_length=10000),
        notice: str = "",
        journal: str = Query("", max_length=5000),
        reason: str = Query("", max_length=5000),
        limit: int = Query(30, ge=1, le=100),
        skip: int = Query(0, ge=0, le=1000000),
    ):
        validate_notice(notice)
        if node_id.split(":", 1)[0] not in NODE_TYPES:
            raise HTTPException(422, "Unknown node type")
        where = """type(r) IN $relations AND n.type IN $types AND (n.type <> 'Article' OR (
            ($notice = '' OR n.retraction_nature = $notice)
            AND ($journal = '' OR EXISTS { MATCH (n)-[:Published_In]->(:RWGraph:Journal {name:$journal}) })
            AND ($reason = '' OR $reason IN coalesce(n.reason_names,[]) OR EXISTS { MATCH (n)-[:Retracted_For]->(:RWGraph:Reason {name:$reason}) })
        ))"""
        rows = run(
            f"""MATCH (s:RWGraph {{id:$id}})
            CALL {{ WITH s MATCH (s)-[r]-(n:RWGraph) WHERE {where} RETURN count(r) AS total }}
            CALL {{ WITH s MATCH (s)-[r]-(n:RWGraph) WHERE {where}
                WITH r,n ORDER BY n.type, n.name, n.id SKIP $skip LIMIT $limit
                RETURN collect({{node:n {PROJECTION}, source:startNode(r).id, target:endNode(r).id, type:type(r)}}) AS neighbors }}
            OPTIONAL MATCH (state:RWImportState {{id:$state_id}})
            RETURN s {PROJECTION} AS center, total, neighbors, state.generation AS generation""",
            {
                "id": node_id,
                "state_id": STATE_ID,
                "relations": list(EDGE_TYPES),
                "types": list(NODE_TYPES),
                "notice": notice,
                "journal": journal,
                "reason": reason,
                "skip": skip,
                "limit": limit,
            },
        )
        if rows is not None:
            if not rows:
                raise HTTPException(404, "Graph node not found")
            row = rows[0]
            center, total, neighbors = row["center"], row["total"], row["neighbors"]
        else:
            nodes, adjacency = index_snapshot(json_data())
            if node_id not in nodes:
                raise HTTPException(404, "Graph node not found")
            center = compact_node(nodes[node_id], node_id)
            neighbors = []
            for edge in adjacency.get(node_id, []):
                other = edge["target"] if edge["source"] == node_id else edge["source"]
                props = nodes[other]
                if props["type"] == "Article":
                    lists, journal_name = source_lists(other, props, nodes, adjacency)
                    if (
                        (notice and props["retraction_nature"] != notice)
                        or (journal and journal_name != journal)
                        or (reason and reason not in lists["reason_names"])
                    ):
                        continue
                neighbors.append(
                    {
                        "node": compact_node(props, other),
                        "source": edge["source"],
                        "target": edge["target"],
                        "type": edge["properties"]["type"],
                    }
                )
            neighbors.sort(
                key=lambda r: (r["node"]["type"], r["node"]["name"], r["node"]["id"])
            )
            total = len(neighbors)
            neighbors = neighbors[skip : skip + limit]
        page = len(neighbors)
        return {
            "snapshot_generation": (
                rows[0].get("generation")
                if rows
                else json_data()["metadata"].get("generated_at")
            ),
            "center": center,
            "nodes": [center] + [item["node"] for item in neighbors],
            "edges": [
                {key: item[key] for key in ("source", "target", "type")}
                for item in neighbors
            ],
            "total_neighbors": total,
            "returned_neighbors": page,
            "skip": skip,
            "limit": limit,
            "has_more": skip + page < total,
            "next_skip": skip + page if skip + page < total else None,
            "identity_note": IDENTITY_NOTE,
        }

    return router
