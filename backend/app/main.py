"""FastAPI entry point for the FundTrail backend."""

from fastapi import FastAPI

app = FastAPI(title="FundTrail")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok"}
