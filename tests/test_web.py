from __future__ import annotations

from io import BytesIO
import sqlite3

from kuka_tool_service import create_app

from conftest import csrf_token, login, sample_src


def test_health_reports_no_controller_access(client) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json == {
        "status": "ok",
        "authentication_configured": True,
        "error": None,
        "controller_access": False,
    }


def test_tools_require_login(client) -> None:
    assert client.get("/").status_code == 302
    assert client.post("/inspect").status_code == 302
    assert client.post("/annotate").status_code == 302


def test_inspection_browser_flow_records_audit(client, app) -> None:
    login(client)
    response = client.post(
        "/inspect",
        data={
            "csrf_token": csrf_token(client),
            "default_speed_mps": "0.06",
            "src_file": (BytesIO(sample_src()), "fixture.src"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Inspection: fixture.src" in response.data
    assert b"4.2 s" in response.data
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            "SELECT username, operation, output_sha256 FROM audit_events"
        ).fetchone()
    assert row == ("operator", "inspect", None)


def test_annotation_download_has_hash_provenance(client) -> None:
    login(client)
    response = client.post(
        "/annotate",
        data={
            "csrf_token": csrf_token(client),
            "src_file": (BytesIO(sample_src()), "fixture.src"),
            "cell_number": "4",
            "part_prefix": "7",
            "part_suffix": "2",
            "part_name": "Back Body",
            "part_link": "PLM-200007-02",
            "flow_rate_percent": "54",
            "cooling_enabled": "yes",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith(
        "attachment; filename=CELL04-00702_BACK_BODY_54%"
    )
    assert len(response.headers["X-Input-SHA256"]) == 64
    assert len(response.headers["X-Output-SHA256"]) == 64
    assert b"; Cell Number = CELL04\r\n" in response.data


def test_velocity_download_is_classified_audited_and_attachment_only(client, app) -> None:
    login(client)
    response = client.post(
        "/modify-velocity",
        data={
            "csrf_token": csrf_token(client),
            "src_file": (BytesIO(sample_src()), "fixture.src"),
            "extrusion_mps": "0.042",
            "travel_mps": "0.125",
            "confirm_review": "yes",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith(
        "attachment; filename=fixture_velocity.src"
    )
    assert response.headers["X-Changed-Line-Count"] == "4"
    assert response.data.count(b"$VEL.CP = 0.042000") == 2
    assert response.data.count(b"$VEL.CP = 0.125000") == 2
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            "SELECT operation, parameters_json FROM audit_events"
        ).fetchone()
    assert row is not None
    assert row[0] == "modify_velocity"
    assert '"changed_line_count":4' in row[1]


def test_velocity_download_requires_operator_confirmation(client) -> None:
    login(client)
    response = client.post(
        "/modify-velocity",
        data={
            "csrf_token": csrf_token(client),
            "src_file": (BytesIO(sample_src()), "fixture.src"),
            "extrusion_mps": "0.042",
            "travel_mps": "0.125",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert b"independent operator review" in response.data


def test_viewer_cannot_generate_artifact(client) -> None:
    login(client, username="viewer", password="view only")
    response = client.post(
        "/annotate",
        data={"csrf_token": csrf_token(client)},
    )
    assert response.status_code == 403
    assert client.post("/modify-velocity").status_code == 403


def test_csrf_is_required(client) -> None:
    login(client)
    response = client.post(
        "/inspect",
        data={"src_file": (BytesIO(sample_src()), "fixture.src")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_https_is_required_outside_local_test_mode(app) -> None:
    app.config["REQUIRE_HTTPS"] = True
    http_client = app.test_client()

    assert http_client.get("/healthz").status_code == 200
    assert http_client.get("/login").status_code == 426
    assert http_client.get("/login", headers={"X-Forwarded-Proto": "https"}).status_code == 200


def test_unconfigured_authentication_degrades_health(tmp_path) -> None:
    application = create_app(
        {
            "TESTING": True,
            "REQUIRE_HTTPS": False,
            "USERS_PATH": str(tmp_path / "missing.json"),
            "DATABASE_PATH": str(tmp_path / "audit.sqlite3"),
        }
    )
    response = application.test_client().get("/healthz")

    assert response.status_code == 503
    assert response.json["authentication_configured"] is False
