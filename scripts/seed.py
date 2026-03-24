"""
Seed script – populates the database with demo users and tasks.

Usage (from project root, with venv activated):
  python scripts/seed.py
"""

import sys
from pathlib import Path

# Make sure the project root is on the path when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta

from app.db import SessionLocal, create_tables
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import TaskCreate
from app.schemas.user import UserCreate
from app.services.task_service import create_task
from app.services.user_service import create_user, get_user_by_username


def seed() -> None:
    create_tables()
    db = SessionLocal()

    try:
        # ── Users ──────────────────────────────────────────────────────────
        users_data = [
            UserCreate(
                email="admin@taskforge.dev",
                username="admin",
                password="password123",
                role="admin",
            ),
            UserCreate(
                email="alice@taskforge.dev",
                username="alice",
                password="password123",
                role="member",
            ),
            UserCreate(
                email="bob@taskforge.dev",
                username="bob",
                password="password123",
                role="member",
            ),
        ]

        created_users = {}
        for user_data in users_data:
            existing = get_user_by_username(db, user_data.username)
            if existing:
                print(f"  User '{user_data.username}' already exists, skipping.")
                created_users[user_data.username] = existing
            else:
                user = create_user(db, user_data)
                created_users[user_data.username] = user
                print(f"  Created user: {user.username} ({user.role})")

        admin = created_users["admin"]
        alice = created_users["alice"]
        bob = created_users["bob"]
        today = date.today()

        # ── Tasks ──────────────────────────────────────────────────────────
        tasks_data = [
            TaskCreate(
                title="Set up CI/CD pipeline",
                description="Configure GitHub Actions for automated testing and deployment.",
                status=TaskStatus.done,
                priority=TaskPriority.high,
                assignee_id=admin.id,
                due_date=today - timedelta(days=5),
            ),
            TaskCreate(
                title="Write API documentation",
                description="Document all endpoints using OpenAPI / Swagger.",
                status=TaskStatus.in_progress,
                priority=TaskPriority.medium,
                assignee_id=alice.id,
                due_date=today + timedelta(days=3),
            ),
            TaskCreate(
                title="Fix password reset flow",
                description="Users report the reset email is not being sent in production.",
                status=TaskStatus.todo,
                priority=TaskPriority.high,
                assignee_id=alice.id,
                due_date=today + timedelta(days=1),
            ),
            TaskCreate(
                title="Migrate database to Postgres",
                description="Switch from SQLite to Postgres for staging environment.",
                status=TaskStatus.todo,
                priority=TaskPriority.medium,
                assignee_id=bob.id,
                due_date=today + timedelta(days=7),
            ),
            TaskCreate(
                title="Add dark mode support",
                description="Implement CSS custom properties for dark/light theme switching.",
                status=TaskStatus.todo,
                priority=TaskPriority.low,
                assignee_id=bob.id,
            ),
            TaskCreate(
                title="Code review: auth module",
                description="Review the new session-based authentication implementation.",
                status=TaskStatus.in_progress,
                priority=TaskPriority.high,
                assignee_id=admin.id,
                due_date=today - timedelta(days=1),  # overdue
            ),
            TaskCreate(
                title="Update dependencies",
                description="Run pip-audit and update any packages with known vulnerabilities.",
                status=TaskStatus.todo,
                priority=TaskPriority.medium,
                due_date=today + timedelta(days=14),
            ),
        ]

        for task_data in tasks_data:
            task = create_task(db, task_data, created_by=admin)
            print(f"  Created task: '{task.title}' [{task.status}/{task.priority}]")

        print("\nSeed complete.")
        print("  Login: admin / password123  (role: admin)")
        print("  Login: alice / password123  (role: member)")
        print("  Login: bob   / password123  (role: member)")

    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding database...")
    seed()
