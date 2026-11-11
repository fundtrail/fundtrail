"""A server bug comes back as a JSON 500, not a dropped connection.

Starlette's own error handling sits outside every middleware, so a response it makes for
an unhandled exception carries no CORS headers, and the browser reports a CORS error
instead of the 500. This catch-all sits inside the CORS middleware (add it before
`add_cors`), so the 500 it returns gets the allowed origin's headers like any response.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def add_error_catch(app: FastAPI) -> None:
    @app.middleware("http")
    async def catch_unhandled(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:
            # The method and path only: no request body, headers or token.
            log.exception("unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse({"detail": "Something went wrong on the server."}, status_code=500)
