"""
Knowledge Graph Generator for Retraction Watch Data

This script parses the retraction_watch.csv dataset and creates a knowledge graph with:
- Entities: Authors, Articles, Journals, Institutions, Reasons
- Relationships: Authored_By, Published_In, Affiliated_With, Retracted_For

Schema (relationship directions):
    (Author)-[:Authored_By]->(Article)
    (Article)-[:Published_In]->(Journal)
    (Author)-[:Affiliated_With]->(Institution)
    (Article)-[:Retracted_For]->(Reason)
"""

import csv
import json
import logging
import os
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime, timezone
import networkx as nx
from rdflib import Graph, Literal, Namespace, URIRef, RDF, RDFS
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KnowledgeGraphGenerator:
    """Generate Knowledge Graph from Retraction Watch data"""
    
    def __init__(self, csv_path: str = "retraction_watch.csv"):
        self.csv_path = csv_path
        self.graph = nx.DiGraph()
        self.stats = {
            'authors': 0,
            'articles': 0,
            'journals': 0,
            'institutions': 0,
            'reasons': 0,
            'authored_by': 0,
            'published_in': 0,
            'affiliated_with': 0,
            'retracted_for': 0,
            'errors': []
        }
        
    def _split_field(self, field: str) -> List[str]:
        """Split semicolon-separated field into list"""
        if not field or field.strip() == '':
            return []
        return [item.strip() for item in field.split(';') if item.strip()]
    
    def _create_node_id(self, node_type: str, name: str) -> str:
        """Create unique node identifier"""
        # Clean the name and create ID
        clean_name = name.strip()
        return f"{node_type}:{clean_name}"
    
    def _add_node(self, node_id: str, node_type: str, properties: Dict) -> None:
        """Add node to graph with properties"""
        if not self.graph.has_node(node_id):
            self.graph.add_node(node_id, type=node_type, **properties)
            self.stats[node_type.lower() + 's'] += 1
    
    def _add_edge(self, from_node: str, to_node: str, edge_type: str, properties: Dict = None) -> None:
        """Add edge to graph with properties"""
        if properties is None:
            properties = {}
        
        # Verify both nodes exist
        if not self.graph.has_node(from_node):
            logger.warning(f"Source node not found: {from_node}")
            self.stats['errors'].append(f"Missing source node: {from_node}")
            return
        
        if not self.graph.has_node(to_node):
            logger.warning(f"Target node not found: {to_node}")
            self.stats['errors'].append(f"Missing target node: {to_node}")
            return
        
        self.graph.add_edge(from_node, to_node, type=edge_type, **properties)
        
        # Count edge types
        edge_stat_key = edge_type.lower()
        if edge_stat_key in self.stats:
            self.stats[edge_stat_key] += 1
    
    def parse_csv(self) -> None:
        """Parse CSV and build knowledge graph"""
        logger.info(f"Parsing CSV file: {self.csv_path}")
        
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 to account for header
                    try:
                        self._process_row(row, row_num)
                    except Exception as e:
                        error_msg = f"Error processing row {row_num}: {str(e)}"
                        logger.error(error_msg)
                        self.stats['errors'].append(error_msg)
                        
        except FileNotFoundError:
            error_msg = f"CSV file not found: {self.csv_path}"
            logger.error(error_msg)
            self.stats['errors'].append(error_msg)
            raise
        
        logger.info("CSV parsing completed")
        self._log_statistics()
    
    def _process_row(self, row: Dict, row_num: int) -> None:
        """Process a single CSV row"""
        # Extract and validate article data
        record_id = row.get('Record ID', '').strip()
        title = row.get('Title', '').strip()
        
        if not record_id or not title:
            logger.warning(f"Row {row_num}: Missing Record ID or Title")
            return
        
        # Create Article node
        article_id = self._create_node_id('Article', record_id)
        article_props = {
            'name': title,
            'record_id': record_id,
            'subject': row.get('Subject', ''),
            'retraction_date': row.get('RetractionDate', ''),
            'original_paper_date': row.get('OriginalPaperDate', ''),
            'retraction_nature': row.get('RetractionNature', ''),
            'article_type': row.get('ArticleType', ''),
            'retraction_doi': row.get('RetractionDOI', ''),
            'original_paper_doi': row.get('OriginalPaperDOI', ''),
            'paywalled': row.get('Paywalled', ''),
            'notes': row.get('Notes', ''),
            'urls': row.get('URLS', '')
        }
        self._add_node(article_id, 'Article', article_props)
        
        # Process Journal
        journal = row.get('Journal', '').strip()
        if journal:
            journal_id = self._create_node_id('Journal', journal)
            journal_props = {
                'name': journal,
                'publisher': row.get('Publisher', '')
            }
            self._add_node(journal_id, 'Journal', journal_props)
            self._add_edge(article_id, journal_id, 'Published_In', {
                'date': row.get('OriginalPaperDate', '')
            })
        
        # Process Authors
        authors = self._split_field(row.get('Author', ''))
        for author in authors:
            if author:
                author_id = self._create_node_id('Author', author)
                author_props = {'name': author}
                self._add_node(author_id, 'Author', author_props)
                self._add_edge(author_id, article_id, 'Authored_By', {})
        
        # Process Institutions
        institutions = self._split_field(row.get('Institution', ''))
        for institution in institutions:
            if institution:
                institution_id = self._create_node_id('Institution', institution)
                institution_props = {
                    'name': institution,
                    'country': row.get('Country', '')
                }
                self._add_node(institution_id, 'Institution', institution_props)
                
                # Link institutions to authors (if we have authors)
                if authors:
                    # For simplicity, link institution to all authors
                    # In reality, we'd need more specific affiliation data
                    for author in authors:
                        author_id = self._create_node_id('Author', author)
                        self._add_edge(author_id, institution_id, 'Affiliated_With', {})
        
        # Process Retraction Reasons
        reasons = self._split_field(row.get('Reason', ''))
        for reason in reasons:
            if reason:
                reason_id = self._create_node_id('Reason', reason)
                reason_props = {'name': reason}
                self._add_node(reason_id, 'Reason', reason_props)
                self._add_edge(article_id, reason_id, 'Retracted_For', {
                    'date': row.get('RetractionDate', '')
                })
    
    def _log_statistics(self) -> None:
        """Log graph statistics"""
        logger.info("=" * 60)
        logger.info("Knowledge Graph Statistics:")
        logger.info(f"  Nodes:")
        logger.info(f"    - Articles: {self.stats['articles']}")
        logger.info(f"    - Authors: {self.stats['authors']}")
        logger.info(f"    - Journals: {self.stats['journals']}")
        logger.info(f"    - Institutions: {self.stats['institutions']}")
        logger.info(f"    - Reasons: {self.stats['reasons']}")
        logger.info(f"  Edges:")
        logger.info(f"    - Authored_By: {self.stats['authored_by']}")
        logger.info(f"    - Published_In: {self.stats['published_in']}")
        logger.info(f"    - Affiliated_With: {self.stats['affiliated_with']}")
        logger.info(f"    - Retracted_For: {self.stats['retracted_for']}")
        logger.info(f"  Errors: {len(self.stats['errors'])}")
        logger.info("=" * 60)
    
    def visualize(self, output_path: str = "knowledge_graph.png", sample_size: int = 100) -> None:
        """Create NetworkX visualization (sample for large graphs)"""
        logger.info(f"Creating visualization (sample size: {sample_size})")
        
        # Sample nodes for visualization if graph is large
        if len(self.graph.nodes()) > sample_size:
            # Get a sample of nodes
            nodes = list(self.graph.nodes())[:sample_size]
            subgraph = self.graph.subgraph(nodes)
        else:
            subgraph = self.graph
        
        # Create figure
        plt.figure(figsize=(20, 20))
        
        # Node colors based on type
        node_colors = []
        for node in subgraph.nodes():
            node_type = subgraph.nodes[node].get('type', '')
            if node_type == 'Article':
                node_colors.append('lightblue')
            elif node_type == 'Author':
                node_colors.append('lightgreen')
            elif node_type == 'Journal':
                node_colors.append('yellow')
            elif node_type == 'Institution':
                node_colors.append('orange')
            elif node_type == 'Reason':
                node_colors.append('pink')
            else:
                node_colors.append('gray')
        
        # Layout
        pos = nx.spring_layout(subgraph, k=0.5, iterations=50)
        
        # Draw nodes
        nx.draw_networkx_nodes(subgraph, pos, node_color=node_colors, 
                              node_size=500, alpha=0.7)
        
        # Draw edges
        nx.draw_networkx_edges(subgraph, pos, alpha=0.3, arrows=True,
                              arrowsize=10, width=0.5)
        
        # Draw labels (only for small graphs)
        if len(subgraph.nodes()) <= 50:
            labels = {node: subgraph.nodes[node].get('name', node.split(':')[1][:20]) 
                     for node in subgraph.nodes()}
            nx.draw_networkx_labels(subgraph, pos, labels, font_size=6)
        
        plt.title(f"Retraction Watch Knowledge Graph (Sample: {len(subgraph.nodes())} nodes)")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Visualization saved to {output_path}")
    
    def export_to_json(self, output_path: str = "knowledge_graph.json") -> None:
        """Export graph to JSON format"""
        logger.info(f"Exporting to JSON: {output_path}")
        source_date_epoch = os.getenv('SOURCE_DATE_EPOCH')
        generated_at = (
            datetime.fromtimestamp(int(source_date_epoch), timezone.utc).isoformat()
            if source_date_epoch
            else datetime.now().isoformat()
        )
        
        # Convert graph to JSON-serializable format
        data = {
            'metadata': {
                'generated_at': generated_at,
                'statistics': self.stats
            },
            'nodes': [],
            'edges': []
        }
        
        # Add nodes
        for node_id in self.graph.nodes():
            node_data = {
                'id': node_id,
                'properties': dict(self.graph.nodes[node_id])
            }
            data['nodes'].append(node_data)
        
        # Add edges
        for source, target in self.graph.edges():
            edge_data = {
                'source': source,
                'target': target,
                'properties': dict(self.graph[source][target])
            }
            data['edges'].append(edge_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON export completed: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    
    def export_to_graphml(self, output_path: str = "knowledge_graph.graphml") -> None:
        """Export graph to GraphML format (for Gephi)"""
        logger.info(f"Exporting to GraphML: {output_path}")
        nx.write_graphml(self.graph, output_path)
        logger.info(f"GraphML export completed")
    
    def export_to_rdf(self, output_path: str = "knowledge_graph.rdf") -> None:
        """Export graph to RDF format"""
        logger.info(f"Exporting to RDF: {output_path}")
        
        # Create RDF graph
        rdf_graph = Graph()
        
        # Define namespace
        RW = Namespace("http://retractionwatch.org/ontology#")
        rdf_graph.bind("rw", RW)
        
        # Add nodes
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            node_type = node_data.get('type', 'Unknown')
            node_uri = URIRef(f"http://retractionwatch.org/resource/{node_id.replace(':', '/')}")
            
            # Add type
            rdf_graph.add((node_uri, RDF.type, RW[node_type]))
            
            # Add properties
            for key, value in node_data.items():
                if key != 'type' and value:
                    rdf_graph.add((node_uri, RW[key], Literal(value)))
        
        # Add edges
        for source, target in self.graph.edges():
            edge_data = self.graph[source][target]
            edge_type = edge_data.get('type', 'RelatedTo')
            
            source_uri = URIRef(f"http://retractionwatch.org/resource/{source.replace(':', '/')}")
            target_uri = URIRef(f"http://retractionwatch.org/resource/{target.replace(':', '/')}")
            
            rdf_graph.add((source_uri, RW[edge_type], target_uri))
            
            # Add edge properties
            for key, value in edge_data.items():
                if key != 'type' and value:
                    # Create a blank node for edge properties
                    # (simplified - in practice, might use reification)
                    pass
        
        # Serialize to file
        rdf_graph.serialize(destination=output_path, format='xml')
        logger.info(f"RDF export completed")
    
    def get_statistics(self) -> Dict:
        """Return graph statistics"""
        return self.stats.copy()


def main():
    """Main execution function"""
    logger.info("Starting Knowledge Graph Generation")
    os.makedirs("outputs", exist_ok=True)
    
    # Create generator
    generator = KnowledgeGraphGenerator("retraction_watch.csv")
    
    # Parse CSV and build graph
    generator.parse_csv()
    
    # Create visualizations and exports
    generator.visualize("outputs/knowledge_graph.png")
    generator.export_to_json("outputs/knowledge_graph.json")
    generator.export_to_graphml("outputs/knowledge_graph.graphml")
    generator.export_to_rdf("outputs/knowledge_graph.rdf")
    
    # Print statistics
    stats = generator.get_statistics()
    logger.info("\nFinal Statistics:")
    logger.info(f"Total Nodes: {sum([stats['articles'], stats['authors'], stats['journals'], stats['institutions'], stats['reasons']])}")
    logger.info(f"Total Edges: {sum([stats['authored_by'], stats['published_in'], stats['affiliated_with'], stats['retracted_for']])}")
    logger.info(f"Errors encountered: {len(stats['errors'])}")
    
    logger.info("\nKnowledge Graph generation completed successfully!")


if __name__ == "__main__":
    main()
