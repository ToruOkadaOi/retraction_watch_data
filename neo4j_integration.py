"""
Neo4j Integration for Retraction Watch Knowledge Graph

This script loads the knowledge graph into a Neo4j database.
"""

import json
import logging
from typing import Dict, List, Optional
from neo4j import GraphDatabase
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Neo4jLoader:
    """Load knowledge graph into Neo4j database"""
    
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """
        Initialize Neo4j connection
        
        Args:
            uri: Neo4j URI (default: neo4j://localhost:7687)
            user: Neo4j username (default: neo4j)
            password: Neo4j password (from NEO4J_PASSWORD env var)
        """
        self.uri = uri or os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
        self.user = user or os.getenv('NEO4J_USER', 'neo4j')
        self.password = password or os.getenv('NEO4J_PASSWORD', 'password')
        
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    def clear_database(self):
        """Clear all nodes and relationships from database"""
        logger.info("Clearing database...")
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Database cleared")
    
    def create_constraints(self):
        """Create constraints and indexes for better performance"""
        logger.info("Creating constraints and indexes...")
        
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Article) REQUIRE a.record_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Author) REQUIRE a.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (j:Journal) REQUIRE j.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Institution) REQUIRE i.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Reason) REQUIRE r.name IS UNIQUE",
        ]
        
        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint[:50]}...")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")
    
    def load_from_json(self, json_path: str = "outputs/knowledge_graph.json"):
        """Load knowledge graph from JSON file into Neo4j"""
        logger.info(f"Loading knowledge graph from {json_path}")
        
        # Read JSON file
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"JSON file not found: {json_path}")
            raise
        
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        
        logger.info(f"Found {len(nodes)} nodes and {len(edges)} edges")
        
        # Load nodes
        self._load_nodes(nodes)
        
        # Load edges
        self._load_edges(edges)
        
        logger.info("Knowledge graph loaded successfully")
    
    def _load_nodes(self, nodes: List[Dict]):
        """Load nodes into Neo4j"""
        logger.info(f"Loading {len(nodes)} nodes...")
        
        # Group nodes by type for batch processing
        nodes_by_type = {}
        for node in nodes:
            node_type = node['properties'].get('type', 'Unknown')
            if node_type not in nodes_by_type:
                nodes_by_type[node_type] = []
            nodes_by_type[node_type].append(node)
        
        with self.driver.session() as session:
            for node_type, type_nodes in nodes_by_type.items():
                logger.info(f"Loading {len(type_nodes)} {node_type} nodes...")
                
                # Batch process nodes
                batch_size = 1000
                for i in range(0, len(type_nodes), batch_size):
                    batch = type_nodes[i:i + batch_size]
                    
                    # Create Cypher query for batch
                    query = f"""
                    UNWIND $nodes AS node
                    CREATE (n:{node_type})
                    SET n = node.properties
                    """
                    
                    session.run(query, nodes=batch)
                    
                    if (i + batch_size) % 5000 == 0:
                        logger.info(f"  Processed {i + batch_size} {node_type} nodes")
        
        logger.info("All nodes loaded")
    
    def _load_edges(self, edges: List[Dict]):
        """Load edges into Neo4j"""
        logger.info(f"Loading {len(edges)} edges...")
        
        # Group edges by type
        edges_by_type = {}
        for edge in edges:
            edge_type = edge['properties'].get('type', 'RELATED_TO')
            if edge_type not in edges_by_type:
                edges_by_type[edge_type] = []
            edges_by_type[edge_type].append(edge)
        
        with self.driver.session() as session:
            for edge_type, type_edges in edges_by_type.items():
                logger.info(f"Loading {len(type_edges)} {edge_type} edges...")
                
                # Batch process edges
                batch_size = 1000
                for i in range(0, len(type_edges), batch_size):
                    batch = type_edges[i:i + batch_size]
                    
                    # Create edges based on node types
                    for edge in batch:
                        source_id = edge['source']
                        target_id = edge['target']
                        
                        # Extract node types from IDs
                        source_type = source_id.split(':')[0]
                        target_type = target_id.split(':')[0]
                        
                        # Create relationship
                        query = f"""
                        MATCH (s:{source_type}), (t:{target_type})
                        WHERE (s.name = $source_name OR s.record_id = $source_id)
                        AND (t.name = $target_name OR t.record_id = $target_id)
                        CREATE (s)-[r:{edge_type}]->(t)
                        SET r = $properties
                        """
                        
                        # Extract names/IDs
                        source_name = source_id.split(':', 1)[1] if ':' in source_id else source_id
                        target_name = target_id.split(':', 1)[1] if ':' in target_id else target_id
                        
                        try:
                            session.run(query,
                                      source_name=source_name,
                                      source_id=source_name,
                                      target_name=target_name,
                                      target_id=target_name,
                                      properties=edge['properties'])
                        except Exception as e:
                            logger.warning(f"Error creating edge: {e}")
                    
                    if (i + batch_size) % 5000 == 0:
                        logger.info(f"  Processed {i + batch_size} {edge_type} edges")
        
        logger.info("All edges loaded")
    
    def get_statistics(self) -> Dict:
        """Get database statistics"""
        stats = {}
        
        with self.driver.session() as session:
            # Count nodes by type
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as type, count(n) as count
                ORDER BY count DESC
            """)
            
            stats['nodes'] = {record['type']: record['count'] for record in result}
            
            # Count relationships by type
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) as type, count(r) as count
                ORDER BY count DESC
            """)
            
            stats['relationships'] = {record['type']: record['count'] for record in result}
        
        return stats
    
    def example_queries(self):
        """Run example Cypher queries"""
        logger.info("\nRunning example queries:")
        
        with self.driver.session() as session:
            # Query 1: Top journals by retraction count
            logger.info("\n1. Top 10 journals by retraction count:")
            result = session.run("""
                MATCH (a:Article)-[:Published_In]->(j:Journal)
                RETURN j.name as journal, count(a) as retraction_count
                ORDER BY retraction_count DESC
                LIMIT 10
            """)
            for record in result:
                logger.info(f"   {record['journal']}: {record['retraction_count']}")
            
            # Query 2: Most common retraction reasons
            logger.info("\n2. Top 10 retraction reasons:")
            result = session.run("""
                MATCH (a:Article)-[:Retracted_For]->(r:Reason)
                RETURN r.name as reason, count(a) as count
                ORDER BY count DESC
                LIMIT 10
            """)
            for record in result:
                logger.info(f"   {record['reason']}: {record['count']}")
            
            # Query 3: Most prolific authors (by retractions)
            logger.info("\n3. Top 10 authors by retraction count:")
            result = session.run("""
                MATCH (author:Author)-[:Authored_By]->(a:Article)
                RETURN author.name as author, count(a) as retraction_count
                ORDER BY retraction_count DESC
                LIMIT 10
            """)
            for record in result:
                logger.info(f"   {record['author']}: {record['retraction_count']}")


def main():
    """Main execution function"""
    logger.info("Starting Neo4j integration")
    
    # Check if Neo4j is available
    neo4j_password = os.getenv('NEO4J_PASSWORD')
    if not neo4j_password:
        logger.warning("NEO4J_PASSWORD environment variable not set. Using default 'password'")
        logger.warning("Please set NEO4J_PASSWORD for production use")
    
    try:
        # Create loader
        loader = Neo4jLoader()
        
        # Clear existing data
        loader.clear_database()
        
        # Create constraints
        loader.create_constraints()
        
        # Load data
        loader.load_from_json()
        
        # Show statistics
        stats = loader.get_statistics()
        logger.info("\nDatabase Statistics:")
        logger.info(f"Nodes: {stats['nodes']}")
        logger.info(f"Relationships: {stats['relationships']}")
        
        # Run example queries
        loader.example_queries()
        
        # Close connection
        loader.close()
        
        logger.info("\nNeo4j integration completed successfully!")
        
    except Exception as e:
        logger.error(f"Neo4j integration failed: {e}")
        logger.info("\nNote: Make sure Neo4j is running and accessible at the configured URI")
        logger.info("You can skip Neo4j integration if the database is not available")


if __name__ == "__main__":
    main()
