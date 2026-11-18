"""Tests for the AI Link Analysis API."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.utils.validators import validate_url, is_private_ip
from app.services.website_extractor import extract_content, clean_text, WebsiteContent


# ──────────────────────────────────────────────
# URL Validation Tests
# ──────────────────────────────────────────────


class TestURLValidation:
    """Tests for URL validation and SSRF protection."""

    def test_valid_https_url(self):
        """Valid HTTPS URL should pass validation."""
        result = validate_url("https://www.google.com")
        assert result == "https://www.google.com"

    def test_valid_http_url(self):
        """Valid HTTP URL should pass validation."""
        result = validate_url("http://example.com")
        assert result == "http://example.com"

    def test_empty_url_raises(self):
        """Empty URL should raise HTTPException."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("")
        assert exc_info.value.status_code == 400

    def test_no_scheme_raises(self):
        """URL without scheme should raise HTTPException."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("example.com")
        assert exc_info.value.status_code == 400

    def test_file_scheme_blocked(self):
        """File scheme should be blocked."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("file:///etc/passwd")
        assert exc_info.value.status_code == 400

    def test_ftp_scheme_blocked(self):
        """FTP scheme should be blocked."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("ftp://example.com")
        assert exc_info.value.status_code == 400

    def test_localhost_blocked(self):
        """Localhost should be blocked (SSRF)."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://localhost:8080")
        assert exc_info.value.status_code == 400

    def test_loopback_blocked(self):
        """127.0.0.1 should be blocked (SSRF)."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://127.0.0.1")
        assert exc_info.value.status_code == 400


class TestPrivateIPDetection:
    """Tests for private IP address detection."""

    def test_private_10_range(self):
        assert is_private_ip("10.0.0.1") is True

    def test_private_172_range(self):
        assert is_private_ip("172.16.0.1") is True

    def test_private_192_range(self):
        assert is_private_ip("192.168.1.1") is True

    def test_loopback(self):
        assert is_private_ip("127.0.0.1") is True

    def test_public_ip(self):
        assert is_private_ip("8.8.8.8") is False

    def test_public_ip_2(self):
        assert is_private_ip("142.250.185.14") is False

    def test_ipv6_loopback(self):
        assert is_private_ip("::1") is True


# ──────────────────────────────────────────────
# Content Extraction Tests
# ──────────────────────────────────────────────

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Company - Best Services</title>
    <meta name="description" content="Test Company provides excellent services.">
</head>
<body>
    <nav><a href="/">Home</a><a href="/about">About</a></nav>
    <h1>Welcome to Test Company</h1>
    <h2>Our Services</h2>
    <p>We provide web development, mobile apps, and cloud solutions for businesses worldwide.</p>
    <p>Our team of experts delivers high-quality software solutions.</p>
    <h3>Web Development</h3>
    <p>Custom websites and web applications built with modern technologies.</p>
    <script>console.log("this should be removed");</script>
    <style>.hidden { display: none; }</style>
    <footer>Copyright 2024 Test Company</footer>
</body>
</html>
"""


