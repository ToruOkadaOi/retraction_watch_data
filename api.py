"""
FastAPI Application for Knowledge Graph Queries

Provides REST API endpoints for querying the Retraction Watch Knowledge Graph.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json
import logging
import os
from neo4j import GraphDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Retraction Watch Knowledge Graph API",
    description="API for querying the Retraction Watch Knowledge Graph",
    version="1.0.0"
)

# Neo4j connection (optional, fallback to JSON)
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', '')

neo4j_driver = None
if NEO4J_PASSWORD:
    try:
        neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        neo4j_driver.verify_connectivity()
        logger.info("Connected to Neo4j database")
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j: {e}")
        logger.info("Falling back to JSON-based queries")

# Load JSON data as fallback
json_data = None
try:
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    logger.info("Loaded JSON knowledge graph data")
except FileNotFoundError:
    logger.warning("JSON knowledge graph file not found")


# Pydantic models
class NodeResponse(BaseModel):
    id: str
    type: str
    properties: Dict[str, Any]


class EdgeResponse(BaseModel):
    source: str
    target: str
    type: str
    properties: Dict[str, Any]


class GraphResponse(BaseModel):
    nodes: List[NodeResponse]
    edges: List[EdgeResponse]


class CypherQuery(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = {}


class QueryResult(BaseModel):
    records: List[Dict[str, Any]]
    count: int


# Helper functions
def query_neo4j(cypher: str, parameters: Dict = None) -> List[Dict]:
    """Execute Cypher query on Neo4j"""
    if not neo4j_driver:
        raise HTTPException(status_code=503, detail="Neo4j database not available")
    
    if parameters is None:
        parameters = {}
    
    with neo4j_driver.session() as session:
        result = session.run(cypher, parameters)
        records = [dict(record) for record in result]
        return records


def query_json(node_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Query JSON data"""
    if not json_data:
        raise HTTPException(status_code=503, detail="Knowledge graph data not available")
    
    nodes = json_data.get('nodes', [])
    
    if node_type:
        nodes = [n for n in nodes if n.get('properties', {}).get('type') == node_type]
    
    return nodes[:limit]


# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Retraction Watch Knowledge Graph API",
        "version": "1.0.0",
        "status": "online",
        "neo4j_connected": neo4j_driver is not None,
        "endpoints": {
            "docs": "/docs",
            "statistics": "/api/statistics",
            "nodes": "/api/nodes",
            "search": "/api/search",
            "cypher": "/api/cypher"
        }
    }


@app.get("/api/statistics")
async def get_statistics():
    """Get knowledge graph statistics"""
    if neo4j_driver:
        try:
            with neo4j_driver.session() as session:
                # Count nodes
                node_result = session.run("""
                    MATCH (n)
                    RETURN labels(n)[0] as type, count(n) as count
                """)
                nodes = {record['type']: record['count'] for record in node_result}
                
                # Count edges
                edge_result = session.run("""
                    MATCH ()-[r]->()
                    RETURN type(r) as type, count(r) as count
                """)
                edges = {record['type']: record['count'] for record in edge_result}
                
                return {
                    "source": "neo4j",
                    "nodes": nodes,
                    "edges": edges,
                    "total_nodes": sum(nodes.values()),
                    "total_edges": sum(edges.values())
                }
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
    
    # Fallback to JSON
    if json_data:
        metadata = json_data.get('metadata', {})
        stats = metadata.get('statistics', {})
        
        return {
            "source": "json",
            "nodes": {
                "Article": stats.get('articles', 0),
                "Author": stats.get('authors', 0),
                "Journal": stats.get('journals', 0),
                "Institution": stats.get('institutions', 0),
                "Reason": stats.get('reasons', 0)
            },
            "edges": {
                "Authored_By": stats.get('authored_by', 0),
                "Published_In": stats.get('published_in', 0),
                "Affiliated_With": stats.get('affiliated_with', 0),
                "Retracted_For": stats.get('retracted_for', 0)
            }
        }
    
    raise HTTPException(status_code=503, detail="No data source available")


@app.get("/api/nodes/{node_type}")
async def get_nodes_by_type(
    node_type: str,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0)
):
    """Get nodes by type with pagination"""
    if neo4j_driver:
        try:
            cypher = f"""
            MATCH (n:{node_type})
            RETURN n
            SKIP $skip
            LIMIT $limit
            """
            
            with neo4j_driver.session() as session:
                result = session.run(cypher, skip=skip, limit=limit)
                nodes = []
                for record in result:
                    node = record['n']
                    nodes.append({
                        'id': node.element_id,
                        'type': node_type,
                        'properties': dict(node)
                    })
                
                return {
                    "nodes": nodes,
                    "count": len(nodes),
                    "skip": skip,
                    "limit": limit
                }
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
    
    # Fallback to JSON
    if json_data:
        nodes = [n for n in json_data.get('nodes', [])
                if n.get('properties', {}).get('type') == node_type]
        
        paginated = nodes[skip:skip + limit]
        
        return {
            "nodes": paginated,
            "count": len(paginated),
            "total": len(nodes),
            "skip": skip,
            "limit": limit
        }
    
    raise HTTPException(status_code=503, detail="No data source available")


