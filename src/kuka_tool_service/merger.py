"""Strict alternating merge for compatible LFAM SRC path programs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re

from .models import SourceDocument
from .parser import SourceValidationError, decode_source, inspect_source


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_LIN = re.compile(r"^\s*LIN\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_PTP = re.compile(r"^\s*PTP\b\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_COORD = re.compile(rf"\b([XYZ])\s*({_NUMBER})", re.IGNORECASE)
_VELOCITY = re.compile(rf"\$VEL\.CP\s*=\s*{_NUMBER}", re.IGNORECASE)
_TRAVEL_START = re.compile(r";\s*travel\s+start\b", re.IGNORECASE)
_TRAVEL_END = re.compile(r";\s*travel\s+end\b", re.IGNORECASE)
_DEF = re.compile(r"^(\s*DEF\s+).+?(\s*\(\s*\).*)$", re.IGNORECASE)


@dataclass(frozen=True)
class PathBlock:
    """One return/entry travel plus one extrusion region."""

    lines: tuple[str, ...]
    z_height_mm: float


@dataclass(frozen=True)
class ParsedProgram:
    """Sections required to assemble one alternating merge."""

    document: SourceDocument
    prefix: tuple[str, ...]
    blocks: tuple[PathBlock, ...]
    tail: tuple[str, ...]


@dataclass(frozen=True)
class MergedArtifact:
    """Merged program and provenance for both inputs."""

    filename: str
    data: bytes
    primary_sha256: str
    secondary_sha256: str
    output_sha256: str
    primary_block_count: int
    secondary_block_count: int


def build_merged_source(
    primary_data: bytes,
    secondary_data: bytes,
    primary_filename: str,
    secondary_filename: str,
) -> MergedArtifact:
    """Interleave compatible path blocks while retaining primary scaffolding."""

    if primary_data == secondary_data:
        raise SourceValidationError("Primary and secondary SRC inputs must be different.")
    primary = _parse_program(primary_data, primary_filename)
    secondary = _parse_program(secondary_data, secondary_filename)
    if primary.document.encoding != secondary.document.encoding:
        raise SourceValidationError("Merge inputs must use the same text encoding.")
    if primary.document.newline_label != secondary.document.newline_label:
        raise SourceValidationError("Merge inputs must use the same newline style.")
    if primary.document.newline_label == "mixed":
        raise SourceValidationError("Merge inputs cannot use mixed newline styles.")
    if _scaffold(primary.prefix) != _scaffold(secondary.prefix):
        raise SourceValidationError("Merge input headers are not structurally compatible.")
    if _scaffold(primary.tail) != _scaffold(secondary.tail):
        raise SourceValidationError("Merge input tails are not structurally compatible.")
    if len(primary.blocks) != len(secondary.blocks):
        raise SourceValidationError("Merge inputs must contain the same number of path blocks.")
    for index, (primary_block, secondary_block) in enumerate(
        zip(primary.blocks, secondary.blocks), 1
    ):
        if not math.isclose(
            primary_block.z_height_mm,
            secondary_block.z_height_mm,
            abs_tol=0.05,
        ):
            raise SourceValidationError(
                f"Path block {index} differs in Z height by more than 0.05 mm."
            )

    output_lines = list(primary.prefix)
    for primary_block, secondary_block in zip(primary.blocks, secondary.blocks):
        output_lines.extend(primary_block.lines)
        output_lines.extend(secondary_block.lines)
    output_lines.extend(primary.tail)
    output_text = primary.document.newline.join(output_lines)
    if primary.document.terminal_newline:
        output_text += primary.document.newline
    output_data = output_text.encode(primary.document.encoding)
    output_report = inspect_source(output_data, filename="merged-output.src")
    expected_blocks = len(primary.blocks) + len(secondary.blocks)
    if output_report.incomplete_motion_count:
        raise SourceValidationError("Merged output contains an incomplete Cartesian LIN command.")
    if output_report.extrusion_layer_count != expected_blocks:
        raise SourceValidationError(
            "Merged output validation did not retain every interleaved path block."
        )
    stem = re.sub(
        r"[^A-Za-z0-9._-]+", "_", Path(primary_filename).stem
    ).strip("._") or "program"
    return MergedArtifact(
        filename=f"{stem}_merged.src",
        data=output_data,
        primary_sha256=primary.document.sha256,
        secondary_sha256=secondary.document.sha256,
        output_sha256=sha256(output_data).hexdigest(),
        primary_block_count=len(primary.blocks),
        secondary_block_count=len(secondary.blocks),
    )


def _parse_program(data: bytes, filename: str) -> ParsedProgram:
    document = decode_source(data)
    report = inspect_source(data, filename=filename)
    if report.incomplete_motion_count:
        raise SourceValidationError(
            f"{filename} contains incomplete Cartesian LIN commands."
        )
    lines = document.lines
    ptp_index = next((i for i, line in enumerate(lines) if _PTP.search(line)), None)
    if ptp_index is None:
        raise SourceValidationError(f"{filename} requires a Cartesian PTP path entry.")
    first_velocity = next(
        (i for i in range(ptp_index + 1, len(lines)) if _VELOCITY.search(lines[i])),
        None,
    )
    if first_velocity is None:
        raise SourceValidationError(f"{filename} has no path velocity after its PTP entry.")

    blocks: list[PathBlock] = []
    cursor = first_velocity
    tail_start = cursor
    while True:
        travel_end = _next_index(lines, cursor, _TRAVEL_END)
        if travel_end is None:
            tail_start = cursor
            break
        early_start = _next_index(lines, cursor, _TRAVEL_START)
        if early_start is not None and early_start < travel_end:
            raise SourceValidationError(
                f"{filename} has a travel-start marker before travel-end near line {early_start + 1}."
            )
        if not any(_VELOCITY.search(lines[i]) for i in range(cursor, travel_end)):
            raise SourceValidationError(
                f"{filename} path block near line {cursor + 1} has no entry velocity."
            )
        travel_start = _next_index(lines, travel_end + 1, _TRAVEL_START)
        if travel_start is None:
            raise SourceValidationError(
                f"{filename} path block near line {cursor + 1} has no travel-start terminator."
            )
        duplicate_end = _next_index(lines, travel_end + 1, _TRAVEL_END)
        if duplicate_end is not None and duplicate_end < travel_start:
            raise SourceValidationError(
                f"{filename} has duplicate travel-end markers near line {duplicate_end + 1}."
            )

        extrusion_points: list[tuple[float, float, float]] = []
        for line_number in range(travel_end + 1, travel_start):
            if _LIN.search(lines[line_number]):
                point = _xyz(lines[line_number])
                if point is None:
                    raise SourceValidationError(
                        f"{filename} has an incomplete extrusion LIN on line {line_number + 1}."
                    )
                extrusion_points.append(point)
        if not extrusion_points:
            raise SourceValidationError(
                f"{filename} path block near line {cursor + 1} has no extrusion LIN."
            )

        block_end = travel_start + 1
        next_end = _next_index(lines, block_end, _TRAVEL_END)
        search_limit = next_end if next_end is not None else len(lines)
        for line_number in range(block_end, search_limit):
            if _LIN.search(lines[line_number]):
                wipe = _xyz(lines[line_number])
                if wipe is None:
                    raise SourceValidationError(
                        f"{filename} has an incomplete post-travel LIN on line {line_number + 1}."
                    )
                if math.isclose(wipe[2], extrusion_points[-1][2], abs_tol=0.01):
                    block_end = line_number + 1
                break

        blocks.append(
            PathBlock(
                lines=tuple(lines[cursor:block_end]),
                z_height_mm=extrusion_points[0][2],
            )
        )
        cursor = block_end

    if not blocks:
        raise SourceValidationError(f"{filename} contains no complete path blocks.")
    tail = tuple(lines[tail_start:])
    if not any(line.strip().upper() == "END" for line in tail):
        raise SourceValidationError(f"{filename} tail does not contain END.")
    return ParsedProgram(
        document=document,
        prefix=tuple(lines[:first_velocity]),
        blocks=tuple(blocks),
        tail=tail,
    )


def _next_index(
    lines: tuple[str, ...], start: int, pattern: re.Pattern[str]
) -> int | None:
    return next((i for i in range(start, len(lines)) if pattern.search(lines[i])), None)


def _xyz(line: str) -> tuple[float, float, float] | None:
    motion = _LIN.search(line) or _PTP.search(line)
    if motion is None:
        return None
    matches = _COORD.findall(motion.group("body"))
    axes = [axis.upper() for axis, _ in matches]
    if set(axes) != {"X", "Y", "Z"} or len(axes) != 3:
        return None
    values = {axis.upper(): float(value) for axis, value in matches}
    if not all(math.isfinite(value) for value in values.values()):
        return None
    return values["X"], values["Y"], values["Z"]


def _scaffold(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize allowed program identity and path-coordinate differences."""

    normalized: list[str] = []
    for line in lines:
        if _DEF.match(line):
            normalized.append("<DEF>")
        elif _LIN.search(line):
            normalized.append("<LIN>")
        elif _PTP.search(line):
            normalized.append("<PTP>")
        elif _VELOCITY.search(line):
            normalized.append(_VELOCITY.sub("$VEL.CP=<VALUE>", line))
        else:
            normalized.append(line)
    return tuple(normalized)
