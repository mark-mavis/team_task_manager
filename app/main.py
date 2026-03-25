from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import create_tables
from app.routes import auth, dashboard, tasks


# ---------------------------------------------------------------------------
# Startup / shutdown lifecycle
# ---------------------------------------------------------------------------
# The lifespan context manager runs once when the server starts (before the
# first request) and once when it shuts down (after the yield).  Creating the
# database tables here ensures the schema exists before any request arrives.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_tables()
    yield


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------
# The FastAPI app is the central object that ties together middleware, routes,
# and exception handlers.  Title and debug flag come from environment-backed
# settings so they can be overridden without changing code.
app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# SessionMiddleware wraps every request/response to read and write a signed,
# server-side session cookie.  It must be registered before any route that
# calls request.session, which is why it is added here at the top level
# rather than inside a router.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    session_cookie=settings.session_cookie_name,
)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
# Mounts the app/static directory at the /static URL prefix so the browser
# can fetch CSS, images, and JavaScript directly without hitting route logic.
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# Each router is defined in its own module and handles a logical section of
# the URL space.  Including them here wires their paths into the main app.
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(tasks.router)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
# FastAPI would normally return a plain JSON 401 response for unauthenticated
# requests, which looks broken in a browser-based app.  This handler intercepts
# every HTTPException: 401s are redirected to the login page, while all other
# HTTP errors (403, 404, 422, …) are returned as JSON so API clients and
# integration tests receive structured error details.
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse | RedirectResponse:
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
# Visiting the bare domain (/) immediately forwards the browser to the
# dashboard.  Auth protection on the dashboard route then handles the case
# where the user is not logged in.
@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")
