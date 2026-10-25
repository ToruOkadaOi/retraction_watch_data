# Security and data integrity

The REST API exposes fixed read queries only. `/api/cypher` has been removed.
Node type parameters are restricted to Article, Author, Journal, Institution,
and Reason before any database access. Values are passed as query parameters.
API queries run with read routing and only select loader-owned `RWGraph` nodes.
Read routing is not an authorization boundary. Where the Neo4j tier supports
read-only accounts, deploy the API with a separate account granted read access
only and use loader credentials only for imports. AuraDB Free does not include
role-based access control; keep its credentials server-side and expose only the
fixed API queries.

## Imports

`NEO4J_PASSWORD` is required; there is no fallback password. The loader validates
the complete versioned JSON snapshot before database writes. It rejects
unknown labels and relationship types, duplicate IDs/edges, missing endpoints,
invalid relationship directions, and reported generation errors.

Full-profile replacement is one transaction, including deletion and all insertion batches.
Failures roll back to the previous graph and return a nonzero CLI exit status.
Only nodes marked `RWGraph` are replaced; unmarked data is preserved. Relationships
touching replaced nodes are removed with those nodes. Reserve this label for this
loader and use a dedicated database for unrelated applications.

Imports can require substantial transaction memory for a full snapshot. A memory
or constraint failure aborts replacement rather than publishing a partial graph.

## Source validation

CSV input is decoded strictly as UTF-8 with optional BOM. Required headers,
duplicate headers, row widths, IDs, duplicate IDs, titles, notice vocabulary, and
nonempty input are validated. A failed parse blocks exports. The CLI builds all
exports in a staging directory before replacing published files. Each file rename
is atomic; consumers needing consistency across multiple formats should read a
completed build after the generator exits successfully.

Article institutions are recorded without inferring individual author affiliations.
Country lists stay on the article. Nodes keyed by author name can still represent
multiple people with the same name; the CSV does not supply person identifiers.
Rankings count only `Retraction` notices, not corrections, expressions of concern,
or reinstatements. Historical notices do not establish a paper's current status.

## Deployment

Serve the API behind HTTPS and apply request/concurrency limits appropriate to
your hosting environment. The API provides public dataset access without user
authentication. Keep credentials out of source control and configure Neo4j TLS
for remote connections. Dependency versions are minimum requirements, not a
locked or vulnerability-certified environment; maintain dependency updates and
security scanning separately.

## Verification

Regression tests cover rejected injection inputs, removal of arbitrary Cypher,
Unicode/BOM parsing, invalid data, notice-specific rankings, statistics, and sync
change detection. The optional disposable Neo4j integration test verifies real
query execution, repeat imports, rollback, and preservation of unowned nodes.
Run `python -m pytest -q`; see [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) for setup.

## Compact Aura import boundary

Schema version 3 validates complete source lists and recomputes expected shared
entities and relationships. Default quota budgets leave count headroom, include
the maintenance marker, and account for unowned database objects. Serialized
artifact size does not certify actual Aura storage usage.

The Aura profile uses bounded commits rather than an atomic replacement because
its free tier cannot accommodate two complete graph copies. It explicitly enters
maintenance: API data endpoints/readiness return 503 while loading or failed.
Generation checks reject queries crossing refreshes. Failures require rerunning
the import; after a process crash, the five-minute lease must expire first.
Unowned nodes survive, although relationships touching managed nodes are removed.
The `RWImportState` label and `RWGraph` label are reserved for the loader.

Direct database clients must respect the maintenance marker. A cooperating-importer
lease prevents concurrent imports; it cannot prevent an administrator or another
application from writing directly. Reserve a dedicated Aura instance. GitHub
imports are manual and use separate `AURA_NEO4J_*` secrets. No account credentials
are required to build or test compact snapshots.
