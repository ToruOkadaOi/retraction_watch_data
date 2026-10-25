"""Validate and atomically replace the loader-owned Neo4j graph."""

import json
import logging
import os
from collections import defaultdict

from neo4j import READ_ACCESS, GraphDatabase

from graph_schema import validate_snapshot

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Neo4jLoader:
    """Only nodes carrying the RWGraph label belong to this loader."""

    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        if not self.password:
            raise ValueError("NEO4J_PASSWORD is required")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        try:
            self.driver.verify_connectivity()
        except Exception:
            self.driver.close()
            raise

    def close(self):
        self.driver.close()

    def create_constraints(self):
        with self.driver.session() as session:
            session.run("""CREATE CONSTRAINT rwgraph_id IF NOT EXISTS
                           FOR (n:RWGraph) REQUIRE n.id IS UNIQUE""").consume()

    @staticmethod
    def read_snapshot(json_path):
        with open(json_path, encoding="utf-8") as source:
            return validate_snapshot(json.load(source))

    def load_from_json(self, json_path="outputs/knowledge_graph.json"):
        # Every row and reference is validated before the first database write.
        data = self.read_snapshot(json_path)
        self.create_constraints()
        with self.driver.session() as session:
            session.execute_write(self._replace_graph, data)
        logger.info(
            "Graph replacement committed: %s nodes, %s edges",
            len(data["nodes"]),
            len(data["edges"]),
        )

    @staticmethod
    def _replace_graph(tx, data):
        # All batches share one transaction: any error restores the prior graph.
        tx.run("MATCH (n:RWGraph) DETACH DELETE n").consume()
        nodes_by_type = defaultdict(list)
        edges_by_type = defaultdict(list)
        for node in data["nodes"]:
            nodes_by_type[node["properties"]["type"]].append(node)
        for edge in data["edges"]:
            edges_by_type[edge["properties"]["type"]].append(edge)
        for kind, nodes in nodes_by_type.items():
            for offset in range(0, len(nodes), 1000):
                tx.run(
                    f"""UNWIND $nodes AS node
                    CREATE (n:RWGraph:{kind})
                    SET n = node.properties, n.id = node.id""",
                    nodes=nodes[offset : offset + 1000],
                ).consume()
        for kind, edges in edges_by_type.items():
            for offset in range(0, len(edges), 1000):
                batch = edges[offset : offset + 1000]
                result = tx.run(
                    f"""UNWIND $edges AS edge
                    MATCH (s:RWGraph {{id: edge.source}}), (t:RWGraph {{id: edge.target}})
                    CREATE (s)-[r:{kind}]->(t)
                    SET r = edge.properties
                    RETURN count(r) AS created""",
                    edges=batch,
                )
                if result.single()["created"] != len(batch):
                    raise ValueError("Not all graph relationships could be loaded")

    def get_statistics(self):
        with self.driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = session.run("""MATCH (n:RWGraph)
                RETURN n.type AS type, count(n) AS count""").data()
            relationships = session.run("""MATCH (:RWGraph)-[r]->(:RWGraph)
                RETURN type(r) AS type, count(r) AS count""").data()
        return {
            "nodes": {r["type"]: r["count"] for r in nodes},
            "relationships": {r["type"]: r["count"] for r in relationships},
        }

    def example_queries(self):
        with self.driver.session(default_access_mode=READ_ACCESS) as session:
            for label, query in (
                (
                    "journals",
                    """MATCH (a:RWGraph:Article)-[:Published_In]->(j:RWGraph:Journal)
                    WHERE a.retraction_nature = 'Retraction'
                    RETURN j.name AS journal, count(DISTINCT a) AS retraction_count
                    ORDER BY retraction_count DESC, journal LIMIT 10""",
                ),
                (
                    "reasons",
                    """MATCH (a:RWGraph:Article)-[:Retracted_For]->(r:RWGraph:Reason)
                    WHERE a.retraction_nature = 'Retraction'
                    RETURN r.name AS reason, count(DISTINCT a) AS count
                    ORDER BY count DESC, reason LIMIT 10""",
                ),
                (
                    "authors",
                    """MATCH (author:RWGraph:Author)-[:Authored_By]->(a:RWGraph:Article)
                    WHERE a.retraction_nature = 'Retraction'
                    RETURN author.name AS author, count(DISTINCT a) AS retraction_count
                    ORDER BY retraction_count DESC, author LIMIT 10""",
                ),
            ):
                logger.info("Top %s: %s", label, session.run(query).data())


def main():
    loader = None
    try:
        loader = Neo4jLoader()
        loader.load_from_json()
        logger.info("Database statistics: %s", loader.get_statistics())
        return 0
    except Exception:
        logger.exception("Neo4j integration failed; replacement was not committed")
        return 1
    finally:
        if loader:
            loader.close()


if __name__ == "__main__":
    raise SystemExit(main())
