"""Main analysis orchestration service.

Coordinates the full pipeline: URL validation → content extraction →
LLM analysis → response building. Supports both single-provider and
multi-provider comparison modes.
"""

from typing import Optional
import time

from fastapi import HTTPException

# In-memory cache for ultra-fast repeat responses
# Key: (url, model_or_compare_mode), Value: (timestamp, response_obj)
_RESPONSE_CACHE: dict[str, tuple[float, any]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache

from app.services.website_extractor import extract_website_content, WebsiteContent
from app.services.llm.factory import (
    get_provider,
    get_available_providers,
)
from app.services.llm.base import LLMResponse
from app.utils.validators import validate_url
from app.schemas import (
    BrandInfo,
    AnalysisResult,
    CompetitorAnalysis,
    Competitor,
    SearchQuery,
    SEOImprovements,
    KeywordRecommendations,
    SupportingContent,
    Service,
    TargetAudience,
    AudienceSegment,
    LLMMetrics,
    LinkAnalysisResponse,
    ComparisonEntry,
    ComparisonResponse,
)


# ──────────────────────────────────────────────
# Analysis Prompt Template
# ──────────────────────────────────────────────

ANALYSIS_PROMPT = """You are an expert business analyst specializing in website analysis, competitive intelligence, SEO optimization, and digital marketing strategy.

Analyze the following website content and generate a comprehensive business analysis report.

=== WEBSITE INFORMATION ===
URL: {url}
Title: {title}
Meta Description: {meta_description}

=== HEADINGS ===
{headings}

=== PAGE LINKS / NAVIGATION ===
{links}

=== WEBSITE CONTENT ===
{content}

=== REQUIRED OUTPUT ===

Generate a detailed JSON analysis with ALL of the following sections. Return ONLY valid JSON.

{{
  "brand": {{
    "name": "Brand or company name extracted from the website",
    "category": "Main business category",
    "summary": "1-2 sentence business summary"
  }},
  "competitor_analysis": {{
    "brand_overview": "Detailed overview of the brand's business based on website content",
    "main_category": "Primary business category",
    "main_products_services": ["list of main products or services offered"],
    "competitors": [
      {{
        "name": "Real competitor company name",
        "main_service": "Their primary service",
        "target_market": "Their target market",
        "key_strength": "Their main competitive advantage",
        "weakness": "A gap or weakness",
        "opportunity": "How the analyzed brand can capitalize"
      }}
    ],
    "brand_strengths": ["list of the analyzed brand's competitive advantages"],
    "opportunities": ["list of market positioning improvements"]
  }},
  "target_search_queries": [
    {{
      "query": "Search query text",
      "platforms": ["Platform name - one of: Google, Facebook, Instagram, LinkedIn, X (Twitter)"],
      "intent": "Search intent (Service Discovery, B2B Search, Inspiration, etc.)",
      "business_relevance": "Why this query is relevant",
      "target_audience": "Who would search this"
    }}
  ],
  "seo_improvements": {{
    "keywords": {{
      "primary_keyword": "Main target keyword",
      "secondary_keywords": ["3-5 secondary keywords"],
      "long_tail_keywords": ["3-5 long-tail keyword phrases"],
      "business_keywords": ["3-5 industry-specific keywords"]
    }},
    "recommended_title": "Optimized SEO title (50-60 characters)",
    "primary_keyword": "Primary keyword used in title",
    "improved_title_structure": "Explanation of the title structure",
    "meta_description": "Optimized meta description (150-160 characters)",
    "business_summary": "Short human-friendly business summary",
    "meta_keywords": ["relevant keywords for meta tags"],
    "supporting_content": [
      {{
        "type": "Content type (Service Landing Page, Blog Post, FAQ, Location Page, etc.)",
        "title": "Suggested content title",
        "description": "What the content should cover",
        "seo_benefit": "How it improves search visibility"
      }}
    ]
  }},
  "top_services": [
    {{
      "name": "Service name",
      "description": "Short 1-2 sentence description",
      "target_industry": "Relevant industry",
      "target_customer": "Potential customer type",
      "main_benefit": "Key benefit for customers",
      "is_inferred": false
    }}
  ],
  "target_audience": {{
    "primary_audience": [
      {{"audience": "Audience label", "business_type": "Type of business", "requirement": "Primary need"}}
    ],
    "secondary_audience": [
      {{"audience": "Audience label", "business_type": "Type of business", "requirement": "Primary need"}}
    ],
    "industries": ["Relevant industry segments"],
    "business_types": ["Relevant business types"],
    "customer_needs": ["Customer needs and challenges"],
    "geographical_focus": "Location focus if identifiable from the website, otherwise null",
    "customer_interests": ["Potential customer interests"],
    "recommended_segments": ["Recommended marketing audience segments"]
  }}
}}

=== RULES ===
1. Base ALL analysis on the actual website content provided above.
2. Identify at least 3 REAL competitors (well-known companies in the same industry).
3. Generate exactly 5 search queries, each targeting a DIFFERENT platform (Google, Facebook, Instagram, LinkedIn, X).
4. Identify exactly 5 services. Mark any inferred services with "is_inferred": true.
5. Do NOT invent search volumes, rankings, or traffic data.
6. Suggest at least 5 supporting content ideas for SEO.
7. Competitor information should be based on well-known industry players.
8. Return ONLY valid JSON — no markdown, no explanations, no code blocks."""


def build_prompt(content: WebsiteContent) -> str:
    """Build the analysis prompt from extracted website content.

    Args:
        content: Extracted website content.

    Returns:
        Formatted prompt string ready for LLM consumption.
    """
    headings_text = "\n".join(content.headings) if content.headings else "No headings found"
    links_text = ", ".join(content.links) if content.links else "No navigation links found"

    return ANALYSIS_PROMPT.format(
        url=content.url,
        title=content.title or "No title found",
        meta_description=content.meta_description or "No meta description found",
        headings=headings_text,
        links=links_text,
        content=content.body_text or "No content could be extracted from this website",
    )


# ──────────────────────────────────────────────
# Response Builders
# ──────────────────────────────────────────────

def _safe_get(data: dict, *keys, default=None):
    """Safely traverse nested dict keys."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current if current is not None else default


def build_brand_info(analysis: dict) -> BrandInfo:
    """Extract BrandInfo from LLM analysis output."""
    brand_data = analysis.get("brand", {})
    return BrandInfo(
        name=brand_data.get("name", "Unknown"),
        category=brand_data.get("category", ""),
        summary=brand_data.get("summary", ""),
    )


def build_analysis_result(analysis: dict) -> AnalysisResult:
    """Convert raw LLM JSON output into structured AnalysisResult."""

    # --- Competitor Analysis ---
    ca_data = analysis.get("competitor_analysis", {})
    competitors = []
    for c in ca_data.get("competitors", []):
        competitors.append(Competitor(
            name=c.get("name", "Unknown"),
            main_service=c.get("main_service", ""),
            target_market=c.get("target_market", ""),
            key_strength=c.get("key_strength", ""),
            weakness=c.get("weakness", ""),
            opportunity=c.get("opportunity", ""),
        ))
    competitor_analysis = CompetitorAnalysis(
        brand_overview=ca_data.get("brand_overview", ""),
        main_category=ca_data.get("main_category", ""),
        main_products_services=ca_data.get("main_products_services", []),
        competitors=competitors,
        brand_strengths=ca_data.get("brand_strengths", []),
        opportunities=ca_data.get("opportunities", []),
    )

    # --- Search Queries ---
    search_queries = []
    for sq in analysis.get("target_search_queries", []):
        search_queries.append(SearchQuery(
            query=sq.get("query", ""),
            platforms=sq.get("platforms", []),
            intent=sq.get("intent", ""),
            business_relevance=sq.get("business_relevance", ""),
            target_audience=sq.get("target_audience", ""),
        ))

    # --- SEO Improvements ---
    seo_data = analysis.get("seo_improvements", {})
    kw_data = seo_data.get("keywords", {})
    keywords = KeywordRecommendations(
        primary_keyword=kw_data.get("primary_keyword", ""),
        secondary_keywords=kw_data.get("secondary_keywords", []),
        long_tail_keywords=kw_data.get("long_tail_keywords", []),
        business_keywords=kw_data.get("business_keywords", []),
    )
    supporting = []
    for sc in seo_data.get("supporting_content", []):
        supporting.append(SupportingContent(
            type=sc.get("type", ""),
            title=sc.get("title", ""),
            description=sc.get("description", ""),
            seo_benefit=sc.get("seo_benefit", ""),
        ))
    seo_improvements = SEOImprovements(
        keywords=keywords,
        primary_keyword=seo_data.get("primary_keyword", kw_data.get("primary_keyword", "")),
        secondary_keywords=seo_data.get("secondary_keywords", kw_data.get("secondary_keywords", [])),
        recommended_title=seo_data.get("recommended_title", ""),
        improved_title_structure=seo_data.get("improved_title_structure", ""),
        meta_description=seo_data.get("meta_description", ""),
        business_summary=seo_data.get("business_summary", ""),
        meta_keywords=seo_data.get("meta_keywords", []),
        supporting_content=supporting,
    )

    # --- Top Services ---
    services = []
    for svc in analysis.get("top_services", []):
        services.append(Service(
            name=svc.get("name", "Unknown Service"),
            description=svc.get("description", ""),
            target_industry=svc.get("target_industry", ""),
            target_customer=svc.get("target_customer", ""),
            main_benefit=svc.get("main_benefit", ""),
            is_inferred=svc.get("is_inferred", False),
        ))

    # --- Target Audience ---
    ta_data = analysis.get("target_audience", {})
    primary_aud = [
        AudienceSegment(
            audience=a.get("audience", ""),
            business_type=a.get("business_type", ""),
            requirement=a.get("requirement", ""),
        )
        for a in ta_data.get("primary_audience", [])
    ]
    secondary_aud = [
        AudienceSegment(
            audience=a.get("audience", ""),
            business_type=a.get("business_type", ""),
            requirement=a.get("requirement", ""),
        )
        for a in ta_data.get("secondary_audience", [])
    ]
    target_audience = TargetAudience(
        primary_audience=primary_aud,
        secondary_audience=secondary_aud,
        industries=ta_data.get("industries", []),
        business_types=ta_data.get("business_types", []),
        customer_needs=ta_data.get("customer_needs", []),
        geographical_focus=ta_data.get("geographical_focus"),
        customer_interests=ta_data.get("customer_interests", []),
        recommended_segments=ta_data.get("recommended_segments", []),
    )

    return AnalysisResult(
        competitor_analysis=competitor_analysis,
        target_search_queries=search_queries,
        seo_improvements=seo_improvements,
        top_services=services,
        target_audience=target_audience,
    )


def build_llm_metrics(response: LLMResponse) -> LLMMetrics:
    """Convert LLMResponse metrics into LLMMetrics schema."""
    return LLMMetrics(
        provider=response.provider,
        model=response.model,
        response_time_ms=response.response_time_ms,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        estimated_cost_usd=response.estimated_cost_usd,
    )


# ──────────────────────────────────────────────
# Main Analysis Functions
# ──────────────────────────────────────────────

async def analyze_website(url: str, model: str = "groq") -> LinkAnalysisResponse:
    """Analyze a website using the Groq LPU model.

    Args:
        url: Website URL to analyze.
        model: LLM provider name (defaults to 'groq').

    Returns:
        LinkAnalysisResponse with structured analysis.

    Raises:
        HTTPException: On validation, extraction, or LLM errors.
    """
    # Step 1: Validate URL (SSRF protection)
    validated_url = validate_url(url)

    # Check cache for fast repeat requests
    cache_key = f"single:{validated_url}:{model}"
    if cache_key in _RESPONSE_CACHE:
        cached_time, cached_result = _RESPONSE_CACHE[cache_key]
        if time.time() - cached_time < CACHE_TTL_SECONDS:
            return cached_result

    # Step 2: Extract website content
    content = await extract_website_content(validated_url)
    if not content.extraction_success:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to extract website content: {content.error}",
        )

    # Step 3: Build prompt
    prompt = build_prompt(content)

    # Step 4: Get LLM analysis
    try:
        provider = get_provider(model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    response = await provider.generate(prompt)

    if not response.success:
        raise HTTPException(
            status_code=503,
            detail=f"LLM analysis failed: {response.error}",
        )

    # Step 5: Build structured response
    brand = build_brand_info(response.analysis)
    analysis = build_analysis_result(response.analysis)
    metrics = build_llm_metrics(response)

    result = LinkAnalysisResponse(
        success=True,
        website=validated_url,
        brand=brand,
        analysis=analysis,
        llm_metrics=metrics,
    )
    _RESPONSE_CACHE[cache_key] = (time.time(), result)
    return result


async def compare_llms(url: str) -> ComparisonResponse:
    """Analyze a website using all available LLMs and compare results.

    Runs all configured LLM providers in parallel and returns
    a comparison with metrics and the best recommendation.

    Args:
        url: Website URL to analyze.

    Returns:
        ComparisonResponse with all provider results and recommendation.

    Raises:
        HTTPException: On validation or extraction errors.
    """
    # Step 1: Validate URL
    validated_url = validate_url(url)

    # Check cache for fast repeat comparisons
    cache_key = f"compare:{validated_url}"
    if cache_key in _RESPONSE_CACHE:
        cached_time, cached_result = _RESPONSE_CACHE[cache_key]
        if time.time() - cached_time < CACHE_TTL_SECONDS:
            return cached_result

    # Step 2: Check available providers
    available = get_available_providers()
    if not available:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured. Please set GROQ_API_KEY in .env",
        )

    # Step 3: Extract website content
    content = await extract_website_content(validated_url)
    if not content.extraction_success:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to extract website content: {content.error}",
        )

    # Step 4: Build prompt
    prompt = build_prompt(content)

    # Step 5: Run Groq provider
    provider = get_provider("groq")
    resp = await provider.generate(prompt)

    if not resp.success:
        raise HTTPException(
            status_code=503,
            detail=f"Groq analysis failed: {resp.error}",
        )

    brand = build_brand_info(resp.analysis)
    analysis = build_analysis_result(resp.analysis)

    comparison_entries = {
        "groq": ComparisonEntry(
            provider=resp.provider,
            model=resp.model,
            response_time_ms=resp.response_time_ms,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            estimated_cost_usd=resp.estimated_cost_usd,
            analysis=analysis,
        )
    }

    final_response = ComparisonResponse(
        success=True,
        website=validated_url,
        brand=brand,
        best_recommendation="groq",
        comparison=comparison_entries,
        analysis=analysis,
    )
    _RESPONSE_CACHE[cache_key] = (time.time(), final_response)
    return final_response
