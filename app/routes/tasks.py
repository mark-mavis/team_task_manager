from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models.task import TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.task import TaskCreate, TaskFilters, TaskUpdate
from app.services.task_service import (
    can_delete_task,
    can_edit_task,
    create_task,
    delete_task,
    get_task_by_id,
    list_tasks,
    update_task,
)
from app.services.user_service import get_all_users

router = APIRouter(prefix="/tasks")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def task_list(
    request: Request,
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    filters = TaskFilters(
        status=TaskStatus(status_filter) if status_filter else None,
        priority=TaskPriority(priority) if priority else None,
        assignee_id=assignee_id,
        search=search,
    )
    tasks = list_tasks(db, filters)
    users = get_all_users(db)
    return templates.TemplateResponse(
        request,
        "tasks/list.html",
        {
            "current_user": current_user,
            "tasks": tasks,
            "users": users,
            "filters": {
                "status": status_filter,
                "priority": priority,
                "assignee_id": assignee_id,
                "search": search,
            },
            "statuses": [s.value for s in TaskStatus],
            "priorities": [p.value for p in TaskPriority],
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def task_new_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    users = get_all_users(db)
    return templates.TemplateResponse(
        request,
        "tasks/form.html",
        {
            "current_user": current_user,
            "task": None,
            "users": users,
            "statuses": [s.value for s in TaskStatus],
            "priorities": [p.value for p in TaskPriority],
            "error": None,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def task_create(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    task_status: str = Form("todo"),
    priority: str = Form("medium"),
    due_date: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    from datetime import date as date_type

    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = date_type.fromisoformat(due_date)
        except ValueError:
            pass

    try:
        data = TaskCreate(
            title=title,
            description=description or None,
            status=TaskStatus(task_status),
            priority=TaskPriority(priority),
            due_date=parsed_due_date,
            assignee_id=assignee_id,
        )
    except Exception as exc:
        users = get_all_users(db)
        return templates.TemplateResponse(
            request,
            "tasks/form.html",
            {
                "current_user": current_user,
                "task": None,
                "users": users,
                "statuses": [s.value for s in TaskStatus],
                "priorities": [p.value for p in TaskPriority],
                "error": str(exc),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    create_task(db, data, created_by=current_user)
    return RedirectResponse(url="/tasks", status_code=status.HTTP_302_FOUND)


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    task = get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return templates.TemplateResponse(
        request,
        "tasks/detail.html",
        {
            "current_user": current_user,
            "task": task,
            "can_edit": can_edit_task(current_user, task),
            "can_delete": can_delete_task(current_user),
        },
    )


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def task_edit_form(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    task = get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not can_edit_task(current_user, task):
        raise HTTPException(status_code=403, detail="You cannot edit this task")
    users = get_all_users(db)
    return templates.TemplateResponse(
        request,
        "tasks/form.html",
        {
            "current_user": current_user,
            "task": task,
            "users": users,
            "statuses": [s.value for s in TaskStatus],
            "priorities": [p.value for p in TaskPriority],
            "error": None,
        },
    )


@router.post("/{task_id}/edit", response_class=HTMLResponse)
async def task_update(
    task_id: int,
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    task_status: str = Form(...),
    priority: str = Form(...),
    due_date: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    from datetime import date as date_type

    task = get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = date_type.fromisoformat(due_date)
        except ValueError:
            pass

    try:
        data = TaskUpdate(
            title=title,
            description=description or None,
            status=TaskStatus(task_status),
            priority=TaskPriority(priority),
            due_date=parsed_due_date,
            assignee_id=assignee_id,
        )
        update_task(db, task, data, updated_by=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        users = get_all_users(db)
        return templates.TemplateResponse(
            request,
            "tasks/form.html",
            {
                "current_user": current_user,
                "task": task,
                "users": users,
                "statuses": [s.value for s in TaskStatus],
                "priorities": [p.value for p in TaskPriority],
                "error": str(exc),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return RedirectResponse(url=f"/tasks/{task_id}", status_code=status.HTTP_302_FOUND)


@router.post("/{task_id}/delete")
async def task_delete(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RedirectResponse:
    task = get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        delete_task(db, task, deleted_by=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return RedirectResponse(url="/tasks", status_code=status.HTTP_302_FOUND)