@app.get("/api/search")
async def search_nodes(
    q: str = Query(..., min_length=1),
    node_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500)
):
    """Search nodes by name or properties"""
    if neo4j_driver:
        try:
            type_filter = f":{node_type}" if node_type else ""
            cypher = f"""
            MATCH (n{type_filter})
            WHERE n.name CONTAINS $query OR n.title CONTAINS $query
            RETURN n
            LIMIT $limit
            """
            
            with neo4j_driver.session() as session:
                result = session.run(cypher, query=q, limit=limit)
                nodes = []
                for record in result:
                    node = record['n']
                    node_labels = list(node.labels)
                    nodes.append({
                        'id': node.element_id,
                        'type': node_labels[0] if node_labels else 'Unknown',
                        'properties': dict(node)
                    })
                
                return {
                    "query": q,
                    "nodes": nodes,
                    "count": len(nodes)
                }
        except Exception as e:
            logger.error(f"Error searching Neo4j: {e}")
    
    # Fallback to JSON
    if json_data:
        q_lower = q.lower()
        nodes = []
        
        for node in json_data.get('nodes', []):
            props = node.get('properties', {})
            
            # Check node type filter
            if node_type and props.get('type') != node_type:
                continue
            
            # Search in properties
            match = False
            for value in props.values():
                if isinstance(value, str) and q_lower in value.lower():
                    match = True
                    break
            
            if match:
                nodes.append(node)
            
            if len(nodes) >= limit:
                break
        
        return {
            "query": q,
            "nodes": nodes,
            "count": len(nodes)
        }
    
    raise HTTPException(status_code=503, detail="No data source available")


@app.post("/api/cypher")
async def execute_cypher(query: CypherQuery):
    """Execute custom Cypher query (Neo4j only)"""
    if not neo4j_driver:
        raise HTTPException(
            status_code=503,
            detail="Neo4j database not available. This endpoint requires Neo4j connection."
        )
    
    try:
        records = query_neo4j(query.query, query.parameters)
        
        return {
            "query": query.query,
            "records": records,
            "count": len(records)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query execution failed: {str(e)}")


@app.get("/api/articles/{record_id}")
async def get_article(record_id: str):
    """Get article details with related entities"""
    if neo4j_driver:
        try:
            cypher = """
            MATCH (a:Article {record_id: $record_id})
            OPTIONAL MATCH (author:Author)-[:Authored_By]->(a)
            OPTIONAL MATCH (a)-[:Published_In]->(j:Journal)
            OPTIONAL MATCH (a)-[:Retracted_For]->(r:Reason)
            RETURN a, collect(DISTINCT author) as authors, j, collect(DISTINCT r) as reasons
            """
            
            with neo4j_driver.session() as session:
                result = session.run(cypher, record_id=record_id)
                record = result.single()
                
                if not record:
                    raise HTTPException(status_code=404, detail="Article not found")
                
                return {
                    "article": dict(record['a']) if record['a'] else None,
                    "authors": [dict(a) for a in record['authors'] if a],
                    "journal": dict(record['j']) if record['j'] else None,
                    "reasons": [dict(r) for r in record['reasons'] if r]
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
    
    # Fallback to JSON
    if json_data:
        # Find article node
        article_node = None
        for node in json_data.get('nodes', []):
            props = node.get('properties', {})
            if props.get('type') == 'Article' and props.get('record_id') == record_id:
                article_node = node
                break
        
        if not article_node:
            raise HTTPException(status_code=404, detail="Article not found")
        
        article_id = article_node['id']
        
        # Find related nodes
        authors = []
        journal = None
        reasons = []
        
        for edge in json_data.get('edges', []):
            if edge['target'] == article_id and edge['properties'].get('type') == 'Authored_By':
                # Find author node
                for node in json_data.get('nodes', []):
                    if node['id'] == edge['source']:
                        authors.append(node['properties'])
            
            elif edge['source'] == article_id and edge['properties'].get('type') == 'Published_In':
                # Find journal node
                for node in json_data.get('nodes', []):
                    if node['id'] == edge['target']:
                        journal = node['properties']
            
            elif edge['source'] == article_id and edge['properties'].get('type') == 'Retracted_For':
                # Find reason node
                for node in json_data.get('nodes', []):
                    if node['id'] == edge['target']:
                        reasons.append(node['properties'])
        
        return {
            "article": article_node['properties'],
            "authors": authors,
            "journal": journal,
            "reasons": reasons
        }
    
    raise HTTPException(status_code=503, detail="No data source available")


@app.get("/api/journals/top")
async def get_top_journals(limit: int = Query(10, ge=1, le=100)):
    """Get top journals by retraction count"""
    if neo4j_driver:
        try:
            cypher = """
            MATCH (a:Article)-[:Published_In]->(j:Journal)
            RETURN j.name as journal, count(a) as retraction_count
            ORDER BY retraction_count DESC
            LIMIT $limit
            """
            
            records = query_neo4j(cypher, {'limit': limit})
            
            return {
                "journals": records,
                "count": len(records)
            }
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint requires Neo4j connection"
    )


@app.get("/api/reasons/top")
async def get_top_reasons(limit: int = Query(10, ge=1, le=100)):
    """Get top retraction reasons"""
    if neo4j_driver:
        try:
            cypher = """
            MATCH (a:Article)-[:Retracted_For]->(r:Reason)
            RETURN r.name as reason, count(a) as count
            ORDER BY count DESC
            LIMIT $limit
            """
            
            records = query_neo4j(cypher, {'limit': limit})
            
            return {
                "reasons": records,
                "count": len(records)
            }
        except Exception as e:
            logger.error(f"Error querying Neo4j: {e}")
    
    raise HTTPException(
        status_code=501,
        detail="This endpoint requires Neo4j connection"
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Close Neo4j connection on shutdown"""
    if neo4j_driver:
        neo4j_driver.close()
        logger.info("Neo4j connection closed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
