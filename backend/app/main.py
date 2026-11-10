"""FastAPI entry point for the FundTrail backend."""

from fastapi import FastAPI

from app.api import lifespan, router

app = FastAPI(title="FundTrail", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok"}
