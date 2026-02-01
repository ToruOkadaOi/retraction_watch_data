"""
Quick test of Knowledge Graph generation with sample data
"""

import csv
import os
import logging
from knowledge_graph import KnowledgeGraphGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_with_sample():
    """Test with first 100 rows of data"""
    logger.info("Testing Knowledge Graph generation with sample data...")
    
    # Create sample CSV
    sample_csv = "sample_data.csv"
    
    with open("retraction_watch.csv", 'r', encoding='utf-8') as infile:
        reader = csv.reader(infile)
        with open(sample_csv, 'w', encoding='utf-8', newline='') as outfile:
            writer = csv.writer(outfile)
            
            # Copy header and first 100 rows
            for i, row in enumerate(reader):
                writer.writerow(row)
                if i >= 100:  # Header + 100 data rows
                    break
    
    logger.info(f"Created sample CSV with 100 rows")
    
    # Generate graph
    generator = KnowledgeGraphGenerator(sample_csv)
    generator.parse_csv()
    
    # Create outputs
    os.makedirs("outputs", exist_ok=True)
    generator.visualize("outputs/sample_graph.png", sample_size=50)
    generator.export_to_json("outputs/sample_graph.json")
    generator.export_to_graphml("outputs/sample_graph.graphml")
    generator.export_to_rdf("outputs/sample_graph.rdf")
    
    # Get statistics
    stats = generator.get_statistics()
    
    logger.info("\nSample Graph Statistics:")
    logger.info(f"  Articles: {stats['articles']}")
    logger.info(f"  Authors: {stats['authors']}")
    logger.info(f"  Journals: {stats['journals']}")
    logger.info(f"  Institutions: {stats['institutions']}")
    logger.info(f"  Reasons: {stats['reasons']}")
    logger.info(f"  Total Edges: {stats['authored_by'] + stats['published_in'] + stats['affiliated_with'] + stats['retracted_for']}")
    logger.info(f"  Errors: {len(stats['errors'])}")
    
    # Clean up sample file
    os.remove(sample_csv)
    
    logger.info("\n✓ Sample graph generation successful!")
    
    return True


if __name__ == "__main__":
    test_with_sample()
