# Knowledge Graph for Retraction Watch Data

This project provides a comprehensive Knowledge Graph solution for the Retraction Watch dataset, including graph generation, storage, visualization, and querying capabilities.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Neo4j Integration](#neo4j-integration)
- [CI/CD Automation](#cicd-automation)
- [Graph Schema](#graph-schema)
- [Example Queries](#example-queries)

## Overview

The Knowledge Graph transforms the Retraction Watch CSV dataset into a rich, interconnected graph structure with:
- **Entities**: Authors, Articles, Journals, Institutions, Reasons
- **Relationships**: Authored_By, Published_In, Affiliated_With, Retracted_For
- **Properties**: Metadata like titles, dates, DOIs, and more

## Features

✅ **Graph Generation**
- Parse CSV data into a structured knowledge graph
- Error checking for missing nodes/edges
- Comprehensive statistics and logging

✅ **Visualization**
- NetworkX-based graph visualization
- Support for large graphs through sampling

✅ **Multiple Export Formats**
- JSON (for programmatic access)
- GraphML (for Gephi visualization)
- RDF (for semantic web applications)

✅ **Neo4j Integration**
- Store graph in Neo4j database
- Efficient batch loading
- Cypher query support

✅ **REST API**
- FastAPI-based query interface
- Search, filter, and aggregate operations
- Works with or without Neo4j

✅ **CI/CD Automation**
- Automatic graph regeneration on data updates
- GitHub Actions workflow
- Artifact storage

## Installation

### Prerequisites
- Python 3.11 or higher
- (Optional) Neo4j 5.x for database storage

### Setup

1. Clone the repository:
```bash
git clone https://github.com/ToruOkadaOi/retraction_watch_data.git
cd retraction_watch_data
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create outputs directory:
```bash
mkdir -p outputs
```

## Usage

### Generate Knowledge Graph

```bash
python knowledge_graph.py
```

This will:
- Parse `retraction_watch.csv`
- Generate the knowledge graph
- Create visualizations and exports in the `outputs/` directory

**Output files:**
- `outputs/knowledge_graph.json` - JSON representation
- `outputs/knowledge_graph.graphml` - GraphML for Gephi
- `outputs/knowledge_graph.rdf` - RDF/XML format
- `outputs/knowledge_graph.png` - Sample visualization

In CI, these full graph outputs are uploaded as workflow artifacts instead of committed to the repository because several files exceed GitHub's normal 100 MB file limit.

### Load into Neo4j (Optional)

If you have Neo4j running:

```bash
# Set environment variables
export NEO4J_URI="neo4j://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"

# Load the graph
python neo4j_integration.py
```

### Start the API Server

```bash
python api.py
```

Or with uvicorn:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Access the API documentation at: http://localhost:8000/docs

If Neo4j is not configured, the API falls back to `outputs/knowledge_graph.json`. That file must be generated locally with `python knowledge_graph.py` or downloaded from a GitHub Actions artifact.

## API Documentation

### Endpoints

#### GET /
Root endpoint with API information

#### GET /api/statistics
Get knowledge graph statistics
```json
{
  "source": "neo4j",
  "nodes": {
    "Article": 68489,
    "Author": 245632,
    "Journal": 8543,
    "Institution": 32145,
    "Reason": 87
  },
  "edges": {
    "Authored_By": 312456,
    "Published_In": 68489,
    "Affiliated_With": 198234,
    "Retracted_For": 89234
  }
}
```

#### GET /api/nodes/{node_type}
Get nodes by type with pagination
- Parameters: `limit` (default: 100), `skip` (default: 0)
- Example: `/api/nodes/Article?limit=10&skip=0`

#### GET /api/search
Search nodes by name or properties
- Parameters: `q` (required), `node_type` (optional), `limit` (default: 50)
- Example: `/api/search?q=cancer&node_type=Article&limit=20`

#### GET /api/articles/{record_id}
Get article details with related entities
- Example: `/api/articles/69157`

#### GET /api/journals/top
Get top journals by retraction count
- Parameters: `limit` (default: 10)
- Example: `/api/journals/top?limit=20`

#### GET /api/reasons/top
Get top retraction reasons
- Parameters: `limit` (default: 10)

#### POST /api/cypher
Execute custom Cypher query (Neo4j only)
```json
{
  "query": "MATCH (a:Article) RETURN a LIMIT 10",
  "parameters": {}
}
```

## Neo4j Integration

### Database Schema

**Node Types:**
- `Article` - Retracted articles with properties: record_id, name (title), subject, dates, DOIs, etc.
- `Author` - Authors with property: name
- `Journal` - Journals with properties: name, publisher
- `Institution` - Institutions with properties: name, country
- `Reason` - Retraction reasons with property: name

**Relationship Types:**
- `Authored_By` - (Author)-[:Authored_By]->(Article)
- `Published_In` - (Article)-[:Published_In]->(Journal)
- `Affiliated_With` - (Author)-[:Affiliated_With]->(Institution)
- `Retracted_For` - (Article)-[:Retracted_For]->(Reason)

### Setup Neo4j

1. Install Neo4j:
```bash
# Using Docker
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:latest
```

2. Access Neo4j Browser: http://localhost:7474

3. Load the knowledge graph:
```bash
export NEO4J_PASSWORD="your-password"
python neo4j_integration.py
```

## CI/CD Automation

The repository includes a GitHub Actions workflow that automatically:
1. Detects changes to `retraction_watch.csv`
2. Regenerates the knowledge graph
3. Uploads generated graph files as workflow artifacts

### Workflow Configuration

File: `.github/workflows/knowledge-graph-update.yml`

**Triggers:**
- Push to main branch (when CSV changes)
- Manual workflow dispatch

The `.github/workflows/sync-gitlab.yml` workflow also generates and uploads graph artifacts after it syncs a changed dataset from GitLab.

**Optional Features** (commented out in workflow):
- Neo4j loading (requires secrets: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
- Slack/Email notifications

### Enable Notifications

To enable notifications, uncomment the notification steps in the workflow and configure:

For Slack:
```yaml
- name: Send Slack notification
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "Knowledge Graph updated successfully!"
      }
```

For Email:
```yaml
- name: Send email
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: smtp.gmail.com
    server_port: 465
    username: ${{ secrets.EMAIL_USERNAME }}
    password: ${{ secrets.EMAIL_PASSWORD }}
    subject: Knowledge Graph Updated
    to: your-email@example.com
    from: GitHub Actions
    body: The Retraction Watch Knowledge Graph has been updated.
```

## Graph Schema

### Entity Properties

**Article**
- `record_id` (unique identifier)
- `name` (title)
- `subject`
- `retraction_date`
- `original_paper_date`
- `retraction_nature`
- `article_type`
- `retraction_doi`
- `original_paper_doi`
- `paywalled`
- `notes`
- `urls`

**Author**
- `name`

**Journal**
- `name`
- `publisher`

**Institution**
- `name`
- `country`

**Reason**
- `name`

### Relationship Properties

**Published_In**
- `date` (publication date)

**Retracted_For**
- `date` (retraction date)

## Example Queries

### Cypher Queries (Neo4j)

1. **Find articles by author:**
```cypher
MATCH (author:Author {name: "John Smith"})-[:Authored_By]->(article:Article)
RETURN article.name, article.retraction_date
LIMIT 10
```

2. **Top journals by retraction count:**
```cypher
MATCH (a:Article)-[:Published_In]->(j:Journal)
RETURN j.name as journal, count(a) as retractions
ORDER BY retractions DESC
LIMIT 10
```

3. **Most common retraction reasons:**
```cypher
MATCH (a:Article)-[:Retracted_For]->(r:Reason)
RETURN r.name as reason, count(a) as count
ORDER BY count DESC
```

4. **Articles with multiple authors from same institution:**
```cypher
MATCH (author:Author)-[:Affiliated_With]->(inst:Institution)
WITH inst, collect(author) as authors
WHERE size(authors) > 5
MATCH (author)-[:Authored_By]->(article:Article)
WHERE author IN authors
RETURN inst.name, article.name, collect(author.name) as authors
LIMIT 10
```

5. **Retraction timeline by year:**
```cypher
MATCH (a:Article)
WHERE a.retraction_date IS NOT NULL
WITH split(a.retraction_date, '/')[2] as year
RETURN year, count(*) as retractions
ORDER BY year DESC
```

### API Queries (REST)

1. **Search for cancer-related articles:**
```bash
curl "http://localhost:8000/api/search?q=cancer&node_type=Article&limit=10"
```

2. **Get top journals:**
```bash
curl "http://localhost:8000/api/journals/top?limit=20"
```

3. **Get article details:**
```bash
curl "http://localhost:8000/api/articles/69157"
```

4. **Execute custom Cypher:**
```bash
curl -X POST "http://localhost:8000/api/cypher" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (a:Article) WHERE a.subject CONTAINS \"Biology\" RETURN a.name LIMIT 5"
  }'
```

### Python Queries

```python
import json

# Load JSON graph
with open('outputs/knowledge_graph.json', 'r') as f:
    data = json.load(f)

# Get all articles
articles = [n for n in data['nodes'] 
           if n['properties']['type'] == 'Article']

# Get all edges of type "Retracted_For"
retraction_edges = [e for e in data['edges']
                   if e['properties']['type'] == 'Retracted_For']

print(f"Total articles: {len(articles)}")
print(f"Total retraction reasons: {len(retraction_edges)}")
```

## Visualization with Gephi

1. Open Gephi
2. File → Open → Select `outputs/knowledge_graph.graphml`
3. Choose "Directed Graph" when prompted
4. Apply layouts:
   - Force Atlas 2 for large graphs
   - Fruchterman Reingold for smaller graphs
5. Color nodes by type
6. Size nodes by degree (connections)
7. Export visualization

## Error Handling

The knowledge graph generator includes comprehensive error checking:
- **Missing nodes**: Warns when edges reference non-existent nodes
- **Empty fields**: Handles missing data gracefully
- **Malformed data**: Logs errors with row numbers for debugging
- **Statistics**: Tracks all errors in `stats['errors']` list

View errors in the console output or check the JSON export's metadata section.

## Performance Considerations

- **Large datasets**: The full Retraction Watch dataset has ~68K articles
- **Memory usage**: Graph generation requires ~1-2GB RAM
- **Neo4j loading**: Takes 10-30 minutes depending on hardware
- **Visualization**: Only samples 100 nodes by default to avoid rendering issues
- **Artifact size**: Full JSON, GraphML, and RDF outputs are each several hundred MB, so CI stores them as workflow artifacts instead of git-tracked files

To adjust sampling for visualization:
```python
generator.visualize("output.png", sample_size=500)
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

This project uses data from Retraction Watch, which is made available by Crossref. Please refer to the Retraction Watch database license and terms of use.

## Support

For issues or questions:
1. Check the [GitHub Issues](https://github.com/ToruOkadaOi/retraction_watch_data/issues)
2. Review the API documentation at `/docs` when running the server
3. Consult the Neo4j documentation for database-specific queries

## Acknowledgments

- Retraction Watch and Crossref for providing the dataset
- NetworkX for graph processing capabilities
- Neo4j for graph database functionality
- FastAPI for the REST API framework
