from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus
from app.models.task_event import EventType, TaskEvent
from app.models.user import User, UserRole
from app.schemas.task import TaskCreate, TaskFilters, TaskUpdate


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def can_edit_task(user: User, task: Task) -> bool:
    """Return True if the user is allowed to edit this task."""
    if user.role == UserRole.admin:
        return True
    # Members can only edit tasks assigned to them
    return task.assignee_id == user.id


def can_delete_task(user: User) -> bool:
    """Only admins may delete tasks."""
    return user.role == UserRole.admin


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_task_by_id(db: Session, task_id: int) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def list_tasks(db: Session, filters: Optional[TaskFilters] = None) -> list[Task]:
    """Return tasks matching the given filters, ordered newest-first."""
    query = db.query(Task)

    if filters:
        if filters.status is not None:
            query = query.filter(Task.status == filters.status)
        if filters.priority is not None:
            query = query.filter(Task.priority == filters.priority)
        if filters.assignee_id is not None:
            query = query.filter(Task.assignee_id == filters.assignee_id)
        if filters.search:
            query = query.filter(Task.title.ilike(f"%{filters.search}%"))

    return query.order_by(Task.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def create_task(db: Session, data: TaskCreate, created_by: User) -> Task:
    """Create a task and record a 'created' event."""
    task = Task(
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        due_date=data.due_date,
        assignee_id=data.assignee_id,
        created_by_id=created_by.id,
    )
    db.add(task)
    db.flush()  # Get task.id without committing

    _record_event(db, task, created_by, EventType.created)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task: Task, data: TaskUpdate, updated_by: User) -> Task:
    """
    Apply a partial update to a task, recording events for each changed field.
    Raises PermissionError if the user is not allowed to edit this task.
    """
    if not can_edit_task(updated_by, task):
        raise PermissionError("You do not have permission to edit this task")

    update_data = data.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(task, field)
        if old_value == new_value:
            continue

        # Record status change with its own event type
        event_type = EventType.status_changed if field == "status" else EventType.updated
        _record_event(
            db, task, updated_by, event_type,
            field_name=field,
            old_value=_to_audit_str(old_value),
            new_value=_to_audit_str(new_value),
        )

        setattr(task, field, new_value)

    # If status is being set to done and completed_at is not set, stamp it now
    if update_data.get("status") == TaskStatus.done and task.completed_at is None:
        task.completed_at = datetime.now(timezone.utc)
    elif update_data.get("status") in (TaskStatus.todo, TaskStatus.in_progress):
        task.completed_at = None

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task, deleted_by: User) -> None:
    """
    Delete a task. Only admins may delete.
    Raises PermissionError if the user lacks permission.
    """
    if not can_delete_task(deleted_by):
        raise PermissionError("Only admins can delete tasks")
    db.delete(task)
    db.commit()


# ---------------------------------------------------------------------------
# Dashboard statistics
# ---------------------------------------------------------------------------

def get_dashboard_stats(db: Session) -> dict:
    """Return counts for the dashboard summary cards."""
    now = datetime.now(timezone.utc).date()

    open_statuses = [TaskStatus.todo.value, TaskStatus.in_progress.value]

    total_open = db.query(Task).filter(Task.status.in_(open_statuses)).count()
    in_progress = db.query(Task).filter(Task.status == TaskStatus.in_progress.value).count()
    completed = db.query(Task).filter(Task.status == TaskStatus.done.value).count()
    overdue = (
        db.query(Task)
        .filter(Task.status.in_(open_statuses), Task.due_date < now)
        .count()
    )

    return {
        "total_open": total_open,
        "in_progress": in_progress,
        "completed": completed,
        "overdue": overdue,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

import enum as _enum


def _to_audit_str(value: object) -> Optional[str]:
    """Convert a field value to a human-readable audit string.

    Enum members expose their .value (e.g. 'in_progress') rather than
    the Python repr ('TaskStatus.in_progress').
    """
    if value is None:
        return None
    if isinstance(value, _enum.Enum):
        return str(value.value)
    return str(value)


def _record_event(
    db: Session,
    task: Task,
    user: User,
    event_type: EventType,
    field_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task.id,
        user_id=user.id,
        event_type=event_type,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(event)
    return event
