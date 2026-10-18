"""Scriptoria web API + static front end."""
from __future__ import annotations

from contextlib import asynccontextmanager

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import config, userdb

WEB = config.PACKAGE / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Notes from the first release lived inside the scripture database; carry them over once.
    try:
        con = userdb.connect()
        try:
            n = userdb.import_legacy_notes(con, config.content_db())
            if n:
                print(f"Moved {n} note(s)/highlight(s) from the old database into your profile.")
        finally:
            con.close()
    except Exception as e:                          # never block startup on this
        print(f"(Couldn't check for old notes: {e})")
    yield


def create_app() -> FastAPI:
    from . import library_api, reading, search, study, user

    app = FastAPI(title="Scriptoria", lifespan=lifespan)
    for r in (reading.router, study.router, search.router, library_api.router, user.router):
        app.include_router(r)

    hosts = config.allowed_hosts()

    @app.middleware("http")
    async def guard_writes(request: Request, call_next):
        """Changes need the app's own X-Scriptoria header (a cross-site form or script can't
        send it without a CORS preflight, which is never granted), and a foreign Origin is
        refused outright."""
        origin = request.headers.get("origin")
        if origin and origin != "null" and urlsplit(origin).hostname not in {h.strip("[]") for h in hosts}:
            return JSONResponse({"detail": "Requests from other sites are not allowed."}, status_code=403)
        if (request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS")
                and request.headers.get("x-scriptoria") != "1"):
            return JSONResponse({"detail": "Missing X-Scriptoria header."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def revalidate_assets(request: Request, call_next):
        resp = await call_next(request)
        if not request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-cache"     # always check for updated files after git pull
        return resp

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    if WEB.exists():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(WEB / "index.html")

    return app
