"""Authenticated Flask browser service for KUKA SRC tools."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Any, TypeVar, cast

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from .parser import MAX_SOURCE_BYTES, SourceValidationError, inspect_source
from .merger import build_merged_source
from .mesh import MAX_MESH_BYTES, parse_mesh_csv
from .mesh_editor import (
    MeshEditRequest,
    MeshFalloffRequest,
    build_edited_mesh,
    build_falloff_mesh,
)
from .mesh_generator import MeshGenerationRequest, build_mesh_from_source
from .layer_inspector import inspect_layers
from .path_overlay import build_path_overlay
from .mesh_compensation import MeshCompensationRequest, build_mesh_compensated_source
from .probe_generator import ProbeRequest, build_probe_source
from .transforms import (
    MetadataRequest,
    VelocityRequest,
    XYZRequest,
    build_annotated_source,
    build_velocity_source,
    build_xyz_source,
)


ROLES = {"viewer": 0, "operator": 1, "admin": 2}
F = TypeVar("F", bound=Callable[..., Any])


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Create a configured service instance."""

    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=secrets.token_urlsafe(48),
        SESSION_COOKIE_NAME="kuka_tools_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=True,
        MAX_CONTENT_LENGTH=(2 * MAX_SOURCE_BYTES) + 1024 * 1024,
        USERS_PATH=os.getenv(
            "KUKA_TOOL_USERS_PATH", "/run/secrets/production_desk_users"
        ),
        DATABASE_PATH=os.getenv(
            "KUKA_TOOL_DATABASE_PATH", "/data/kuka-tool-service.sqlite3"
        ),
        AUDIT_RETENTION_DAYS=os.getenv("KUKA_TOOL_AUDIT_RETENTION_DAYS", "365"),
        AUDIT_MAX_ROWS=os.getenv("KUKA_TOOL_AUDIT_MAX_ROWS", "100000"),
        REQUIRE_HTTPS=os.getenv("KUKA_TOOL_REQUIRE_HTTPS", "true").lower() == "true",
        PUBLIC_HTTPS_URL=os.getenv(
            "KUKA_TOOL_PUBLIC_HTTPS_URL", "https://fleetlord.local:6000"
        ),
    )
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def configure_secret() -> None:
        try:
            payload = _users_payload(app, required=False)
        except (OSError, ValueError, json.JSONDecodeError):
            payload = None
        if payload is not None:
            app.secret_key = payload["session_secret"]
        if request.endpoint not in {"healthz", "static"}:
            _require_https(app)

    @app.context_processor
    def template_context() -> dict[str, Any]:
        return {
            "csrf_token": _csrf_token,
            "current_user": session.get("username"),
            "current_role": session.get("role"),
        }

    @app.get("/healthz")
    def healthz() -> Response:
        auth_configured = False
        auth_error = None
        try:
            _users_payload(app, required=True)
            auth_configured = True
            _initialize_database(app)
        except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
            auth_error = str(exc)
        status = 200 if auth_configured and auth_error is None else 503
        return jsonify(
            {
                "status": "ok" if status == 200 else "degraded",
                "authentication_configured": auth_configured,
                "error": auth_error,
                "controller_access": False,
            }
        ), status

    @app.get("/login")
    def login() -> str:
        return render_template("login.html")

    @app.post("/login")
    def login_post() -> Response | tuple[str, int]:
        _require_csrf()
        try:
            users = _users(app)
        except (OSError, ValueError, json.JSONDecodeError):
            abort(503, description="KUKA Tool Service authentication is not configured")
        username = request.form.get("username", "").strip()
        user = users.get(username)
        password = request.form.get("password", "")
        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid username or password."), 401
        session.clear()
        session.update(
            username=username,
            role=user["role"],
            csrf_token=secrets.token_urlsafe(32),
        )
        return redirect(url_for("index"))

    @app.post("/logout")
    @require_role("viewer")
    def logout() -> Response:
        _require_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @require_role("viewer")
    def index() -> str:
        return render_template("index.html")

    @app.post("/inspect")
    @require_role("viewer")
    def inspect_upload() -> str:
        _require_csrf()
        filename, data = _uploaded_src()
        default_speed = _positive_float(
            request.form.get("default_speed_mps", "0.06"), "Default speed"
        )
        report = inspect_source(data, filename=filename, default_speed_mps=default_speed)
        _record_audit(
            app,
            operation="inspect",
            input_sha256=report.sha256,
            output_sha256=None,
            parameters={"default_speed_mps": default_speed},
            result="completed",
        )
        return render_template("inspection.html", report=report)

    @app.post("/inspect-layers")
    @require_role("viewer")
    def inspect_layers_upload() -> str:
        _require_csrf()
        filename, data = _uploaded_src()
        preview_index = _bounded_int("preview_layer", 0, 499_999)
        report = inspect_layers(data, filename, preview_index)
        _record_audit(
            app,
            operation="inspect_layers",
            input_sha256=report.input_sha256,
            output_sha256=None,
            parameters={
                "preview_layer": preview_index,
                "layer_count": len(report.layers),
                "preview_point_count": report.preview_point_count,
                "rendered_point_count": report.rendered_point_count,
            },
            result="completed",
        )
        return render_template("layer_inspection.html", report=report)

    @app.post("/preview-path-mesh")
    @require_role("viewer")
    def preview_path_mesh_upload() -> str:
        _require_csrf()
        source_name, source_data = _uploaded_src()
        mesh_name, mesh_data = _uploaded_file(
            "mesh_file", ".csv", MAX_MESH_BYTES, "mesh CSV"
        )
        layer_index = _bounded_int("preview_layer", 0, 499_999)
        report = build_path_overlay(
            source_data, source_name, mesh_data, mesh_name, layer_index
        )
        _record_audit(
            app,
            operation="preview_path_mesh",
            input_sha256=report.source_sha256,
            output_sha256=None,
            parameters={
                "mesh_sha256": report.mesh_sha256,
                "preview_layer": layer_index,
                "mesh_point_count": report.mesh_point_count,
                "path_point_count": report.path_point_count,
                "rendered_path_point_count": report.rendered_path_point_count,
                "outside_mesh_count": report.outside_mesh_count,
            },
            result="completed",
        )
        return render_template("path_overlay.html", report=report)

    @app.post("/inspect-mesh")
    @require_role("viewer")
    def inspect_mesh_upload() -> str:
        _require_csrf()
        filename, data = _uploaded_file("mesh_file", ".csv", MAX_MESH_BYTES, "mesh CSV")
        mesh = parse_mesh_csv(data)
        _record_audit(
            app,
            operation="inspect_mesh",
            input_sha256=mesh.sha256,
            output_sha256=None,
            parameters={"filename": filename},
            result="completed",
        )
        return render_template("mesh_inspection.html", filename=filename, mesh=mesh)

    @app.post("/edit-mesh")
    @require_role("operator")
    def edit_mesh_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that edited mesh values require independent operator review."
            )
        filename, data = _uploaded_file("mesh_file", ".csv", MAX_MESH_BYTES, "mesh CSV")
        edit = MeshEditRequest(
            operation=request.form.get("operation", ""),
            value=_bounded_float("edit_value", -10_000, 10_000),
            x_min=_bounded_float("x_min", -100_000, 100_000),
            x_max=_bounded_float("x_max", -100_000, 100_000),
            y_min=_bounded_float("y_min", -100_000, 100_000),
            y_max=_bounded_float("y_max", -100_000, 100_000),
        )
        artifact = build_edited_mesh(data, filename, edit)
        _record_audit(
            app,
            operation="edit_mesh",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "operation": edit.operation,
                "value": edit.value,
                "x_min": edit.x_min,
                "x_max": edit.x_max,
                "y_min": edit.y_min,
                "y_max": edit.y_max,
                "changed_cell_count": artifact.changed_cell_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Changed-Cell-Count"] = str(artifact.changed_cell_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/edit-mesh-falloff")
    @require_role("operator")
    def edit_mesh_falloff_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that falloff-edited mesh values require independent operator review."
            )
        filename, data = _uploaded_file("mesh_file", ".csv", MAX_MESH_BYTES, "mesh CSV")
        edit = MeshFalloffRequest(
            operation=request.form.get("operation", ""),
            value=_bounded_float("edit_value", -10_000, 10_000),
            center_x=_bounded_float("center_x", -100_000, 100_000),
            center_y=_bounded_float("center_y", -100_000, 100_000),
            radius_mm=_bounded_float("radius_mm", 0.000001, 100_000),
            falloff=request.form.get("falloff", ""),
        )
        artifact = build_falloff_mesh(data, filename, edit)
        _record_audit(
            app,
            operation="edit_mesh_falloff",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "operation": edit.operation,
                "value": edit.value,
                "center_x": edit.center_x,
                "center_y": edit.center_y,
                "radius_mm": edit.radius_mm,
                "falloff": edit.falloff,
                "changed_cell_count": artifact.changed_cell_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Changed-Cell-Count"] = str(artifact.changed_cell_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/generate-mesh")
    @require_role("operator")
    def generate_mesh_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that the generated mesh requires independent operator review."
            )
        filename, data = _uploaded_src()
        parameters = MeshGenerationRequest(
            spacing_x_mm=_bounded_float("spacing_x_mm", 0.1, 1000),
            spacing_y_mm=_bounded_float("spacing_y_mm", 0.1, 1000),
            margin_mm=_bounded_float("margin_mm", 0, 10_000),
            baseline_height_mm=_bounded_float("baseline_height_mm", -10_000, 10_000),
        )
        artifact = build_mesh_from_source(data, filename, parameters)
        _record_audit(
            app,
            operation="generate_mesh",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "spacing_x_mm": parameters.spacing_x_mm,
                "spacing_y_mm": parameters.spacing_y_mm,
                "margin_mm": parameters.margin_mm,
                "baseline_height_mm": parameters.baseline_height_mm,
                "x_count": artifact.x_count,
                "y_count": artifact.y_count,
                "cell_count": artifact.cell_count,
                "bounds": artifact.bounds,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="text/csv",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Mesh-Cell-Count"] = str(artifact.cell_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/compensate-mesh-speed")
    @require_role("operator")
    def compensate_mesh_speed_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that mesh-derived speed changes require independent operator review."
            )
        source_name, source_data = _uploaded_src()
        _, mesh_data = _uploaded_file("mesh_file", ".csv", MAX_MESH_BYTES, "mesh CSV")
        parameters = MeshCompensationRequest(
            baseline_height_mm=_bounded_float("baseline_height_mm", -10_000, 10_000),
            zone_step_mm=_bounded_float("zone_step_mm", 0.000001, 100),
            speed_step_fraction=_bounded_float("speed_step_fraction", -1, 1),
            speed_tolerance_mps=_bounded_float("speed_tolerance_mps", 0, 0.1),
        )
        artifact = build_mesh_compensated_source(
            source_data, mesh_data, source_name, parameters
        )
        _record_audit(
            app,
            operation="compensate_mesh_speed",
            input_sha256=artifact.source_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "mesh_sha256": artifact.mesh_sha256,
                "baseline_height_mm": parameters.baseline_height_mm,
                "zone_step_mm": parameters.zone_step_mm,
                "speed_step_fraction": parameters.speed_step_fraction,
                "speed_tolerance_mps": parameters.speed_tolerance_mps,
                "inserted_speed_count": artifact.inserted_speed_count,
                "compensated_motion_count": artifact.compensated_motion_count,
                "baseline_fallback_count": artifact.baseline_fallback_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Source-SHA256"] = artifact.source_sha256
        response.headers["X-Mesh-SHA256"] = artifact.mesh_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Inserted-Speed-Count"] = str(artifact.inserted_speed_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/annotate")
    @require_role("operator")
    def annotate_upload() -> Response:
        _require_csrf()
        _, data = _uploaded_src()
        metadata = MetadataRequest(
            cell_number=_bounded_int("cell_number", 1, 12),
            part_prefix=_bounded_int("part_prefix", 0, 100),
            part_suffix=_bounded_int("part_suffix", 0, 99),
            part_name=request.form.get("part_name", ""),
            part_link=request.form.get("part_link", ""),
            flow_rate_percent=_bounded_int("flow_rate_percent", 0, 100),
            cooling_enabled=request.form.get("cooling_enabled") == "yes",
        )
        artifact = build_annotated_source(data, metadata)
        _record_audit(
            app,
            operation="annotate_metadata",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "cell_number": metadata.cell_number,
                "part_number": f"{metadata.part_prefix:03d}{metadata.part_suffix:02d}",
                "flow_rate_percent": metadata.flow_rate_percent,
                "cooling_enabled": metadata.cooling_enabled,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/modify-velocity")
    @require_role("operator")
    def modify_velocity_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that the requested velocities require independent operator review."
            )
        filename, data = _uploaded_src()
        velocity = VelocityRequest(
            extrusion_mps=_positive_float(
                request.form.get("extrusion_mps", ""), "Extrusion velocity"
            ),
            travel_mps=_positive_float(
                request.form.get("travel_mps", ""), "Travel velocity"
            ),
        )
        artifact = build_velocity_source(data, filename, velocity)
        _record_audit(
            app,
            operation="modify_velocity",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "extrusion_mps": velocity.extrusion_mps,
                "travel_mps": velocity.travel_mps,
                "changed_line_count": artifact.changed_line_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Changed-Line-Count"] = str(artifact.changed_line_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/adjust-xyz")
    @require_role("operator")
    def adjust_xyz_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that the coordinate changes require independent operator review."
            )
        filename, data = _uploaded_src()
        layer_mode = request.form.get("layer_mode", "all")
        if layer_mode == "all":
            first_layer = last_layer = None
        elif layer_mode == "range":
            first_layer = _bounded_int("first_layer", 0, 499_999)
            last_layer = _bounded_int("last_layer", 0, 499_999)
        else:
            raise SourceValidationError("Layer mode must be all or range.")
        adjustment = XYZRequest(
            x_offset_mm=_bounded_float("x_offset_mm", -1000, 1000),
            y_offset_mm=_bounded_float("y_offset_mm", -1000, 1000),
            z_offset_mm=_bounded_float("z_offset_mm", -1000, 1000),
            first_layer=first_layer,
            last_layer=last_layer,
        )
        artifact = build_xyz_source(data, filename, adjustment)
        _record_audit(
            app,
            operation="adjust_xyz",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "x_offset_mm": adjustment.x_offset_mm,
                "y_offset_mm": adjustment.y_offset_mm,
                "z_offset_mm": adjustment.z_offset_mm,
                "layer_mode": layer_mode,
                "first_layer": adjustment.first_layer,
                "last_layer": adjustment.last_layer,
                "changed_line_count": artifact.changed_line_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Changed-Line-Count"] = str(artifact.changed_line_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/merge-paths")
    @require_role("operator")
    def merge_paths_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that the merged path requires independent operator review."
            )
        primary_name, primary_data = _uploaded_src("primary_src")
        secondary_name, secondary_data = _uploaded_src("secondary_src")
        artifact = build_merged_source(
            primary_data,
            secondary_data,
            primary_name,
            secondary_name,
        )
        _record_audit(
            app,
            operation="merge_paths",
            input_sha256=artifact.primary_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "secondary_sha256": artifact.secondary_sha256,
                "primary_block_count": artifact.primary_block_count,
                "secondary_block_count": artifact.secondary_block_count,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Primary-SHA256"] = artifact.primary_sha256
        response.headers["X-Secondary-SHA256"] = artifact.secondary_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/generate-probe-grid")
    @require_role("operator")
    def generate_probe_grid_upload() -> Response:
        _require_csrf()
        if request.form.get("confirm_review") != "yes":
            raise SourceValidationError(
                "Confirm that the probe program requires independent operator review."
            )
        filename, data = _uploaded_src()
        probe = ProbeRequest(
            safe_z_mm=_bounded_float("safe_z_mm", -10_000, 10_000),
            probe_z_mm=_bounded_float("probe_z_mm", -10_000, 10_000),
            spacing_mm=_bounded_float("spacing_mm", 0.1, 1000),
            margin_mm=_bounded_float("margin_mm", 0, 1000),
            travel_speed_mps=_bounded_float("travel_speed_mps", 0.000001, 2),
            probe_speed_mps=_bounded_float("probe_speed_mps", 0.000001, 2),
            scan_pattern=request.form.get("scan_pattern", ""),
            scan_priority=request.form.get("scan_priority", ""),
        )
        artifact = build_probe_source(data, filename, probe)
        _record_audit(
            app,
            operation="generate_probe_grid",
            input_sha256=artifact.input_sha256,
            output_sha256=artifact.output_sha256,
            parameters={
                "point_count": artifact.point_count,
                "bounds": artifact.bounds,
                "safe_z_mm": probe.safe_z_mm,
                "probe_z_mm": probe.probe_z_mm,
                "spacing_mm": probe.spacing_mm,
                "margin_mm": probe.margin_mm,
                "travel_speed_mps": probe.travel_speed_mps,
                "probe_speed_mps": probe.probe_speed_mps,
                "scan_pattern": probe.scan_pattern,
                "scan_priority": probe.scan_priority,
            },
            result="completed",
        )
        response = send_file(
            BytesIO(artifact.data),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=artifact.filename,
            max_age=0,
        )
        response.headers["X-Input-SHA256"] = artifact.input_sha256
        response.headers["X-Output-SHA256"] = artifact.output_sha256
        response.headers["X-Probe-Point-Count"] = str(artifact.point_count)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(SourceValidationError)
    def source_error(error: SourceValidationError) -> tuple[str, int]:
        return render_template("index.html", error=str(error)), 400

    @app.errorhandler(413)
    def too_large(_: Exception) -> tuple[str, int]:
        return render_template("index.html", error="The uploaded file is too large."), 413

    return app


def require_role(required: str) -> Callable[[F], F]:
    """Require a signed-in role at or above ``required``."""

    def decorator(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            role = str(session.get("role", ""))
            if role not in ROLES:
                session.clear()
                return redirect(url_for("login"))
            if ROLES[role] < ROLES[required]:
                abort(403)
            return function(*args, **kwargs)

        return cast(F, wrapped)

    return decorator


def _users_payload(app: Flask, required: bool) -> dict[str, Any] | None:
    injected = app.config.get("USERS_PAYLOAD")
    if injected is not None:
        payload = injected
    else:
        path = Path(str(app.config["USERS_PATH"]))
        if not path.is_file():
            if required:
                raise ValueError("authentication secret is not configured")
            return None
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("users secret must contain a JSON object")
    session_secret = payload.get("session_secret")
    users = payload.get("users")
    if not isinstance(session_secret, str) or len(session_secret) < 32:
        raise ValueError("users secret requires session_secret of at least 32 characters")
    if not isinstance(users, list) or not users:
        raise ValueError("users secret requires a non-empty users list")
    return payload


def _users(app: Flask) -> dict[str, dict[str, str]]:
    payload = _users_payload(app, required=True)
    assert payload is not None
    result: dict[str, dict[str, str]] = {}
    for raw in payload["users"]:
        if not isinstance(raw, dict):
            raise ValueError("invalid user entry")
        username = str(raw.get("username", "")).strip()
        password_hash = str(raw.get("password_hash", "")).strip()
        role = str(raw.get("role", "")).strip().lower()
        if not username or not password_hash or role not in ROLES or username in result:
            raise ValueError("each user needs a unique username, password_hash, and valid role")
        result[username] = {"password_hash": password_hash, "role": role}
    return result


def _require_https(app: Flask) -> None:
    if not app.config["REQUIRE_HTTPS"]:
        return
    forwarded = request.headers.get("X-Forwarded-Proto", "").lower()
    if not request.is_secure and forwarded != "https":
        abort(
            make_response(
                jsonify({"error": f"Use {app.config['PUBLIC_HTTPS_URL']}"}),
                426,
            )
        )


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def _require_csrf() -> None:
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not secrets.compare_digest(str(supplied), str(expected)):
        abort(400, description="invalid CSRF token")


def _uploaded_src(field_name: str = "src_file") -> tuple[str, bytes]:
    return _uploaded_file(field_name, ".src", MAX_SOURCE_BYTES, "SRC file")


def _uploaded_file(
    field_name: str, suffix: str, byte_limit: int, label: str
) -> tuple[str, bytes]:
    upload = request.files.get(field_name)
    if upload is None or not upload.filename:
        raise SourceValidationError(f"Select a {label}.")
    filename = secure_filename(upload.filename)
    if not filename or Path(filename).suffix.lower() != suffix:
        raise SourceValidationError(f"Only {suffix} files are accepted for {label}.")
    data = upload.stream.read(byte_limit + 1)
    if len(data) > byte_limit:
        raise SourceValidationError(
            f"The uploaded {label} exceeds the {byte_limit // (1024 * 1024)} MiB limit."
        )
    return filename, data


def _positive_float(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise SourceValidationError(f"{label} must be numeric.") from exc
    if not 0 < value <= 2:
        raise SourceValidationError(f"{label} must be greater than 0 and at most 2 m/s.")
    return value


def _bounded_float(name: str, minimum: float, maximum: float) -> float:
    label = name.replace("_", " ").title()
    try:
        value = float(request.form.get(name, ""))
    except ValueError as exc:
        raise SourceValidationError(f"{label} must be numeric.") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise SourceValidationError(
            f"{label} must be between {minimum:g} and {maximum:g}."
        )
    return value


def _bounded_int(name: str, minimum: int, maximum: int) -> int:
    try:
        value = int(request.form.get(name, ""))
    except ValueError as exc:
        raise SourceValidationError(f"{name.replace('_', ' ').title()} must be an integer.") from exc
    if not minimum <= value <= maximum:
        raise SourceValidationError(
            f"{name.replace('_', ' ').title()} must be between {minimum} and {maximum}."
        )
    return value


@contextmanager
def _database(app: Flask) -> Iterator[sqlite3.Connection]:
    path = Path(str(app.config["DATABASE_PATH"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _initialize_database(app: Flask) -> None:
    _audit_retention_settings(app)
    with _database(app) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                username TEXT NOT NULL,
                operation TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                output_sha256 TEXT,
                parameters_json TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )


def _record_audit(
    app: Flask,
    *,
    operation: str,
    input_sha256: str,
    output_sha256: str | None,
    parameters: dict[str, Any],
    result: str,
) -> None:
    _initialize_database(app)
    retention_days, max_rows = _audit_retention_settings(app)
    created_at = datetime.now(timezone.utc)
    with _database(app) as connection:
        connection.execute(
            """
            INSERT INTO audit_events (
                created_at, username, operation, input_sha256,
                output_sha256, parameters_json, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at.isoformat(),
                str(session["username"]),
                operation,
                input_sha256,
                output_sha256,
                json.dumps(parameters, sort_keys=True, separators=(",", ":")),
                result,
            ),
        )
        _prune_audit(connection, created_at, retention_days, max_rows)


def _audit_retention_settings(app: Flask) -> tuple[int, int]:
    try:
        retention_days = int(app.config["AUDIT_RETENTION_DAYS"])
        max_rows = int(app.config["AUDIT_MAX_ROWS"])
    except (TypeError, ValueError) as exc:
        raise ValueError("audit retention settings must be integers") from exc
    if not 1 <= retention_days <= 3_650:
        raise ValueError("audit retention days must be between 1 and 3650")
    if not 1 <= max_rows <= 1_000_000:
        raise ValueError("audit maximum rows must be between 1 and 1000000")
    return retention_days, max_rows


def _prune_audit(
    connection: sqlite3.Connection,
    now: datetime,
    retention_days: int,
    max_rows: int,
) -> None:
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    connection.execute("DELETE FROM audit_events WHERE created_at < ?", (cutoff,))
    connection.execute(
        """
        DELETE FROM audit_events
        WHERE id NOT IN (
            SELECT id FROM audit_events ORDER BY id DESC LIMIT ?
        )
        """,
        (max_rows,),
    )
