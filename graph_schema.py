"""Shared graph vocabulary and validation for generated/imported snapshots."""

NODE_TYPES = ("Article", "Author", "Journal", "Institution", "Reason")
EDGE_TYPES = {
    "Authored_By": ("Author", "Article"),
    "Published_In": ("Article", "Journal"),
    "Has_Institution": ("Article", "Institution"),
    "Retracted_For": ("Article", "Reason"),
}
NOTICE_TYPES = {"Retraction", "Correction", "Expression of concern", "Reinstatement"}
REQUIRED_COLUMNS = {
    "Record ID",
    "Title",
    "Subject",
    "Institution",
    "Journal",
    "Publisher",
    "Country",
    "Author",
    "URLS",
    "ArticleType",
    "RetractionDate",
    "RetractionDOI",
    "OriginalPaperDate",
    "OriginalPaperDOI",
    "RetractionNature",
    "Reason",
    "Paywalled",
    "Notes",
}
SCHEMA_VERSION = 2
AURA_SCHEMA_VERSION = 3
AURA_NODE_LIMIT = 200_000
AURA_RELATIONSHIP_LIMIT = 400_000
AURA_NODE_BUDGET = 180_000
AURA_RELATIONSHIP_BUDGET = 360_000
LIST_PROPERTIES = ("author_names", "institution_names", "reason_names")
IDENTITY_NOTE = (
    "Author nodes group exact name strings across records, not verified people. "
    "Matching names may refer to different people; name variants may refer to one person."
)


def check_aura_quota(
    data, max_nodes=AURA_NODE_BUDGET, max_relationships=AURA_RELATIONSHIP_BUDGET
):
    """Count the graph plus one import-state node; storage needs separate measurement."""
    if (
        type(max_nodes) is not int
        or type(max_relationships) is not int
        or not 1 <= max_nodes <= AURA_NODE_LIMIT
        or not 1 <= max_relationships <= AURA_RELATIONSHIP_LIMIT
    ):
        raise ValueError("Budgets must stay within Aura Free hard limits")
    nodes, edges = len(data["nodes"]) + 1, len(data["edges"])
    if nodes > max_nodes or edges > max_relationships:
        raise ValueError(
            f"Aura budget exceeded: {nodes}/{max_nodes} nodes (including import state), "
            f"{edges}/{max_relationships} relationships"
        )
    return {
        "nodes_including_import_state": nodes,
        "relationships": edges,
        "node_budget": max_nodes,
        "relationship_budget": max_relationships,
        "storage_limit_bytes": 1_000_000_000,
        "storage_note": "Serialized size is not Neo4j store size; verify Aura storage after import.",
    }


