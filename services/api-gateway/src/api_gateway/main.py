"""API Gateway entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="Local Autocorrection API",
    version="1.0.0",
    description="Privacy-first local text correction REST API",
)


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "llm_status": "loading", "version": "1.0.0"}
