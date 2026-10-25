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

Full-profile JSON metadata contains `schema_version: 2`, a generation timestamp, and graph
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
before writing. Full-profile imports replace only `RWGraph` nodes in one transaction. Repeat loads
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

Without a working Neo4j connection, queries use the validated schema version 2 or 3
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

## Compact AuraDB Free profile

The `aura` profile retains every notice record and journal. Author and institution
nodes are created only for exact trimmed names appearing in at least two distinct
records. Duplicate mentions within one record do not count toward that threshold.
Reasons and singleton names remain article properties. Rebuilds promote newly
shared names and demote names no longer shared.

```bash
python knowledge_graph.py --profile aura
# To reduce graph size further while preserving all article records:
python knowledge_graph.py --profile aura --min-shared-records 3
```

The default compact build writes JSON only, separately under `outputs/aura/`:

- `knowledge_graph.json`: schema version 3, profile `aura`.
- `aura_report.json`: exact counts, source CSV SHA-256, serialized size and budgets.

The full profile remains the default for `python knowledge_graph.py`. To export
additional compact formats use `--formats json graphml rdf png`. GraphML encodes
list properties as JSON strings; RDF emits repeated literals. The source record
preserves list order, duplicates, and every original column value in all formats.

Each compact article has `author_names`, `institution_names`, and `reason_names`
string arrays, plus a `source_record` JSON string containing every CSV column,
including PubMed IDs and any additional fields. Connected Author nodes carry
`identity_basis: exact_name_string` and a distinct `record_count`; this is a name
match, not a verified person. Institution names are likewise exact-string groups.

The complete source lists preserve information, but do not create graph paths.
For example, common reasons stored on two articles do not connect those articles
through a Reason node. Singletons can still be found through article properties.

