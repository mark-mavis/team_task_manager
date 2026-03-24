from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import create_tables
from app.routes import auth, dashboard, tasks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_tables()
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

# Session middleware must be added before routes
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    session_cookie=settings.session_cookie_name,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(tasks.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> RedirectResponse:
    if exc.status_code == 401:
        return RedirectResponse(url="/login")
    raise exc


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")
