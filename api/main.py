"""
FastAPI application for Retraction Watch data API.

This API provides endpoints for querying retraction data including:
- Searching retractions by various filters
- Retrieving specific retraction details
- Listing authors and journals

The API complies with OpenAPI standards and includes automatic Swagger documentation.
"""
from fastapi import FastAPI, HTTPException, Query
from typing import Optional, List
from sqlalchemy import func, or_
from api.database import get_session, RetractionDB, init_db
from api.models import Retraction, RetractionList, Author, AuthorList, Journal, JournalList
import re

# Initialize FastAPI app
app = FastAPI(
    title="Retraction Watch API",
    description="""
    API for querying the Retraction Watch database containing information about 
    retracted research papers, corrections, and expressions of concern.
    
    ## Features
    
    * **Query retractions** - Search by author, year, journal with pagination
    * **Get retraction details** - Retrieve specific retraction by ID
    * **List authors** - Get all authors with retraction counts
    * **List journals** - Get journals with retraction statistics
    
    ## Data Source
    
    Data is sourced from the Retraction Watch database, maintained by Crossref.
    The database is updated daily and includes retractions from publisher websites.
    """,
    version="1.0.0",
    contact={
        "name": "Retraction Watch API",
        "url": "https://github.com/ToruOkadaOi/retraction_watch_data",
    },
    license_info={
        "name": "Data License",
        "url": "https://retractionwatch.com/",
    },
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


@app.get("/", tags=["General"])
async def root():
    """
    Root endpoint providing API information.
    
    Returns basic information about the API and links to documentation.
    """
    return {
        "message": "Welcome to the Retraction Watch API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "endpoints": {
            "retractions": "/retractions",
            "retraction_by_id": "/retractions/{id}",
            "authors": "/authors",
            "journals": "/journals"
        }
    }


@app.get(
    "/retractions",
    response_model=RetractionList,
    tags=["Retractions"],
    summary="List and filter retractions",
    description="""
    Query all retractions with optional filtering by author, year, and journal.
    
    Results are paginated. Use the page and page_size parameters to control pagination.
    
    **Filters:**
    - `author`: Filter by author name (partial match, case-insensitive)
    - `year`: Filter by retraction year (format: YYYY)
    - `journal`: Filter by journal name (partial match, case-insensitive)
    
    **Pagination:**
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)
    """
)
async def get_retractions(
    author: Optional[str] = Query(None, description="Filter by author name (partial match)"),
    year: Optional[int] = Query(None, description="Filter by retraction year (e.g., 2021)"),
    journal: Optional[str] = Query(None, description="Filter by journal name (partial match)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)")
):
    """Get list of retractions with optional filters and pagination."""
    session = get_session()
    
    try:
        # Build query
        query = session.query(RetractionDB)
        
        # Apply filters
        if author:
            query = query.filter(RetractionDB.author.ilike(f"%{author}%"))
        
        if year:
            # Extract year from retraction_date (format: M/D/YYYY H:MM)
            query = query.filter(RetractionDB.retraction_date.like(f"%{year}%"))
        
        if journal:
            query = query.filter(RetractionDB.journal.ilike(f"%{journal}%"))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * page_size
        results = query.offset(offset).limit(page_size).all()
        
        # Convert to response model
        retractions = []
        for r in results:
            retractions.append(Retraction(
                record_id=r.record_id,
                title=r.title,
                subject=r.subject,
                institution=r.institution,
                journal=r.journal,
                publisher=r.publisher,
                country=r.country,
                author=r.author,
                urls=r.urls,
                article_type=r.article_type,
                retraction_date=r.retraction_date,
                retraction_doi=r.retraction_doi,
                retraction_pubmed_id=r.retraction_pubmed_id,
                original_paper_date=r.original_paper_date,
                original_paper_doi=r.original_paper_doi,
                original_paper_pubmed_id=r.original_paper_pubmed_id,
                retraction_nature=r.retraction_nature,
                reason=r.reason,
                paywalled=r.paywalled,
                notes=r.notes
            ))
        
        return RetractionList(
            total=total,
            page=page,
            page_size=page_size,
            retractions=retractions
        )
    
    finally:
        session.close()


