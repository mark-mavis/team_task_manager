"""
Integration tests for task CRUD routes.

Demonstrates:
  - End-to-end form submission via TestClient
  - Admin vs member permission enforcement at the HTTP layer
  - Parametrized status/priority round-trips
  - Database persistence verified after HTTP call
"""

import pytest

from app.models.task import TaskStatus, TaskPriority
from app.services.task_service import get_task_by_id
from tests.conftest import make_task, make_user, login


class TestTaskList:
    def test_list_page_renders(self, admin_client):
        response = admin_client.get("/tasks")
        assert response.status_code == 200
        assert b"Tasks" in response.content

    def test_empty_state_shown_when_no_tasks(self, admin_client):
        response = admin_client.get("/tasks")
        assert b'data-testid="empty-state"' in response.content

    def test_tasks_appear_in_table(self, admin_client, db, admin_user):
        make_task(db, title="Visible Task", created_by=admin_user)
        response = admin_client.get("/tasks")
        assert b"Visible Task" in response.content

    def test_filter_by_status(self, admin_client, db, admin_user):
        make_task(db, title="Todo Task", created_by=admin_user, status=TaskStatus.todo)
        make_task(db, title="Done Task", created_by=admin_user, status=TaskStatus.done)

        response = admin_client.get("/tasks?status_filter=todo")
        assert b"Todo Task" in response.content
        assert b"Done Task" not in response.content

    def test_search_by_title(self, admin_client, db, admin_user):
        make_task(db, title="Fix the login bug", created_by=admin_user)
        make_task(db, title="Update homepage", created_by=admin_user)

        response = admin_client.get("/tasks?search=login")
        assert b"Fix the login bug" in response.content
        assert b"Update homepage" not in response.content


class TestTaskCreate:
    def test_get_new_task_form(self, member_client):
        response = member_client.get("/tasks/new")
        assert response.status_code == 200
        assert b'data-testid="task-form"' in response.content

    def test_create_task_redirects_to_list(self, member_client):
        response = member_client.post(
            "/tasks/new",
            data={"title": "Brand new task", "task_status": "todo", "priority": "medium"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/tasks"

    def test_created_task_persists_in_db(self, member_client, db):
        member_client.post(
            "/tasks/new",
            data={"title": "Persist Me", "task_status": "todo", "priority": "high"},
            follow_redirects=True,
        )
        tasks = db.query(__import__("app.models.task", fromlist=["Task"]).Task).filter_by(title="Persist Me").all()
        assert len(tasks) == 1
        assert tasks[0].priority.value == "high"

    def test_empty_title_returns_error(self, member_client):
        response = member_client.post(
            "/tasks/new",
            data={"title": "   ", "task_status": "todo", "priority": "medium"},
            follow_redirects=False,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("priority", ["low", "medium", "high"])
    def test_all_priorities_accepted(self, member_client, db, priority):
        member_client.post(
            "/tasks/new",
            data={"title": f"Task {priority}", "task_status": "todo", "priority": priority},
            follow_redirects=True,
        )
        from app.models.task import Task
        task = db.query(Task).filter_by(title=f"Task {priority}").first()
        assert task is not None
        assert task.priority.value == priority


class TestTaskDetail:
    def test_detail_page_renders(self, admin_client, db, admin_user):
        task = make_task(db, title="Detail Task", created_by=admin_user)
        response = admin_client.get(f"/tasks/{task.id}")
        assert response.status_code == 200
        assert b"Detail Task" in response.content

    def test_404_for_missing_task(self, admin_client):
        response = admin_client.get("/tasks/99999")
        assert response.status_code == 404

    def test_audit_trail_shown(self, admin_client, db, admin_user):
        from app.schemas.task import TaskCreate
        from app.services.task_service import create_task
        data = TaskCreate(title="Audited Task")
        task = create_task(db, data, created_by=admin_user)

        response = admin_client.get(f"/tasks/{task.id}")
        assert b'data-testid="audit-row"' in response.content


class TestTaskEdit:
    def test_admin_can_edit_any_task(self, admin_client, db, admin_user, member_user):
        task = make_task(db, title="Any Task", created_by=member_user, assignee=None)
        response = admin_client.post(
            f"/tasks/{task.id}/edit",
            data={"title": "Updated By Admin", "task_status": "in_progress", "priority": "high"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_member_can_edit_assigned_task(self, member_client, db, member_user):
        task = make_task(db, title="My Task", created_by=member_user, assignee=member_user)
        response = member_client.post(
            f"/tasks/{task.id}/edit",
            data={"title": "My Updated Task", "task_status": "in_progress", "priority": "medium"},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_member_cannot_edit_unassigned_task(self, member_client, db, admin_user):
        task = make_task(db, title="Admin Task", created_by=admin_user, assignee=None)
        response = member_client.post(
            f"/tasks/{task.id}/edit",
            data={"title": "Hijacked", "task_status": "todo", "priority": "low"},
            follow_redirects=False,
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("new_status", ["todo", "in_progress", "done"])
    def test_status_update_persists(self, admin_client, db, admin_user, new_status):
        task = make_task(db, title="Status Task", created_by=admin_user)

        admin_client.post(
            f"/tasks/{task.id}/edit",
            data={"title": task.title, "task_status": new_status, "priority": "medium"},
            follow_redirects=True,
        )

        db.refresh(task)
        assert task.status.value == new_status


class TestTaskDelete:
    def test_admin_can_delete(self, admin_client, db, admin_user):
        task = make_task(db, title="Delete Me", created_by=admin_user)
        task_id = task.id

        response = admin_client.post(f"/tasks/{task_id}/delete", follow_redirects=False)
        assert response.status_code == 302

        assert get_task_by_id(db, task_id) is None

    def test_member_cannot_delete(self, member_client, db, member_user):
        task = make_task(db, title="Dont Delete", created_by=member_user, assignee=member_user)

        response = member_client.post(f"/tasks/{task.id}/delete", follow_redirects=False)
        assert response.status_code == 403

    def test_delete_nonexistent_task_returns_404(self, admin_client):
        response = admin_client.post("/tasks/99999/delete")
        assert response.status_code == 404
