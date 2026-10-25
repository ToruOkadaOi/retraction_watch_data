# Retraction Watch knowledge graph

Generate a NetworkX graph from the public CSV, export JSON/GraphML/RDF, optionally
load Neo4j, and query it through a fixed read-only REST API. Articles represent
notice records, including retractions, corrections, expressions of concern, and
reinstatements.

## Setup and generation

Requires Python 3.11 or later. Neo4j 5.x is optional.

```bash
pip install -r requirements.txt
python knowledge_graph.py
```

The generator reads `retraction_watch.csv` in the current directory and writes
`outputs/knowledge_graph.{json,graphml,rdf,png}`. It accepts UTF-8 with or without
a BOM. Missing required columns, malformed row widths, duplicate headers or record
IDs, empty titles, unknown notice types, invalid encoding, and empty input fail
the build. No incomplete graph is exported. All formats finish in a staging
directory before publication; each file is replaced by an atomic rename.

The full graph needs substantial memory and disk space. Visualizations sample
100 nodes by default. Full outputs are uploaded as CI artifacts rather than
committed to Git. Existing sample outputs are illustrative and may use an older
schema; regenerate before using them for analysis.

## Graph schema, version 2

Node types are `Article`, `Author`, `Journal`, `Institution`, and `Reason`.
Article IDs are `Article:<Record ID>`. Other IDs use their type and exact trimmed
name. Authors with matching names are not verified to be the same person.

| Relationship | Direction | Meaning |
| --- | --- | --- |
| `Authored_By` | Author → Article | Author listed for the notice record |
| `Published_In` | Article → Journal | Source journal |
| `Has_Institution` | Article → Institution | Institution listed for the article |
| `Retracted_For` | Article → Reason | Listed notice reason; retained name for compatibility |

The source does not map individual authors to institutions. Version 2 removes
`Affiliated_With` and replaces it with `Has_Institution`; the statistics key is
`has_institution`. Article `countries` retains the source country list without
assigning every country to each institution. Statistics count actual unique graph
nodes and edges. `Article` counts include every notice type; retraction rankings
filter `retraction_nature = 'Retraction'`.

JSON metadata contains `schema_version: 2`, a generation timestamp, and graph
statistics. JSON includes node and relationship properties. RDF resource IDs are
percent-encoded. RDF exports node properties and relationships; relationship date
properties remain available in JSON and GraphML.

## Neo4j import

```bash
export NEO4J_URI="neo4j://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-loader-password"
python neo4j_integration.py
```

The password is mandatory. Every node is labeled `RWGraph` and its entity type,
and stores the stable exported `id`. The loader validates the complete snapshot
before writing and replaces only `RWGraph` nodes in one transaction. Repeat loads
replace the prior snapshot without duplicates. Errors preserve the prior graph
and make the CLI exit nonzero. Unmarked nodes are preserved; relationships touching
replaced nodes are deleted with those nodes. Reserve `RWGraph` for this loader.

Use a dedicated database with enough transaction memory for the full replacement.
Legacy unmarked imports are deliberately not deleted or adopted. For migration,
start with a fresh dedicated database; old global uniqueness constraints may
conflict with a new import. Back up and handle any legacy database separately.

## REST API

```bash
# Use a separate Neo4j account with read-only grants for the API.
export NEO4J_USER="your-readonly-user"
export NEO4J_PASSWORD="your-readonly-password"
uvicorn api:app --host 127.0.0.1 --port 8000
```

Without a working Neo4j connection, queries use the validated schema version 2
file `outputs/knowledge_graph.json`. Generate it locally or download a CI artifact.
Neo4j queries only read nodes imported by the current loader.

| Endpoint | Parameters / result |
| --- | --- |
| `GET /` | API version and endpoints |
| `GET /api/statistics` | Actual node/edge counts, totals, and source |
| `GET /api/nodes/{node_type}` | `limit` 1–1000, `skip` ≥0; stable ID order |
| `GET /api/search` | `q` 1–500 characters, optional `node_type`, `limit` 1–500 |
| `GET /api/articles/{record_id}` | Article, authors, journal, reasons, institutions |
| `GET /api/journals/top` | Retraction notice counts; `limit` 1–100 |
| `GET /api/reasons/top` | Retraction notice counts; `limit` 1–100 |

Node types must exactly match the five schema types; invalid values return 422.
Node responses include `id`, `type`, and `properties` on both backends. Pagination
returns `nodes`, `count`, `skip`, and `limit`. Search is case-insensitive. Data
unavailability returns 503; missing articles return 404. Interactive docs: `/docs`.

**API version 2 migration:** `/api/cypher` is removed and returns 404. Run custom
queries through a separately authorized Neo4j client. Rebuild schema version 1
exports before serving or loading them. Consumers of `Affiliated_With`,
`affiliated_with`, or institution `country` must migrate to the article-based
schema above. Neo4j node responses now use exported IDs rather than element IDs.

```bash
curl "http://localhost:8000/api/search?q=cancer&node_type=Article&limit=10"
curl "http://localhost:8000/api/journals/top?limit=20"
curl "http://localhost:8000/api/articles/69157"
```

Example query in an authorized Neo4j client:

```cypher
MATCH (a:RWGraph:Article)-[:Published_In]->(j:RWGraph:Journal)
WHERE a.retraction_nature = 'Retraction'
RETURN j.name AS journal, count(DISTINCT a) AS retraction_count
ORDER BY retraction_count DESC, journal
LIMIT 10
```

Historical notice counts do not resolve a publication's current status. Reinstated
papers can also have earlier retraction records.

## Tests and automation

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use temporary output directories and do not overwrite tracked sample graphs.
`python test_setup.py` runs pytest; `python test_sample.py` verifies a real CSV sample
and all export formats in a temporary directory.

To include the integration test, point these variables only at a **disposable**
Neo4j instance. The test replaces its managed graph and creates a test sentinel.

```bash
export TEST_NEO4J_URI="bolt://localhost:17687"
export TEST_NEO4J_PASSWORD="your-disposable-instance-password"
python -m pytest -q
```

Code CI runs regression tests with a disposable Neo4j service. CSV update workflows
run non-integration tests before generation and upload artifacts only after
successful generation. GitLab sync compares both staged CSV changes and README
changes against HEAD, then commits/pushes only when either changed.

See [SECURITY.md](SECURITY.md) for security boundaries and deployment guidance.
