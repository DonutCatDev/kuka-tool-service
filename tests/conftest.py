from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from kuka_tool_service import create_app


SAMPLE_LINES = (
    "&ACCESS RVP",
    "DEF SAMPLE()",
    "; generated fixture",
    "$VEL.CP = 0.200000",
    "PTP {A 0, Z 0, Y 0, X 0}",
    "$VEL.CP = 0.100000",
    "LIN {X 0, Y 0, Z 0, A 0}",
    ";travel end",
    "$VEL.CP = 0.050000",
    "LIN {X 100, Y 0, Z 0}",
    ";travel start",
    "$VEL.CP = 0.100000",
    "LIN {X 110, Y 0, Z 0}",
    "LIN {X 110, Y 0, Z 10}",
    ";travel end",
    "$VEL.CP = 0.050000",
    "LIN {Z 10, X 210, Y 0}",
    ";travel start",
    "$VEL.CP = 0.100000",
    "LIN {X 210, Y 0, Z 10}",
    "END",
)


def sample_src(newline: str = "\r\n", encoding: str = "utf-8") -> bytes:
    return (newline.join(SAMPLE_LINES) + newline).encode(encoding)


@pytest.fixture
def app(tmp_path: Path):
    users = {
        "session_secret": "test-session-secret-that-is-long-enough-12345",
        "users": [
            {
                "username": "operator",
                "password_hash": generate_password_hash("correct horse"),
                "role": "operator",
            },
            {
                "username": "viewer",
                "password_hash": generate_password_hash("view only"),
                "role": "viewer",
            },
        ],
    }
    application = create_app(
        {
            "TESTING": True,
            "SESSION_COOKIE_SECURE": False,
            "REQUIRE_HTTPS": False,
            "USERS_PAYLOAD": users,
            "DATABASE_PATH": str(tmp_path / "audit.sqlite3"),
        }
    )
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username: str = "operator", password: str = "correct horse") -> None:
    client.get("/login")
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": csrf},
    )
    assert response.status_code == 302


def csrf_token(client) -> str:
    with client.session_transaction() as session:
        return str(session["csrf_token"])
