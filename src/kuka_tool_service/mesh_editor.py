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

    newline = _newline_style(data)
    buffer = StringIO(newline="")
    csv.writer(buffer, lineterminator=newline).writerows(rows)
    output_data = buffer.getvalue().encode(mesh.encoding)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.rsplit(".", 1)[0]).strip("._")
    if not safe_stem:
        safe_stem = "mesh"
    return MeshEditArtifact(
        filename=f"{safe_stem}_edited.csv",
        data=output_data,
        input_sha256=mesh.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        changed_cell_count=changed_count,
    )


def _validate_request(request: MeshEditRequest) -> None:
    if request.operation not in {"set", "add", "subtract", "multiply"}:
        raise SourceValidationError(
            "Mesh edit operation must be set, add, subtract, or multiply."
        )
    values = (request.value, request.x_min, request.x_max, request.y_min, request.y_max)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise SourceValidationError("Mesh edit values and bounds must be finite numbers.")
    if request.x_min > request.x_max or request.y_min > request.y_max:
        raise SourceValidationError("Mesh edit minimum bounds must not exceed maximum bounds.")
    if not -10_000 <= request.value <= 10_000:
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


def _canonical_rows(mesh: MeshGrid) -> list[list[str]]:
    rows = [[""] + [_format_number(value) for value in mesh.y_values]]
    for x_value, z_row in zip(mesh.x_values, mesh.z_values):
        rows.append(
            [_format_number(x_value)]
            + ["" if value is None else _format_number(value) for value in z_row]
        )
    return rows


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    if value.is_integer():
        return str(int(value))
    return repr(value)


def _newline_style(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"
