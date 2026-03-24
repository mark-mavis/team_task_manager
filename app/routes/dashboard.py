from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.user import User
from app.services.task_service import get_dashboard_stats

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    stats = get_dashboard_stats(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_user": current_user,
            "stats": stats,
        },
    )