Default budgets are **180,000 total nodes** and **360,000 relationships**, below
Aura Free's hard limits of 200,000/400,000. One import-state node is included in
the budget, and import preflight also counts unowned database objects. Override
with `--max-nodes` and `--max-relationships`, up to the hard limits. A budget
failure aborts generation/import; no articles are silently dropped. The serialized
file is also checked against 1 GB, but its size is not the Neo4j database size.
Verify actual storage in Aura after importing; properties, indexes, and internal
storage add overhead. See [Aura quotas](https://neo4j.com/docs/aura/quotas-and-limits/).

### Import and refresh on Aura

Use a dedicated Aura instance and its encrypted `neo4j+s://...` connection URI:

```bash
export NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-instance-password"
python neo4j_integration.py --json outputs/aura/knowledge_graph.json --mode aura
```

Compact snapshots automatically select bounded Aura mode even without `--mode`.
The loader validates the source lists and the entire expected compact topology
before writes. Imports use independently committed batches (default 500 objects,
configurable with `--batch-size`, maximum 1000). This bounds transaction memory and
avoids storing two copies of the graph inside the free-tier quotas.

**Refreshes require maintenance time.** Once import begins, the API's data
endpoints and `/ready` return 503. The old managed graph is removed in batches,
the new graph is inserted, counts are checked, and readiness is restored only at
completion. This mode does not preserve the old graph on failure: it leaves a
failed/loading marker and the API stays unavailable. Rerun the same import to
clear partial data and rebuild. Failed imports can be retried immediately; after
an abrupt process crash, wait for the five-minute lease to expire. An active
import lease prevents a second cooperating importer from starting. Do not write
to this managed graph outside the loader.

Full-profile imports retain their previous single-transaction replacement mode.
The API checks the import generation before and after each Neo4j query and rejects
responses that crossed a refresh. It does not fall back to potentially stale JSON
when the database explicitly reports an incomplete refresh. Direct Neo4j clients
must also honor the `RWImportState` status or avoid querying during refreshes.

### Serve the compact graph

The API works with either Neo4j or a compact JSON artifact:

```bash
# JSON only:
GRAPH_JSON_PATH=outputs/aura/knowledge_graph.json python api.py
# Aura only: configure NEO4J_* above and disable loading a JSON fallback on the VPS.
GRAPH_JSON_PATH='' python api.py
```

The article response retains `authors`, `institutions`, and `reasons` as connected
nodes. Compact responses additionally expose complete `listed_authors`,
`listed_institutions`, and `listed_reasons` lists, `graph_profile: aura`,
`connected_entities: shared_names_only`, and an identity caveat. An empty Reason
node list does not mean the record has no reasons; inspect `listed_reasons`.
Retraction reason rankings use the complete property lists, counting a reason
once per retraction notice and excluding other notice types.

Search within properties using `/api/search?q=...&node_type=Article`. To retrieve
records for an exact name, including names without nodes:

```bash
curl --get http://localhost:8000/api/name-records \
  --data-urlencode 'kind=Author' --data-urlencode 'name=Alice Smith'
```

`kind` accepts `Author`, `Institution`, or `Reason`; `limit` is 1–500 and `skip`
is nonnegative. Matching is exact and case-sensitive, as with node identity.
Responses describe source-name matches, not disambiguated people. Both full and
compact graphs support this endpoint. `/ready` is the readiness probe.

### Build off-server and deploy

Dataset workflows produce a separate `aura-compact-graph` artifact containing the
JSON snapshot and quota report. The VPS need only run the API and query Aura.

For an import entirely from GitHub Actions, configure repository secrets
`AURA_NEO4J_URI`, `AURA_NEO4J_USER`, and `AURA_NEO4J_PASSWORD`, then manually run
**Deploy compact graph to Aura**. It builds main, runs regression checks, uploads
the compact artifact, and imports it with bounded transactions. Concurrent runs
are serialized. This deployment workflow is manual; ordinary builds do not write
to an Aura account. Schedule a maintenance window for each refresh.


## Public research dashboard

The buildless frontend in `dashboard/` is published to GitHub Pages after **Code CI** passes on main. The **Publish research dashboard** workflow can also be run manually on main. Enable GitHub Pages with **GitHub Actions** as its source. FastAPI serves the same files at `/dashboard/` for a same-origin alternative.

GitHub Pages calls the public Render API; database credentials remain on the API host. The API allows GET requests from `https://toruokadaoi.github.io` and the localhost preview on port 8765. Set `CORS_ORIGINS` to a comma-separated list of exact origins when moving the frontend to another host. CORS is a browser policy, not authentication; the service remains public and read-only.

The dashboard uses these bounded routes:

| Route | Purpose and bounds |
| --- | --- |
| `/api/dashboard/overview` | Whole-snapshot notice counts and top ten journals/reasons for retraction notices; cached for 60 seconds with import readiness checks. |
| `/api/dashboard/records` | Title, DOI, record ID, author/institution name search; optional exact journal/reason and notice filters. `limit` 1–50, `skip` 0–1,000,000. |
| `/api/dashboard/entities` | Name search for `Author`, `Institution`, or `Journal`; `limit` 1–50. |
| `/api/dashboard/neighborhood` | One-hop neighbors for a stable `node_id`; `limit` 1–100, `skip` 0–1,000,000. Notice/journal/reason filters constrain article neighbors. |

The frontend requests 30 neighbors at a time and limits the visible graph to 150 nodes and 300 edges. Search and graph responses omit large narrative/source fields; selecting an article retrieves its complete detail separately. Export includes only the visible graph, its active filters, and snapshot provenance. Overview counts describe the whole hosted snapshot, while explorer filters apply to the records and article neighbors. Journal counts do not measure retraction rates, publication volume, or research quality.

Shared name strings are not resolved people or verified affiliations. The compact profile retains singleton names and reasons in article properties; the dashboard shows those complete lists without inventing graph edges. Hosted refreshes are independent of CSV updates. New imports record their completion time; existing snapshots may have no recorded import time. Snapshot generation checks prevent combining responses across an import.

For a disposable local preview, install Python requirements and run `python scripts/preview_dashboard.py`, then open `http://localhost:8765/dashboard/`. This builds a temporary 200-record sample from the real CSV and does not connect to Aura or replace exports. Node 20 or later is needed only for frontend checks: `npm install`, `npm test`, and, with the preview running, `npm run test:dom`. CI also checks the actual queries against Neo4j. DOM tests exercise interactions with a headless graph model; they do not verify browser rendering.
