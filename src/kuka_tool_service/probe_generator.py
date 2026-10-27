"""Deterministic review-only probing grid generation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re

from .parser import MAX_SOURCE_BYTES, SourceValidationError, decode_source, inspect_source


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_LIN = re.compile(r"^\s*LIN\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_COORD = re.compile(
    rf"(?P<prefix>\b(?P<axis>[XYZ])\s*)(?P<value>{_NUMBER})", re.IGNORECASE
)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)
MAX_PROBE_POINTS = 10_000


@dataclass(frozen=True)
class ProbeRequest:
    safe_z_mm: float
    probe_z_mm: float
    spacing_mm: float
    margin_mm: float
    travel_speed_mps: float
    probe_speed_mps: float
    scan_pattern: str
    scan_priority: str


@dataclass(frozen=True)
class ProbeArtifact:
    filename: str
    data: bytes
    input_sha256: str
    output_sha256: str
    point_count: int
    bounds: dict[str, float]


def build_probe_source(data: bytes, filename: str, request: ProbeRequest) -> ProbeArtifact:
    """Generate a standalone review-only probe program from extrusion XY bounds."""

    _validate_request(request)
    document = decode_source(data)
    inspect_source(data, filename=filename)
    if document.newline_label == "mixed":
        raise SourceValidationError("Probe generation does not accept mixed newline styles.")
    points, template = _extrusion_points(document.lines, filename)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    center_x = (min(xs) + max(xs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    half_x = math.ceil((((max(xs) - min(xs)) / 2) + request.margin_mm) / request.spacing_mm) * request.spacing_mm
    half_y = math.ceil((((max(ys) - min(ys)) / 2) + request.margin_mm) / request.spacing_mm) * request.spacing_mm
    bounds = {
        "min_x": center_x - half_x,
        "max_x": center_x + half_x,
        "min_y": center_y - half_y,
        "max_y": center_y + half_y,
    }
    if any(abs(value) > 10_000 for value in bounds.values()):
        raise SourceValidationError("Generated probe bounds exceed the +/-10000 mm limit.")
    x_values = _axis_values(bounds["min_x"], bounds["max_x"], request.spacing_mm)
    y_values = _axis_values(bounds["min_y"], bounds["max_y"], request.spacing_mm)
    point_count = len(x_values) * len(y_values)
    if point_count > MAX_PROBE_POINTS:
        raise SourceValidationError(
            f"Probe grid contains {point_count:,} points; the limit is {MAX_PROBE_POINTS:,}."
        )
    scan_points = _scan_points(x_values, y_values, request.scan_priority, request.scan_pattern)

    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).stem).strip("._") or "program"
    lines = [
        "&ACCESS RVP",
        "DEF PROBE_GRID()",
        "; REVIEW-ONLY PROBING ARTIFACT - NOT CONTROLLER VALIDATED",
        "; This file intentionally omits source setup, tool/base, safety, and shutdown logic.",
        f"; INPUT_SHA256 = {document.sha256}",
        f"; SOURCE_FILE = {safe_stem}.src",
        f"; GRID_POINTS = {point_count}",
        f"; GRID_BOUNDS = X[{bounds['min_x']:.3f},{bounds['max_x']:.3f}] Y[{bounds['min_y']:.3f},{bounds['max_y']:.3f}]",
        f"; SPACING_MM = {request.spacing_mm:.3f}",
        f"; SAFE_Z_MM = {request.safe_z_mm:.3f}",
        f"; PROBE_Z_MM = {request.probe_z_mm:.3f}",
        f"; SCAN = {request.scan_priority}/{request.scan_pattern}",
    ]
    current_speed: float | None = None
    for x, y in scan_points:
        if current_speed != request.travel_speed_mps:
            lines.append(f"$VEL.CP = {request.travel_speed_mps:.6f}")
            current_speed = request.travel_speed_mps
        lines.append(_replace_xyz(template, x, y, request.safe_z_mm))
        lines.append("; PROBE DOWN")
        if current_speed != request.probe_speed_mps:
            lines.append(f"$VEL.CP = {request.probe_speed_mps:.6f}")
            current_speed = request.probe_speed_mps
        lines.append(_replace_xyz(template, x, y, request.probe_z_mm))
        lines.append("HALT")
        lines.append("; RETURN TO SAFE HEIGHT")
        if current_speed != request.travel_speed_mps:
            lines.append(f"$VEL.CP = {request.travel_speed_mps:.6f}")
            current_speed = request.travel_speed_mps
        lines.append(_replace_xyz(template, x, y, request.safe_z_mm))
    lines.append("END")
    output_text = document.newline.join(lines) + document.newline
    output_data = output_text.encode(document.encoding)
    if len(output_data) > MAX_SOURCE_BYTES:
        raise SourceValidationError("Generated probe program exceeds the 32 MiB source limit.")
    return ProbeArtifact(
        filename=f"{safe_stem}_probe_grid.src",
        data=output_data,
        input_sha256=document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        point_count=point_count,
        bounds=bounds,
    )


def _extrusion_points(
    lines: tuple[str, ...], filename: str
) -> tuple[list[tuple[float, float, float]], str]:
    phase = "initial"
    expected = "end"
    markers = 0
    points: list[tuple[float, float, float]] = []
    template = ""
    for index, line in enumerate(lines):
        has_start = _TRAVEL_START.search(line) is not None
        has_end = _TRAVEL_END.search(line) is not None
        if has_start and has_end:
            raise SourceValidationError(f"{filename} has ambiguous markers on line {index + 1}.")
        if has_end:
            if expected != "end":
                raise SourceValidationError(f"{filename} travel markers do not alternate.")
            phase, expected, markers = "extrusion", "start", markers + 1
        elif has_start:
            if expected != "start":
                raise SourceValidationError(f"{filename} travel markers do not alternate.")
            phase, expected, markers = "travel", "end", markers + 1
        motion = _LIN.search(line)
        if motion is None or phase != "extrusion":
            continue
        coordinates = _coordinates(motion.group("body"))
        if coordinates is None:
            raise SourceValidationError(
                f"{filename} has an incomplete or duplicate extrusion LIN on line {index + 1}."
            )
        points.append(coordinates)
        if not template:
            template = line
    if markers < 2 or not points:
        raise SourceValidationError("Probe generation requires marker-classified extrusion LIN commands.")
    return points, template


def _coordinates(body: str) -> tuple[float, float, float] | None:
    matches = list(_COORD.finditer(body))
    axes = [match.group("axis").upper() for match in matches]
    if set(axes) != {"X", "Y", "Z"} or len(axes) != 3:
        return None
    values = {match.group("axis").upper(): float(match.group("value")) for match in matches}
    if not all(math.isfinite(value) for value in values.values()):
        return None
    return values["X"], values["Y"], values["Z"]


def _replace_xyz(template: str, x: float, y: float, z: float) -> str:
    replacements = {"X": x, "Y": y, "Z": z}
    motion = _LIN.search(template)
    assert motion is not None
    body = _COORD.sub(
        lambda match: f"{match.group('prefix')}{replacements[match.group('axis').upper()]:.3f}",
        motion.group("body"),
    )
    return template[: motion.start("body")] + body + template[motion.end("body") :]


def _axis_values(minimum: float, maximum: float, spacing: float) -> list[float]:
    count = int(round((maximum - minimum) / spacing))
    return [minimum + (index * spacing) for index in range(count + 1)]


def _scan_points(
    xs: list[float], ys: list[float], priority: str, pattern: str
) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    if priority == "row":
        for index, y in enumerate(ys):
            row = xs if pattern == "one_way" or index % 2 == 0 else list(reversed(xs))
            result.extend((x, y) for x in row)
    else:
        for index, x in enumerate(xs):
            column = ys if pattern == "one_way" or index % 2 == 0 else list(reversed(ys))
            result.extend((x, y) for y in column)
    return result


def _validate_request(request: ProbeRequest) -> None:
    numeric = (
        request.safe_z_mm,
        request.probe_z_mm,
        request.spacing_mm,
        request.margin_mm,
        request.travel_speed_mps,
        request.probe_speed_mps,
    )
    if not all(math.isfinite(value) for value in numeric):
        raise SourceValidationError("Probe parameters must be finite numbers.")
    if not -10_000 <= request.probe_z_mm < request.safe_z_mm <= 10_000:
        raise SourceValidationError("Safe Z must be greater than probe Z within +/-10000 mm.")
    if not 0.1 <= request.spacing_mm <= 1000:
        raise SourceValidationError("Probe spacing must be between 0.1 and 1000 mm.")
    if not 0 <= request.margin_mm <= 1000:
        raise SourceValidationError("Probe margin must be between 0 and 1000 mm.")
    if not 0 < request.travel_speed_mps <= 2 or not 0 < request.probe_speed_mps <= 2:
        raise SourceValidationError("Probe speeds must be greater than 0 and at most 2 m/s.")
    if request.scan_pattern not in {"one_way", "zigzag"}:
        raise SourceValidationError("Scan pattern must be one_way or zigzag.")
    if request.scan_priority not in {"row", "column"}:
        raise SourceValidationError("Scan priority must be row or column.")
