"""API Gateway FastAPI application.

Provides the public-facing REST API with authentication, rate limiting,
request validation, and forwarding to the Correction Engine.
"""

import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

CORRECTION_ENGINE_URL = os.environ.get(
    "CORRECTION_ENGINE_URL", "http://correction-engine:8081"
)
API_KEY = os.environ.get("API_KEY", "changeme")
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
MAX_TEXT_LENGTH = 50_000


# ─── Request/Response Models ──────────────────────────────────────────────────


class CorrectionRequest(BaseModel):
    """Request body for POST /api/v1/correct."""

    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LENGTH)
    language: Optional[str] = None
    options: Optional[dict] = None

    @field_validator("text")
    @classmethod
    def text_not_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Text must not be empty or whitespace-only")
        return v


class BatchRequest(BaseModel):
    """Request body for POST /api/v1/batch."""

    file_path: str
    options: Optional[dict] = None


class HealthResponse(BaseModel):
    """Response for GET /api/v1/health."""

    status: str
    llm_ready: str


class ErrorBody(BaseModel):
    """Structured error response."""

    code: str
    message: str
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Error response wrapper."""

    error: ErrorBody


# ─── Rate Limiter ─────────────────────────────────────────────────────────────


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter.

    Tracks request timestamps per API key and enforces a maximum
    number of requests within a 60-second sliding window.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        """Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed per window.
            window_seconds: Window size in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key.

        Args:
            key: The API key or identifier.

        Returns:
            True if the request is allowed.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]

        # Check limit
        if len(self._requests[key]) >= self.max_requests:
            return False

        # Record this request
        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for a key in the current window.

        Args:
            key: The API key or identifier.

        Returns:
            Number of remaining allowed requests.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]

        return max(0, self.max_requests - len(self._requests[key]))


# ─── Global State ─────────────────────────────────────────────────────────────

rate_limiter = SlidingWindowRateLimiter(
    max_requests=RATE_LIMIT_PER_MINUTE, window_seconds=60
)
http_client: Optional[httpx.AsyncClient] = None


# ─── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize and cleanup HTTP client."""
    global http_client
    http_client = httpx.AsyncClient(
        base_url=CORRECTION_ENGINE_URL,
        timeout=120.0,
    )
    logger.info(
        f"API Gateway started, forwarding to {CORRECTION_ENGINE_URL}"
    )
    yield
    if http_client:
        await http_client.aclose()
    logger.info("API Gateway shut down")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Auto-Correction API Gateway",
    description="External-facing REST API for the Local Auto-Correction Tool",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Authentication Middleware ────────────────────────────────────────────────


