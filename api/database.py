"""
Database utilities for loading and querying retraction data.
"""
import os
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

# Database setup
Base = declarative_base()
DATABASE_URL = "sqlite:///./api/retractions.db"

# Create engine and session factory once at module level
_engine = None
SessionLocal = None


def get_engine():
    """Get database engine (singleton)."""
    global _engine, SessionLocal
    if _engine is None:
        _engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


class RetractionDB(Base):
    """SQLAlchemy model for retraction data."""
    __tablename__ = "retractions"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(Integer, unique=True, index=True)
    title = Column(Text)
    subject = Column(Text)
    institution = Column(Text)
    journal = Column(String, index=True)
    publisher = Column(String)
    country = Column(Text)
    author = Column(Text, index=True)
    urls = Column(Text)
    article_type = Column(String)
    retraction_date = Column(String, index=True)
    retraction_doi = Column(String)
    retraction_pubmed_id = Column(String)
    original_paper_date = Column(String)
    original_paper_doi = Column(String)
    original_paper_pubmed_id = Column(String)
    retraction_nature = Column(String)
    reason = Column(Text)
    paywalled = Column(String)
    notes = Column(Text)


def get_engine():
    """Get database engine."""
    return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def get_session():
    """Get database session."""
    engine = get_engine()
    return SessionLocal()


def init_db():
    """Initialize the database and create tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def load_csv_to_db(csv_path: str):
    """Load retraction data from CSV into SQLite database."""
    print(f"Loading data from {csv_path}...")
    
    # Read CSV file
    df = pd.read_csv(csv_path)
    
    # Rename columns to match database model
    column_mapping = {
        'Record ID': 'record_id',
        'Title': 'title',
        'Subject': 'subject',
        'Institution': 'institution',
        'Journal': 'journal',
        'Publisher': 'publisher',
        'Country': 'country',
        'Author': 'author',
        'URLS': 'urls',
        'ArticleType': 'article_type',
        'RetractionDate': 'retraction_date',
        'RetractionDOI': 'retraction_doi',
        'RetractionPubMedID': 'retraction_pubmed_id',
        'OriginalPaperDate': 'original_paper_date',
        'OriginalPaperDOI': 'original_paper_doi',
        'OriginalPaperPubMedID': 'original_paper_pubmed_id',
        'RetractionNature': 'retraction_nature',
        'Reason': 'reason',
        'Paywalled': 'paywalled',
        'Notes': 'notes'
    }
    
    df = df.rename(columns=column_mapping)
    
    # Convert NaN to None for proper NULL handling
    df = df.where(pd.notnull(df), None)
    
    # Add an id column (auto-incrementing index)
    df.insert(0, 'id', range(1, len(df) + 1))
    
    # Create database engine
    engine = get_engine()
    
    # Drop existing table if it exists and create new one
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Load data into database using pandas (much faster than ORM)
    df.to_sql('retractions', engine, if_exists='append', index=False)
    
    print(f"Successfully loaded {len(df)} records into database.")


if __name__ == "__main__":
    # Load data when script is run directly
    csv_path = os.path.join(os.path.dirname(__file__), "..", "retraction_watch.csv")
    load_csv_to_db(csv_path)
