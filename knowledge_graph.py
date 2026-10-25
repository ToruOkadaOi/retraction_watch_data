"""
Knowledge Graph Generator for Retraction Watch Data

This script parses the retraction_watch.csv dataset and creates a knowledge graph with:
- Entities: Authors, Articles, Journals, Institutions, Reasons
- Relationships: Authored_By, Published_In, Has_Institution, Retracted_For

Schema (relationship directions):
    (Author)-[:Authored_By]->(Article)
    (Article)-[:Published_In]->(Journal)
    (Article)-[:Has_Institution]->(Institution)
    (Article)-[:Retracted_For]->(Reason)
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import tempfile
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote

import matplotlib
import networkx as nx
from rdflib import RDF, Graph, Literal, Namespace, URIRef

from graph_schema import (
    AURA_NODE_BUDGET,
    AURA_RELATIONSHIP_BUDGET,
    AURA_SCHEMA_VERSION,
    IDENTITY_NOTE,
    NOTICE_TYPES,
    REQUIRED_COLUMNS,
    SCHEMA_VERSION,
    check_aura_quota,
)

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KnowledgeGraphGenerator:
    """Generate Knowledge Graph from Retraction Watch data"""

    def __init__(
        self,
        csv_path: str = "retraction_watch.csv",
        *,
        profile="full",
        min_shared_records=2,
        max_nodes=AURA_NODE_BUDGET,
        max_relationships=AURA_RELATIONSHIP_BUDGET,
    ):
        if (
            profile not in ("full", "aura")
            or type(min_shared_records) is not int
            or min_shared_records < 2
        ):
            raise ValueError(
                "Use full/aura profile and a shared-record threshold of at least 2"
            )
        self.profile = profile
        self.min_shared_records = min_shared_records
        self.max_nodes, self.max_relationships = max_nodes, max_relationships
        self._frequencies = {"Author": Counter(), "Institution": Counter()}
        self.source_sha256 = None
        self.csv_path = csv_path
        self._parse_failed = False
        self.graph = nx.DiGraph()
        self.stats = {
            "authors": 0,
            "articles": 0,
            "journals": 0,
            "institutions": 0,
            "reasons": 0,
            "authored_by": 0,
            "published_in": 0,
            "has_institution": 0,
            "retracted_for": 0,
            "errors": [],
        }

    def _split_field(self, field: str) -> List[str]:
        """Split semicolon-separated field into list"""
        if not field or field.strip() == "":
            return []
        return [item.strip() for item in field.split(";") if item.strip()]

    def _create_node_id(self, node_type: str, name: str) -> str:
        """Create unique node identifier"""
        # Clean the name and create ID
        clean_name = name.strip()
        return f"{node_type}:{clean_name}"

    def _add_node(self, node_id: str, node_type: str, properties: Dict) -> None:
        """Add node to graph with properties"""
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id, type=node_type, **properties)
            self.stats[node_type.lower() + "s"] += 1

    def _add_edge(
        self, from_node: str, to_node: str, edge_type: str, properties: Dict = None
    ) -> None:
        """Add edge to graph with properties"""
        if properties is None:
            properties = {}

        if from_node not in self.graph or to_node not in self.graph:
            raise ValueError("Relationship references a missing node")
        exists = self.graph.has_edge(from_node, to_node)
        self.graph.add_edge(from_node, to_node, type=edge_type, **properties)
        if not exists:
            self.stats[edge_type.lower()] += 1

    def parse_csv(self) -> None:
        """Build a validated snapshot; never expose partially parsed rows."""
        candidate = type(self)(
            self.csv_path,
            profile=self.profile,
            min_shared_records=self.min_shared_records,
            max_nodes=self.max_nodes,
            max_relationships=self.max_relationships,
        )
        seen_ids = set()
        row_num = 1
        try:
            with open(self.csv_path, "rb") as source:
                source_hash = hashlib.file_digest(source, "sha256").hexdigest()
            if self.profile == "aura":
                # Count each name once per record; repeated mentions are not shared entities.
                with open(self.csv_path, encoding="utf-8-sig", newline="") as source:
                    for row in csv.DictReader(source, strict=True):
                        for field in candidate._frequencies:
                            candidate._frequencies[field].update(
                                set(self._split_field(row.get(field, "")))
                            )
            with open(self.csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, strict=True)
                headers = reader.fieldnames or []
                missing = REQUIRED_COLUMNS - set(headers)
                if missing:
                    raise ValueError(
                        f"Missing required columns: {', '.join(sorted(missing))}"
                    )
                if len(headers) != len(set(headers)):
                    raise ValueError("Duplicate column names")
                for row_num, row in enumerate(reader, start=2):
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("Row width does not match header")
                    record_id = row["Record ID"].strip()
                    if (
                        not record_id
                        or not record_id.isascii()
                        or not record_id.isdigit()
                    ):
                        raise ValueError("Record ID must contain ASCII digits")
                    if record_id in seen_ids:
                        raise ValueError(f"Duplicate Record ID: {record_id}")
                    if not row["Title"].strip():
                        raise ValueError("Missing Title")
                    if row["RetractionNature"].strip() not in NOTICE_TYPES:
                        raise ValueError("Unknown RetractionNature")
                    seen_ids.add(record_id)
                    candidate._process_row(row, row_num)
            if not seen_ids:
                raise ValueError("CSV contains no records")
            with open(self.csv_path, "rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != source_hash:
                    raise ValueError("Source CSV changed during generation")
            candidate.source_sha256 = source_hash
            if self.profile == "aura":
                candidate.quota_report()
        except Exception as exc:
            self._parse_failed = True
            message = f"CSV validation failed near row {row_num}: {exc}"
            self.stats["errors"] = [message]
            raise ValueError(message) from exc
        self.graph, self.stats = candidate.graph, candidate.get_statistics()
        self.source_sha256 = candidate.source_sha256
        self._parse_failed = False
        self._log_statistics()

    def _ensure_exportable(self):
        if self._parse_failed or self.stats["errors"] or not self.stats["articles"]:
            raise ValueError("Cannot export an empty or failed graph")

    def _process_row(self, row: Dict, row_num: int) -> None:
        """Process a single CSV row"""
        # Extract and validate article data
        record_id = row.get("Record ID", "").strip()
        title = row.get("Title", "").strip()

        if not record_id or not title:
            raise ValueError(f"Row {row_num}: Missing Record ID or Title")

        # Create Article node
        article_id = self._create_node_id("Article", record_id)
        article_props = {
            "name": title,
            "record_id": record_id,
            "subject": row.get("Subject", ""),
            "retraction_date": row.get("RetractionDate", ""),
            "original_paper_date": row.get("OriginalPaperDate", ""),
            "retraction_nature": row.get("RetractionNature", "").strip(),
            "countries": row.get("Country", ""),
            "article_type": row.get("ArticleType", ""),
            "retraction_doi": row.get("RetractionDOI", ""),
            "original_paper_doi": row.get("OriginalPaperDOI", ""),
            "paywalled": row.get("Paywalled", ""),
            "notes": row.get("Notes", ""),
            "urls": row.get("URLS", ""),
        }
        if self.profile == "aura":
            article_props.update(
                {
                    "graph_profile": "aura",
                    "author_names": self._split_field(row["Author"]),
                    "institution_names": self._split_field(row["Institution"]),
                    "reason_names": self._split_field(row["Reason"]),
                    # Retain every source column, including fields not otherwise modeled.
                    "source_record": json.dumps(
                        row, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
        self._add_node(article_id, "Article", article_props)

        # Process Journal
        journal = row.get("Journal", "").strip()
        if journal:
            journal_id = self._create_node_id("Journal", journal)
            journal_props = {"name": journal, "publisher": row.get("Publisher", "")}
            self._add_node(journal_id, "Journal", journal_props)
            self._add_edge(
                article_id,
                journal_id,
                "Published_In",
                {"date": row.get("OriginalPaperDate", "")},
            )

        # Process Authors
        authors = self._split_field(row.get("Author", ""))
        for author in authors:
            if author and (
                self.profile == "full"
                or self._frequencies["Author"][author] >= self.min_shared_records
            ):
                author_id = self._create_node_id("Author", author)
                author_props = {"name": author}
                if self.profile == "aura":
                    author_props.update(
                        identity_basis="exact_name_string",
                        record_count=str(self._frequencies["Author"][author]),
                    )
                self._add_node(author_id, "Author", author_props)
                self._add_edge(author_id, article_id, "Authored_By", {})

        # Process Institutions
        institutions = self._split_field(row.get("Institution", ""))
        for institution in institutions:
            if institution and (
                self.profile == "full"
                or self._frequencies["Institution"][institution]
                >= self.min_shared_records
            ):
                institution_id = self._create_node_id("Institution", institution)
                institution_props = {"name": institution}
                if self.profile == "aura":
                    institution_props.update(
                        identity_basis="exact_institution_string",
                        record_count=str(self._frequencies["Institution"][institution]),
                    )
                self._add_node(institution_id, "Institution", institution_props)
                # The CSV lists affiliations per article, without author mappings.
                self._add_edge(article_id, institution_id, "Has_Institution", {})

        # Process Retraction Reasons
        reasons = self._split_field(row.get("Reason", ""))
        for reason in reasons:
            if reason and self.profile == "full":
                reason_id = self._create_node_id("Reason", reason)
                reason_props = {"name": reason}
                self._add_node(reason_id, "Reason", reason_props)
                self._add_edge(
                    article_id,
                    reason_id,
                    "Retracted_For",
                    {"date": row.get("RetractionDate", "")},
                )

    def _log_statistics(self) -> None:
        """Log graph statistics"""
        logger.info("=" * 60)
        logger.info("Knowledge Graph Statistics:")
        logger.info("  Nodes:")
        logger.info(f"    - Articles: {self.stats['articles']}")
        logger.info(f"    - Authors: {self.stats['authors']}")
        logger.info(f"    - Journals: {self.stats['journals']}")
        logger.info(f"    - Institutions: {self.stats['institutions']}")
        logger.info(f"    - Reasons: {self.stats['reasons']}")
        logger.info("  Edges:")
        logger.info(f"    - Authored_By: {self.stats['authored_by']}")
        logger.info(f"    - Published_In: {self.stats['published_in']}")
        logger.info(f"    - Has_Institution: {self.stats['has_institution']}")
        logger.info(f"    - Retracted_For: {self.stats['retracted_for']}")
        logger.info(f"  Errors: {len(self.stats['errors'])}")
        logger.info("=" * 60)

    def visualize(
        self, output_path: str = "knowledge_graph.png", sample_size: int = 100
    ) -> None:
        """Create NetworkX visualization (sample for large graphs)"""
        self._ensure_exportable()
        logger.info(f"Creating visualization (sample size: {sample_size})")

        # Sample nodes for visualization if graph is large
        if len(self.graph.nodes()) > sample_size:
            # Get a sample of nodes
            nodes = list(self.graph.nodes())[:sample_size]
            subgraph = self.graph.subgraph(nodes)
        else:
            subgraph = self.graph

        # Create figure
        plt.figure(figsize=(20, 20))

        # Node colors based on type
        node_colors = []
        for node in subgraph.nodes():
            node_type = subgraph.nodes[node].get("type", "")
            if node_type == "Article":
                node_colors.append("lightblue")
            elif node_type == "Author":
                node_colors.append("lightgreen")
            elif node_type == "Journal":
                node_colors.append("yellow")
            elif node_type == "Institution":
                node_colors.append("orange")
            elif node_type == "Reason":
                node_colors.append("pink")
            else:
                node_colors.append("gray")

        # Layout
        pos = nx.spring_layout(subgraph, k=0.5, iterations=50)

        # Draw nodes
        nx.draw_networkx_nodes(
            subgraph, pos, node_color=node_colors, node_size=500, alpha=0.7
        )

        # Draw edges
        nx.draw_networkx_edges(
            subgraph, pos, alpha=0.3, arrows=True, arrowsize=10, width=0.5
        )

        # Draw labels (only for small graphs)
        if len(subgraph.nodes()) <= 50:
            labels = {
                node: subgraph.nodes[node].get("name", node.split(":")[1][:20])
                for node in subgraph.nodes()
            }
            nx.draw_networkx_labels(subgraph, pos, labels, font_size=6)

        plt.title(
            f"Retraction Watch Knowledge Graph (Sample: {len(subgraph.nodes())} nodes)"
        )
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info(f"Visualization saved to {output_path}")

    def quota_report(self):
        return check_aura_quota(
            {"nodes": self.graph.nodes, "edges": self.graph.edges},
            self.max_nodes,
            self.max_relationships,
        )

    def metadata(self):
        epoch = os.getenv("SOURCE_DATE_EPOCH")
        result = {
            "generated_at": datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
            if epoch
            else datetime.now(timezone.utc).isoformat(),
            "schema_version": AURA_SCHEMA_VERSION
            if self.profile == "aura"
            else SCHEMA_VERSION,
            "profile": self.profile,
            "source_csv_sha256": self.source_sha256,
            "statistics": self.get_statistics(),
            "identity_note": IDENTITY_NOTE,
        }
        if self.profile == "aura":
            result.update(
                min_shared_records=self.min_shared_records,
                aura_quota=self.quota_report(),
            )
        return result

    def export_to_json(self, output_path: str = "knowledge_graph.json") -> None:
        """Stream the snapshot without constructing another full graph in memory."""
        self._ensure_exportable()
        with open(output_path, "w", encoding="utf-8") as output:
            output.write(
                '{"metadata":' + json.dumps(self.metadata(), ensure_ascii=False)
            )
            output.write(',"nodes":[\n')
            for index, (identity, props) in enumerate(self.graph.nodes(data=True)):
                if index:
                    output.write(",\n")
                output.write(
                    json.dumps(
                        {"id": identity, "properties": props}, ensure_ascii=False
                    )
                )
            output.write('],"edges":[\n')
            for index, (source, target, props) in enumerate(
                self.graph.edges(data=True)
            ):
                if index:
                    output.write(",\n")
                output.write(
                    json.dumps(
                        {"source": source, "target": target, "properties": props},
                        ensure_ascii=False,
                    )
                )
            output.write("]}\n")
        logger.info("JSON export completed: %s", output_path)

    def export_to_graphml(self, output_path: str = "knowledge_graph.graphml") -> None:
        """Export graph to GraphML format (for Gephi)"""
        self._ensure_exportable()
        logger.info(f"Exporting to GraphML: {output_path}")
        # GraphML has scalar attributes; encode list properties as JSON strings.
        graph = self.graph
        if self.profile == "aura":
            graph = self.graph.copy()
            for _, props in graph.nodes(data=True):
                for key, value in list(props.items()):
                    if isinstance(value, list):
                        props[key] = json.dumps(value, ensure_ascii=False)
        nx.write_graphml(graph, output_path)
        logger.info("GraphML export completed")

    def export_to_rdf(self, output_path: str = "knowledge_graph.rdf") -> None:
        """Export graph to RDF format"""
        self._ensure_exportable()
        logger.info(f"Exporting to RDF: {output_path}")

        # Create RDF graph
        rdf_graph = Graph()

        # Define namespace
        RW = Namespace("http://retractionwatch.org/ontology#")
        rdf_graph.bind("rw", RW)

        # Add nodes
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            node_type = node_data.get("type", "Unknown")
            node_uri = URIRef(
                f"http://retractionwatch.org/resource/{quote(node_id, safe='')}"
            )

            # Add type
            rdf_graph.add((node_uri, RDF.type, RW[node_type]))

            # Add properties
            for key, value in node_data.items():
                if key != "type" and value:
                    for item in value if isinstance(value, list) else [value]:
                        rdf_graph.add((node_uri, RW[key], Literal(item)))

        # Add edges
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            edge_type = edge_data.get("type", "RelatedTo")

            source_uri = URIRef(
                f"http://retractionwatch.org/resource/{quote(source, safe='')}"
            )
            target_uri = URIRef(
                f"http://retractionwatch.org/resource/{quote(target, safe='')}"
            )

            rdf_graph.add((source_uri, RW[edge_type], target_uri))

            # Add edge properties
            for key, value in edge_data.items():
                if key != "type" and value:
                    # Create a blank node for edge properties
                    # (simplified - in practice, might use reification)
                    pass

        # Serialize to file
        rdf_graph.serialize(destination=output_path, format="xml")
        logger.info("RDF export completed")

    def get_statistics(self) -> Dict:
        """Return graph statistics"""
        nodes = Counter(
            data["type"].lower() + "s" for _, data in self.graph.nodes(data=True)
        )
        edges = Counter(
            data["type"].lower() for _, _, data in self.graph.edges(data=True)
        )
        for key in self.stats:
            if key != "errors":
                self.stats[key] = nodes.get(key, 0) + edges.get(key, 0)
        return deepcopy(self.stats)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate full or compact Aura graphs")
    parser.add_argument("--csv", default="retraction_watch.csv")
    parser.add_argument("--profile", choices=["full", "aura"], default="full")
    parser.add_argument("--min-shared-records", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=AURA_NODE_BUDGET)
    parser.add_argument(
        "--max-relationships", type=int, default=AURA_RELATIONSHIP_BUDGET
    )
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--formats", nargs="+", choices=["json", "graphml", "rdf", "png"]
    )
    args = parser.parse_args(argv or [])
    formats = args.formats or (
        ["json"] if args.profile == "aura" else ["json", "graphml", "rdf", "png"]
    )
    destination = Path(
        args.output_dir or ("outputs/aura" if args.profile == "aura" else "outputs")
    )
    generator = KnowledgeGraphGenerator(
        args.csv,
        profile=args.profile,
        min_shared_records=args.min_shared_records,
        max_nodes=args.max_nodes,
        max_relationships=args.max_relationships,
    )
    generator.parse_csv()
    destination.mkdir(parents=True, exist_ok=True)
    exporters = {
        "json": generator.export_to_json,
        "graphml": generator.export_to_graphml,
        "rdf": generator.export_to_rdf,
        "png": generator.visualize,
    }
    with tempfile.TemporaryDirectory(dir=destination, prefix=".build-") as staging:
        for suffix in formats:
            exporters[suffix](Path(staging) / f"knowledge_graph.{suffix}")
        if args.profile == "aura":
            report = generator.quota_report()
            report["source_csv_sha256"] = generator.source_sha256
            json_path = Path(staging) / "knowledge_graph.json"
            if json_path.exists():
                report["json_bytes"] = json_path.stat().st_size
                if report["json_bytes"] > report["storage_limit_bytes"]:
                    raise ValueError(
                        "Serialized graph alone exceeds Aura Free storage limit"
                    )
            (Path(staging) / "aura_report.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            logger.info("Aura quota report: %s", report)
        for path in Path(staging).iterdir():
            os.replace(path, destination / path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
