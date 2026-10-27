"""Endpoint-based mesh speed compensation for extrusion LIN commands."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re
from time import monotonic

from .mesh import compensated_speed, parse_mesh_csv
from .parser import (
    MAX_PARSE_SECONDS,
    MAX_SOURCE_BYTES,
    SourceValidationError,
    decode_source,
    inspect_source,
)


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_LIN = re.compile(r"^\s*LIN\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_COORD = re.compile(rf"\b([XYZ])\s*({_NUMBER})", re.IGNORECASE)
_VELOCITY = re.compile(rf"\$VEL\.CP\s*=\s*({_NUMBER})", re.IGNORECASE)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)


@dataclass(frozen=True)
class MeshCompensationRequest:
    baseline_height_mm: float
    zone_step_mm: float
    speed_step_fraction: float
    speed_tolerance_mps: float


@dataclass(frozen=True)
class MeshCompensationArtifact:
    filename: str
    data: bytes
    source_sha256: str
    mesh_sha256: str
    output_sha256: str
    inserted_speed_count: int
    compensated_motion_count: int
    baseline_fallback_count: int


def build_mesh_compensated_source(
    source_data: bytes,
    mesh_data: bytes,
    source_filename: str,
    request: MeshCompensationRequest,
) -> MeshCompensationArtifact:
    """Insert endpoint-derived speeds before extrusion motions without moving them."""

    _validate_request(request)
    document = decode_source(source_data)
    before = inspect_source(source_data, filename=source_filename)
    mesh = parse_mesh_csv(mesh_data)
    deadline = monotonic() + MAX_PARSE_SECONDS
    lines: list[str] = []
    phase = "initial"
    expected_marker = "end"
    marker_count = 0
    current_program_speed: float | None = None
    active_output_speed: float | None = None
    inserted_count = 0
    compensated_count = 0
    fallback_count = 0

    for index, line in enumerate(document.lines):
        if index % 4096 == 0 and monotonic() > deadline:
            raise SourceValidationError(
                f"Mesh compensation exceeded the {MAX_PARSE_SECONDS:g}-second processing limit."
            )
        has_start = _TRAVEL_START.search(line) is not None
        has_end = _TRAVEL_END.search(line) is not None
        if has_start and has_end:
            raise SourceValidationError(f"Ambiguous travel markers on line {index + 1}.")
        if has_end:
            if expected_marker != "end":
                raise SourceValidationError("Travel markers must begin with travel-end and alternate.")
            phase, expected_marker, marker_count = "extrusion", "start", marker_count + 1
        elif has_start:
            if expected_marker != "start":
                raise SourceValidationError("Travel markers must begin with travel-end and alternate.")
            phase, expected_marker, marker_count = "travel", "end", marker_count + 1

        velocity_match = _VELOCITY.search(line)
        if velocity_match:
            velocity = float(velocity_match.group(1))
            if not math.isfinite(velocity) or velocity <= 0:
                raise SourceValidationError(f"Velocity on line {index + 1} must be positive and finite.")
            current_program_speed = velocity
            active_output_speed = velocity
            lines.append(line)
            continue

        motion = _LIN.search(line)
        if motion is None or phase != "extrusion":
            lines.append(line)
            continue
        coordinates = _coordinates(motion.group("body"))
        if coordinates is None:
            raise SourceValidationError(
                f"Extrusion LIN on line {index + 1} must contain exactly one finite X, Y, and Z."
            )
        if current_program_speed is None:
            raise SourceValidationError(
                f"Extrusion LIN on line {index + 1} has no preceding $VEL.CP assignment."
            )
        compensated_count += 1
        if current_program_speed <= 0.1:
            x, y, _ = coordinates
            height, used_fallback = mesh.height_lookup(x, y, request.baseline_height_mm)
            if used_fallback:
                fallback_count += 1
            target_speed = compensated_speed(
                current_program_speed,
                height,
                request.baseline_height_mm,
                request.zone_step_mm,
                request.speed_step_fraction,
                request.speed_tolerance_mps,
            )
            if active_output_speed is None or abs(target_speed - active_output_speed) > request.speed_tolerance_mps:
                indent = line[: len(line) - len(line.lstrip())]
                lines.append(f"{indent}$VEL.CP = {target_speed:.6f}")
                active_output_speed = target_speed
                inserted_count += 1
        lines.append(line)

    if marker_count < 2 or compensated_count == 0:
        raise SourceValidationError(
            "Mesh compensation requires marker-classified extrusion LIN commands."
        )
    if inserted_count == 0:
        raise SourceValidationError("Mesh compensation produced no speed changes.")
    output_text = document.newline.join(lines)
    if document.terminal_newline:
        output_text += document.newline
    output_data = output_text.encode(document.encoding)
    if len(output_data) > MAX_SOURCE_BYTES:
        raise SourceValidationError("Mesh-compensated output exceeds the 32 MiB source limit.")
    after = inspect_source(output_data, filename="mesh-compensated-output.src")
    if after.lin_count != before.lin_count or after.incomplete_motion_count:
        raise SourceValidationError("Mesh-compensated output did not preserve complete LIN motions.")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source_filename).stem).strip("._") or "program"
    return MeshCompensationArtifact(
        filename=f"{stem}_mesh_speed.src",
        data=output_data,
        source_sha256=document.sha256,
        mesh_sha256=mesh.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        inserted_speed_count=inserted_count,
        compensated_motion_count=compensated_count,
        baseline_fallback_count=fallback_count,
    )


def _coordinates(body: str) -> tuple[float, float, float] | None:
    matches = _COORD.findall(body)
    axes = [axis.upper() for axis, _ in matches]
    if set(axes) != {"X", "Y", "Z"} or len(axes) != 3:
        return None
    values = {axis.upper(): float(value) for axis, value in matches}
    if not all(math.isfinite(value) for value in values.values()):
        return None
    return values["X"], values["Y"], values["Z"]


def _validate_request(request: MeshCompensationRequest) -> None:
    values = (
        request.baseline_height_mm,
        request.zone_step_mm,
        request.speed_step_fraction,
        request.speed_tolerance_mps,
    )
    if not all(math.isfinite(value) for value in values):
        raise SourceValidationError("Mesh compensation parameters must be finite.")
    if not -10_000 <= request.baseline_height_mm <= 10_000:
        raise SourceValidationError("Baseline height must be within +/-10000 mm.")
    if not 0 < request.zone_step_mm <= 100:
        raise SourceValidationError("Zone step must be greater than 0 and at most 100 mm.")
    if not -1 <= request.speed_step_fraction <= 1:
        raise SourceValidationError("Speed step fraction must be between -1 and 1.")
    if not 0 <= request.speed_tolerance_mps <= 0.1:
        raise SourceValidationError("Speed tolerance must be between 0 and 0.1 m/s.")
