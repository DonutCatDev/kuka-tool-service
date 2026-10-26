"""KUKA SRC parsing based on the established LFAM file conventions."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
import re
from time import monotonic
from typing import Final

from .models import InspectionReport, MotionSegment, SourceDocument, VelocityCommand


MAX_SOURCE_BYTES: Final = 32 * 1024 * 1024
MAX_SOURCE_LINES: Final = 500_000
DEFAULT_SPEED_MPS: Final = 0.06
MAX_PARSE_SECONDS: Final = 15.0

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_DEF_PATTERN = re.compile(
    r"^\s*DEF\s+(.+?)\s*\(\s*\)", re.IGNORECASE
)
_MOTION_PATTERN = re.compile(r"\b(LIN|PTP)\b\s*\{([^}]*)\}", re.IGNORECASE)
_COORD_PATTERN = re.compile(rf"\b([XYZ])\s*({_NUMBER})", re.IGNORECASE)
_VELOCITY_PATTERN = re.compile(rf"\$VEL\.CP\s*=\s*({_NUMBER})", re.IGNORECASE)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)


class SourceValidationError(ValueError):
    """Raised when source bytes cannot be inspected safely."""


def decode_source(data: bytes) -> SourceDocument:
    """Decode source bytes while recording information needed for byte fidelity."""

    if not data:
        raise SourceValidationError("The uploaded SRC file is empty.")
    if len(data) > MAX_SOURCE_BYTES:
        raise SourceValidationError(
            f"The uploaded SRC file exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB limit."
        )

    encoding = ""
    text = ""
    candidates = ("utf-8-sig",) if data.startswith(b"\xef\xbb\xbf") else ()
    candidates += ("utf-8", "cp1252", "latin-1")
    for candidate in candidates:
        try:
            text = data.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if not encoding:
        raise SourceValidationError("The SRC file encoding could not be decoded.")

    lines = tuple(text.splitlines())
    if len(lines) > MAX_SOURCE_LINES:
        raise SourceValidationError(
            f"The SRC file exceeds the {MAX_SOURCE_LINES:,}-line limit."
        )

    crlf_count = data.count(b"\r\n")
    lf_count = data.count(b"\n") - crlf_count
    cr_count = data.count(b"\r") - crlf_count
    newline_counts = {"\r\n": crlf_count, "\n": lf_count, "\r": cr_count}
    present = [item for item, count in newline_counts.items() if count]
    newline = max(newline_counts, key=newline_counts.get) if present else "\n"
    labels = {"\r\n": "CRLF", "\n": "LF", "\r": "CR"}
    newline_label = "mixed" if len(present) > 1 else labels[newline]
    terminal_newline = data.endswith((b"\r\n", b"\n", b"\r"))

    return SourceDocument(
        original_bytes=data,
        text=text,
        lines=lines,
        encoding=encoding,
        newline=newline,
        newline_label=newline_label,
        terminal_newline=terminal_newline,
        sha256=sha256(data).hexdigest(),
    )


def _parse_motion(
    line: str,
    line_number: int,
    velocity_mps: float | None,
    phase: str,
) -> tuple[MotionSegment | None, bool]:
    match = _MOTION_PATTERN.search(line)
    if not match:
        return None, False
    coordinates = {
        axis.upper(): float(value)
        for axis, value in _COORD_PATTERN.findall(match.group(2))
    }
    if not {"X", "Y", "Z"}.issubset(coordinates):
        return None, True
    return (
        MotionSegment(
            line_number=line_number,
            command=match.group(1).upper(),
            x=coordinates["X"],
            y=coordinates["Y"],
            z=coordinates["Z"],
            velocity_mps=velocity_mps,
            phase=phase,
        ),
        False,
    )


def inspect_source(
    data: bytes,
    filename: str = "upload.src",
    default_speed_mps: float = DEFAULT_SPEED_MPS,
    max_parse_seconds: float = MAX_PARSE_SECONDS,
) -> InspectionReport:
    """Inspect one SRC file without modifying its bytes."""

    if not math.isfinite(default_speed_mps) or default_speed_mps <= 0:
        raise SourceValidationError("Default speed must be a positive finite value.")
    if not math.isfinite(max_parse_seconds) or max_parse_seconds <= 0:
        raise SourceValidationError("Parse time limit must be a positive finite value.")

    document = decode_source(data)
    deadline = monotonic() + max_parse_seconds
    def_name: str | None = None
    phase = "initial"
    current_speed = default_speed_mps
    velocities: list[VelocityCommand] = []
    motions: list[MotionSegment] = []
    incomplete_motion_count = 0
    raw_lin_count = 0
    raw_ptp_count = 0
    travel_start_lines: list[int] = []
    travel_end_lines: list[int] = []
    invalid_velocity_lines: list[int] = []

    for line_number, line in enumerate(document.lines, 1):
        if line_number % 4096 == 0:
            _check_deadline(deadline)
        if def_name is None and (def_match := _DEF_PATTERN.search(line)):
            def_name = def_match.group(1)

        if _TRAVEL_START.search(line):
            phase = "travel"
            travel_start_lines.append(line_number)
        elif _TRAVEL_END.search(line):
            phase = "extrusion"
            travel_end_lines.append(line_number)

        if velocity_match := _VELOCITY_PATTERN.search(line):
            value = float(velocity_match.group(1))
            velocities.append(VelocityCommand(line_number, value, phase))
            if math.isfinite(value) and value > 0:
                current_speed = value
            else:
                invalid_velocity_lines.append(line_number)

        raw_motion = _MOTION_PATTERN.search(line)
        if raw_motion:
            if raw_motion.group(1).upper() == "LIN":
                raw_lin_count += 1
            else:
                raw_ptp_count += 1

        motion, incomplete = _parse_motion(line, line_number, current_speed, phase)
        if incomplete:
            # Joint-space PTP commands legitimately omit Cartesian XYZ fields.
            if raw_motion and raw_motion.group(1).upper() == "LIN":
                incomplete_motion_count += 1
        elif motion is not None:
            motions.append(motion)

    lin_motions = [motion for motion in motions if motion.command == "LIN"]
    extrusion_motions = [motion for motion in lin_motions if motion.phase == "extrusion"]
    travel_motions = [motion for motion in lin_motions if motion.phase == "travel"]

    path_distance_mm = 0.0
    estimated_runtime_seconds = 0.0
    for index, (previous, current) in enumerate(zip(lin_motions, lin_motions[1:]), 1):
        if index % 4096 == 0:
            _check_deadline(deadline)
        distance = math.dist(
            (previous.x, previous.y, previous.z),
            (current.x, current.y, current.z),
        )
        path_distance_mm += distance
        speed = current.velocity_mps or default_speed_mps
        if speed > 0:
            estimated_runtime_seconds += (distance / 1000.0) / speed

    bounds = None
    if motions:
        bounds = {
            "x": {"min": min(item.x for item in motions), "max": max(item.x for item in motions)},
            "y": {"min": min(item.y for item in motions), "max": max(item.y for item in motions)},
            "z": {"min": min(item.z for item in motions), "max": max(item.z for item in motions)},
        }

    z_layer_count = len({round(item.z, 1) for item in extrusion_motions})
    extrusion_layer_count = _count_extrusion_blocks(document.lines, deadline)
    wipe_count = _count_wipes(document.lines, extrusion_motions, deadline)
    distribution: dict[str, Counter[float]] = {
        "initial": Counter(),
        "extrusion": Counter(),
        "travel": Counter(),
    }
    for command in velocities:
        distribution.setdefault(command.phase, Counter())[command.value_mps] += 1

    initial_layer_speed = next(
        (item.value_mps for item in velocities if item.phase == "extrusion"), None
    )
    final_layer_speed = next(
        (item.value_mps for item in reversed(velocities) if item.phase == "extrusion"), None
    )

    warnings: list[str] = []
    if document.newline_label == "mixed":
        warnings.append("The source uses mixed newline styles.")
    if def_name is None:
        warnings.append("No supported DEF declaration was found.")
    if not raw_ptp_count:
        warnings.append("No PTP motion was found.")
    if not raw_lin_count:
        warnings.append("No LIN motion was found.")
    if incomplete_motion_count:
        warnings.append(
            f"{incomplete_motion_count} motion command(s) did not contain complete XYZ coordinates."
        )
    if invalid_velocity_lines:
        warnings.append("One or more $VEL.CP commands contain a non-positive speed.")
    if bool(travel_start_lines) != bool(travel_end_lines):
        warnings.append("Travel markers are incomplete.")
    elif abs(len(travel_start_lines) - len(travel_end_lines)) > 1:
        warnings.append("Travel marker counts do not follow the expected layer convention.")

    return InspectionReport(
        filename=filename,
        sha256=document.sha256,
        byte_count=len(data),
        line_count=len(document.lines),
        encoding=document.encoding,
        newline=document.newline_label,
        terminal_newline=document.terminal_newline,
        def_name=def_name,
        ptp_count=raw_ptp_count,
        lin_count=raw_lin_count,
        incomplete_motion_count=incomplete_motion_count,
        velocity_command_count=len(velocities),
        velocity_distribution={
            phase_name: {f"{speed:.6f}": count for speed, count in sorted(counts.items())}
            for phase_name, counts in distribution.items()
            if counts
        },
        travel_start_count=len(travel_start_lines),
        travel_end_count=len(travel_end_lines),
        extrusion_layer_count=extrusion_layer_count,
        return_travel_count=len(travel_motions),
        z_layer_count=z_layer_count,
        wipe_count=wipe_count,
        bounds=bounds,
        path_distance_mm=path_distance_mm,
        estimated_runtime_seconds=estimated_runtime_seconds,
        initial_layer_speed_mps=initial_layer_speed,
        final_layer_speed_mps=final_layer_speed,
        warnings=tuple(warnings),
    )


def _count_extrusion_blocks(lines: tuple[str, ...], deadline: float) -> int:
    """Count travel-end to travel-start regions containing a complete LIN."""

    in_extrusion = False
    block_has_motion = False
    count = 0
    for index, line in enumerate(lines, 1):
        if index % 4096 == 0:
            _check_deadline(deadline)
        if _TRAVEL_END.search(line):
            if in_extrusion and block_has_motion:
                count += 1
            in_extrusion = True
            block_has_motion = False
            continue
        if _TRAVEL_START.search(line):
            if in_extrusion and block_has_motion:
                count += 1
            in_extrusion = False
            block_has_motion = False
            continue
        if in_extrusion and _MOTION_PATTERN.search(line):
            motion, incomplete = _parse_motion(line, 0, None, "extrusion")
            block_has_motion = block_has_motion or (motion is not None and not incomplete and motion.command == "LIN")
    if in_extrusion and block_has_motion:
        count += 1
    return count


def _count_wipes(
    lines: tuple[str, ...],
    extrusion_motions: list[MotionSegment],
    deadline: float,
) -> int:
    """Count first same-Z LIN moves immediately following travel-start markers."""

    extrusion_z = {round(item.z, 2) for item in extrusion_motions}
    count = 0
    for index, line in enumerate(lines):
        if index % 4096 == 0:
            _check_deadline(deadline)
        if not _TRAVEL_START.search(line):
            continue
        for offset, candidate in enumerate(lines[index + 1 : index + 5], 1):
            motion, incomplete = _parse_motion(candidate, index + offset + 1, None, "travel")
            if motion is not None and motion.command == "LIN":
                if round(motion.z, 2) in extrusion_z:
                    count += 1
                break
            if incomplete:
                break
    return count


def _check_deadline(deadline: float) -> None:
    if monotonic() > deadline:
        raise SourceValidationError(
            f"SRC parsing exceeded the {MAX_PARSE_SECONDS:g}-second processing limit."
        )
