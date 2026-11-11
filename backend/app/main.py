"""FastAPI entry point for the FundTrail backend."""

from fastapi import FastAPI

from app.api import lifespan, router
from app.api.cors import add_cors
from app.api.errors import add_error_catch

app = FastAPI(title="FundTrail", lifespan=lifespan)
app.include_router(router)
# The catch-all goes in first, so CORS wraps it and a 500 carries the origin's headers.
add_error_catch(app)
add_cors(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok"}