def validate_snapshot(data):
    """Reject malformed, legacy, or internally inconsistent graphs before writes."""
    if not isinstance(data, dict):
        raise ValueError("Snapshot must be an object")
    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("schema_version") not in (
        SCHEMA_VERSION,
        AURA_SCHEMA_VERSION,
    ):
        raise ValueError("Expected graph schema version 2 or 3; regenerate from CSV")
    compact = metadata["schema_version"] == AURA_SCHEMA_VERSION
    if not compact and metadata.get("profile", "full") != "full":
        raise ValueError("Schema version 2 requires the full profile")
    if compact and (
        metadata.get("profile") != "aura"
        or type(metadata.get("min_shared_records")) is not int
        or metadata["min_shared_records"] < 2
    ):
        raise ValueError("Invalid Aura profile metadata")
    statistics = metadata.get("statistics")
    if not isinstance(statistics, dict) or statistics.get("errors"):
        raise ValueError("Snapshot reports generation errors")
    nodes, edges = data.get("nodes"), data.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise ValueError(
            "Snapshot must contain a nonempty nodes list and an edges list"
        )
    identities = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("properties"), dict):
            raise ValueError("Invalid node")
        props = node["properties"]
        kind = props.get("type")
        if (
            kind not in NODE_TYPES
            or not isinstance(props.get("name"), str)
            or not props["name"].strip()
        ):
            raise ValueError("Invalid node type or name")
        for key, value in props.items():
            is_list = compact and kind == "Article" and key in LIST_PROPERTIES
            if not isinstance(key, str) or (
                not isinstance(value, str)
                and not (
                    is_list
                    and isinstance(value, list)
                    and all(isinstance(item, str) for item in value)
                )
            ):
                raise ValueError(
                    "Node properties must be strings or supported article string lists"
                )
        if compact and kind == "Reason":
            raise ValueError("Aura profile stores reasons as article properties")
        if compact and kind in ("Author", "Institution"):
            basis = (
                "exact_name_string" if kind == "Author" else "exact_institution_string"
            )
            count = props.get("record_count", "")
            if (
                props.get("identity_basis") != basis
                or not count.isascii()
                or not count.isdigit()
                or int(count) < metadata["min_shared_records"]
            ):
                raise ValueError("Invalid shared-name entity")
        if "id" in props:
            raise ValueError("Node properties cannot override the managed id")
        key = props.get("record_id") if kind == "Article" else props["name"]
        if kind == "Article":
            if not key or not key.isascii() or not key.isdigit():
                raise ValueError("Invalid article record_id")
            if props.get("retraction_nature") not in NOTICE_TYPES:
                raise ValueError("Invalid article notice type")
            if compact:
                if props.get("graph_profile") != "aura" or any(
                    not isinstance(props.get(field), list) for field in LIST_PROPERTIES
                ):
                    raise ValueError("Aura articles require complete source lists")
                import json

                try:
                    source = json.loads(props["source_record"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("Missing source record") from exc
                if (
                    not isinstance(source, dict)
                    or REQUIRED_COLUMNS - source.keys()
                    or any(not isinstance(value, str) for value in source.values())
                ):
                    raise ValueError("Invalid source record")
                if (
                    source["Record ID"].strip() != key
                    or source["Title"].strip() != props["name"]
                    or source["RetractionNature"].strip() != props["retraction_nature"]
                ):
                    raise ValueError("Article differs from source record")
                for field, column in zip(
                    LIST_PROPERTIES, ("Author", "Institution", "Reason")
                ):
                    expected_list = [
                        value.strip()
                        for value in source[column].split(";")
                        if value.strip()
                    ]
                    if props[field] != expected_list:
                        raise ValueError("Article lists differ from source record")
        expected = f"{kind}:{key}"
        if node.get("id") != expected or expected in identities:
            raise ValueError("Invalid or duplicate node id")
        identities[expected] = kind
    if "Article" not in identities.values():
        raise ValueError("Snapshot must contain articles")
    seen_edges = set()
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("properties"), dict):
            raise ValueError("Invalid edge")
        props = edge["properties"]
        if any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in props.items()
        ):
            raise ValueError("Edge properties must be strings")
        kind = props.get("type")
        source, target = edge.get("source"), edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError("Invalid edge endpoints")
        if source not in identities or target not in identities:
            raise ValueError("Edge references a missing node")
        if EDGE_TYPES.get(kind) != (identities[source], identities[target]):
            raise ValueError("Invalid relationship type or direction")
        key = (source, target)
        if key in seen_edges:
            raise ValueError("Duplicate edge")
        seen_edges.add(key)
    if compact:
        _validate_projection(data, identities)
    return data


def _validate_projection(data, identities):
    """Verify the compact topology against all preserved per-record name lists."""
    from collections import Counter

    counts = {"Author": Counter(), "Institution": Counter()}
    articles = [
        node for node in data["nodes"] if node["properties"]["type"] == "Article"
    ]
    for node in articles:
        for kind, field in (
            ("Author", "author_names"),
            ("Institution", "institution_names"),
        ):
            counts[kind].update(set(node["properties"][field]))
    threshold = data["metadata"]["min_shared_records"]
    expected_entities = {
        f"{kind}:{name}"
        for kind, values in counts.items()
        for name, count in values.items()
        if count >= threshold
    }
    actual_entities = {
        identity for identity, kind in identities.items() if kind in counts
    }
    if expected_entities != actual_entities:
        raise ValueError("Shared-name nodes do not match distinct record frequencies")
    by_id = {node["id"]: node["properties"] for node in data["nodes"]}
    for identity in actual_entities:
        kind, name = identity.split(":", 1)
        if by_id[identity]["record_count"] != str(counts[kind][name]):
            raise ValueError("Incorrect shared-name record count")
    expected_edges = set()
    journals = set()
    for node in articles:
        identity, props = node["id"], node["properties"]
        import json

        journal = json.loads(props["source_record"])["Journal"].strip()
        if journal:
            journal_id = f"Journal:{journal}"
            journals.add(journal_id)
            expected_edges.add((identity, journal_id, "Published_In"))
        for kind, field, relation in (
            ("Author", "author_names", "Authored_By"),
            ("Institution", "institution_names", "Has_Institution"),
        ):
            for name in set(props[field]):
                other = f"{kind}:{name}"
                if other in expected_entities:
                    expected_edges.add(
                        (other, identity, relation)
                        if kind == "Author"
                        else (identity, other, relation)
                    )
    actual_edges = {
        (edge["source"], edge["target"], edge["properties"]["type"])
        for edge in data["edges"]
    }
    if actual_edges != expected_edges or journals != {
        identity for identity, kind in identities.items() if kind == "Journal"
    }:
        raise ValueError("Compact relationships do not match source records")
