"""
Example usage of the Retraction Watch Knowledge Graph

This script demonstrates various ways to work with the Knowledge Graph.
"""

import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def example_1_load_json():
    """Example 1: Load and explore the JSON graph"""
    logger.info("\n=== Example 1: Load and explore JSON graph ===")
    
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Get statistics
    stats = data['metadata']['statistics']
    logger.info(f"Total Articles: {stats['articles']}")
    logger.info(f"Total Authors: {stats['authors']}")
    logger.info(f"Total Journals: {stats['journals']}")
    
    # Find a sample article
    articles = [n for n in data['nodes'] if n['properties'].get('type') == 'Article']
    if articles:
        sample = articles[0]['properties']
        logger.info(f"\nSample Article:")
        logger.info(f"  Title: {sample.get('name', 'N/A')[:80]}...")
        logger.info(f"  Retraction Date: {sample.get('retraction_date', 'N/A')}")


def example_2_search_authors():
    """Example 2: Search for articles by specific authors"""
    logger.info("\n=== Example 2: Search for articles by author ===")
    
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find all unique authors
    authors = set()
    for node in data['nodes']:
        if node['properties'].get('type') == 'Author':
            authors.add(node['properties']['name'])
    
    logger.info(f"Total unique authors: {len(authors)}")
    logger.info(f"Sample authors: {list(authors)[:5]}")


def example_3_journal_statistics():
    """Example 3: Analyze journal statistics"""
    logger.info("\n=== Example 3: Journal statistics ===")
    
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Count articles per journal
    journal_counts = {}
    
    for edge in data['edges']:
        if edge['properties'].get('type') == 'Published_In':
            # Find the journal node
            journal_id = edge['target']
            for node in data['nodes']:
                if node['id'] == journal_id:
                    journal_name = node['properties']['name']
                    journal_counts[journal_name] = journal_counts.get(journal_name, 0) + 1
                    break
    
    # Sort by count
    top_journals = sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)
    
    logger.info("Top 10 journals by retraction count:")
    for journal, count in top_journals[:10]:
        logger.info(f"  {journal}: {count} retractions")


def example_4_retraction_reasons():
    """Example 4: Analyze retraction reasons"""
    logger.info("\n=== Example 4: Retraction reasons ===")
    
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Count reasons
    reason_counts = {}
    
    for edge in data['edges']:
        if edge['properties'].get('type') == 'Retracted_For':
            # Find the reason node
            reason_id = edge['target']
            for node in data['nodes']:
                if node['id'] == reason_id:
                    reason_name = node['properties']['name']
                    reason_counts[reason_name] = reason_counts.get(reason_name, 0) + 1
                    break
    
    # Sort by count
    top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
    
    logger.info("Top 10 retraction reasons:")
    for reason, count in top_reasons[:10]:
        logger.info(f"  {reason}: {count} occurrences")


def example_5_networkx_analysis():
    """Example 5: NetworkX graph analysis"""
    logger.info("\n=== Example 5: NetworkX analysis ===")
    
    try:
        import networkx as nx
        from knowledge_graph import KnowledgeGraphGenerator
        
        # Load the graph (assuming it's already generated)
        generator = KnowledgeGraphGenerator()
        
        # Note: For this example, we'd need to parse the CSV first
        # generator.parse_csv()
        
        logger.info("NetworkX analysis would include:")
        logger.info("  - Degree centrality (most connected nodes)")
        logger.info("  - Betweenness centrality (most important nodes)")
        logger.info("  - Community detection")
        logger.info("  - Path analysis between nodes")
        
    except Exception as e:
        logger.warning(f"NetworkX example requires generated graph: {e}")


def example_6_query_by_subject():
    """Example 6: Query articles by subject"""
    logger.info("\n=== Example 6: Query by subject ===")
    
    with open('outputs/knowledge_graph.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Find articles with "Cancer" in subject
    cancer_articles = []
    for node in data['nodes']:
        props = node['properties']
        if props.get('type') == 'Article':
            subject = props.get('subject', '').lower()
            if 'cancer' in subject or 'oncology' in subject:
                cancer_articles.append(props)
    
    logger.info(f"Found {len(cancer_articles)} cancer-related articles")
    
    if cancer_articles:
        sample = cancer_articles[0]
        logger.info(f"\nSample cancer article:")
        logger.info(f"  Title: {sample.get('name', 'N/A')[:80]}...")
        logger.info(f"  Subject: {sample.get('subject', 'N/A')[:80]}...")


def main():
    """Run all examples"""
    logger.info("=" * 60)
    logger.info("Retraction Watch Knowledge Graph - Usage Examples")
    logger.info("=" * 60)
    
    try:
        example_1_load_json()
        example_2_search_authors()
        example_3_journal_statistics()
        example_4_retraction_reasons()
        example_5_networkx_analysis()
        example_6_query_by_subject()
        
        logger.info("\n" + "=" * 60)
        logger.info("Examples completed!")
        logger.info("=" * 60)
        
    except FileNotFoundError as e:
        logger.error(f"\nError: {e}")
        logger.info("\nPlease generate the knowledge graph first:")
        logger.info("  python knowledge_graph.py")


if __name__ == "__main__":
    main()
