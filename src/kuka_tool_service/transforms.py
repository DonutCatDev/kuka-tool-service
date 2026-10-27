"""Controlled transformations for reviewable SRC artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import re

from .parser import SourceValidationError, decode_source, inspect_source


_DEF_LINE = re.compile(
    r"^(?P<prefix>\s*DEF\s+)(?P<name>.+?)(?P<suffix>\s*\(\s*\).*)$",
    re.IGNORECASE,
)
_METADATA_LINE = re.compile(
    r"^; (?:Cell Number|Part Number|Part Name|Part Link|Flow Rate|Cooling Enabled|"
    r"Initial Layer Speed|Final Layer Speed|Time Estimate) ="
)
_KRL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,23}$")
_VELOCITY_VALUE = re.compile(
    r"(?P<prefix>\$VEL\.CP\s*=\s*)"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)",
    re.IGNORECASE,
)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)
_LIN_BODY = re.compile(r"^\s*LIN\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_COORD_VALUE = re.compile(
    r"(?P<prefix>\b(?P<axis>[XYZ])\s*)"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MetadataRequest:
    """Validated metadata fields used to create an annotated artifact."""

    cell_number: int
    part_prefix: int
    part_suffix: int
    part_name: str
    part_link: str
    flow_rate_percent: int
    cooling_enabled: bool


@dataclass(frozen=True)
class GeneratedArtifact:
    """One generated program and its provenance."""

    filename: str
    data: bytes
    input_sha256: str
    output_sha256: str
    changed_line_count: int


@dataclass(frozen=True)
class VelocityRequest:
    """Replacement speeds for marker-classified motion regions."""

    extrusion_mps: float
    travel_mps: float


@dataclass(frozen=True)
class XYZRequest:
    """Cartesian offsets applied to complete LIN motions in extrusion regions."""

    x_offset_mm: float
    y_offset_mm: float
    z_offset_mm: float


def build_annotated_source(data: bytes, request: MetadataRequest) -> GeneratedArtifact:
    """Add or replace managed metadata while preserving encoding and newlines."""

    _validate_request(request)
    document = decode_source(data)
    report = inspect_source(data)
    safe_part_name = re.sub(r"[^A-Za-z0-9]+", "_", request.part_name.upper()).strip("_")
    output_stem = (
        f"CELL{request.cell_number:02d}-{request.part_prefix:03d}{request.part_suffix:02d}_"
        f"{safe_part_name}_{request.flow_rate_percent}%"
    )
    if not _KRL_IDENTIFIER.fullmatch(output_stem.replace("-", "_").replace("%", "P")):
        # KRL identifiers are short; keep the filename descriptive but derive a bounded DEF name.
        def_name = f"C{request.cell_number:02d}_{request.part_prefix:03d}{request.part_suffix:02d}"
    else:
        def_name = output_stem.replace("-", "_").replace("%", "P")

    lines = list(document.lines)
    def_index = next((index for index, line in enumerate(lines) if _DEF_LINE.match(line)), None)
    if def_index is None:
        raise SourceValidationError("Metadata annotation requires a supported DEF declaration.")

    match = _DEF_LINE.match(lines[def_index])
    assert match is not None
    lines[def_index] = f"{match.group('prefix')}{def_name}{match.group('suffix')}"

    remove_index = def_index + 1
    while remove_index < len(lines) and _METADATA_LINE.match(lines[remove_index]):
        del lines[remove_index]

    initial = (
        f"{report.initial_layer_speed_mps * 1000:.3f} mm/s"
        if report.initial_layer_speed_mps is not None
        else "n/a"
    )
    final = (
        f"{report.final_layer_speed_mps * 1000:.3f} mm/s"
        if report.final_layer_speed_mps is not None
        else "n/a"
    )
    runtime_minutes = round(report.estimated_runtime_seconds / 60)
    metadata = [
        f"; Cell Number = CELL{request.cell_number:02d}",
        f"; Part Number = {request.part_prefix:03d}{request.part_suffix:02d}",
        f"; Part Name = {request.part_name.strip().upper()}",
        f"; Part Link = {request.part_link.strip()}",
        f"; Flow Rate = {request.flow_rate_percent}%",
        f"; Cooling Enabled = {'yes' if request.cooling_enabled else 'no'}",
        f"; Initial Layer Speed = {initial}",
        f"; Final Layer Speed = {final}",
        f"; Time Estimate = {runtime_minutes // 60:02d}:{runtime_minutes % 60:02d}",
    ]
    lines[def_index + 1 : def_index + 1] = metadata

    output_text = document.newline.join(lines)
    if document.terminal_newline:
        output_text += document.newline
    output_data = output_text.encode(document.encoding)
    return GeneratedArtifact(
        filename=f"{output_stem}.src",
        data=output_data,
        input_sha256=document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        changed_line_count=len(metadata) + 1,
    )


def build_velocity_source(
    data: bytes, filename: str, request: VelocityRequest
) -> GeneratedArtifact:
    """Replace marker-classified velocities without changing other source text."""

    _validate_velocity_request(request)
    document = decode_source(data)
    # Inspection applies the same resource limits and catches unsupported source basics.
    inspect_source(data, filename=filename)
    lines = list(document.lines)
    phase = "initial"
    expected_marker = "end"
    marker_count = 0
    changed_count = 0
    changed_by_phase = {"extrusion": 0, "travel": 0}

    for index, line in enumerate(lines):
        has_start = _TRAVEL_START.search(line) is not None
        has_end = _TRAVEL_END.search(line) is not None
        if has_start and has_end:
            raise SourceValidationError(
                f"Line {index + 1} contains ambiguous travel markers."
            )
        if has_end:
            if expected_marker != "end":
                raise SourceValidationError(
                    f"Unexpected travel-end marker on line {index + 1}; markers must alternate."
                )
            phase = "extrusion"
            expected_marker = "start"
            marker_count += 1
        elif has_start:
            if expected_marker != "start":
                raise SourceValidationError(
                    f"Unexpected travel-start marker on line {index + 1}; markers must alternate."
                )
            phase = "travel"
            expected_marker = "end"
            marker_count += 1

        match = _VELOCITY_VALUE.search(line)
        if match is None or phase == "initial":
            continue
        replacement = (
            request.extrusion_mps if phase == "extrusion" else request.travel_mps
        )
        lines[index] = (
            line[: match.start("value")]
            + f"{replacement:.6f}"
            + line[match.end("value") :]
        )
        changed_count += 1
        changed_by_phase[phase] += 1

    if marker_count < 2:
        raise SourceValidationError(
            "Velocity modification requires alternating travel-end and travel-start markers."
        )
    for phase_name in ("extrusion", "travel"):
        if changed_by_phase[phase_name] == 0:
            raise SourceValidationError(
                f"No $VEL.CP command was found in a {phase_name} region."
            )

    output_text = document.newline.join(lines)
    if document.terminal_newline:
        output_text += document.newline
    output_data = output_text.encode(document.encoding)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.rsplit(".", 1)[0]).strip("._")
    if not safe_stem:
        safe_stem = "program"
    return GeneratedArtifact(
        filename=f"{safe_stem}_velocity.src",
        data=output_data,
        input_sha256=document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        changed_line_count=changed_count,
    )


def build_xyz_source(data: bytes, filename: str, request: XYZRequest) -> GeneratedArtifact:
    """Offset complete extrusion LIN coordinates using strict travel markers."""

    _validate_xyz_request(request)
    document = decode_source(data)
    inspect_source(data, filename=filename)
    lines = list(document.lines)
    phase = "initial"
    expected_marker = "end"
    marker_count = 0
    changed_count = 0
    offsets = {
        "X": request.x_offset_mm,
        "Y": request.y_offset_mm,
        "Z": request.z_offset_mm,
    }

    for index, line in enumerate(lines):
        has_start = _TRAVEL_START.search(line) is not None
        has_end = _TRAVEL_END.search(line) is not None
        if has_start and has_end:
            raise SourceValidationError(
                f"Line {index + 1} contains ambiguous travel markers."
            )
        if has_end:
            if expected_marker != "end":
                raise SourceValidationError(
                    f"Unexpected travel-end marker on line {index + 1}; markers must alternate."
                )
            phase = "extrusion"
            expected_marker = "start"
            marker_count += 1
        elif has_start:
            if expected_marker != "start":
                raise SourceValidationError(
                    f"Unexpected travel-start marker on line {index + 1}; markers must alternate."
                )
            phase = "travel"
            expected_marker = "end"
            marker_count += 1

        motion = _LIN_BODY.search(line)
        if motion is None or phase != "extrusion":
            continue
        coordinates = list(_COORD_VALUE.finditer(motion.group("body")))
        axes = [match.group("axis").upper() for match in coordinates]
        if set(axes) != {"X", "Y", "Z"} or len(axes) != 3:
            raise SourceValidationError(
                f"Extrusion LIN on line {index + 1} must contain exactly one X, Y, and Z coordinate."
            )

        def replace_coordinate(match: re.Match[str]) -> str:
            axis = match.group("axis").upper()
            original = float(match.group("value"))
            adjusted = original + offsets[axis]
            if not math.isfinite(original) or not math.isfinite(adjusted):
                raise SourceValidationError(
                    f"Coordinate on line {index + 1} is outside the supported numeric range."
                )
            return f"{match.group('prefix')}{adjusted:.3f}"

        adjusted_body = _COORD_VALUE.sub(replace_coordinate, motion.group("body"))
        lines[index] = line[: motion.start("body")] + adjusted_body + line[motion.end("body") :]
        changed_count += 1

    if marker_count < 2:
        raise SourceValidationError(
            "XYZ adjustment requires alternating travel-end and travel-start markers."
        )
    if changed_count == 0:
        raise SourceValidationError("No complete extrusion LIN command was found to adjust.")

    output_text = document.newline.join(lines)
    if document.terminal_newline:
        output_text += document.newline
    output_data = output_text.encode(document.encoding)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.rsplit(".", 1)[0]).strip("._")
    if not safe_stem:
        safe_stem = "program"
    return GeneratedArtifact(
        filename=f"{safe_stem}_xyz.src",
        data=output_data,
        input_sha256=document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        changed_line_count=changed_count,
    )


def _validate_request(request: MetadataRequest) -> None:
    if not 1 <= request.cell_number <= 12:
        raise SourceValidationError("Cell number must be between 1 and 12.")
    if not 0 <= request.part_prefix <= 100:
        raise SourceValidationError("Part prefix must be between 0 and 100.")
    if not 0 <= request.part_suffix <= 99:
        raise SourceValidationError("Part suffix must be between 0 and 99.")
    if not 0 <= request.flow_rate_percent <= 100:
        raise SourceValidationError("Flow rate must be between 0 and 100 percent.")
    for label, value in (("Part name", request.part_name), ("Part link", request.part_link)):
        if not value.strip() or len(value.strip()) > 120:
            raise SourceValidationError(f"{label} must contain 1 to 120 characters.")
        if any(character in value for character in ("\r", "\n", ";")):
            raise SourceValidationError(f"{label} contains unsupported control characters.")


def _validate_velocity_request(request: VelocityRequest) -> None:
    for label, value in (
        ("Extrusion velocity", request.extrusion_mps),
        ("Travel velocity", request.travel_mps),
    ):
        if not isinstance(value, (int, float)) or not 0 < value <= 2:
            raise SourceValidationError(
                f"{label} must be greater than 0 and at most 2 m/s."
            )


def _validate_xyz_request(request: XYZRequest) -> None:
    values = (request.x_offset_mm, request.y_offset_mm, request.z_offset_mm)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise SourceValidationError("XYZ offsets must be finite numbers.")
    if any(abs(value) > 1000 for value in values):
        raise SourceValidationError("XYZ offsets must be between -1000 and 1000 mm.")
    if all(value == 0 for value in values):
        raise SourceValidationError("At least one XYZ offset must be non-zero.")
