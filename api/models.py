"""
Pydantic models for request and response validation.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date


class RetractionBase(BaseModel):
    """Base model for retraction data."""
    record_id: int = Field(..., description="Internal identifier from Retraction Watch")
    title: str = Field(..., description="The title of the retracted or updated content")
    subject: Optional[str] = Field(None, description="The subject area of the publication")
    institution: Optional[str] = Field(None, description="Author affiliations")
    journal: str = Field(..., description="The source in which the research was published")
    publisher: Optional[str] = Field(None, description="The organisation responsible for publication")
    country: Optional[str] = Field(None, description="Countries included in author affiliations")
    author: Optional[str] = Field(None, description="A list of author names (semicolon-separated)")
    urls: Optional[str] = Field(None, description="Links to relevant pages on the Retraction Watch website")
    article_type: Optional[str] = Field(None, description="The content type")
    retraction_date: Optional[str] = Field(None, description="The date of the published retraction")
    retraction_doi: Optional[str] = Field(None, description="The DOI of the published retraction")
    retraction_pubmed_id: Optional[str] = Field(None, description="PubMED ID of the published retraction")
    original_paper_date: Optional[str] = Field(None, description="The publication date of the retracted content")
    original_paper_doi: Optional[str] = Field(None, description="The DOI of the retracted publication")
    original_paper_pubmed_id: Optional[str] = Field(None, description="PubMED ID of the original publication")
    retraction_nature: Optional[str] = Field(None, description="The type of update notice")
    reason: Optional[str] = Field(None, description="A list of reasons for retraction (semicolon-separated)")
    paywalled: Optional[str] = Field(None, description="Is a fee required to access the retraction notice")
    notes: Optional[str] = Field(None, description="Additional comments about the retraction")

    class Config:
        from_attributes = True


class Retraction(RetractionBase):
    """Complete retraction model."""
    pass


class RetractionList(BaseModel):
    """Paginated list of retractions."""
    total: int = Field(..., description="Total number of retractions matching the query")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    retractions: List[Retraction] = Field(..., description="List of retractions")


class Author(BaseModel):
    """Author model."""
    name: str = Field(..., description="Author name")
    retraction_count: int = Field(..., description="Number of retractions for this author")


class AuthorList(BaseModel):
    """List of authors."""
    total: int = Field(..., description="Total number of authors")
    authors: List[Author] = Field(..., description="List of authors")


class Journal(BaseModel):
    """Journal model."""
    name: str = Field(..., description="Journal name")
    retraction_count: int = Field(..., description="Number of retractions for this journal")


class JournalList(BaseModel):
    """List of journals."""
    total: int = Field(..., description="Total number of journals")
    journals: List[Journal] = Field(..., description="List of journals")
