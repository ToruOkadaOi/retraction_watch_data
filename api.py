"""Read-only REST queries for the Retraction Watch knowledge graph."""

import json
import logging
import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from neo4j import READ_ACCESS, GraphDatabase

from aura_import import STATE_ID
from dashboard_api import create_dashboard_router
from graph_schema import EDGE_TYPES, IDENTITY_NOTE, NODE_TYPES, validate_snapshot

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
NodeType = Literal["Article", "Author", "Journal", "Institution", "Reason"]


def create_neo4j_driver():
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        return None
    # Keep the lazy, thread-safe driver even when Aura is temporarily unreachable.
    # Each later query can establish a connection after the database resumes.
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), password),
        connection_timeout=5,
        connection_acquisition_timeout=10,
    )


neo4j_driver = create_neo4j_driver()
# Last observed query result, not merely whether credentials were configured.
neo4j_available = False

json_data = None
try:
    snapshot_path = os.getenv("GRAPH_JSON_PATH", "outputs/knowledge_graph.json")
    if snapshot_path:
        with open(snapshot_path, encoding="utf-8") as source:
            json_data = validate_snapshot(json.load(source))
except (OSError, ValueError, TypeError, AttributeError):
    logger.warning(
        "No valid JSON snapshot; generate one or configure GRAPH_JSON_PATH before serving JSON queries"
    )


@asynccontextmanager
async def lifespan(app):
    yield
    if neo4j_driver:
        neo4j_driver.close()


app = FastAPI(
    title="Retraction Watch Knowledge Graph API", version="2.0.0", lifespan=lifespan
)


# Browser clients are restricted to the published dashboard and local previews.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "https://toruokadaoi.github.io,http://localhost:8765,http://127.0.0.1:8765",
        ).split(",")
        if origin.strip()
    ],
    allow_methods=["GET"],
    allow_headers=["Accept"],
    allow_credentials=False,
)


def database_state(session):
    states = session.run(
        """MATCH (s:RWImportState {id: $state_id})
        RETURN s.status AS status, s.generation AS generation""",
        state_id=STATE_ID,
    ).data()
    state = states[0] if states else None
    if state and state["status"] != "ready":
        raise HTTPException(
            503, "Graph refresh incomplete; retry after a successful import"
        )
    return state


def query_neo4j(cypher, parameters=None):
    global neo4j_available
    if not neo4j_driver:
        raise HTTPException(503, "Neo4j database not available")
    try:
        with neo4j_driver.session(default_access_mode=READ_ACCESS) as session:
            before = database_state(session)
            records = session.run(cypher, parameters or {}).data()
            # Detect refreshes that started or finished while a query was running.
            if before != database_state(session):
                raise HTTPException(503, "Graph changed during query; retry")
        neo4j_available = True
        return records
    except HTTPException:
        # An import maintenance response still demonstrates database connectivity.
        neo4j_available = True
        raise
    except Exception:
        neo4j_available = False
        raise


def with_fallback(cypher, parameters=None):
    """Return Neo4j records or None when a JSON fallback should be attempted."""
    if neo4j_driver:
        try:
            return query_neo4j(cypher, parameters)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Neo4j query failed")
    if json_data is None:
        if neo4j_driver:
            raise HTTPException(
                503,
                "Graph database unavailable; check Aura status and retry",
                headers={"Retry-After": "15"},
            )
        raise HTTPException(503, "No data source available")
    return None


def node_response(node):
    # Both backends use the stable exported ID and the same response shape.
    props = dict(node)
    identity = props.pop("id")
    return {"id": identity, "type": props["type"], "properties": props}


