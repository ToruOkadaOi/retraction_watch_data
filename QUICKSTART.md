# Quick start

Use Python 3.11 or later from the repository directory.

```bash
pip install -r requirements.txt
python knowledge_graph.py
python api.py
```

Open http://localhost:8000/docs. Without Neo4j, the API uses the generated
`outputs/knowledge_graph.json` file. Generation validates UTF-8 CSV input before
publishing JSON, GraphML, RDF, and a sample PNG.

For optional Neo4j loading:

```bash
export NEO4J_URI="neo4j://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-loader-password"
python neo4j_integration.py
```

The loader validates schema version 2 input and atomically replaces its own
`RWGraph` nodes. Use a fresh dedicated database when migrating legacy imports.
Run the API with separate read-only credentials. The API exposes fixed queries;
`/api/cypher` has been removed.

```bash
curl "http://localhost:8000/api/search?q=cancer&node_type=Article&limit=10"
curl "http://localhost:8000/api/journals/top?limit=20"
```

Rankings count only retraction notices. Article nodes also include corrections,
expressions of concern, and reinstatements. Article-to-institution relationships
are `Has_Institution`; individual author affiliations are not inferred.

Run regression tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests leave tracked sample outputs unchanged. See
[KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) for schema migration, database integration
tests, API contracts, and CI behavior, and [SECURITY.md](SECURITY.md) for deployment.
