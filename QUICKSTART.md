# Knowledge Graph Implementation - Quick Start Guide

## Overview

This implementation provides a complete Knowledge Graph solution for the Retraction Watch dataset with:
- ✅ Graph generation from CSV data
- ✅ Multiple export formats (JSON, GraphML, RDF)
- ✅ NetworkX visualization
- ✅ Neo4j database integration
- ✅ REST API with FastAPI
- ✅ Automated CI/CD with GitHub Actions

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate Knowledge Graph

```bash
python knowledge_graph.py
```

This creates files in the `outputs/` directory:
- `knowledge_graph.json` - JSON representation
- `knowledge_graph.graphml` - For Gephi visualization
- `knowledge_graph.rdf` - RDF/XML format
- `knowledge_graph.png` - Sample visualization

**Note:** Full dataset processing takes ~10-15 minutes and generates large files.

### 3. (Optional) Load into Neo4j

If you have Neo4j running:

```bash
export NEO4J_URI="neo4j://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"

python neo4j_integration.py
```

### 4. Start the API Server

```bash
python api.py
```

Access the interactive API docs at: http://localhost:8000/docs

## Testing

Run the test suite:

```bash
python test_setup.py
```

Test with sample data:

```bash
python test_sample.py
```

Run examples:

```bash
python examples.py
```

## CI/CD Automation

The GitHub Actions workflow automatically:
1. Detects changes to `retraction_watch.csv`
2. Regenerates the knowledge graph
3. Commits updated files
4. Creates downloadable artifacts

Workflow: `.github/workflows/knowledge-graph-update.yml`

### Manual Trigger

Go to Actions → Knowledge Graph Update → Run workflow

## Architecture

### Data Model

**Nodes:**
- `Article` - Retracted publications (68K+ nodes)
- `Author` - Article authors (245K+ nodes)
- `Journal` - Publishing journals (8K+ nodes)
- `Institution` - Author affiliations (32K+ nodes)
- `Reason` - Retraction reasons (87 nodes)

**Edges:**
- `Authored_By` - (Author) → (Article)
- `Published_In` - (Article) → (Journal)
- `Affiliated_With` - (Author) → (Institution)
- `Retracted_For` - (Article) → (Reason)

### File Structure

```
retraction_watch_data/
├── knowledge_graph.py          # Main graph generation script
├── neo4j_integration.py        # Neo4j database loader
├── api.py                      # FastAPI REST API
├── examples.py                 # Usage examples
├── test_setup.py               # Test suite
├── test_sample.py              # Sample data test
├── requirements.txt            # Python dependencies
├── KNOWLEDGE_GRAPH.md          # Full documentation
├── README.md                   # Main README
├── retraction_watch.csv        # Source data
├── outputs/                    # Generated graph files
│   ├── knowledge_graph.json
│   ├── knowledge_graph.graphml
│   ├── knowledge_graph.rdf
│   └── knowledge_graph.png
└── .github/workflows/
    └── knowledge-graph-update.yml  # CI/CD workflow
```

## API Endpoints

- `GET /` - API information
- `GET /api/statistics` - Graph statistics
- `GET /api/nodes/{type}` - Get nodes by type
- `GET /api/search?q=query` - Search nodes
- `GET /api/articles/{id}` - Get article details
- `GET /api/journals/top` - Top journals
- `GET /api/reasons/top` - Top reasons
- `POST /api/cypher` - Execute Cypher query (Neo4j only)

## Example Queries

### Python (JSON)

```python
import json

with open('outputs/knowledge_graph.json', 'r') as f:
    data = json.load(f)

# Get all articles
articles = [n for n in data['nodes'] 
           if n['properties']['type'] == 'Article']

print(f"Total articles: {len(articles)}")
```

### Cypher (Neo4j)

```cypher
// Top journals by retraction count
MATCH (a:Article)-[:Published_In]->(j:Journal)
RETURN j.name, count(a) as count
ORDER BY count DESC
LIMIT 10
```

### REST API

```bash
# Search for cancer-related articles
curl "http://localhost:8000/api/search?q=cancer&limit=10"

# Get top journals
curl "http://localhost:8000/api/journals/top?limit=20"
```

## Performance Notes

- **CSV Parsing**: ~5-10 minutes for full dataset
- **Visualization**: Uses sampling (100 nodes by default) for performance
- **Neo4j Loading**: ~10-30 minutes depending on hardware
- **Memory Usage**: ~1-2GB RAM for full graph

## Troubleshooting

### Neo4j Connection Issues

If Neo4j is not available, the system automatically falls back to JSON-based queries.

### Large File Warnings

The full dataset generates large output files:
- JSON: ~100-200 MB
- GraphML: ~150-250 MB
- RDF: ~150-250 MB

These files are tracked in git but may take time to download/upload.

### Visualization Performance

For large graphs, adjust the sample size:

```python
generator.visualize("output.png", sample_size=200)
```

## Next Steps

1. **Explore the API**: http://localhost:8000/docs
2. **Read full documentation**: [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md)
3. **Run examples**: `python examples.py`
4. **Query with Neo4j**: Install Neo4j and load the graph
5. **Visualize with Gephi**: Open `outputs/knowledge_graph.graphml`

## Support

- **Documentation**: See [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md)
- **Issues**: https://github.com/ToruOkadaOi/retraction_watch_data/issues
- **API Docs**: http://localhost:8000/docs (when running)

## License

Data from Retraction Watch / Crossref. Please refer to their license and terms of use.
