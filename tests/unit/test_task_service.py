"""
Unit tests for app/services/task_service.py

Demonstrates:
  - Service-layer testing with a real (in-memory) DB
  - Parametrized permission cases
  - monkeypatch for datetime.now (freezing time)
  - Arrange / Act / Assert structure
"""

from datetime import date, datetime, timezone

import pytest

from app.models.task import TaskPriority, TaskStatus
from app.models.user import UserRole
from app.schemas.task import TaskCreate, TaskFilters, TaskUpdate
from app.services.task_service import (
    can_delete_task,
    can_edit_task,
    create_task,
    delete_task,
    get_dashboard_stats,
    get_task_by_id,
    list_tasks,
    update_task,
)
from tests.conftest import make_task, make_user


# ---------------------------------------------------------------------------
# Permission helpers (pure logic – no DB)
# ---------------------------------------------------------------------------

class TestCanEditTask:
    @pytest.mark.parametrize("role", [UserRole.admin, UserRole.member])
    def test_admin_can_edit_any_task(self, db, role):
        owner = make_user(db, username="owner", email="owner@x.com", role=UserRole.member)
        actor = make_user(db, username="actor", email="actor@x.com", role=role)
        task = make_task(db, created_by=owner, assignee=owner)

        if role == UserRole.admin:
            assert can_edit_task(actor, task) is True
        else:
            # member can only edit tasks assigned to them
            assert can_edit_task(actor, task) is False

    def test_member_can_edit_own_assigned_task(self, db):
        user = make_user(db, username="mu", email="mu@x.com")
        task = make_task(db, created_by=user, assignee=user)
        assert can_edit_task(user, task) is True

    def test_member_cannot_edit_unassigned_task(self, db):
        creator = make_user(db, username="cr", email="cr@x.com")
        other = make_user(db, username="ot", email="ot@x.com")
        task = make_task(db, created_by=creator, assignee=None)
        assert can_edit_task(other, task) is False


class TestCanDeleteTask:
    def test_admin_can_delete(self, db):
        admin = make_user(db, username="del_admin", email="da@x.com", role=UserRole.admin)
        assert can_delete_task(admin) is True

    def test_member_cannot_delete(self, db):
        member = make_user(db, username="del_member", email="dm@x.com", role=UserRole.member)
        assert can_delete_task(member) is False


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_creates_task_with_correct_fields(self, db):
        user = make_user(db, username="ct_user", email="ct@x.com")
        data = TaskCreate(title="My Task", priority=TaskPriority.high)

        task = create_task(db, data, created_by=user)

        assert task.id is not None
        assert task.title == "My Task"
        assert task.priority == TaskPriority.high
        assert task.created_by_id == user.id
        assert task.status == TaskStatus.todo

    def test_records_created_event(self, db):
        user = make_user(db, username="ev_user", email="ev@x.com")
        data = TaskCreate(title="Audit Task")

        task = create_task(db, data, created_by=user)

        assert len(task.events) == 1
        assert task.events[0].event_type.value == "created"
        assert task.events[0].user_id == user.id

    def test_sets_assignee_id(self, db):
        creator = make_user(db, username="cr2", email="cr2@x.com")
        assignee = make_user(db, username="as2", email="as2@x.com")
        data = TaskCreate(title="Assigned", assignee_id=assignee.id)

        task = create_task(db, data, created_by=creator)

        assert task.assignee_id == assignee.id


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_updates_title(self, db):
        user = make_user(db, username="up_user", email="up@x.com", role=UserRole.admin)
        task = make_task(db, created_by=user, assignee=user)

        updated = update_task(db, task, TaskUpdate(title="New Title"), updated_by=user)

        assert updated.title == "New Title"

    def test_records_field_change_event(self, db):
        user = make_user(db, username="ev2", email="ev2@x.com", role=UserRole.admin)
        task = make_task(db, title="Old", created_by=user)

        update_task(db, task, TaskUpdate(title="New"), updated_by=user)

        change_events = [e for e in task.events if e.field_name == "title"]
        assert len(change_events) == 1
        assert change_events[0].old_value == "Old"
        assert change_events[0].new_value == "New"

    def test_status_change_sets_completed_at(self, db, monkeypatch):
        """
        Demonstrates monkeypatching datetime.now to freeze time.
        We verify completed_at is stamped when status → done.
        """
        fixed_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        monkeypatch.setattr(
            "app.services.task_service.datetime",
            type("FakeDatetime", (), {
                "now": staticmethod(lambda tz=None: fixed_time),
            }),
        )

        user = make_user(db, username="tc_user", email="tc@x.com", role=UserRole.admin)
        task = make_task(db, created_by=user, status=TaskStatus.in_progress)

        updated = update_task(db, task, TaskUpdate(status=TaskStatus.done), updated_by=user)

        # SQLite stores datetimes as naive; strip tzinfo before comparing
        assert updated.completed_at == fixed_time.replace(tzinfo=None)

    def test_reverting_from_done_clears_completed_at(self, db):
        user = make_user(db, username="rev_user", email="rev@x.com", role=UserRole.admin)
        task = make_task(db, created_by=user, status=TaskStatus.done)
        task.completed_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        db.commit()

        updated = update_task(db, task, TaskUpdate(status=TaskStatus.todo), updated_by=user)

        assert updated.completed_at is None

    def test_member_cannot_edit_unassigned_task(self, db):
        creator = make_user(db, username="cr3", email="cr3@x.com")
        member = make_user(db, username="mem3", email="mem3@x.com")
        task = make_task(db, created_by=creator, assignee=None)

        with pytest.raises(PermissionError):
            update_task(db, task, TaskUpdate(title="Hijack"), updated_by=member)

    @pytest.mark.parametrize("new_status", [TaskStatus.todo, TaskStatus.in_progress, TaskStatus.done])
    def test_all_status_transitions_persist(self, db, new_status):
        user = make_user(
            db, username=f"st_{new_status.value}", email=f"st_{new_status.value}@x.com",
            role=UserRole.admin
        )
        task = make_task(db, created_by=user)

        updated = update_task(db, task, TaskUpdate(status=new_status), updated_by=user)

        assert updated.status == new_status


