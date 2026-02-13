"""
Define the canonical `Article` data contract for PMC processing pipelines.

The model is shared by API XML, FTP XML, and other acquisition paths. It uses
Pydantic validation plus field aliases so ingestion code can pass either
internal attribute names (e.g., `Title`) or normalized source keys
(e.g., `title`).
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Article(BaseModel):
    """
    Structured representation of one PMC article and review state.

    The DTO captures:
    - Ingestion metadata (URL, source channel, errors)
    - Core bibliographic fields (identifiers, title, journal, dates)
    - Content payload (abstract, keywords, full-text sections)
    - Multi-stage relevance/review annotations

    The model intentionally keeps optional fields to support partial extraction
    from heterogeneous PMC sources.
    """
    
    # ==================== Identifiers ====================
    url: Optional[str] = Field(None, description="URL of the PMC article")
    source: Optional[int] = Field(None, description="Source of the article: -1=Failed, 1=FTP, 2=XML_API, 3=Web")
    error_message: Optional[str] = Field(None, description="Error message if article retrieval failed")
    PMCID: Optional[int] = Field(None, description="PubMed Central ID as integer (e.g., 4049904 for PMC4049904)", alias="pmcid")
    PMID: Optional[int] = Field(None, description="PubMed ID as integer (e.g., 24256712)", alias="pmid")
    DOI: Optional[str] = Field(None, description="Digital Object Identifier", alias="doi")
    
    # ==================== Basic Information ====================
    Title: Optional[str] = Field(None, description="Article title", alias="title")
    Year: Optional[str] = Field(None, description="Year of publication", alias="year")
    type: Optional[str] = Field("article", description="Type of article (default: 'article')")
    
    # ==================== Authors and Affiliations ====================
    Authors: Optional[str] = Field(None, description="List of authors (comma-separated or formatted string)", alias="authors")
    corresponding_author: Optional[str] = Field(None, description="Corresponding author information")
    affiliations: Optional[List[str]] = Field(None, description="Author affiliations")
    
    # ==================== Journal Information ====================
    Journal: Optional[str] = Field(None, description="Journal name", alias="journal")
    Volume: Optional[int] = Field(None, description="Journal volume number", alias="volume")
    Issue: Optional[int] = Field(None, description="Journal issue number", alias="issue")
    
    # ==================== Dates ====================
    Publication_Date: Optional[datetime] = Field(None, description="Publication date", alias="publication_date")
    received_date: Optional[str] = Field(None, description="Date article was received")
    accepted_date: Optional[str] = Field(None, description="Date article was accepted")
    published_date: Optional[str] = Field(None, description="Date article was published")
    
    # ==================== Content ====================
    Abstract: Optional[str] = Field(None, description="Article abstract", alias="abstract")
    Keywords: Optional[str] = Field(None, description="Article keywords (comma-separated or formatted string)", alias="keywords")
    Full_Text_Sections: Optional[Dict[str, str]] = Field(None, description="Full text sections as dictionary (section_title: content)", alias="full_text_sections")
    
    # ==================== References and Citation ====================
    References: Optional[List[str]] = Field(None, description="List of article references", alias="references")
    citation: Optional[str] = Field(None, description="Formatted citation string")
    
    # ==================== Stage 1: Keyword-based Relevance Check ====================
    s1_is_relevant: Optional[bool] = Field(None, description="Stage 1: Whether article is relevant based on keyword check")
    s1_keyword: Optional[str] = Field(None, description="Stage 1: Keyword that caused flagging (if irrelevant)")
    
    # ==================== Stage 2: Title and Abstract Relevance Check ====================
    s2_is_checked: bool = Field(False, description="Stage 2: Whether title/abstract check has been performed")
    s2_is_relevant: Optional[bool] = Field(None, description="Stage 2: Whether article is relevant based on title/abstract")
    s2_reasoning: Optional[str] = Field(None, description="Stage 2: LLM reasoning for relevance decision")
    s2_check_datetime: Optional[datetime] = Field(None, description="Stage 2: Datetime when title/abstract check was performed")
    
    # ==================== Stage 3: Professional Detailed Review ====================
    s3_is_checked: bool = Field(False, description="Stage 3: Whether professional review has been performed")
    s3_Type: Optional[int] = Field(None, description="Stage 3: Flag value (0=white/safe, 1=yellow/caution, 2=red/irrelevant)", ge=0, le=2)
    s3_reasoning: Optional[str] = Field(None, description="Stage 3: Detailed reasoning for flag assignment")
    s3_review_datetime: Optional[datetime] = Field(None, description="Stage 3: Datetime when professional review was performed")
    
    class Config:
        """
        Pydantic configuration for alias and serialization behavior.

        Notes:
            - ``populate_by_name`` accepts both canonical and alias keys.
            - ``json_encoders`` normalizes datetime values to ISO 8601.
            - ``json_schema_extra`` provides a representative payload sample.
        """
        populate_by_name = True  # Allow both field name and alias
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        json_schema_extra = {
            "example": {
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4049904/",
                "source": 3,
                "PMCID": 4049904,
                "PMID": 24256712,
                "DOI": "10.4161/bioe.26887",
                "Title": "A versatile Escherichia coli strain for identification of biotin transporters",
                "type": "article",
                "Authors": "Friedrich Finkenwirth, Franziska Kirsch, Thomas Eitinger",
                "Journal": "Bioengineered",
                "Volume": 5,
                "Issue": 2,
                "Publication_Date": "2013 Nov 5",
                "Abstract": "Biotin is an essential cofactor...",
                "Keywords": "biotin bioassay, ECF transporter, BioY",
                "Full_Text_Sections": {
                    "Abstract": "Biotin is an essential cofactor...",
                    "Introduction": "...",
                    "Methods": "..."
                },
                "s1_is_relevant": True,
                "s1_keyword": None,
                "s2_is_checked": True,
                "s2_is_relevant": True,
                "s2_reasoning": "Article discusses biotin transporters which is relevant to the research topic.",
                "s2_check_datetime": "2024-01-15T10:30:00",
                "s3_is_checked": True,
                "s3_Type": 0,
                "s3_reasoning": "Article is highly relevant and well-structured.",
                "s3_review_datetime": "2024-01-15T14:20:00"
            }
        }
