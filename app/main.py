"""FastAPI application for AI-Powered Website Link Analysis.

Provides a REST API endpoint that analyzes websites using LLMs
to generate business intelligence, competitor analysis, SEO
recommendations, and audience insights.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 4000
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

from app.config import settings
from app.schemas import (
    LinkAnalysisRequest,
    LinkAnalysisResponse,
    ComparisonResponse,
    ErrorResponse,
)
from app.services.analysis_service import analyze_website, compare_llms
from app.services.llm.factory import get_available_providers


# ──────────────────────────────────────────────
# Application Lifespan
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    available = get_available_providers()
    print("=" * 60)
    print("  AI-Powered Website Link Analysis API")
    print("=" * 60)
    print(f"  Default LLM:    {settings.default_llm}")
    print(f"  Available LLMs: {', '.join(available) if available else 'NONE (set API keys!)'}")
    print(f"  API Docs:       http://{settings.host}:{settings.port}/docs")
    print("=" * 60)

    if not available:
        print("\n  ⚠️  WARNING: GROQ_API_KEY is not configured!")
        print("  Please set GROQ_API_KEY in your .env file.\n")

    yield
    # Shutdown
    print("\nShutting down AI Link Analysis API...")


# ──────────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────────

app = FastAPI(
    title="AI-Powered Website Link Analysis API",
    description=(
        "Analyze any website URL to get structured business intelligence including "
        "competitor analysis, search queries, SEO improvements, top services, "
        "and target audience identification — powered by LLMs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware for cross-origin access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Exception Handlers
# ──────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Return structured error responses for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            detail=f"HTTP {exc.status_code}",
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Catch-all handler for unexpected errors."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
        ).model_dump(),
    )


STATIC_DIR = Path(__file__).parent / "static"


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@app.get("/", tags=["Frontend"])
async def serve_dashboard():
    """Serve the interactive web frontend dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AI Link Analysis API is running. Visit /docs for documentation."}


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    available = get_available_providers()
    return {
        "status": "healthy",
        "available_llms": available,
        "default_llm": settings.default_llm,
    }


@app.post(
    "/link-analysis",
    response_model=None,
    tags=["Analysis"],
    summary="Analyze a website URL",
    description=(
        "Submit a website URL for comprehensive AI-powered analysis powered by Groq LPU silicon. "
        "Returns competitor insights, search queries, SEO recommendations, "
        "top services, and target audience identification."
    ),
    responses={
        200: {
            "description": "Successful analysis",
            "model": LinkAnalysisResponse,
        },
        400: {"description": "Invalid URL or validation error", "model": ErrorResponse},
        502: {"description": "Website fetch error", "model": ErrorResponse},
        503: {"description": "LLM service error", "model": ErrorResponse},
    },
)
async def link_analysis(
    request: LinkAnalysisRequest,
    model: str = Query(
        default="groq",
        description="LLM provider to use (defaults to 'groq')",
    ),
    compare: bool = Query(
        default=False,
        description="Run analysis with performance scorecard metrics",
    ),
):
    """Analyze a website URL and return structured business intelligence.

    **Single LLM Mode** (default):
    Returns analysis from one LLM provider with performance metrics.

    **Comparison Mode** (`compare=true`):
    Runs all configured LLMs in parallel and returns side-by-side
    results with metrics, costs, and a best-provider recommendation.
    """
    if compare:
        return await compare_llms(request.url)

    # Use specified model or fall back to configured default
    provider_name = model or settings.default_llm
    return await analyze_website(request.url, model=provider_name)


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
