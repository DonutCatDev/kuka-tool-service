"""Generate deterministic editable mesh grids from strict SRC extrusion bounds."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re

from .mesh import MAX_MESH_AXIS, MAX_MESH_BYTES, MAX_MESH_CELLS, parse_mesh_csv
from .parser import SourceValidationError, decode_source, inspect_source
from .probe_generator import extract_extrusion_points


@dataclass(frozen=True)
class MeshGenerationRequest:
    spacing_x_mm: float
    spacing_y_mm: float
    margin_mm: float
    baseline_height_mm: float


@dataclass(frozen=True)
class GeneratedMeshArtifact:
    filename: str
    data: bytes
    input_sha256: str
    output_sha256: str
    x_count: int
    y_count: int
    cell_count: int
    bounds: dict[str, float]


def build_mesh_from_source(
    data: bytes, filename: str, request: MeshGenerationRequest
) -> GeneratedMeshArtifact:
    """Create a complete baseline mesh covering strict extrusion coordinates."""

    _validate_request(request)
    document = decode_source(data)
    inspect_source(data, filename=filename)
    points, _ = extract_extrusion_points(document.lines, filename)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_values = _covering_axis(min(xs), max(xs), request.spacing_x_mm, request.margin_mm)
    y_values = _covering_axis(min(ys), max(ys), request.spacing_y_mm, request.margin_mm)
    if len(x_values) > MAX_MESH_AXIS or len(y_values) > MAX_MESH_AXIS:
        raise SourceValidationError(
            f"A generated mesh axis exceeds the {MAX_MESH_AXIS:,}-value limit."
        )
    cell_count = len(x_values) * len(y_values)
    if cell_count > MAX_MESH_CELLS:
        raise SourceValidationError(
            f"Generated mesh contains {cell_count:,} cells; the limit is {MAX_MESH_CELLS:,}."
        )
    bounds = {
        "min_x": x_values[0],
        "max_x": x_values[-1],
        "min_y": y_values[0],
        "max_y": y_values[-1],
    }
    if any(abs(value) > 100_000 for value in bounds.values()):
        raise SourceValidationError("Generated mesh bounds exceed the +/-100000 mm limit.")

    header = "," + ",".join(_format_number(value) for value in y_values)
    baseline = _format_number(round(request.baseline_height_mm, 6))
    lines = [header]
    for x_value in x_values:
        lines.append(
            ",".join([_format_number(x_value)] + [baseline] * len(y_values))
        )
    output_data = ("\n".join(lines) + "\n").encode("utf-8")
    if len(output_data) > MAX_MESH_BYTES:
        raise SourceValidationError("Generated mesh exceeds the 8 MiB CSV limit.")
    parse_mesh_csv(output_data)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).stem).strip("._")
    if not safe_stem:
        safe_stem = "program"
    return GeneratedMeshArtifact(
        filename=f"{safe_stem}_mesh.csv",
        data=output_data,
        input_sha256=document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        x_count=len(x_values),
        y_count=len(y_values),
        cell_count=cell_count,
        bounds=bounds,
    )


def _validate_request(request: MeshGenerationRequest) -> None:
    values = (
        request.spacing_x_mm,
        request.spacing_y_mm,
        request.margin_mm,
        request.baseline_height_mm,
    )
    if not all(math.isfinite(value) for value in values):
        raise SourceValidationError("Mesh generation parameters must be finite numbers.")
    if not 0.1 <= request.spacing_x_mm <= 1000 or not 0.1 <= request.spacing_y_mm <= 1000:
        raise SourceValidationError("Mesh spacing must be between 0.1 and 1000 mm.")
    if not 0 <= request.margin_mm <= 10_000:
        raise SourceValidationError("Mesh margin must be between 0 and 10000 mm.")
    if not -10_000 <= request.baseline_height_mm <= 10_000:
        raise SourceValidationError("Baseline height must be between -10000 and 10000 mm.")


def _covering_axis(
    minimum: float, maximum: float, spacing: float, margin: float
) -> list[float]:
    start = math.floor((minimum - margin) / spacing) * spacing
    stop = math.ceil((maximum + margin) / spacing) * spacing
    if stop == start:
        stop += spacing
    count = int(round((stop - start) / spacing))
    return [round(start + index * spacing, 9) for index in range(count + 1)]


def _format_number(value: float) -> str:
    if value == 0:
        return "0"
    if value.is_integer():
        return str(int(value))
    return repr(value)