class TestContentExtraction:
    """Tests for website content extraction."""

    def test_extract_title(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert content.title == "Test Company - Best Services"

    def test_extract_meta_description(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert content.meta_description == "Test Company provides excellent services."

    def test_extract_headings(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert any("Welcome to Test Company" in h for h in content.headings)
        assert any("Our Services" in h for h in content.headings)

    def test_script_removed(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert "console.log" not in content.body_text

    def test_style_removed(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert ".hidden" not in content.body_text

    def test_body_text_extracted(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert "web development" in content.body_text.lower()

    def test_extraction_success(self):
        content = extract_content(SAMPLE_HTML, "https://test.com")
        assert content.extraction_success is True

    def test_empty_html(self):
        content = extract_content("", "https://test.com")
        assert content.extraction_success is True
        assert content.title == ""


class TestCleanText:
    """Tests for text cleaning utility."""

    def test_collapse_whitespace(self):
        result = clean_text("hello    world")
        assert "    " not in result

    def test_remove_short_lines(self):
        result = clean_text("ok\n\na longer line of text")
        assert "longer line" in result

    def test_strip_text(self):
        result = clean_text("  hello world  ")
        assert result == "hello world"


# ──────────────────────────────────────────────
# API Endpoint Tests
# ──────────────────────────────────────────────

MOCK_LLM_RESPONSE = {
    "brand": {
        "name": "Test Company",
        "category": "Technology",
        "summary": "A technology company.",
    },
    "competitor_analysis": {
        "brand_overview": "Test overview",
        "main_category": "Technology",
        "main_products_services": ["Web Development"],
        "competitors": [
            {
                "name": "Competitor A",
                "main_service": "Web Dev",
                "target_market": "SMBs",
                "key_strength": "Brand",
                "weakness": "Price",
                "opportunity": "Better pricing",
            }
        ],
        "brand_strengths": ["Innovation"],
        "opportunities": ["Expand market"],
    },
    "target_search_queries": [
        {
            "query": "best web dev company",
            "platforms": ["Google"],
            "intent": "Service Discovery",
            "business_relevance": "Direct match",
            "target_audience": "Business owners",
        }
    ],
    "seo_improvements": {
        "keywords": {
            "primary_keyword": "web development",
            "secondary_keywords": ["software"],
            "long_tail_keywords": ["best web dev company"],
            "business_keywords": ["technology services"],
        },
        "recommended_title": "Test Company - Web Development",
        "primary_keyword": "web development",
        "improved_title_structure": "Brand - Service",
        "meta_description": "Test meta desc",
        "business_summary": "A tech company",
        "meta_keywords": ["web", "dev"],
        "supporting_content": [
            {
                "type": "Blog Post",
                "title": "Top 10 Web Trends",
                "description": "Cover trends",
                "seo_benefit": "Traffic",
            }
        ],
    },
    "top_services": [
        {
            "name": "Web Development",
            "description": "Custom websites",
            "target_industry": "Technology",
            "target_customer": "SMBs",
            "main_benefit": "Online presence",
            "is_inferred": False,
        }
    ],
    "target_audience": {
        "primary_audience": [
            {"audience": "SMBs", "business_type": "Small Business", "requirement": "Website"}
        ],
        "secondary_audience": [],
        "industries": ["Technology"],
        "business_types": ["Startups"],
        "customer_needs": ["Online presence"],
        "geographical_focus": None,
        "customer_interests": ["Digital transformation"],
        "recommended_segments": ["Tech startups"],
    },
}


@pytest.mark.asyncio
async def test_root_dashboard_endpoint():
    """Root endpoint should serve the frontend dashboard."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "AI Link Analysis API" in response.text


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check should return status and available LLMs."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "available_llms" in data


@pytest.mark.asyncio
async def test_link_analysis_invalid_url():
    """Invalid URL should return 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/link-analysis",
            json={"url": "not-a-valid-url"},
        )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_link_analysis_ssrf_blocked():
    """Private network URLs should be blocked."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/link-analysis",
            json={"url": "http://localhost:8080/admin"},
        )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False


@pytest.mark.asyncio
async def test_link_analysis_missing_url():
    """Missing URL field should return 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/link-analysis",
            json={},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_link_analysis_success_mocked():
    """Full analysis with mocked extractor and LLM should succeed."""
    mock_content = WebsiteContent(
        url="https://example.com",
        title="Example",
        meta_description="Example site",
        headings=["H1: Welcome"],
        body_text="We provide web development services.",
        extraction_success=True,
    )

    mock_llm_response = MagicMock()
    mock_llm_response.success = True
    mock_llm_response.analysis = MOCK_LLM_RESPONSE
    mock_llm_response.provider = "Test"
    mock_llm_response.model = "test-model"
    mock_llm_response.response_time_ms = 100.0
    mock_llm_response.input_tokens = 500
    mock_llm_response.output_tokens = 1000
    mock_llm_response.estimated_cost_usd = 0.001
    mock_llm_response.error = None

    with (
        patch(
            "app.services.analysis_service.extract_website_content",
            new_callable=AsyncMock,
            return_value=mock_content,
        ),
        patch(
            "app.services.analysis_service.validate_url",
            return_value="https://example.com",
        ),
        patch(
            "app.services.analysis_service.get_provider",
        ) as mock_get_provider,
    ):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = mock_llm_response
        mock_get_provider.return_value = mock_provider

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/link-analysis",
                json={"url": "https://example.com"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["brand"]["name"] == "Test Company"
    assert "competitor_analysis" in data["analysis"]
    assert "target_search_queries" in data["analysis"]
    assert "seo_improvements" in data["analysis"]
    assert "top_services" in data["analysis"]
    assert "target_audience" in data["analysis"]
