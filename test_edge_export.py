"""
Test script for validating edge export consistency in Knowledge Graph

This test validates that all edges in the graph are properly exported to JSON
and that the edge count matches between NetworkX and the JSON export.
"""

import os
import json
import csv
import logging
from knowledge_graph import KnowledgeGraphGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_edge_export_consistency():
    """Test that edge export matches NetworkX edge count"""
    logger.info("=" * 60)
    logger.info("Testing Edge Export Consistency")
    logger.info("=" * 60)
    
    # Create sample CSV with known structure
    sample_csv = "test_edge_data.csv"
    test_output_json = "test_edge_graph.json"
    
    try:
        # Create a small test dataset
        with open(sample_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['Record ID', 'Title', 'Journal', 'Author', 'Institution', 
                           'Reason', 'Publisher', 'OriginalPaperDate', 'RetractionDate', 
                           'Country', 'Subject', 'RetractionNature', 'ArticleType', 
                           'RetractionDOI', 'OriginalPaperDOI', 'Paywalled', 'Notes', 'URLS'])
            
            # Add test rows with multiple authors/institutions to test duplicate edges
            writer.writerow(['1', 'Test Article 1', 'Test Journal A', 'Author A;Author B', 
                           'Institution X;Institution Y', 'Reason 1;Reason 2', 
                           'Publisher A', '2020-01-01', '2021-01-01', 'USA', 
                           'Subject 1', 'Retraction', 'Article', 'doi:1', 'doi:2', 'No', '', ''])
            writer.writerow(['2', 'Test Article 2', 'Test Journal B', 'Author A;Author C', 
                           'Institution X', 'Reason 1', 
                           'Publisher B', '2020-02-01', '2021-02-01', 'UK', 
                           'Subject 2', 'Retraction', 'Article', 'doi:3', 'doi:4', 'No', '', ''])
            writer.writerow(['3', 'Test Article 3', 'Test Journal A', 'Author B', 
                           'Institution Z', 'Reason 3', 
                           'Publisher A', '2020-03-01', '2021-03-01', 'Canada', 
                           'Subject 1', 'Retraction', 'Article', 'doi:5', 'doi:6', 'No', '', ''])
            # Test case for multiple edges: same author publishing in same journal twice
            writer.writerow(['4', 'Test Article 4', 'Test Journal A', 'Author A', 
                           'Institution X', 'Reason 1', 
                           'Publisher A', '2020-04-01', '2021-04-01', 'USA', 
                           'Subject 1', 'Retraction', 'Article', 'doi:7', 'doi:8', 'No', '', ''])
        
        logger.info(f"Created test CSV: {sample_csv}")
        
        # Generate knowledge graph
        generator = KnowledgeGraphGenerator(sample_csv)
        generator.parse_csv()
        
        # Get stats before export
        nx_edge_count = generator.graph.number_of_edges()
        stats_edge_count = (generator.stats['authored_by'] + 
                          generator.stats['published_in'] + 
                          generator.stats['affiliated_with'] + 
                          generator.stats['retracted_for'])
        
        logger.info(f"\nPre-Export Statistics:")
        logger.info(f"  NetworkX edge count: {nx_edge_count}")
        logger.info(f"  Stats edge count: {stats_edge_count}")
        logger.info(f"  Skipped edges: {generator.stats['skipped_edges']}")
        
        # Verify MultiDiGraph supports multiple edges between same nodes
        # Author A should have multiple edges to Institution X
        author_a_id = 'Author:Author A'
        institution_x_id = 'Institution:Institution X'
        multiple_edges = list(generator.graph[author_a_id][institution_x_id].keys())
        logger.info(f"\nMultiDiGraph Test:")
        logger.info(f"  Multiple edges between {author_a_id} and {institution_x_id}: {len(multiple_edges)} edges")
        
        # Export to JSON
        generator.export_to_json(test_output_json)
        
        # Load and validate JSON
        with open(test_output_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        json_edge_count = len(data['edges'])
        json_node_count = len(data['nodes'])
        metadata_edge_count = data['metadata'].get('graph_edge_count', 0)
        
        logger.info(f"\nPost-Export Statistics:")
        logger.info(f"  JSON edge count: {json_edge_count}")
        logger.info(f"  JSON node count: {json_node_count}")
        logger.info(f"  Metadata edge count: {metadata_edge_count}")
        
        # Count multiple edges in JSON for the same node pair
        edges_author_a_to_inst_x = [e for e in data['edges'] 
                                    if e['source'] == author_a_id and e['target'] == institution_x_id]
        logger.info(f"  Multiple edges in JSON for test pair: {len(edges_author_a_to_inst_x)} edges")
        
        # Validate counts match
        success = True
        if nx_edge_count != json_edge_count:
            logger.error(f"❌ FAIL: NetworkX edges ({nx_edge_count}) != JSON edges ({json_edge_count})")
            success = False
        else:
            logger.info(f"✓ PASS: NetworkX edges == JSON edges ({nx_edge_count})")
        
        if stats_edge_count != nx_edge_count:
            logger.warning(f"⚠️  WARNING: Stats edge count ({stats_edge_count}) != NetworkX edges ({nx_edge_count})")
            logger.warning(f"   This might indicate duplicate edges being consolidated")
        else:
            logger.info(f"✓ PASS: Stats edge count == NetworkX edges ({stats_edge_count})")
        
        if metadata_edge_count != json_edge_count:
            logger.error(f"❌ FAIL: Metadata edge count ({metadata_edge_count}) != JSON edges ({json_edge_count})")
            success = False
        else:
            logger.info(f"✓ PASS: Metadata edge count == JSON edges ({metadata_edge_count})")
        
        # Verify MultiDiGraph correctly exports multiple edges
        if len(multiple_edges) != len(edges_author_a_to_inst_x):
            logger.error(f"❌ FAIL: MultiDiGraph edges ({len(multiple_edges)}) != JSON exported edges ({len(edges_author_a_to_inst_x)})")
            success = False
        else:
            logger.info(f"✓ PASS: MultiDiGraph multiple edges correctly exported ({len(multiple_edges)} edges)")
        
        # Verify sample edges exist in JSON
        logger.info(f"\nSample Edge Validation:")
        sample_edges_found = 0
        for edge in data['edges'][:5]:
            logger.info(f"  {edge['source']} -> {edge['target']} (type: {edge['properties'].get('type', 'N/A')})")
            sample_edges_found += 1
        
        logger.info(f"  ... and {json_edge_count - sample_edges_found} more edges")
        
        # Final result
        logger.info("\n" + "=" * 60)
        if success:
            logger.info("✓ ALL TESTS PASSED")
            logger.info("=" * 60)
            return True
        else:
            logger.error("❌ SOME TESTS FAILED")
            logger.info("=" * 60)
            return False
            
    finally:
        # Cleanup
        if os.path.exists(sample_csv):
            os.remove(sample_csv)
        if os.path.exists(test_output_json):
            os.remove(test_output_json)
        logger.info("\nCleaned up test files")


def test_with_sample_data():
    """Test with existing sample data if available"""
    logger.info("\n" + "=" * 60)
    logger.info("Testing with Sample Data")
    logger.info("=" * 60)
    
    sample_csv = "retraction_watch.csv"
    
    if not os.path.exists(sample_csv):
        logger.warning(f"Sample CSV not found: {sample_csv}")
        logger.info("Skipping sample data test")
        return True
    
    # Create a small sample
    test_sample_csv = "test_sample_100.csv"
    test_output_json = "test_sample_graph.json"
    
    try:
        with open(sample_csv, 'r', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            with open(test_sample_csv, 'w', encoding='utf-8', newline='') as outfile:
                writer = csv.writer(outfile)
                
                # Copy header and first 100 data rows (101 rows total)
                for i, row in enumerate(reader):
                    writer.writerow(row)
                    if i >= 100:  # Stop after header (row 0) + 100 data rows (rows 1-100)
                        break
        
        logger.info(f"Created test sample CSV with 100 rows")
        
        # Generate graph
        generator = KnowledgeGraphGenerator(test_sample_csv)
        generator.parse_csv()
        
        # Get counts
        nx_edge_count = generator.graph.number_of_edges()
        stats_edge_count = (generator.stats['authored_by'] + 
                          generator.stats['published_in'] + 
                          generator.stats['affiliated_with'] + 
                          generator.stats['retracted_for'])
        
        logger.info(f"\nSample Data Statistics:")
        logger.info(f"  NetworkX edge count: {nx_edge_count}")
        logger.info(f"  Stats edge count: {stats_edge_count}")
        logger.info(f"  Difference: {abs(nx_edge_count - stats_edge_count)}")
        
        # Export
        generator.export_to_json(test_output_json)
        
        # Validate
        with open(test_output_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        json_edge_count = len(data['edges'])
        
        logger.info(f"  JSON edge count: {json_edge_count}")
        
        success = (nx_edge_count == json_edge_count)
        
        if success:
            logger.info("✓ Edge counts match for sample data")
        else:
            logger.error(f"❌ Edge count mismatch: NetworkX={nx_edge_count}, JSON={json_edge_count}")
        
        return success
        
    finally:
        # Cleanup
        if os.path.exists(test_sample_csv):
            os.remove(test_sample_csv)
        if os.path.exists(test_output_json):
            os.remove(test_output_json)
        logger.info("Cleaned up test files")


if __name__ == "__main__":
    logger.info("Starting Edge Export Tests\n")
    
    test1_passed = test_edge_export_consistency()
    test2_passed = test_with_sample_data()
    
    logger.info("\n" + "=" * 60)
    logger.info("FINAL TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Test 1 (Edge Export Consistency): {'✓ PASSED' if test1_passed else '❌ FAILED'}")
    logger.info(f"Test 2 (Sample Data Test): {'✓ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        logger.info("\n✓ ALL TESTS PASSED!")
        exit(0)
    else:
        logger.error("\n❌ SOME TESTS FAILED!")
        exit(1)
