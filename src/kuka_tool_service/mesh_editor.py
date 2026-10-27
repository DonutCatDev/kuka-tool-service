"""Bounded, auditable transformations for measured mesh CSV files."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from hashlib import sha256
from io import StringIO
import math
import re

from .mesh import MeshGrid, parse_mesh_csv
from .parser import SourceValidationError


@dataclass(frozen=True)
class MeshEditRequest:
    """One rectangular edit expressed in mesh-coordinate space."""

    operation: str
    value: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass(frozen=True)
class MeshFalloffRequest:
    """One radial grouped edit expressed in mesh-coordinate space."""

    operation: str
    value: float
    center_x: float
    center_y: float
    radius_mm: float
    falloff: str


@dataclass(frozen=True)
class MeshEditArtifact:
    filename: str
    data: bytes
    input_sha256: str
    output_sha256: str
    changed_cell_count: int


def build_edited_mesh(
    data: bytes, filename: str, request: MeshEditRequest
) -> MeshEditArtifact:
    """Apply an operation to every measured cell in an inclusive rectangle."""

    _validate_request(request)
    mesh = parse_mesh_csv(data)
    x_indices = _selected_indices(mesh.x_values, request.x_min, request.x_max, "X")
    y_indices = _selected_indices(mesh.y_values, request.y_min, request.y_max, "Y")

    rows = _canonical_rows(mesh)
    changed_count = 0
    for x_index in x_indices:
        for y_index in y_indices:
            current = mesh.z_values[x_index][y_index]
            if current is None:
                raise SourceValidationError(
                    "The selected rectangle contains an unmeasured mesh cell; no edits were applied."
                )
            adjusted = _apply_operation(current, request.operation, request.value)
            if not math.isfinite(adjusted) or not -10_000 <= adjusted <= 10_000:
                raise SourceValidationError(
                    "A resulting mesh height is outside the supported -10000 to 10000 mm range."
                )
            adjusted = round(adjusted, 6)
            rows[x_index + 1][y_index + 1] = _format_number(adjusted)
            if adjusted != current:
                changed_count += 1

    if changed_count == 0:
        raise SourceValidationError("The selected mesh edit would not change any values.")

    return _artifact(data, filename, mesh, rows, changed_count, "edited")


def build_falloff_mesh(
    data: bytes, filename: str, request: MeshFalloffRequest
) -> MeshEditArtifact:
    """Blend a grouped edit radially across measured mesh coordinates."""

    _validate_falloff_request(request)
    mesh = parse_mesh_csv(data)
    rows = _canonical_rows(mesh)
    selected_count = 0
    changed_count = 0
    for x_index, x_value in enumerate(mesh.x_values):
        for y_index, y_value in enumerate(mesh.y_values):
            distance = math.hypot(x_value - request.center_x, y_value - request.center_y)
            if distance > request.radius_mm:
                continue
            weight = _falloff_weight(distance / request.radius_mm, request.falloff)
            if weight <= 0:
                continue
            selected_count += 1
            current = mesh.z_values[x_index][y_index]
            if current is None:
                raise SourceValidationError(
                    "The falloff region contains an unmeasured mesh cell; no edits were applied."
                )
            adjusted = _apply_weighted_operation(
                current, request.operation, request.value, weight
            )
            if not math.isfinite(adjusted) or not -10_000 <= adjusted <= 10_000:
                raise SourceValidationError(
                    "A resulting mesh height is outside the supported -10000 to 10000 mm range."
                )
            adjusted = round(adjusted, 6)
            rows[x_index + 1][y_index + 1] = _format_number(adjusted)
            if adjusted != current:
                changed_count += 1

    if selected_count == 0:
        raise SourceValidationError("The falloff region contains no mesh coordinates.")
    if changed_count == 0:
        raise SourceValidationError("The falloff mesh edit would not change any values.")
    return _artifact(data, filename, mesh, rows, changed_count, "falloff")


def _validate_request(request: MeshEditRequest) -> None:
    _validate_operation_and_value(request.operation, request.value)
    values = (request.value, request.x_min, request.x_max, request.y_min, request.y_max)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise SourceValidationError("Mesh edit values and bounds must be finite numbers.")
    if request.x_min > request.x_max or request.y_min > request.y_max:
        raise SourceValidationError("Mesh edit minimum bounds must not exceed maximum bounds.")


def _validate_falloff_request(request: MeshFalloffRequest) -> None:
    _validate_operation_and_value(request.operation, request.value)
    values = (request.center_x, request.center_y, request.radius_mm)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise SourceValidationError("Falloff center and radius must be finite numbers.")
    if not 0 < request.radius_mm <= 100_000:
        raise SourceValidationError("Falloff radius must be greater than 0 and at most 100000 mm.")
    if request.falloff not in {"linear", "quadratic", "cubic"}:
        raise SourceValidationError("Falloff type must be linear, quadratic, or cubic.")


def _validate_operation_and_value(operation: str, value: float) -> None:
    if operation not in {"set", "add", "subtract", "multiply"}:
        raise SourceValidationError(
            "Mesh edit operation must be set, add, subtract, or multiply."
        )
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SourceValidationError("Mesh edit value must be a finite number.")
    if not -10_000 <= value <= 10_000:
        raise SourceValidationError("Mesh edit value must be between -10000 and 10000.")


def _selected_indices(
    axis: tuple[float, ...], minimum: float, maximum: float, label: str
) -> tuple[int, ...]:
    selected = tuple(
        index for index, coordinate in enumerate(axis) if minimum <= coordinate <= maximum
    )
    if not selected:
        raise SourceValidationError(
            f"The selected {label} bounds contain no mesh coordinates."
        )
    return selected


def _apply_operation(current: float, operation: str, value: float) -> float:
    if operation == "set":
        return value
    if operation == "add":
        return current + value
    if operation == "subtract":
        return current - value
    return current * value


def _falloff_weight(normalized_distance: float, falloff: str) -> float:
    if falloff == "linear":
        return max(0.0, 1 - normalized_distance)
    if falloff == "quadratic":
        return max(0.0, 1 - normalized_distance**2)
    return max(0.0, 1 - normalized_distance**3)


def _apply_weighted_operation(
    current: float, operation: str, value: float, weight: float
) -> float:
    if operation == "set":
        return current + ((value - current) * weight)
    if operation == "add":
        return current + (value * weight)
    if operation == "subtract":
        return current - (value * weight)
    return current * (1 + ((value - 1) * weight))


def _canonical_rows(mesh: MeshGrid) -> list[list[str]]:
    rows = [[""] + [_format_number(value) for value in mesh.y_values]]
    for x_value, z_row in zip(mesh.x_values, mesh.z_values):
        rows.append(
            [_format_number(x_value)]
            + ["" if value is None else _format_number(value) for value in z_row]
        )
    return rows


def _artifact(
    data: bytes,
    filename: str,
    mesh: MeshGrid,
    rows: list[list[str]],
    changed_count: int,
    suffix: str,
) -> MeshEditArtifact:
    newline = _newline_style(data)
    buffer = StringIO(newline="")
    csv.writer(buffer, lineterminator=newline).writerows(rows)
    output_data = buffer.getvalue().encode(mesh.encoding)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.rsplit(".", 1)[0]).strip("._")
    if not safe_stem:
        safe_stem = "mesh"
    return MeshEditArtifact(
        filename=f"{safe_stem}_{suffix}.csv",
        data=output_data,
        input_sha256=mesh.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        changed_cell_count=changed_count,
    )


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    if value.is_integer():
        return str(int(value))
    return repr(value)


def _newline_style(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"