@app.get(
    "/retractions/{record_id}",
    response_model=Retraction,
    tags=["Retractions"],
    summary="Get retraction by ID",
    description="""
    Retrieve detailed information about a specific retraction using its Record ID.
    
    The Record ID is the internal identifier from Retraction Watch.
    """
)
async def get_retraction_by_id(record_id: int):
    """Get a specific retraction by its record ID."""
    session = get_session()
    
    try:
        result = session.query(RetractionDB).filter(RetractionDB.record_id == record_id).first()
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Retraction with ID {record_id} not found")
        
        return Retraction(
            record_id=result.record_id,
            title=result.title,
            subject=result.subject,
            institution=result.institution,
            journal=result.journal,
            publisher=result.publisher,
            country=result.country,
            author=result.author,
            urls=result.urls,
            article_type=result.article_type,
            retraction_date=result.retraction_date,
            retraction_doi=result.retraction_doi,
            retraction_pubmed_id=result.retraction_pubmed_id,
            original_paper_date=result.original_paper_date,
            original_paper_doi=result.original_paper_doi,
            original_paper_pubmed_id=result.original_paper_pubmed_id,
            retraction_nature=result.retraction_nature,
            reason=result.reason,
            paywalled=result.paywalled,
            notes=result.notes
        )
    
    finally:
        session.close()


@app.get(
    "/authors",
    response_model=AuthorList,
    tags=["Authors"],
    summary="List authors with retraction counts",
    description="""
    Get a list of all authors in the dataset along with the number of retractions
    associated with each author.
    
    Authors are extracted from the author field (semicolon-separated list).
    Results are sorted by retraction count (descending).
    
    **Pagination:**
    - `limit`: Maximum number of authors to return (default: 100, max: 1000)
    """
)
async def get_authors(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of authors to return")
):
    """Get list of authors with retraction counts."""
    session = get_session()
    
    try:
        # Get all retractions with authors
        results = session.query(RetractionDB.author).filter(RetractionDB.author.isnot(None)).all()
        
        # Parse authors (semicolon-separated) and count
        author_counts = {}
        for row in results:
            if row.author:
                # Split by semicolon and clean up
                authors = [a.strip() for a in row.author.split(';') if a.strip()]
                for author in authors:
                    author_counts[author] = author_counts.get(author, 0) + 1
        
        # Sort by count (descending) and limit
        sorted_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        
        authors = [Author(name=name, retraction_count=count) for name, count in sorted_authors]
        
        return AuthorList(
            total=len(author_counts),
            authors=authors
        )
    
    finally:
        session.close()


@app.get(
    "/journals",
    response_model=JournalList,
    tags=["Journals"],
    summary="List journals with retraction counts",
    description="""
    Get a list of all journals in the dataset along with the number of retractions
    for each journal.
    
    Results are sorted by retraction count (descending).
    
    **Pagination:**
    - `limit`: Maximum number of journals to return (default: 100, max: 1000)
    """
)
async def get_journals(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of journals to return")
):
    """Get list of journals with retraction counts."""
    session = get_session()
    
    try:
        # Query journals with counts
        results = (
            session.query(
                RetractionDB.journal,
                func.count(RetractionDB.id).label('count')
            )
            .filter(RetractionDB.journal.isnot(None))
            .group_by(RetractionDB.journal)
            .order_by(func.count(RetractionDB.id).desc())
            .limit(limit)
            .all()
        )
        
        journals = [Journal(name=name, retraction_count=count) for name, count in results]
        
        # Get total journal count
        total = session.query(func.count(func.distinct(RetractionDB.journal))).scalar()
        
        return JournalList(
            total=total,
            journals=journals
        )
    
    finally:
        session.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
