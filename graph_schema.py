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


def validate_snapshot(data):
    """Reject malformed, legacy, or internally inconsistent graphs before writes."""
    if not isinstance(data, dict):
        raise ValueError("Snapshot must be an object")
    metadata = data.get("metadata")
    if (
        not isinstance(metadata, dict)
        or metadata.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("Expected graph schema version 2; regenerate from CSV")
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
        if any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in props.items()
        ):
            raise ValueError("Node properties must be strings")
        if "id" in props:
            raise ValueError("Node properties cannot override the managed id")
        key = props.get("record_id") if kind == "Article" else props["name"]
        if kind == "Article":
            if not key or not key.isascii() or not key.isdigit():
                raise ValueError("Invalid article record_id")
            if props.get("retraction_nature") not in NOTICE_TYPES:
                raise ValueError("Invalid article notice type")
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
    return data
