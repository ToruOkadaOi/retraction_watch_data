"""Bounded, maintenance-mode imports for a compact graph on AuraDB Free."""

import uuid
from collections import defaultdict

from graph_schema import (
    AURA_NODE_BUDGET,
    AURA_RELATIONSHIP_BUDGET,
    check_aura_quota,
    validate_snapshot,
)

STATE_ID = "retraction-watch"
LEASE_MS = 300_000


class AuraImporter:
    """Refresh in small commits. Failed/interrupted refreshes stay unavailable.

    A server-side lease serializes cooperating importers. A restart after failure
    (or lease expiry after a crash) clears partial data and rebuilds from scratch.
    """

    def __init__(
        self,
        driver,
        *,
        batch_size=500,
        max_nodes=AURA_NODE_BUDGET,
        max_relationships=AURA_RELATIONSHIP_BUDGET,
    ):
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("Batch size must be between 1 and 1000")
        self.driver, self.batch_size = driver, batch_size
        self.max_nodes, self.max_relationships = max_nodes, max_relationships
        self.owner = uuid.uuid4().hex

    def load(self, data, snapshot_hash):
        validate_snapshot(data)
        if data["metadata"].get("profile") != "aura":
            raise ValueError("Bounded Aura imports require the compact Aura profile")
        quota = check_aura_quota(data, self.max_nodes, self.max_relationships)
        with self.driver.session() as session:
            # Account for unowned objects too; do not consume someone else's quota.
            extra_nodes = session.run(
                """MATCH (n)
                WHERE NOT n:RWGraph AND NOT (n:RWImportState AND n.id = $state_id)
                RETURN count(n) AS count""",
                state_id=STATE_ID,
            ).single()["count"]
            extra_edges = session.run("""MATCH (s)-[r]->(t)
                WHERE NOT s:RWGraph AND NOT t:RWGraph
                RETURN count(r) AS count""").single()["count"]
            if (
                quota["nodes_including_import_state"] + extra_nodes > self.max_nodes
                or quota["relationships"] + extra_edges > self.max_relationships
            ):
                raise ValueError(
                    "Aura budget exceeded after including unowned database objects"
                )
            session.run("""CREATE CONSTRAINT rwgraph_id IF NOT EXISTS
                FOR (n:RWGraph) REQUIRE n.id IS UNIQUE""").consume()
            session.run("""CREATE CONSTRAINT rw_import_state_id IF NOT EXISTS
                FOR (s:RWImportState) REQUIRE s.id IS UNIQUE""").consume()
            session.execute_write(self._claim, data, snapshot_hash)
            try:
                while self._run(
                    session,
                    """MATCH (n:RWGraph)-[r]-()
                    WITH DISTINCT r LIMIT $batch_size DELETE r RETURN count(*) AS count""",
                ):
                    pass
                while self._run(
                    session,
                    """MATCH (n:RWGraph)
                    WITH n LIMIT $batch_size DELETE n RETURN count(*) AS count""",
                ):
                    pass
                groups = defaultdict(list)
                for node in data["nodes"]:
                    groups[node["properties"]["type"]].append(node)
                for kind, nodes in groups.items():
                    for offset in range(0, len(nodes), self.batch_size):
                        rows = nodes[offset : offset + self.batch_size]
                        count = self._run(
                            session,
                            f"""UNWIND $rows AS row
                            MERGE (n:RWGraph:{kind} {{id: row.id}})
                            SET n = row.properties, n.id = row.id
                            RETURN count(*) AS count""",
                            rows=rows,
                        )
                        if count != len(rows):
                            raise ValueError("Incomplete node batch")
                groups = defaultdict(list)
                for edge in data["edges"]:
                    groups[edge["properties"]["type"]].append(edge)
                for kind, edges in groups.items():
                    for offset in range(0, len(edges), self.batch_size):
                        rows = edges[offset : offset + self.batch_size]
                        count = self._run(
                            session,
                            f"""UNWIND $rows AS row
                            MATCH (s:RWGraph {{id: row.source}}), (t:RWGraph {{id: row.target}})
                            MERGE (s)-[r:{kind}]->(t) SET r = row.properties
                            RETURN count(*) AS count""",
                            rows=rows,
                        )
                        if count != len(rows):
                            raise ValueError("Incomplete relationship batch")
                session.execute_write(self._finish, data)
            except Exception:
                # A connection loss may prevent this update. The loading marker
                # still blocks readers, and its lease eventually permits a retry.
                try:
                    session.execute_write(self._fail)
                except Exception:
                    pass
                raise

    def _claim(self, tx, data, snapshot_hash):
        row = tx.run(
            """MERGE (s:RWImportState {id: $state_id})
            SET s.lock = coalesce(s.lock, 0) + 1
            RETURN s.status AS status, coalesce(s.lease_until, 0) > timestamp() AS active""",
            state_id=STATE_ID,
        ).single()
        if row["status"] == "loading" and row["active"]:
            raise ValueError(
                "Another import holds the active lease; retry after it completes or expires"
            )
        tx.run(
            """MATCH (s:RWImportState {id: $state_id})
            SET s.status = 'loading', s.generation = $owner, s.owner = $owner,
                s.lease_until = timestamp() + $lease, s.profile = 'aura',
                s.snapshot_sha256 = $snapshot_hash, s.source_csv_sha256 = $csv_hash,
                s.min_shared_records = $threshold""",
            state_id=STATE_ID,
            owner=self.owner,
            lease=LEASE_MS,
            snapshot_hash=snapshot_hash,
            csv_hash=data["metadata"].get("source_csv_sha256", ""),
            threshold=data["metadata"]["min_shared_records"],
        ).consume()

    def _lock(self, tx):
        row = tx.run(
            """MATCH (s:RWImportState {id: $state_id})
            SET s.lock = coalesce(s.lock, 0) + 1
            RETURN s.owner AS owner, s.status AS status""",
            state_id=STATE_ID,
        ).single()
        if not row or row["owner"] != self.owner or row["status"] != "loading":
            raise ValueError("Import lease was lost")
        tx.run(
            """MATCH (s:RWImportState {id: $state_id})
            SET s.lease_until = timestamp() + $lease""",
            state_id=STATE_ID,
            lease=LEASE_MS,
        ).consume()

    def _run(self, session, query, **parameters):
        return session.execute_write(self._batch, query, parameters)

    def _batch(self, tx, query, parameters):
        self._lock(tx)
        return tx.run(query, batch_size=self.batch_size, **parameters).single()["count"]

    def _finish(self, tx, data):
        self._lock(tx)
        nodes = tx.run("MATCH (n:RWGraph) RETURN count(n) AS count").single()["count"]
        edges = tx.run(
            "MATCH (:RWGraph)-[r]->(:RWGraph) RETURN count(r) AS count"
        ).single()["count"]
        if nodes != len(data["nodes"]) or edges != len(data["edges"]):
            raise ValueError("Imported graph counts do not match the snapshot")
        tx.run(
            """MATCH (s:RWImportState {id: $state_id})
            SET s.status = 'ready', s.owner = '', s.lease_until = 0,
                s.nodes = $nodes, s.relationships = $edges""",
            state_id=STATE_ID,
            nodes=nodes,
            edges=edges,
        ).consume()

    def _fail(self, tx):
        # Take the same write lock before inspecting ownership.
        row = tx.run(
            """MATCH (s:RWImportState {id: $state_id})
            SET s.lock = coalesce(s.lock, 0) + 1 RETURN s.owner AS owner""",
            state_id=STATE_ID,
        ).single()
        if row and row["owner"] == self.owner:
            tx.run(
                """MATCH (s:RWImportState {id: $state_id})
                SET s.status = 'failed', s.owner = '', s.lease_until = 0""",
                state_id=STATE_ID,
            ).consume()
