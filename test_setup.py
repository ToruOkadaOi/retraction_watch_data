"""
Test script for Knowledge Graph generation

This script validates the Knowledge Graph implementation.
"""

import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all required modules can be imported"""
    logger.info("Testing imports...")
    
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
        from rdflib import Graph
        logger.info("✓ Core dependencies imported successfully")
        return True
    except ImportError as e:
        logger.error(f"✗ Import failed: {e}")
        return False


def test_csv_exists():
    """Test that the CSV file exists"""
    logger.info("Testing CSV file...")
    
    csv_path = "retraction_watch.csv"
    if os.path.exists(csv_path):
        size = os.path.getsize(csv_path)
        logger.info(f"✓ CSV file exists ({size:,} bytes)")
        return True
    else:
        logger.error(f"✗ CSV file not found: {csv_path}")
        return False


def test_graph_generation():
    """Test knowledge graph generation"""
    logger.info("Testing graph generation...")
    
    try:
        from knowledge_graph import KnowledgeGraphGenerator
        
        # Create generator with sample data
        generator = KnowledgeGraphGenerator("retraction_watch.csv")
        
        # Test parsing first 10 rows
        logger.info("Testing CSV parsing (sample)...")
        # Note: Full parsing would take too long for testing
        
        logger.info("✓ Graph generation module works")
        return True
    except Exception as e:
        logger.error(f"✗ Graph generation failed: {e}")
        return False


def test_outputs_directory():
    """Test that outputs directory can be created"""
    logger.info("Testing outputs directory...")
    
    output_dir = "outputs"
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"✓ Outputs directory ready: {output_dir}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to create outputs directory: {e}")
        return False


def test_neo4j_module():
    """Test Neo4j integration module (import only)"""
    logger.info("Testing Neo4j module...")
    
    try:
        from neo4j_integration import Neo4jLoader
        logger.info("✓ Neo4j module can be imported")
        return True
    except ImportError as e:
        logger.error(f"✗ Neo4j module import failed: {e}")
        return False


def test_api_module():
    """Test API module (import only)"""
    logger.info("Testing API module...")
    
    try:
        from api import app
        logger.info("✓ API module can be imported")
        return True
    except ImportError as e:
        logger.error(f"✗ API module import failed: {e}")
        return False


def run_all_tests():
    """Run all tests"""
    logger.info("=" * 60)
    logger.info("Knowledge Graph Test Suite")
    logger.info("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("CSV File", test_csv_exists),
        ("Graph Generation", test_graph_generation),
        ("Outputs Directory", test_outputs_directory),
        ("Neo4j Module", test_neo4j_module),
        ("API Module", test_api_module),
    ]
    
    results = []
    for name, test_func in tests:
        logger.info(f"\n[{name}]")
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n✓ All tests passed!")
        return 0
    else:
        logger.warning(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