# ---------------------------------------------------------------------------
# delete_task
# ---------------------------------------------------------------------------

class TestDeleteTask:
    def test_admin_can_delete(self, db):
        admin = make_user(db, username="del_a", email="dela@x.com", role=UserRole.admin)
        task = make_task(db, created_by=admin)
        task_id = task.id

        delete_task(db, task, deleted_by=admin)

        assert get_task_by_id(db, task_id) is None

    def test_member_delete_raises_permission_error(self, db):
        member = make_user(db, username="del_m", email="delm@x.com")
        task = make_task(db, created_by=member)

        with pytest.raises(PermissionError, match="Only admins"):
            delete_task(db, task, deleted_by=member)


# ---------------------------------------------------------------------------
# list_tasks filters
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_filter_by_status(self, db):
        user = make_user(db, username="lf_user", email="lf@x.com")
        make_task(db, title="Todo task", created_by=user, status=TaskStatus.todo)
        make_task(db, title="Done task", created_by=user, status=TaskStatus.done)

        results = list_tasks(db, TaskFilters(status=TaskStatus.todo))
        titles = [t.title for t in results]

        assert "Todo task" in titles
        assert "Done task" not in titles

    def test_filter_by_search(self, db):
        user = make_user(db, username="ls_user", email="ls@x.com")
        make_task(db, title="Fix login bug", created_by=user)
        make_task(db, title="Update readme", created_by=user)

        results = list_tasks(db, TaskFilters(search="login"))
        assert len(results) == 1
        assert results[0].title == "Fix login bug"

    @pytest.mark.parametrize("priority", [TaskPriority.low, TaskPriority.medium, TaskPriority.high])
    def test_filter_by_priority(self, db, priority):
        user = make_user(
            db, username=f"lp_{priority.value}", email=f"lp_{priority.value}@x.com"
        )
        make_task(db, title="Target", created_by=user, priority=priority)

        results = list_tasks(db, TaskFilters(priority=priority))
        assert any(t.title == "Target" for t in results)


# ---------------------------------------------------------------------------
# get_dashboard_stats
# ---------------------------------------------------------------------------

class TestDashboardStats:
    def test_counts_are_correct(self, db, monkeypatch):
        """
        Demonstrates monkeypatching date.today via the module-level import
        so we can control which tasks count as overdue.
        """
        user = make_user(db, username="ds_user", email="ds@x.com")

        yesterday = date(2024, 1, 14)
        today = date(2024, 1, 15)
        tomorrow = date(2024, 1, 16)

        # Freeze "today" so overdue detection is deterministic
        monkeypatch.setattr(
            "app.services.task_service.datetime",
            type("FakeDatetime", (), {
                "now": staticmethod(lambda tz=None: datetime(2024, 1, 15, tzinfo=timezone.utc)),
            }),
        )

        make_task(db, title="open1", created_by=user, status=TaskStatus.todo)
        make_task(db, title="open2", created_by=user, status=TaskStatus.in_progress)
        make_task(db, title="done1", created_by=user, status=TaskStatus.done)
        make_task(db, title="overdue", created_by=user, status=TaskStatus.todo, due_date=yesterday)

        stats = get_dashboard_stats(db)

        assert stats["completed"] >= 1
        assert stats["in_progress"] >= 1
        assert stats["overdue"] >= 1