def _validate_api_key(request: Request) -> Optional[str]:
    """Validate the API key from request headers.

    Args:
        request: The incoming request.

    Returns:
        The API key if valid, None otherwise.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    if api_key != API_KEY:
        return None
    return api_key


@app.middleware("http")
async def auth_and_rate_limit_middleware(request: Request, call_next):
    """Middleware for authentication and rate limiting.

    Skips auth for health endpoint and docs.
    """
    # Skip auth for health, docs, and openapi
    path = request.url.path
    if path in ("/api/v1/health", "/api/v1/docs", "/api/v1/openapi.json", "/docs", "/openapi.json"):
        return await call_next(request)

    # Skip auth for non-API paths
    if not path.startswith("/api/v1/"):
        return await call_next(request)

    # Validate API key
    api_key = _validate_api_key(request)
    if api_key is None:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Missing or invalid API key. Provide a valid X-API-Key header.",
                }
            },
        )

    # Rate limiting
    if not rate_limiter.is_allowed(api_key):
        remaining = rate_limiter.get_remaining(api_key)
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute.",
                    "details": {"limit": RATE_LIMIT_PER_MINUTE, "remaining": remaining},
                }
            },
            headers={"Retry-After": "60"},
        )

    response = await call_next(request)
    return response


# ─── Endpoints ────────────────────────────────────────────────────────────────


@app.post("/api/v1/correct")
async def correct_text(request: Request):
    """Submit text for correction analysis.

    Requires X-API-Key header. Text must be 1-50,000 characters.
    Returns a CorrectionReport.
    """
    # Parse request body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_JSON",
                    "message": "Request body must be valid JSON.",
                }
            },
        )

    # Validate text field exists
    if "text" not in body or not body["text"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MISSING_FIELD",
                    "message": "The 'text' field is required and must not be empty.",
                }
            },
        )

    text = body["text"]

    # Validate text is a string
    if not isinstance(text, str):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_TYPE",
                    "message": "The 'text' field must be a string.",
                }
            },
        )

    # Validate whitespace-only
    if not text.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "EMPTY_TEXT",
                    "message": "The 'text' field must not be empty or whitespace-only.",
                }
            },
        )

    # Validate text length
    if len(text) > MAX_TEXT_LENGTH:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "TEXT_TOO_LARGE",
                    "message": f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters.",
                    "details": {
                        "field": "text",
                        "constraint": "max_length",
                        "max_value": MAX_TEXT_LENGTH,
                        "actual_value": len(text),
                    },
                }
            },
        )

    # Forward to correction engine
    try:
        engine_payload = {
            "text": text,
            "language": body.get("language"),
            "options": body.get("options"),
        }

        response = await http_client.post(
            "/internal/analyze", json=engine_payload
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(
                f"Correction engine returned {response.status_code}: {response.text}"
            )
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "code": "ENGINE_ERROR",
                        "message": "Correction engine returned an error.",
                    }
                },
            )

    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "code": "TIMEOUT",
                    "message": "Correction engine request timed out.",
                }
            },
        )
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "SERVICE_UNAVAILABLE",
                    "message": "Cannot connect to correction engine.",
                }
            },
        )


@app.get("/")
async def root():
    """Root endpoint with service info and links."""
    return {
        "service": "Auto-Correction API Gateway",
        "version": "0.1.0",
        "endpoints": {
            "health": "/api/v1/health",
            "correct": "POST /api/v1/correct",
            "batch": "POST /api/v1/batch",
            "history": "/api/v1/history",
            "docs": "/api/v1/docs",
        },
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint.

    Returns service status and LLM readiness.
    Does not require authentication.
    """
    try:
        if http_client:
            response = await http_client.get("/internal/health")
            if response.status_code == 200:
                data = response.json()
                llm_ready = "ready" if data.get("llm_ready") else "loading"
                return {"status": "healthy", "llm_ready": llm_ready}

        return {"status": "degraded", "llm_ready": "error"}

    except Exception:
        return {"status": "unavailable", "llm_ready": "error"}


@app.post("/api/v1/batch")
async def batch_process(request: Request):
    """Submit a file for batch correction processing.

    Requires X-API-Key header. Returns a job ID for tracking.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_JSON",
                    "message": "Request body must be valid JSON.",
                }
            },
        )

    if "file_path" not in body or not body["file_path"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "MISSING_FIELD",
                    "message": "The 'file_path' field is required.",
                }
            },
        )

    # Forward to correction engine batch endpoint
    try:
        import uuid

        job_id = str(uuid.uuid4())

        # In a full implementation, this would queue the job
        # For now, return the job ID immediately
        return {"job_id": job_id, "status": "queued"}

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to queue batch job.",
                }
            },
        )


@app.get("/api/v1/history")
async def get_history(
    page: int = 1,
    per_page: int = 50,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    type: Optional[str] = None,
):
    """Get correction history with pagination.

    Requires X-API-Key header.

    Query parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 100)
    - date_from: Filter by start date (ISO format)
    - date_to: Filter by end date (ISO format)
    - type: Filter by correction type
    """
    # Validate pagination
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 1
    if per_page > 100:
        per_page = 100

    # Forward to correction engine (or query directly)
    # For now, return empty history
    return {
        "entries": [],
        "total": 0,
        "page": page,
        "per_page": per_page,
    }
