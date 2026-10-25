"""Read-only REST queries for the Retraction Watch knowledge graph."""

import json
import logging
import os
from collections import Counter
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from neo4j import READ_ACCESS, GraphDatabase

from graph_schema import EDGE_TYPES, NODE_TYPES, validate_snapshot

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
NodeType = Literal["Article", "Author", "Journal", "Institution", "Reason"]
neo4j_driver = None
password = os.getenv("NEO4J_PASSWORD")
if password:
    candidate = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), password),
    )
    try:
        candidate.verify_connectivity()
        neo4j_driver = candidate
    except Exception:
        candidate.close()
        logger.warning("Neo4j unavailable; using JSON fallback", exc_info=True)

json_data = None
try:
    with open("outputs/knowledge_graph.json", encoding="utf-8") as source:
        json_data = validate_snapshot(json.load(source))
except (OSError, ValueError, TypeError, AttributeError):
    logger.warning(
        "No valid schema version 2 JSON snapshot; generate one before serving JSON queries"
    )


@asynccontextmanager
async def lifespan(app):
    yield
    if neo4j_driver:
        neo4j_driver.close()


app = FastAPI(
    title="Retraction Watch Knowledge Graph API", version="2.0.0", lifespan=lifespan
)


def query_neo4j(cypher, parameters=None):
    if not neo4j_driver:
        raise HTTPException(503, "Neo4j database not available")
    # Read routing is defense in depth; use a database user with read-only grants.
    with neo4j_driver.session(default_access_mode=READ_ACCESS) as session:
        return session.run(cypher, parameters or {}).data()


def with_fallback(cypher, parameters=None):
    """Return Neo4j records or None when a JSON fallback should be attempted."""
    if neo4j_driver:
        try:
            return query_neo4j(cypher, parameters)
        except Exception:
            logger.exception("Neo4j query failed")
    if json_data is None:
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
        "neo4j_connected": neo4j_driver is not None,
        "endpoints": {
            "docs": "/docs",
            "statistics": "/api/statistics",
            "nodes": "/api/nodes/{node_type}",
            "search": "/api/search",
        },
    }


@app.get("/api/statistics")
def get_statistics():
    if neo4j_driver:
        try:
            nodes = {
                r["type"]: r["count"]
                for r in query_neo4j(
                    "MATCH (n:RWGraph) RETURN n.type AS type, count(n) AS count"
                )
            }
            edges = {
                r["type"]: r["count"]
                for r in query_neo4j(
                    "MATCH (:RWGraph)-[r]->(:RWGraph) RETURN type(r) AS type, count(r) AS count"
                )
            }
            return {
                "source": "neo4j",
                "nodes": nodes,
                "edges": edges,
                "total_nodes": sum(nodes.values()),
                "total_edges": sum(edges.values()),
            }
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
        WHERE any(key IN keys(n) WHERE toLower(toString(n[key])) CONTAINS toLower($query))
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
                q.lower() in value.lower()
                for value in n["properties"].values()
                if isinstance(value, str)
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
        RETURN a, collect(DISTINCT author) AS authors, j,
               collect(DISTINCT r) AS reasons, collect(DISTINCT i) AS institutions
        """,
        {"record_id": record_id},
    )
    if records is not None:
        if not records:
            raise HTTPException(404, "Article not found")
        row = records[0]

        def properties(node):
            return {k: v for k, v in node.items() if k != "id"}

        return {
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
        "article": index[identity],
        "authors": authors,
        "journal": journals[0] if journals else None,
        "reasons": reasons,
        "institutions": institutions,
    }


def ranking(kind, limit):
    relationship, label, field, count_field = (
        ("Published_In", "Journal", "journal", "retraction_count")
        if kind == "journals"
        else ("Retracted_For", "Reason", "reason", "count")
    )
    records = with_fallback(
        f"""
        MATCH (a:RWGraph:Article)-[:{relationship}]->(n:RWGraph:{label})
        WHERE a.retraction_nature = 'Retraction'
        RETURN n.name AS {field}, count(DISTINCT a) AS {count_field}
        ORDER BY {count_field} DESC, {field} LIMIT $limit""",
        {"limit": limit},
    )
    if records is None:
        index = {n["id"]: n["properties"] for n in json_data["nodes"]}
        counts = Counter(
            e["target"]
            for e in json_data["edges"]
            if e["properties"]["type"] == relationship
            and index[e["source"]].get("retraction_nature") == "Retraction"
        )
        records = [
            {field: index[key]["name"], count_field: count}
            for key, count in sorted(
                counts.items(), key=lambda item: (-item[1], index[item[0]]["name"])
            )[:limit]
        ]
    return {kind: records, "count": len(records)}


@app.get("/api/journals/top")
def get_top_journals(limit: int = Query(10, ge=1, le=100)):
    return ranking("journals", limit)


@app.get("/api/reasons/top")
def get_top_reasons(limit: int = Query(10, ge=1, le=100)):
    return ranking("reasons", limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