@app.get("/")
def root():
    return {
        "name": app.title,
        "version": app.version,
        "neo4j_configured": neo4j_driver is not None,
        "neo4j_connected": neo4j_driver is not None and neo4j_available,
        "identity_note": IDENTITY_NOTE,
        "compact_profile_note": "Article lists retain all names; Author/Institution nodes may represent shared names only.",
        "endpoints": {
            "docs": "/docs",
            "statistics": "/api/statistics",
            "nodes": "/api/nodes/{node_type}",
            "search": "/api/search",
            "name_records": "/api/name-records",
            "readiness": "/ready",
            "dashboard": "/dashboard/",
            "dashboard_overview": "/api/dashboard/overview",
        },
    }


@app.get("/api/statistics")
def get_statistics():
    if neo4j_driver:
        try:
            records = query_neo4j("""MATCH (n:RWGraph)
                RETURN 'node' AS category, n.type AS type, count(n) AS count
                UNION ALL
                MATCH (:RWGraph)-[r]->(:RWGraph)
                RETURN 'edge' AS category, type(r) AS type, count(r) AS count""")
            nodes = {r["type"]: r["count"] for r in records if r["category"] == "node"}
            edges = {r["type"]: r["count"] for r in records if r["category"] == "edge"}
            return {
                "source": "neo4j",
                "nodes": nodes,
                "edges": edges,
                "total_nodes": sum(nodes.values()),
                "total_edges": sum(edges.values()),
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("Neo4j statistics failed")
    if json_data is None:
        raise HTTPException(503, "No data source available")
    nodes = Counter(n["properties"]["type"] for n in json_data["nodes"])
    edges = Counter(e["properties"]["type"] for e in json_data["edges"])
    return {
        "source": "json",
        "nodes": {k: nodes[k] for k in NODE_TYPES},
        "edges": {k: edges[k] for k in EDGE_TYPES},
        "total_nodes": sum(nodes.values()),
        "total_edges": sum(edges.values()),
    }


@app.get("/api/nodes/{node_type}")
def get_nodes_by_type(
    node_type: NodeType,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    records = with_fallback(
        f"MATCH (n:RWGraph:{node_type}) RETURN n ORDER BY n.id SKIP $skip LIMIT $limit",
        {"skip": skip, "limit": limit},
    )
    if records is not None:
        nodes = [node_response(r["n"]) for r in records]
    else:
        matches = sorted(
            (n for n in json_data["nodes"] if n["properties"]["type"] == node_type),
            key=lambda n: n["id"],
        )
        nodes = [dict(n, type=node_type) for n in matches[skip : skip + limit]]
    return {"nodes": nodes, "count": len(nodes), "skip": skip, "limit": limit}


@app.get("/api/search")
def search_nodes(
    q: str = Query(..., min_length=1, max_length=500),
    node_type: Optional[NodeType] = None,
    limit: int = Query(50, ge=1, le=500),
):
    label = f":{node_type}" if node_type else ""
    records = with_fallback(
        f"""MATCH (n:RWGraph{label})
        WHERE any(key IN keys(n) WHERE CASE
            WHEN key IN ['author_names', 'institution_names', 'reason_names']
            THEN any(value IN n[key] WHERE toLower(value) CONTAINS toLower($query))
            ELSE toLower(toString(n[key])) CONTAINS toLower($query) END)
        RETURN n ORDER BY n.id LIMIT $limit""",
        {"query": q, "limit": limit},
    )
    if records is not None:
        nodes = [node_response(r["n"]) for r in records]
    else:
        matches = sorted(json_data["nodes"], key=lambda n: n["id"])
        nodes = [
            dict(n, type=n["properties"]["type"])
            for n in matches
            if (node_type is None or n["properties"]["type"] == node_type)
            and any(
                q.lower() in item.lower()
                for value in n["properties"].values()
                for item in (value if isinstance(value, list) else [value])
                if isinstance(item, str)
            )
        ][:limit]
    return {"query": q, "nodes": nodes, "count": len(nodes)}


@app.get("/api/articles/{record_id}")
def get_article(record_id: str):
    records = with_fallback(
        """
        MATCH (a:RWGraph:Article {record_id: $record_id})
        OPTIONAL MATCH (author:RWGraph:Author)-[:Authored_By]->(a)
        OPTIONAL MATCH (a)-[:Published_In]->(j:RWGraph:Journal)
        OPTIONAL MATCH (a)-[:Retracted_For]->(r:RWGraph:Reason)
        OPTIONAL MATCH (a)-[:Has_Institution]->(i:RWGraph:Institution)
        OPTIONAL MATCH (state:RWImportState {id: $state_id})
        RETURN a, collect(DISTINCT author) AS authors, j,
               collect(DISTINCT r) AS reasons, collect(DISTINCT i) AS institutions,
               state.generation AS snapshot_generation
        """,
        {"record_id": record_id, "state_id": STATE_ID},
    )
    if records is not None:
        if not records:
            raise HTTPException(404, "Article not found")
        row = records[0]

        def properties(node):
            return {k: v for k, v in node.items() if k != "id"}

        return {
            **article_lists(
                properties(row["a"]),
                row["authors"],
                row["institutions"],
                row["reasons"],
            ),
            "snapshot_generation": row.get("snapshot_generation"),
            "article": properties(row["a"]),
            "authors": [properties(n) for n in row["authors"]],
            "journal": properties(row["j"]) if row["j"] else None,
            "reasons": [properties(n) for n in row["reasons"]],
            "institutions": [properties(n) for n in row["institutions"]],
        }
    index = {n["id"]: n["properties"] for n in json_data["nodes"]}
    identity = f"Article:{record_id}"
    if identity not in index:
        raise HTTPException(404, "Article not found")
    authors, journals, reasons, institutions = [], [], [], []
    for edge in json_data["edges"]:
        kind = edge["properties"]["type"]
        if edge["target"] == identity and kind == "Authored_By":
            authors.append(index[edge["source"]])
        elif edge["source"] == identity:
            if kind == "Published_In":
                journals.append(index[edge["target"]])
            elif kind == "Retracted_For":
                reasons.append(index[edge["target"]])
            elif kind == "Has_Institution":
                institutions.append(index[edge["target"]])
    return {
        **article_lists(index[identity], authors, institutions, reasons),
        "snapshot_generation": json_data["metadata"].get("generated_at"),
        "article": index[identity],
        "authors": authors,
        "journal": journals[0] if journals else None,
        "reasons": reasons,
        "institutions": institutions,
    }


def article_lists(article, authors, institutions, reasons):
    compact = article.get("graph_profile") == "aura"
    return {
        "listed_authors": article.get(
            "author_names", [node["name"] for node in authors]
        ),
        "listed_institutions": article.get(
            "institution_names", [node["name"] for node in institutions]
        ),
        "listed_reasons": article.get(
            "reason_names", [node["name"] for node in reasons]
        ),
        "graph_profile": "aura" if compact else "full",
        "connected_entities": "shared_names_only" if compact else "all_listed_names",
        "identity_note": IDENTITY_NOTE,
    }


@app.get("/ready")
def ready():
    records = with_fallback("MATCH (n:RWGraph:Article) RETURN count(n) AS count")
    if records is not None:
        if not records or not records[0]["count"]:
            raise HTTPException(503, "No imported article records")
        return {"ready": True, "source": "neo4j"}
    if json_data and any(
        n["properties"]["type"] == "Article" for n in json_data["nodes"]
    ):
        return {
            "ready": True,
            "source": "json",
            "profile": json_data["metadata"].get("profile", "full"),
        }
    raise HTTPException(503, "No data source available")


@app.get("/api/name-records")
def name_records(
    name: str = Query(..., min_length=1, max_length=500),
    kind: Literal["Author", "Institution", "Reason"] = "Author",
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    field, relation = {
        "Author": ("author_names", "Authored_By"),
        "Institution": ("institution_names", "Has_Institution"),
        "Reason": ("reason_names", "Retracted_For"),
    }[kind]
    pattern = (
        f"(n:RWGraph:{kind} {{name: $name}})-[:{relation}]->(a)"
        if kind == "Author"
        else f"(a)-[:{relation}]->(n:RWGraph:{kind} {{name: $name}})"
    )
    records = with_fallback(
        f"""MATCH (a:RWGraph:Article)
        WHERE $name IN coalesce(a.{field}, []) OR EXISTS {{ MATCH {pattern} }}
        RETURN a ORDER BY a.id SKIP $skip LIMIT $limit""",
        {"name": name, "skip": skip, "limit": limit},
    )
    if records is not None:
        nodes = [node_response(r["a"]) for r in records]
    else:
        linked = set()
        for edge in json_data["edges"]:
            if edge["properties"]["type"] == relation:
                if kind == "Author" and edge["source"] == f"Author:{name}":
                    linked.add(edge["target"])
                elif kind != "Author" and edge["target"] == f"{kind}:{name}":
                    linked.add(edge["source"])
        nodes = [
            dict(node, type="Article")
            for node in sorted(json_data["nodes"], key=lambda n: n["id"])
            if node["properties"]["type"] == "Article"
            and (name in node["properties"].get(field, []) or node["id"] in linked)
        ][skip : skip + limit]
    return {
        "name": name,
        "kind": kind,
        "nodes": nodes,
        "count": len(nodes),
        "skip": skip,
        "limit": limit,
        "match_basis": "exact_source_name",
        "identity_note": IDENTITY_NOTE,
    }


def ranking(kind, limit):
    relationship, label, field, count_field = (
        ("Published_In", "Journal", "journal", "retraction_count")
        if kind == "journals"
        else ("Retracted_For", "Reason", "reason", "count")
    )
    if kind == "reasons":
        cypher = """MATCH (a:RWGraph:Article)
            WHERE a.retraction_nature = 'Retraction'
            OPTIONAL MATCH (a)-[:Retracted_For]->(r:RWGraph:Reason)
            WITH a, collect(DISTINCT r.name) AS connected_reasons
            WITH a, CASE WHEN a.graph_profile = 'aura' THEN a.reason_names
                         ELSE connected_reasons END AS reasons
            UNWIND reasons AS reason
            RETURN reason, count(DISTINCT a) AS count
            ORDER BY count DESC, reason LIMIT $limit"""
    else:
        cypher = f"""MATCH (a:RWGraph:Article)-[:{relationship}]->(n:RWGraph:{label})
            WHERE a.retraction_nature = 'Retraction'
            RETURN n.name AS {field}, count(DISTINCT a) AS {count_field}
            ORDER BY {count_field} DESC, {field} LIMIT $limit"""
    records = with_fallback(cypher, {"limit": limit})
    if records is None:
        index = {n["id"]: n["properties"] for n in json_data["nodes"]}
        counts = Counter()
        for edge in json_data["edges"]:
            if (
                edge["properties"]["type"] == relationship
                and index[edge["source"]].get("retraction_nature") == "Retraction"
            ):
                counts[index[edge["target"]]["name"]] += 1
        if kind == "reasons":
            for props in index.values():
                if (
                    props.get("type") == "Article"
                    and props.get("graph_profile") == "aura"
                    and props["retraction_nature"] == "Retraction"
                ):
                    counts.update(set(props["reason_names"]))
        records = [
            {field: name, count_field: count}
            for name, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )[:limit]
        ]
    return {kind: records, "count": len(records)}


@app.get("/api/journals/top")
def get_top_journals(limit: int = Query(10, ge=1, le=100)):
    return ranking("journals", limit)


@app.get("/api/reasons/top")
def get_top_reasons(limit: int = Query(10, ge=1, le=100)):
    return ranking("reasons", limit)


app.include_router(create_dashboard_router(with_fallback, lambda: json_data))
_dashboard = Path(__file__).parent / "dashboard"
if _dashboard.is_dir():
    app.mount(
        "/dashboard", StaticFiles(directory=_dashboard, html=True), name="dashboard"
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
