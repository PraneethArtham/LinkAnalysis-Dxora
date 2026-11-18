"""Pydantic models for API request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional


# ──────────────────────────────────────────────
# Request
# ──────────────────────────────────────────────

class LinkAnalysisRequest(BaseModel):
    """Request body for /link-analysis endpoint."""
    url: str = Field(..., description="Website URL to analyze", examples=["https://example.com"])


# ──────────────────────────────────────────────
# Section 1: Competitor Analysis
# ──────────────────────────────────────────────

class Competitor(BaseModel):
    """Individual competitor details."""
    name: str = Field(..., description="Competitor brand name")
    main_service: str = Field(..., description="Primary service offered")
    target_market: str = Field(..., description="Target market segment")
    key_strength: str = Field(..., description="Main competitive advantage")
    weakness: str = Field(..., description="Gap or weakness")
    opportunity: str = Field(..., description="Opportunity for the analyzed brand")


class CompetitorAnalysis(BaseModel):
    """Full competitor analysis section."""
    brand_overview: str = Field(..., description="Overview of the analyzed brand")
    main_category: str = Field(default="", description="Primary business category")
    main_products_services: list[str] = Field(default_factory=list, description="Main products/services")
    competitors: list[Competitor] = Field(default_factory=list, description="Identified competitors (min 3)")
    brand_strengths: list[str] = Field(default_factory=list, description="Brand's competitive advantages")
    opportunities: list[str] = Field(default_factory=list, description="Market positioning improvements")


# ──────────────────────────────────────────────
# Section 2: Target Search Queries
# ──────────────────────────────────────────────

class SearchQuery(BaseModel):
    """Individual search query recommendation."""
    query: str = Field(..., description="The search query text")
    platforms: list[str] = Field(..., description="Relevant platforms (Google, Facebook, Instagram, LinkedIn, X)")
    intent: str = Field(..., description="Search intent")
    business_relevance: str = Field(default="", description="Why this query matters")
    target_audience: str = Field(default="", description="Who would search this")


# ──────────────────────────────────────────────
# Section 3: SEO Improvements
# ──────────────────────────────────────────────

class KeywordRecommendations(BaseModel):
    """Keyword recommendations for SEO."""
    primary_keyword: str = Field(..., description="Main target keyword")
    secondary_keywords: list[str] = Field(default_factory=list)
    long_tail_keywords: list[str] = Field(default_factory=list)
    business_keywords: list[str] = Field(default_factory=list)


class SupportingContent(BaseModel):
    """Suggested supporting content for SEO."""
    type: str = Field(..., description="Content type (Blog Post, FAQ, Landing Page, etc.)")
    title: str = Field(default="", description="Suggested title")
    description: str = Field(default="", description="What the content should cover")
    seo_benefit: str = Field(default="", description="How it helps search visibility")


class SEOImprovements(BaseModel):
    """Full SEO improvements section."""
    keywords: KeywordRecommendations = Field(default=None)
    primary_keyword: str = Field(default="", description="Primary keyword")
    secondary_keywords: list[str] = Field(default_factory=list)
    recommended_title: str = Field(default="", description="Optimized SEO title")
    improved_title_structure: str = Field(default="", description="Title structure explanation")
    meta_description: str = Field(default="", description="Optimized meta description")
    business_summary: str = Field(default="", description="Human-friendly business summary")
    meta_keywords: list[str] = Field(default_factory=list)
    supporting_content: list[SupportingContent] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Section 4: Top Services
# ──────────────────────────────────────────────

class Service(BaseModel):
    """Individual service identified from the website."""
    name: str = Field(..., description="Service name")
    description: str = Field(..., description="Short service explanation")
    target_industry: str = Field(default="", description="Relevant industry")
    target_customer: str = Field(default="", description="Potential customer type")
    main_benefit: str = Field(default="", description="Key benefit for customers")
    is_inferred: bool = Field(default=False, description="True if inferred, false if from website content")


# ──────────────────────────────────────────────
# Section 5: Target Audience
# ──────────────────────────────────────────────

class AudienceSegment(BaseModel):
    """Individual audience segment."""
    audience: str = Field(..., description="Audience label")
    business_type: str = Field(default="", description="Type of business")
    requirement: str = Field(default="", description="Primary requirement")


class TargetAudience(BaseModel):
    """Full target audience section."""
    primary_audience: list[AudienceSegment] = Field(default_factory=list)
    secondary_audience: list[AudienceSegment] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list, description="Relevant industry segments")
    business_types: list[str] = Field(default_factory=list)
    customer_needs: list[str] = Field(default_factory=list)
    geographical_focus: Optional[str] = Field(default=None, description="Location focus if identifiable")
    customer_interests: list[str] = Field(default_factory=list)
    recommended_segments: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Brand Info
# ──────────────────────────────────────────────

class BrandInfo(BaseModel):
    """Extracted brand information."""
    name: str = Field(..., description="Brand/company name")
    category: str = Field(default="", description="Main business category")
    summary: str = Field(default="", description="Short business summary")


# ──────────────────────────────────────────────
# Analysis Result (all 5 sections combined)
# ──────────────────────────────────────────────

class AnalysisResult(BaseModel):
    """Combined analysis result containing all five sections."""
    competitor_analysis: CompetitorAnalysis
    target_search_queries: list[SearchQuery] = Field(default_factory=list)
    seo_improvements: SEOImprovements
    top_services: list[Service] = Field(default_factory=list)
    target_audience: TargetAudience


# ──────────────────────────────────────────────
# LLM Metrics
# ──────────────────────────────────────────────

class LLMMetrics(BaseModel):
    """Performance and cost metrics from an LLM call."""
    provider: str
    model: str
    response_time_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None


# ──────────────────────────────────────────────
# API Responses
# ──────────────────────────────────────────────

class LinkAnalysisResponse(BaseModel):
    """Standard API response with single LLM analysis."""
    success: bool = True
    website: str
    brand: BrandInfo
    analysis: AnalysisResult
    llm_metrics: Optional[LLMMetrics] = None


class ComparisonEntry(BaseModel):
    """Single LLM result in a comparison response."""
    provider: str
    model: str
    response_time_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    analysis: Optional[AnalysisResult] = None
    error: Optional[str] = None


class ComparisonResponse(BaseModel):
    """API response with multi-LLM comparison."""
    success: bool = True
    website: str
    brand: BrandInfo
    best_recommendation: str
    comparison: dict[str, ComparisonEntry]
    analysis: AnalysisResult  # From the best/recommended provider


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None
